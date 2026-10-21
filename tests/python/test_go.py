"""模型流和请求边界的模拟验证。 Simulated model stream and request boundary checks."""

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from my_agent.config import DEFAULTS
from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError
from my_agent.evolution.types import EvolutionBudget
from my_agent.models.failures import ModelResponseError
from my_agent.models.go import GoClient
from my_agent.models.http import ModelHttpPool
from my_agent.models.types import TokenUsage
from my_agent.rpc.dto import CredentialInfo
from my_agent.runtime.settings import RunLimits


class ChunkStream(httpx.AsyncByteStream):
    """按字节切开中文与 JSON；记录流清理。 Split Unicode and JSON bytes and record cleanup."""

    def __init__(self, payload):
        """保存已知模拟字节。 Keep known simulated bytes."""
        self.payload = payload
        self.closed = False

    async def __aiter__(self):
        """每次只返回三个字节。 Yield three bytes per chunk."""
        for offset in range(0, len(self.payload), 3):
            yield self.payload[offset : offset + 3]

    async def aclose(self):
        """确认资源已关闭。 Confirm resource closure."""
        self.closed = True


def sse(delta, finish=None, usage=None):
    """生成一个 SSE 事件。 Build one SSE event."""
    packet = {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage:
        packet["usage"] = usage
    return ("data: " + json.dumps(packet, ensure_ascii=False) + "\n\n").encode("utf-8")


@pytest.mark.parametrize("cancel", [False, True])
def test_unlimited_model_budget_omits_output_cap_and_preserves_cancel(cancel):
    """不限不发送 token 上限、不启用 HTTP 超时，长帧可完成且可取消。

    Unlimited requests omit token/time caps, accept large frames and remain cancellable.
    """

    async def scenario():
        delivered = asyncio.Event()
        content = "x" * 300000

        class LargeStream(ChunkStream):
            """大于原容量的完整帧，以及可手动取消的等待。

            A frame beyond former limits followed by an optionally cancellable wait.
            """

            async def __aiter__(self):
                """由客户端实际流解析，不走预算替身。 Exercise actual client stream parsing."""
                yield sse({"content": content})
                if cancel:
                    await asyncio.Event().wait()
                yield sse({}, "stop") + b"data: [DONE]\n\n"

        stream = LargeStream(b"")

        def handler(request):
            """断言实际请求体与 HTTPX 四项超时。

            Inspect request JSON and all four HTTPX timeouts.
            """
            assert "max_tokens" not in json.loads(request.content)
            assert all(value is None for value in request.extensions["timeout"].values())
            return httpx.Response(200, stream=stream)

        async def text(delta):
            """确认真实大帧已到达。 Confirm delivery of the actual large frame."""
            assert delta == content
            delivered.set()

        pool = ModelHttpPool(
            reuse_enabled=True,
            keepalive_expiry=None,
            drain_timeout_seconds=0.1,
            transport=httpx.MockTransport(handler),
        )
        client = GoClient(
            ResolvedCredential(
                SecretStr("sentinel"),
                CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
            ),
            "https://opencode.ai/inference/go/openai/v1",
            pool,
        )
        budget = EvolutionBudget.model_validate({key: None for key in EvolutionBudget.model_fields})
        try:
            task = asyncio.create_task(
                client.complete(
                    model_id="glm-5.3-flash",
                    session_id="test",
                    messages=[],
                    tools=[],
                    limits=budget,
                    on_text=text,
                )
            )
            await asyncio.wait_for(delivered.wait(), 5)
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                assert (await task).text == content
            assert stream.closed
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_reasoning_stream_does_not_publish_duplicate_phase_per_delta():
    """思考仍逐片段交付，重复阶段通知不随片段数量增长。

    Deliver reasoning immediately without a duplicate phase notification for every delta.
    """

    async def scenario():
        """模拟连续流并检查交付发生在下一片段到达前。

        Check delivery before each subsequent synthetic network fragment.
        """
        thoughts, progress = [], []

        class ReasoningStream(ChunkStream):
            """连续思考后完成回答。 Complete an answer after consecutive reasoning deltas."""

            async def __aiter__(self):
                """检查实时输出，没有等待整段思考结束。

                Verify live delivery without waiting for all reasoning to finish.
                """
                for index in range(40):
                    assert len(thoughts) == index
                    yield sse({"reasoning_content": "r"})
                yield sse({"content": "done"}, "stop")
                yield b"data: [DONE]\n\n"

        stream = ReasoningStream(b"")
        pool = ModelHttpPool(
            reuse_enabled=True,
            keepalive_expiry=None,
            drain_timeout_seconds=0.1,
            transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream)),
        )
        client = GoClient(
            ResolvedCredential(
                SecretStr("sentinel"),
                CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
            ),
            "https://opencode.ai/zen/go/v1",
            pool,
        )

        async def thought(delta):
            """记录实时片段。 Collect live deltas."""
            thoughts.append(delta)

        async def observe(value):
            """记录公开状态。 Collect public states."""
            progress.append(value)

        async def text(_):
            """正文交付时首字计时已发布。 TTFT is published before delivering answer text."""
            assert progress[-1].phase == "text" and progress[-1].first_text_ms is not None

        try:
            turn = await client.complete(
                model_id="glm-5.3-flash",
                session_id="phase-throttle",
                messages=[],
                tools=[],
                limits=RunLimits.model_validate(DEFAULTS["run"]),
                on_text=text,
                on_progress=observe,
                on_reasoning=thought,
            )
            assert turn.reasoning == "r" * 40 and turn.text == "done"
            assert sum(p.phase == "reasoning" for p in progress) == 1
            assert progress[-1].received_bytes > 0 and stream.closed
        finally:
            await pool.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("broken", ["disconnect", "malformed"])
