"""模型流和请求边界的模拟验证。 Simulated model stream and request boundary checks."""

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from my_agent.config import DEFAULTS
from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError
from my_agent.models.go import GoClient
from my_agent.models.http import ModelHttpPool
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


@pytest.mark.parametrize("oversized", [False, True])
def test_text_delivered_before_next_network_chunk_with_frame_limits(oversized):
    """首段不等网络块攒满；容量按事件校验。 Deliver text immediately and bound each SSE event."""

    async def scenario():
        """用交付顺序复现延迟，不依赖睡眠或真实网络。

        Reproduce ordering without sleeps or network.
        """
        output = []

        class GatedStream(ChunkStream):
            """后一块只能在首段显示后读取。 Read the next chunk only after displaying the first."""

            async def __aiter__(self):
                """第二块含多个合法事件或一个超限事件。

                Follow with coalesced or oversized events.
                """
                yield sse({"content": "首段"})
                assert output == ["首段"], "Text must arrive before requesting the next chunk"
                yield self.payload

        payload = (
            sse({"content": "x" * 1024})
            if oversized
            else sse({"content": "续"}) * 20 + sse({}, "stop") + b"data: [DONE]\n\n"
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
        )
        if oversized:
            with pytest.raises(AgentError) as error:
                await call
            assert error.value.code == "MODEL_OUTPUT_LIMIT"
            assert output == ["首段"]
        else:
            turn = await call
            assert turn.text == "首段" + "续" * 20
            assert "".join(output) == turn.text
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
                            "index": 0,
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
                            "index": 0,
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
            assert str(request.url) == "https://opencode.ai/zen/go/v1/chat/completions"
            seen.append(json.loads(request.content))
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

        async def text(delta):
            """收集公开流文本。 Collect public streaming text."""
            output.append(delta)

        call = client.complete(
            model_id="glm-5.3-flash",
            session_id="session-fixed",
            messages=[{"role": "user", "content": "read source"}],
            tools=[],
            limits=RunLimits.model_validate(DEFAULTS["run"]),
            on_text=text,
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
        assert len(seen) == 1 and stream.closed
        await client.http.close()

    asyncio.run(scenario())


def test_auth_failure_no_retry_or_raw_body():
    """认证错误不重试、不回显原始网络内容。 Do not retry or expose raw authentication failures."""

    async def scenario():
        """验证实际客户端错误边界。 Verify the actual client error boundary."""
        calls = 0

        async def handler(request):
            """统计模拟请求。 Count simulated requests."""
            nonlocal calls
            calls += 1
            return httpx.Response(401, json={"error": {"message": "private-body-sentinel"}})

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
        await client.http.close()

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
