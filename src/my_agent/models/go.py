"""OpenCode Go 的可配置预算流。 OpenCode Go streaming with configurable budgets."""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Literal

import httpx
from pydantic import JsonValue, TypeAdapter, ValidationError

from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError, http_error_code
from my_agent.models.endpoints import current_base_url, messages_url
from my_agent.models.failures import ModelResponseError, request_failure
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
from my_agent.runtime.settings import ModelLimits

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
    """按可选预算缓存回合并保留实际续接字段。

    Buffer turns with optional budgets and continuation fields.
    """

    text: str = ""
    native_extra: JsonObject = field(default_factory=dict)
    calls: dict[int, CallBuffer] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: TokenUsage = field(
        default_factory=lambda: TokenUsage(input_tokens=None, output_tokens=None)
    )

    async def accept(
        self,
        value: JsonObject,
        on_text: TextSink,
        limit: int | None,
        on_reasoning: TextSink | None = None,
    ) -> Literal["text", "reasoning", "tool_arguments"] | None:
        """先校验累计边界，再发布文本；工具只缓冲。

        Validate limits before streaming display text.
        """
        if value.get("error") is not None:
            raise AgentError("MODEL_STREAM_ERROR", "模型服务在流中返回错误，请显式重试。")
        usage = value.get("usage")
        if isinstance(usage, dict):
            details = usage.get("prompt_tokens_details")
            cached = (
                details.get("cached_tokens", usage.get("prompt_cache_hit_tokens"))
                if isinstance(details, dict)
                else usage.get("prompt_cache_hit_tokens")
            )
            self.usage = TokenUsage.model_validate(
                {
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "cached_input_tokens": cached,
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
            if not isinstance(reason, str):
                raise AgentError("MODEL_PROTOCOL", "模型结束原因不是文本。")
            if self.finish_reason is not None and self.finish_reason != reason:
                raise self.failure("MODEL_PROTOCOL", "同一响应返回了不同的结束原因。")
            # 先读完尾部 usage；重复的相同标记不代表回答不完整。
            # Consume trailing usage first; identical repeated stop markers are harmless.
            self.finish_reason = reason
        if limit is not None:
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

    def failure(self, code: str, message: str, *, phase: str | None = None) -> ModelResponseError:
        """仅携带原因和统计，正文 / 思考不进入异常。

        Carry reasons and statistics, never answer or reasoning text, in failures.
        """
        return ModelResponseError(
            code, message, self.usage, self.finish_reason, phase=phase or "response_validation"
        )

    def finish(self) -> ModelTurn:
        """完整结束标记与参数校验通过后才返回回合。 Return only a fully validated finished turn."""
        if self.finish_reason is None:
            raise self.failure("MODEL_INCOMPLETE", "模型流提前结束，未执行残缺工具调用。")
        if self.finish_reason == "length":
            reasoning = self.native_extra.get("reasoning_content")
            reasoning_chars = len(reasoning) if isinstance(reasoning, str) else 0
            raise self.failure(
                "MODEL_OUTPUT_TRUNCATED",
                "模型因输出额度结束（finish_reason=length）；"
                f"已收到正文 {len(self.text)} 字符、思考 {reasoning_chars} 字符。"
                "本次回答未完整完成，可提高输出预算后重试。",
            )
        if self.finish_reason == "content_filter":
            raise self.failure("MODEL_CONTENT_FILTERED", "模型服务以 content_filter 结束响应。")
        if self.finish_reason not in {"stop", "tool_calls"}:
            raise self.failure("MODEL_STOP_REASON", "模型返回了未支持的响应结束原因。")
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
            raise self.failure("MODEL_INCOMPLETE", "模型结束原因与工具调用不一致。")
        native: JsonObject = {
            "role": "assistant",
            "content": self.text or None,
            **self.native_extra,
        }
        if calls:
            native["tool_calls"] = native_calls
        if not calls and not self.text.strip():
            raise self.failure("MODEL_EMPTY", "模型没有返回可显示的回答。")
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
        *,
        request_model_id: str | None = None,
    ) -> None:
        """借用后端连接池，逐请求构造敏感头。 Borrow a pool; build sensitive headers per call."""
        self.credential = credential
        self.base_url = current_base_url(base_url)
        self.messages_url = messages_url(self.base_url)
        self.http = http
        # 显式适配同一模型在直连接口中的名称；应用身份和历史记录保持不变。
        # Map the explicitly selected upstream name while preserving application identity/history.
        self.request_model_id = request_model_id

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
        limits: ModelLimits,
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
            "model": self.request_model_id or model_id,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        # 不限输出时不发送人为上限；服务商仍决定实际支持的生成长度。
        # Omit the host output cap when unlimited; the provider determines supported length.
        if limits.max_output_tokens is not None:
            body["max_tokens"] = limits.max_output_tokens
        # Go 的 DeepSeek 路由会挂起空 tools 数组；无工具时省略可选字段。
        # Go's DeepSeek route stalls on an empty tools array; omit the optional field when unused.
        if tools:
            body["tools"] = tools

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

        # 计量早于结束标记到达时，断流也不能丢失它；残缺回合仍不能执行。
        # Preserve usage that precedes completion on stream failure; never execute a partial turn.
        buffered_turn = TurnBuffer()
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
                        failure = await self.http_failure(response, "模型请求")
                        code = failure.code
                        raise failure
                    turn = await self._stream(
                        response, limits, deliver_text, timing, deliver_reasoning, buffered_turn
                    )
                    await timing.set_phase("completed")
                    code = "OK"
                    return turn
        except (TimeoutError, httpx.HTTPError) as exc:
            failure = request_failure(exc, timing, limits.request_timeout_seconds)
            code = failure.code
            raise buffered_turn.failure(failure.code, failure.message, phase=failure.phase) from exc
        except (ValidationError, ValueError, UnicodeError) as exc:
            code = "MODEL_PROTOCOL"
            raise buffered_turn.failure(
                code, "模型返回了无法可靠解析的流。", phase="response_stream"
            ) from exc
        except AgentError as exc:
            code = exc.code
            if not isinstance(exc, ModelResponseError) and code.startswith("MODEL_"):
                raise buffered_turn.failure(code, exc.message, phase=exc.phase) from exc
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

    async def http_failure(self, response: httpx.Response, operation: str) -> AgentError:
        """保留服务拒绝类别与脱敏参数原因，不公开整份响应或认证正文。

        Preserve rejection categories and redacted parameter reasons, never raw bodies or auth text.
        """
        kind, detail, parameter = await self._error_details(response)
        code = http_error_code(response.status_code, kind)
        if kind == "api_key_expired" and response.status_code == 401:
            return AgentError(
                code,
                "当前 API key 已过期；续费或重新登录不会续期旧 key。",
                "请在 OpenCode Console 新建 API key，更新应用使用的凭据后重试。",
                cause_code=kind,
                phase="response_headers",
            )
        message = f"{operation}失败（HTTP {response.status_code}）。"
        if kind:
            message += f" 服务类别：{kind}。"
        if parameter:
            message += f" 参数：{parameter}。"
        if detail:
            message += f" 服务说明：{detail}"
        return AgentError(
            code,
            message,
            "检查服务指出的参数或请求格式后显式重试。"
            if response.status_code in {400, 422}
            else "检查认证、Go 额度或服务状态后显式重试。",
            cause_code=kind,
            phase="response_headers",
        )

    async def _error_details(
        self, response: httpx.Response
    ) -> tuple[str | None, str | None, str | None]:
        """只读错误对象的类别／参数／说明；长度限制仅约束诊断文本。

        Read only error category, parameter and message; size bounds apply solely to diagnostics.
        """
        raw = bytearray()
        async for chunk in response.aiter_bytes(4096):
            if len(raw) + len(chunk) > 16384:
                return None, None, None
            raw.extend(chunk)
        try:
            value = json.loads(raw)
            error = value.get("error") if isinstance(value, dict) else None
            if isinstance(error, dict) and response.status_code == 401:
                message = error.get("message")
                # 仅识别已观察到的过期说明，不把服务商响应原文带入 UI。
                # Recognize the observed expiry notice without forwarding provider text to the UI.
                if isinstance(message, str) and message.startswith("This API key has expired."):
                    return "api_key_expired", None, None
            kind = error.get("type", error.get("code")) if isinstance(error, dict) else None
            parameter = error.get("param") if isinstance(error, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            # 认证／HTML／任意整份输入不回显，仅对参数拒绝保留错误说明。
            # Omit auth bodies, HTML and input objects; detail is for request rejection only.
            return (
                self._error_identifier(kind),
                self._redact_error_text(message)
                if response.status_code in {400, 422} and isinstance(message, str)
                else None,
                self._error_identifier(parameter),
            )
        except ValueError:
            return None, None, None

    def _error_identifier(self, value: object) -> str | None:
        """错误类别和字段名只接收短标识，凭据不成为诊断身份。

        Accept short category/field identifiers without treating credentials as diagnostic names.
        """
        if not isinstance(value, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_.\[\]-]{0,119}", value
        ):
            return None
        return value if self._redact_error_text(value) == value else None

    def _redact_error_text(self, value: str) -> str:
        """清除当前模型凭据与常见认证值，再限制公开错误说明长度。

        Remove the current model credential and common auth values before bounding public detail.
        """
        secret = self.credential.secret
        if secret and secret.get_secret_value():
            value = value.replace(secret.get_secret_value(), "[redacted]")
        value = re.sub(r"(?i)\bBearer\s+[^\s\"',;]+", "Bearer [redacted]", value)
        value = re.sub(r"(?i)\b(?:sk-|gh[pousr]_|github_pat_)[A-Za-z0-9_-]+", "[redacted]", value)
        value = re.sub(
            r"""(?ix)\b(?:api[_-]?key|token|password|secret|authorization|cookie)\b
                [\"']?\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)""",
            "[redacted]",
            value,
        )
        value = re.sub(r"(\w+://)[^\s/@]+:[^\s/@]+@", r"\1[redacted]@", value)
        value = " ".join(value.split())
        return value[:512] + ("…" if len(value) > 512 else "")

    async def _stream(
        self,
        response: httpx.Response,
        limits: ModelLimits,
        on_text: TextSink,
        timing: RequestTiming,
        on_reasoning: TextSink | None = None,
        turn: TurnBuffer | None = None,
    ) -> ModelTurn:
        """按可选字节预算组 SSE 帧，要求 DONE 与完整回合。

        Frame SSE bytes under an optional budget and require completion.
        """
        buffer = bytearray()
        data_lines: list[str] = []
        if turn is None:
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
                if (
                    limits.max_response_bytes is not None
                    and len(buffer) + end - offset > limits.max_response_bytes
                ):
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
                        limits.max_response_bytes is not None
                        and sum(len(part.encode("utf-8")) for part in data_lines)
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
            raise turn.failure("MODEL_INCOMPLETE", "模型流未正常结束，未执行残缺工具调用。")
        # DONE 是 SSE 结束，不是 HTTP EOF；有界读完尾部才能复用连接。
        # SSE DONE is not HTTP EOF: drain a bounded tail to permit connection reuse.
        timing.progress = timing.progress.model_copy(update={"response_complete": False})
        try:
            async with asyncio.timeout(self.http.drain_timeout_seconds):
                tail_size = 0
                async for chunk in chunks:
                    tail_size += len(chunk)
                    if (
                        limits.max_response_bytes is not None
                        and tail_size > limits.max_response_bytes
                    ):
                        break
                else:
                    timing.progress = timing.progress.model_copy(update={"response_complete": True})
        except (TimeoutError, httpx.HTTPError):
            # 可选连接回收失败不改变已收到的结束原因；退出上下文会关闭流。
            # Optional connection reuse never changes the received stop reason; exit closes it.
            pass
        return turn.finish()