def test_reported_usage_survives_stream_failure(broken):
    """异常流保留先前真实计量，不交付可执行回合。

    Preserve reported usage on stream failure without returning an executable turn.
    """

    async def scenario():
        """生产解析链只用合成 HTTP。 Exercise the production parser with synthetic HTTP."""

        class BrokenStream(ChunkStream):
            """已报告计量后失败。 Fail after delivering usage."""

            async def __aiter__(self):
                """两种失败均无结束标记。 Neither failure has a terminal marker."""
                yield sse(
                    {},
                    usage={
                        "prompt_tokens": 12,
                        "completion_tokens": 4,
                        "prompt_tokens_details": {"cached_tokens": 9},
                    },
                )
                if broken == "disconnect":
                    raise httpx.ReadError("synthetic detail must not escape")
                yield b"data: {bad}\n\n"

        stream = BrokenStream(b"")
        requests = []

        async def handler(request):
            """记录唯一尝试。 Record the sole attempt."""
            requests.append(request)
            return httpx.Response(200, stream=stream)

        async def text(_):
            """不保存模型原文。 Do not retain model text."""

        client = GoClient(
            ResolvedCredential(
                SecretStr("sentinel-only"),
                CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
            ),
            "https://opencode.ai/zen/go/v1",
            ModelHttpPool(
                reuse_enabled=True,
                keepalive_expiry=None,
                drain_timeout_seconds=0.1,
                transport=httpx.MockTransport(handler),
            ),
        )
        try:
            with pytest.raises(ModelResponseError) as failure:
                await client.complete(
                    model_id="glm-5.3-flash",
                    session_id="stream-failure",
                    messages=[],
                    tools=[],
                    limits=RunLimits.model_validate(DEFAULTS["run"]),
                    on_text=text,
                )
            assert failure.value.code == (
                "MODEL_STREAM_ERROR" if broken == "disconnect" else "MODEL_PROTOCOL"
            )
            assert failure.value.usage == TokenUsage(
                input_tokens=12, output_tokens=4, cached_input_tokens=9
            )
            assert len(requests) == 1 and stream.closed
            assert "synthetic detail" not in failure.value.message
        finally:
            await client.http.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("reason", "code"),
    [
        ("length", "MODEL_OUTPUT_TRUNCATED"),
        ("content_filter", "MODEL_CONTENT_FILTERED"),
        ("stop", None),
    ],
)
def test_terminal_reason_preserves_trailing_usage_and_accepts_repeated_marker(reason, code):
    """区分截断与过滤，读取末尾用量，相同结束标记不误报失败。

    Distinguish truncation/filtering, retain trailing usage and accept repeated terminal markers.
    """

    async def scenario():
        """只用模拟 HTTP 验证完整生产解析链，不消耗模型额度。

        Exercise the production parser with mock HTTP and no model spending.
        """
        stream = ChunkStream(
            sse({"reasoning_content": "summary reasoning"})
            + sse({"content": "summary fragment"})
            + sse({}, reason)
            + sse({}, reason)
            + b'data: {"choices": [], "usage": {"prompt_tokens": 32000, '
            b'"completion_tokens": 2048, "prompt_tokens_details": {"cached_tokens": 12000}}}\n\n'
            + b"data: [DONE]\n\n"
        )
        requests = []

        async def handler(request):
            requests.append(request)
            return httpx.Response(200, stream=stream)

        client = GoClient(
            ResolvedCredential(
                SecretStr("sentinel-only"),
                CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
            ),
            "https://opencode.ai/zen/go/v1",
            ModelHttpPool(
                reuse_enabled=True,
                keepalive_expiry=None,
                drain_timeout_seconds=0.1,
                transport=httpx.MockTransport(handler),
            ),
        )

        async def on_text(_):
            """正文回调无需额外动作。 No extra action for text deltas."""

        try:
            response = client.complete(
                model_id="deepseek-v4.1-flash",
                session_id="summary-stream",
                messages=[],
                tools=[],
                limits=RunLimits.model_validate(DEFAULTS["run"]),
                on_text=on_text,
            )
            expected_usage = TokenUsage(
                input_tokens=32000, output_tokens=2048, cached_input_tokens=12000
            )
            if code:
                with pytest.raises(ModelResponseError) as error:
                    await response
                assert error.value.code == code
                assert error.value.finish_reason == reason
                assert error.value.usage == expected_usage
                assert "summary reasoning" not in error.value.message
            else:
                result = await response
                assert result.text == "summary fragment"
                assert result.usage == expected_usage
            assert len(requests) == 1 and stream.closed
        finally:
            await client.http.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("oversized", [False, True])
