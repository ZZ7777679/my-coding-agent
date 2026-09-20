"""OpenCode Go 的有界 Chat Completions 流。 Bounded OpenCode Go chat streaming."""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Literal

import httpx
from pydantic import JsonValue, TypeAdapter, ValidationError

from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError, http_error_code
from my_agent.models.failures import request_failure
from my_agent.models.http import ModelHttpPool, public_request_headers
from my_agent.models.timing import RequestTiming
from my_agent.models.types import (
    JsonObject,
    ModelId,
    ModelTurn,
    ProgressSink,
    TextSink,
    TokenUsage,
    ToolCall,
)
from my_agent.runtime.settings import RunLimits

JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


def object_value(value: object) -> JsonObject:
    """只接受 JSON 对象，拒绝未经验证的流结构。 Accept validated JSON objects only."""
    try:
        return JSON_OBJECT.validate_python(value, strict=True)
    except ValidationError as exc:
        raise AgentError("MODEL_PROTOCOL", "模型返回了不支持的结构。") from exc


@dataclass
class CallBuffer:
    """按流位置拼接完整调用。 Assemble a full call by its streaming index."""

    identifier: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class TurnBuffer:
    """有界回合缓存，保留实际续接字段。 Bounded turn buffer retaining continuation fields."""

    text: str = ""
    native_extra: JsonObject = field(default_factory=dict)
    calls: dict[int, CallBuffer] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: TokenUsage = field(
        default_factory=lambda: TokenUsage(input_tokens=None, output_tokens=None)
    )

    async def accept(
        self, value: JsonObject, on_text: TextSink, limit: int, on_reasoning: TextSink | None = None
    ) -> Literal["text", "reasoning", "tool_arguments"] | None:
        """先校验累计边界，再发布文本；工具只缓冲。

        Validate limits before streaming display text.
        """
        if value.get("error") is not None:
            raise AgentError("MODEL_STREAM_ERROR", "模型服务在流中返回错误，请显式重试。")
        usage = value.get("usage")
        if isinstance(usage, dict):
            self.usage = TokenUsage.model_validate(
                {
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                }
            )
        choices = value.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise AgentError("MODEL_PROTOCOL", "模型选择结构不受支持。")
        if not choices:
            return None
        choice = object_value(choices[0])
        if choice.get("index") != 0:
            raise AgentError("MODEL_PROTOCOL", "模型回合标识不一致。")
        delta = object_value(choice.get("delta"))
        reasoning = delta.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning and on_reasoning is not None:
            await on_reasoning(reasoning)
        content = delta.get("content")
        if content is not None:
            if not isinstance(content, str):
                raise AgentError("MODEL_PROTOCOL", "模型文本结构不受支持。")
            self.text += content
            if content:
                await on_text(content)
        for key, item in delta.items():
            if key in {"content", "role", "tool_calls"} or item is None:
                continue
            # 原生对象保持续接语义；只有 reasoning_content 文本经独立展示通道交付。
            # Preserve native continuation; only reasoning_content text uses the display channel.
            previous = self.native_extra.get(key)
            if isinstance(item, str):
                self.native_extra[key] = (previous if isinstance(previous, str) else "") + item
            elif isinstance(item, list):
                self.native_extra[key] = (previous if isinstance(previous, list) else []) + item
            elif previous is None or previous == item:
                self.native_extra[key] = item
            else:
                raise AgentError("MODEL_PROTOCOL", "原生续接字段无法可靠合并。")
        incoming = delta.get("tool_calls", [])
        if incoming is None:
            incoming = []
        if not isinstance(incoming, list):
            raise AgentError("MODEL_PROTOCOL", "工具流结构不正确。")
        for raw in incoming:
            call = object_value(raw)
            index = call.get("index")
            if type(index) is not int or index < 0:
                raise AgentError("MODEL_PROTOCOL", "工具流标识不正确。")
            buffer = self.calls.setdefault(index, CallBuffer())
            identifier = call.get("id")
            if identifier is not None:
                if not isinstance(identifier, str):
                    raise AgentError("MODEL_PROTOCOL", "工具 ID 不正确。")
                buffer.identifier += identifier
            # 增量片段可省略或用 null 表示尚无该字段，最终调用仍须完整。
            # A delta may omit/null a field; the assembled call must still be complete.
            if call.get("type") is not None and call["type"] != "function":
                raise AgentError("MODEL_PROTOCOL", "不支持该工具调用类型。")
            function = object_value(call["function"] if call.get("function") is not None else {})
            for key in ("name", "arguments"):
                fragment = function.get(key)
                if fragment is not None:
                    if not isinstance(fragment, str):
                        raise AgentError("MODEL_PROTOCOL", "工具参数流不正确。")
                    setattr(buffer, key, getattr(buffer, key) + fragment)
        reason = choice.get("finish_reason")
        if reason is not None:
            if self.finish_reason is not None or reason not in {"stop", "tool_calls"}:
                raise AgentError(
                    "MODEL_INCOMPLETE", "模型未完整结束回答或工具参数，请调整预算或重试。"
                )
            self.finish_reason = str(reason)
        payload_size = len(self.text.encode("utf-8")) + len(
            json.dumps(self.native_extra, ensure_ascii=False).encode("utf-8")
        )
        payload_size += sum(
            len((call.identifier + call.name + call.arguments).encode("utf-8"))
            for call in self.calls.values()
        )
        if payload_size > limit:
            raise AgentError("MODEL_OUTPUT_LIMIT", "模型累计内容超过输出容量。")
        if incoming:
            return "tool_arguments"
        if content:
            return "text"
        if delta.get("reasoning_content"):
            return "reasoning"
        return None

    def finish(self) -> ModelTurn:
        """完整结束标记与参数校验通过后才返回回合。 Return only a fully validated finished turn."""
        if self.finish_reason is None:
            raise AgentError("MODEL_INCOMPLETE", "模型流提前结束，未执行残缺工具调用。")
        calls: list[ToolCall] = []
        native_calls: list[JsonValue] = []
        for _, value in sorted(self.calls.items()):
            try:
                arguments = JSON_OBJECT.validate_json(value.arguments, strict=True)
                call = ToolCall(tool_call_id=value.identifier, name=value.name, arguments=arguments)
            except ValidationError as exc:
                raise AgentError(
                    "MODEL_PROTOCOL", "模型工具参数不是完整合法的 JSON 对象。"
                ) from exc
            calls.append(call)
            native_calls.append(
                {
                    "id": call.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": value.arguments,
                    },
                }
            )
        if len({call.tool_call_id for call in calls}) != len(calls):
            raise AgentError("MODEL_PROTOCOL", "模型返回了重复工具 ID。")
        if bool(calls) != (self.finish_reason == "tool_calls"):
            raise AgentError("MODEL_INCOMPLETE", "模型结束原因与工具调用不一致。")
        native: JsonObject = {
            "role": "assistant",
            "content": self.text or None,
            **self.native_extra,
        }
        if calls:
            native["tool_calls"] = native_calls
        if not calls and not self.text.strip():
            raise AgentError("MODEL_EMPTY", "模型没有返回可显示的回答。")
        reasoning = self.native_extra.get("reasoning_content")
        return ModelTurn(
            text=self.text,
            reasoning=reasoning if isinstance(reasoning, str) else "",
            tool_calls=calls,
            native=native,
            usage=self.usage,
        )