def test_text_delivered_before_next_network_chunk_with_frame_limits(oversized):
    """首段不等网络块攒满；容量按事件校验。 Deliver text immediately and bound each SSE event."""

    async def scenario():
        """用交付顺序复现延迟，不依赖睡眠或真实网络。

        Reproduce ordering without sleeps or network.
        """
        output = []
        reasoning = []

        class GatedStream(ChunkStream):
            """后一块只能在首段显示后读取。 Read the next chunk only after displaying the first."""

            async def __aiter__(self):
                """第二块含多个合法事件或一个超限事件。

                Follow with coalesced or oversized events.
                """
                yield sse({"reasoning_content": "先读"})
                assert reasoning == ["先读"] and output == []
                yield sse({"reasoning_content": "文件。"})
                assert reasoning == ["先读", "文件。"] and output == []
                yield sse({"content": "首段"})
                assert output == ["首段"], "Text must arrive before requesting the next chunk"
                yield self.payload

        payload = (
            sse({"content": "x" * 1024})
            if oversized
            else sse({"content": "x"}) * 420 + sse({}, "stop") + b"data: [DONE]\n\n"
        )
        assert len(payload) > 1024
        stream = GatedStream(payload)

        async def handler(request):
            """只返回本地模拟流。 Return a local simulated stream only."""
            return httpx.Response(200, stream=stream)

        async def text(delta):
            """观察生产客户端的公开文本回调。

            Observe the production client's public text callback.
            """
            output.append(delta)

        async def thought(delta):
            """思考必须逐片交付，不能等正文出现。 Deliver reasoning before answer text appears."""
            reasoning.append(delta)

        client = GoClient(
            ResolvedCredential(
                SecretStr("sentinel-only"),
                CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
            ),
            "https://opencode.ai/zen/go/v1",
            ModelHttpPool(
                reuse_enabled=True,
                keepalive_expiry=None,
                drain_timeout_seconds=0.1,
                transport=httpx.MockTransport(handler),
            ),
        )
        call = client.complete(
            model_id="glm-5.3-flash",
            session_id="session-fixed",
            messages=[],
            tools=[],
            limits=RunLimits.model_validate({**DEFAULTS["run"], "max_response_bytes": 1024}),
            on_text=text,
            on_reasoning=thought,
        )
        if oversized:
            with pytest.raises(AgentError) as error:
                await call
            assert error.value.code == "MODEL_OUTPUT_LIMIT"
            assert output == ["首段"]
        else:
            turn = await call
            assert turn.text == "首段" + "x" * 420
            assert "".join(output) == turn.text
            assert turn.reasoning == "先读文件。"
            assert turn.native["reasoning_content"] == turn.reasoning
        assert stream.closed
        await client.http.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("broken", [False, True])