class GoClient:
    """受信凭据与统一请求头；无隐式重试。

    Trusted credentials and headers, with no hidden retries.
    """

    def __init__(
        self,
        credential: ResolvedCredential,
        base_url: str,
        http: ModelHttpPool,
    ) -> None:
        """借用后端连接池，逐请求构造敏感头。 Borrow a pool; build sensitive headers per call."""
        self.credential = credential
        self.base_url = base_url
        self.http = http

    def check_available(self) -> None:
        """凭据失败不计为真实请求。 Credential failures do not count as actual requests."""
        if self.credential.secret is None:
            restricted = self.credential.info.source == "restricted"
            raise AgentError(
                "CREDENTIAL_RESTRICTED" if restricted else "CREDENTIAL_MISSING",
                "无法读取 OPENCODE_API_KEY。" if restricted else "未找到 OPENCODE_API_KEY。",
                "在启动进程或 Windows 当前用户环境变量中配置后重试。",
            )

    def request_headers(self, session_id: str, *, messages_api: bool = False) -> dict[str, str]:
        """统一主模型与辅助请求的凭据 / 身份，敏感头不保存到客户端。

        Share credentials and identity across main and auxiliary calls, never client defaults.
        """
        self.check_available()
        assert self.credential.secret is not None  # 已检查 / checked above
        secret = self.credential.secret.get_secret_value()
        headers = {**public_request_headers(session_id), "Authorization": "Bearer " + secret}
        if messages_api:
            headers.update({"x-api-key": secret, "anthropic-version": "2023-06-01"})
        return headers

    async def complete(
        self,
        *,
        model_id: ModelId,
        session_id: str,
        messages: list[JsonObject],
        tools: list[JsonObject],
        limits: RunLimits,
        on_text: TextSink,
        on_progress: ProgressSink | None = None,
        on_reasoning: TextSink | None = None,
    ) -> ModelTurn:
        """每次调用恰好一个请求，取消退出会关闭 HTTP 流。

        Make one request and close on cancellation.
        """
        timing = RequestTiming(on_progress)
        headers = self.request_headers(session_id)
        body = {
            "model": model_id,
            "messages": messages,
            "tools": tools,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": limits.max_output_tokens,
        }

        async def deliver_text(delta: str) -> None:
            """先记真实首字再交付，不等响应结束。 Time text before immediate delivery."""
            await timing.text()
            await on_text(delta)

        async def deliver_reasoning(delta: str) -> None:
            """思考立即交付，但不计为正文首字。

            Deliver reasoning without counting it as answer TTFT.
            """
            await timing.set_phase("reasoning")
            if on_reasoning is not None:
                await on_reasoning(delta)

        code = "UNEXPECTED_ERROR"
        http_status = None
        try:
            await timing.publish()
            async with (
                asyncio.timeout(limits.request_timeout_seconds),
                self.http.borrow() as client,
            ):
                async with client.stream(
                    "POST",
                    self.base_url + "/chat/completions",
                    headers=headers,
                    json=body,
                    timeout=limits.request_timeout_seconds,
                    extensions={"trace": timing.trace},
                ) as response:
                    http_status = response.status_code
                    await timing.headers()
                    if response.status_code != 200:
                        kind = await self._error_kind(response)
                        code = http_error_code(response.status_code, kind)
                        raise AgentError(
                            code,
                            f"模型请求失败（HTTP {response.status_code}）。",
                            "检查认证、Go 额度或网络后显式重试。",
                        )
                    turn = await self._stream(
                        response, limits, deliver_text, timing, deliver_reasoning
                    )
                    await timing.set_phase("completed")
                    code = "OK"
                    return turn
        except (TimeoutError, httpx.HTTPError) as exc:
            failure = request_failure(exc, timing, limits.request_timeout_seconds)
            code = failure.code
            raise failure from exc
        except (ValidationError, ValueError, UnicodeError) as exc:
            code = "MODEL_PROTOCOL"
            raise AgentError(code, "模型返回了无法可靠解析的流。") from exc
        except AgentError as exc:
            code = exc.code
            raise
        except asyncio.CancelledError:
            code = "CANCELLED"
            raise
        finally:
            # 失败和取消也保留最后真实阶段；不记录可能包含秘密的异常消息。
            # Preserve the last actual phase on failure/cancel without raw exception messages.
            try:
                await timing.publish()
            finally:
                self.http.record(timing.progress, code, http_status=http_status, model_id=model_id)

    @staticmethod
    async def _error_kind(response: httpx.Response) -> str | None:
        """只提取有界错误类别，原始响应不公开。 Extract a bounded error category, never its body."""
        raw = bytearray()
        async for chunk in response.aiter_bytes(4096):
            if len(raw) + len(chunk) > 16384:
                return None
            raw.extend(chunk)
        try:
            value = json.loads(raw)
            error = value.get("error") if isinstance(value, dict) else None
            kind = error.get("type", error.get("code")) if isinstance(error, dict) else None
            return kind if isinstance(kind, str) else None
        except ValueError:
            return None

    async def _stream(
        self,
        response: httpx.Response,
        limits: RunLimits,
        on_text: TextSink,
        timing: RequestTiming,
        on_reasoning: TextSink | None = None,
    ) -> ModelTurn:
        """按字节有界组 SSE 帧，要求 DONE 与完整回合。

        Frame bounded SSE bytes and require completion.
        """
        buffer = bytearray()
        data_lines: list[str] = []
        turn = TurnBuffer()
        done = False
        # 指定 chunk_size 会等到攒满才交付；按网络到达解析，容量约束施加在行 / 事件上。
        # A fixed chunk_size delays delivery; parse arrivals and bound lines/events instead.
        chunks = response.aiter_bytes()
        async for chunk in chunks:
            await timing.received(len(chunk))
            offset = 0
            while offset < len(chunk):
                newline = chunk.find(b"\n", offset)
                end = len(chunk) if newline < 0 else newline + 1
                if len(buffer) + end - offset > limits.max_response_bytes:
                    raise AgentError("MODEL_OUTPUT_LIMIT", "模型单帧超过容量限制。")
                buffer.extend(chunk[offset:end])
                offset = end
                if newline < 0:
                    break
                line = buffer.rstrip(b"\r\n").decode("utf-8")
                buffer.clear()
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip(" "))
                    if (
                        sum(len(part.encode("utf-8")) for part in data_lines)
                        > limits.max_response_bytes
                    ):
                        raise AgentError("MODEL_OUTPUT_LIMIT", "模型单事件超过容量限制。")
                elif not line and data_lines:
                    data = "\n".join(data_lines)
                    data_lines.clear()
                    if data == "[DONE]":
                        done = True
                        break
                    value = JSON_OBJECT.validate_json(data, strict=True)
                    await timing.event(None)
                    phase = await turn.accept(
                        value,
                        on_text,
                        limits.max_response_bytes,
                        on_reasoning,
                    )
                    await timing.event(phase)
            if done:
                break
        if not done:
            raise AgentError("MODEL_INCOMPLETE", "模型流未正常结束，未执行残缺工具调用。")
        result = turn.finish()
        # DONE 是 SSE 结束，不是 HTTP EOF；有界读完尾部才能复用连接。
        # SSE DONE is not HTTP EOF: drain a bounded tail to permit connection reuse.
        timing.progress = timing.progress.model_copy(update={"response_complete": False})
        try:
            async with asyncio.timeout(self.http.drain_timeout_seconds):
                tail_size = 0
                async for chunk in chunks:
                    tail_size += len(chunk)
                    if tail_size > limits.max_response_bytes:
                        break
                else:
                    timing.progress = timing.progress.model_copy(update={"response_complete": True})
        except (TimeoutError, httpx.HTTPError):
            # 已完成且验证的回合不因可选连接回收失败变成业务失败。
            # A validated complete turn survives failed optional reuse; context exit closes it.
            pass
        return result