def test_fragmented_tools_headers_native_state_and_partial_rejection(broken):
    """完整参数才返回工具；哨兵凭据不进入结果。

    Return only complete tools without leaking secrets.
    """

    async def scenario():
        """通过假 HTTP 核对请求头、续接字段和流结束。

        Verify headers, continuation and completion.
        """
        seen = []
        stream = ChunkStream(
            sse({"role": "assistant", "reasoning_content": "private reasoning"})
            + sse(
                {
                    "content": "读取",
                    "tool_calls": [
                        {
                            "index": 256,
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path":'},
                        }
                    ],
                }
            )
            + sse(
                {
                    "tool_calls": [
                        {
                            "index": 256,
                            "function": {"arguments": '"main.py"' if broken else '"main.py"}'},
                        }
                    ]
                },
                "tool_calls",
                {"prompt_tokens": 4, "completion_tokens": 8},
            )
            + sse({"tool_calls": None})
            + b"data: [DONE]\n\n"
        )

        async def handler(request):
            """只在测试内检验哨兵请求，不输出头。 Assert sentinel headers without printing them."""
            assert request.headers["Authorization"] == "Bearer sentinel-only"
            assert request.headers["User-Agent"].startswith("my-coding-agent/")
            assert request.headers["x-opencode-session"] == "session-fixed"
            assert str(request.url) == "https://opencode.ai/inference/go/openai/v1/chat/completions"
            seen.append(json.loads(request.content))
            assert seen[-1]["tools"][0]["function"]["name"] == "read_file"
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

        client = GoClient(
            ResolvedCredential(
                SecretStr("sentinel-only"),
                CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
            ),
            "https://opencode.ai/zen/go/v1",
            ModelHttpPool(
                reuse_enabled=True,
                keepalive_expiry=None,
                drain_timeout_seconds=0.1,
                transport=httpx.MockTransport(handler),
            ),
        )
        output = []
        progress = []

        async def text(delta):
            """收集公开流文本。 Collect public streaming text."""
            output.append(delta)

        async def observe(value):
            """验证思考之后的参数生成阶段。 Observe argument generation following reasoning."""
            progress.append(value)

        call = client.complete(
            model_id="glm-5.3-flash",
            session_id="session-fixed",
            messages=[{"role": "user", "content": "read source"}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                        },
                    },
                }
            ],
            limits=RunLimits.model_validate(DEFAULTS["run"]),
            on_text=text,
            on_progress=observe,
        )
        if broken:
            with pytest.raises(AgentError) as error:
                await call
            assert error.value.code == "MODEL_PROTOCOL"
        else:
            turn = await call
            assert turn.tool_calls[0].arguments == {"path": "main.py"}
            assert turn.native["reasoning_content"] == "private reasoning"
            assert turn.usage.input_tokens == 4
            assert output == ["读取"]
            assert "tool_arguments" in [item.phase for item in progress]
            assert progress[-1].phase == "completed"
            assert progress[-1].last_data_ms is not None
            assert progress[-1].received_bytes > 0
        assert len(seen) == 1 and stream.closed
        await client.http.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("expired", [False, True])
def test_auth_failure_no_retry_or_raw_body(expired):
    """认证错误不重试、不回显原始网络内容。 Do not retry or expose raw authentication failures."""

    async def scenario():
        """验证实际客户端错误边界。 Verify the actual client error boundary."""
        calls = 0

        async def handler(request):
            """统计模拟请求。 Count simulated requests."""
            nonlocal calls
            calls += 1
            message = ("This API key has expired. " if expired else "") + "private-body-sentinel"
            return httpx.Response(401, json={"error": {"message": message}})

        client = GoClient(
            ResolvedCredential(
                SecretStr("sentinel-only"),
                CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
            ),
            "https://opencode.ai/zen/go/v1",
            ModelHttpPool(
                reuse_enabled=True,
                keepalive_expiry=None,
                drain_timeout_seconds=0.1,
                transport=httpx.MockTransport(handler),
            ),
        )

        async def text(delta):
            """错误响应不应生成文本。 Error responses must not generate text."""
            pytest.fail("Unexpected text")

        with pytest.raises(AgentError) as error:
            await client.complete(
                model_id="deepseek-v4.1-flash",
                session_id="session-fixed",
                messages=[],
                tools=[],
                limits=RunLimits.model_validate(DEFAULTS["run"]),
                on_text=text,
            )
        assert error.value.code == "AUTHENTICATION_FAILED" and calls == 1
        assert "private-body-sentinel" not in str(error.value)
        assert ("已过期" in str(error.value)) is expired
        if expired:
            assert "OpenCode Console" in error.value.remediation
        await client.http.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("connect", "MODEL_CONNECT_ERROR"),
        ("read", "MODEL_READ_TIMEOUT"),
        ("deadline", "MODEL_REQUEST_TIMEOUT"),
        ("disconnected", "MODEL_STREAM_ERROR"),
    ],
)
def test_failure_cause_is_separate_from_last_reasoning_phase(failure, expected):
    """复现思考后停流与不同失败，阶段保留事实，原因不推测且不重试。

    Reproduce stalled reasoning and distinct failures without inferred causes or retries.
    """

    async def scenario():
        """使用生产解析器和总时限，仅替换传输，检查时间与资源清理。

        Use the production parser/deadline with substituted transport, checking timing and cleanup.
        """
        calls = 0
        progress = []

        class FailingStream(ChunkStream):
            """先返回真实结构的思考事件，再停流或产生指定网络异常。

            Emit a valid reasoning event before stalling or raising a specified transport error.
            """

            async def __aiter__(self):
                """不暴露思考内容，仅保存可公开时序。 Retain public timing, not reasoning text."""
                yield sse({"reasoning_content": "private-reasoning-sentinel"})
                if failure == "read":
                    raise httpx.ReadTimeout("private-error-sentinel")
                if failure == "disconnected":
                    raise httpx.RemoteProtocolError("private-error-sentinel")
                await asyncio.Event().wait()

        stream = FailingStream(b"")

        async def handler(request):
            """区分未连接与连接后异常。 Distinguish connection failure from later faults."""
            nonlocal calls
            calls += 1
            if failure == "connect":
                raise httpx.ConnectError("private-error-sentinel")
            return httpx.Response(200, stream=stream)

        async def observe(value):
            """收集公开阶段快照。 Collect public phase snapshots."""
            progress.append(value)

        async def no_text(delta):
            """失败前只有私有思考，不能伪装为正文。 Private reasoning is not visible answer text."""
            pytest.fail("Unexpected answer text")

        pool = ModelHttpPool(
            reuse_enabled=True,
            keepalive_expiry=None,
            drain_timeout_seconds=0.1,
            transport=httpx.MockTransport(handler),
        )
        client = GoClient(
            ResolvedCredential(
                SecretStr("sentinel-only"),
                CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
            ),
            "https://opencode.ai/zen/go/v1",
            pool,
        )
        try:
            with pytest.raises(AgentError) as error:
                await client.complete(
                    model_id="glm-5.3-flash",
                    session_id="failure-check",
                    messages=[],
                    tools=[],
                    limits=RunLimits.model_validate(
                        {**DEFAULTS["run"], "request_timeout_seconds": 1}
                    ),
                    on_text=no_text,
                    on_progress=observe,
                )
            assert error.value.code == expected and calls == 1
            assert (
                error.value.phase
                == {
                    "connect": "connecting",
                    "read": "response_stream",
                    "deadline": "request_deadline",
                    "disconnected": "response_stream",
                }[failure]
            )
            assert "sentinel" not in error.value.message
            final = progress[-1]
            if failure == "connect":
                assert final.last_data_ms is None and final.received_bytes == 0
            else:
                assert stream.closed and final.phase == "reasoning"
                assert final.last_data_ms is not None and final.received_bytes > 0
                assert final.first_text_ms is None
                if failure == "deadline":
                    assert final.elapsed_ms - final.last_data_ms >= 800
            assert pool.last_request.code == expected
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_complete_sse_does_not_wait_indefinitely_for_http_eof():
    """清理超时只放弃连接复用，不丢失完整回答。 A drain timeout forfeits reuse, not the answer."""

    async def scenario():
        """模拟 DONE 后保持连接的服务。 Simulate a stream kept open after DONE."""
        progress = []
        output = []

        class OpenEndedStream(ChunkStream):
            """已完成 SSE 后不发送 HTTP EOF。 Finish SSE while withholding HTTP EOF."""

            async def __aiter__(self):
                """正文先交付，再做可选清理。 Deliver text before optional draining."""
                yield self.payload
                assert output == ["answer"]
                await asyncio.Event().wait()

        stream = OpenEndedStream(sse({"content": "answer"}, "stop") + b"data: [DONE]\n\n")

        async def handler(request):
            """返回本地长连接替身。 Return the local open-ended stream."""
            return httpx.Response(200, stream=stream)

        pool = ModelHttpPool(
            reuse_enabled=True,
            keepalive_expiry=None,
            drain_timeout_seconds=0.02,
            transport=httpx.MockTransport(handler),
        )
        client = GoClient(
            ResolvedCredential(
                SecretStr("sentinel"),
                CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
            ),
            "https://opencode.ai/zen/go/v1",
            pool,
        )

        async def text(delta):
            """只收集公开正文。 Collect public answer text only."""
            output.append(delta)

        async def phase(value):
            """收集脱敏阶段。 Collect sanitized progress."""
            progress.append(value)

        try:
            async with asyncio.timeout(2):
                turn = await client.complete(
                    model_id="glm-5.3-flash",
                    session_id="test",
                    messages=[],
                    tools=[],
                    limits=RunLimits.model_validate(DEFAULTS["run"]),
                    on_text=text,
                    on_progress=phase,
                )
            assert turn.text == "answer" and stream.closed
            assert progress[-1].response_complete is False
            assert progress[-1].first_text_ms is not None
            assert progress[-1].first_event_ms <= progress[-1].first_text_ms
        finally:
            await pool.close()

    asyncio.run(scenario())
