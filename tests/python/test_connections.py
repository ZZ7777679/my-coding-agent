"""集中验证连接控制、探测与保存边界，不访问外网。

Test pool controls and probes offline.
"""

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from my_agent.config import load_config, resolve_data_dir
from my_agent.credentials import ResolvedCredential, resolve_credential
from my_agent.errors import AgentError
from my_agent.models.connection_probe import probe_connection
from my_agent.models.go import GoClient
from my_agent.models.http import ModelHttpPool
from my_agent.rpc.application import RpcApplication
from my_agent.rpc.dto import CredentialInfo


def credential():
    """只创建哨兵凭据，不读取环境密钥。

    Create a sentinel without reading environment secrets.
    """
    return ResolvedCredential(
        SecretStr("connection-test-sentinel"),
        CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
    )


def test_model_tests_select_targets_and_keep_independent_results(tmp_path):
    """每次仅请求指定模型；并发进度、认证失败与公开结果互不串行覆盖。

    Target one model per call and keep concurrent progress, failures and public results separate.
    """

    async def scenario():
        """真实 RPC / Go 解析配合受控 SSE，不使用个人项目或真实密钥。

        Use real RPC and Go parsing with controlled SSE and no personal data or real keys.
        """
        entered = asyncio.Event()
        finish = asyncio.Event()
        requests = []
        streams = []

        class Stream(httpx.AsyncByteStream):
            """在首字后暂停，允许读取中间状态并测试其他模型。

            Pause after text for live checks.
            """

            closed = False

            async def __aiter__(self):
                """先给正文，再等待完整结束。

                Emit text, then wait before finishing.
                """
                yield (
                    b'data: {"choices":[{"index":0,"delta":{"content":"OK"},'
                    b'"finish_reason":null}]}\n\n'
                )
                entered.set()
                await finish.wait()
                yield (
                    b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}'
                    b"\n\ndata: [DONE]\n\n"
                )

            async def aclose(self):
                """记录取消和完成时的资源释放。

                Track cleanup on cancellation and completion.
                """
                self.closed = True

        def respond(request):
            """核对实际目标、无工具短消息及受信请求头。

            Verify target, short prompt and headers.
            """
            body = json.loads(request.content)
            requests.append(body["model"])
            assert request.method == "POST" and request.url.path == "/zen/go/v1/chat/completions"
            assert request.headers["authorization"] == "Bearer connection-test-sentinel"
            assert request.headers["user-agent"].startswith("my-coding-agent/")
            assert request.headers["x-opencode-session"]
            assert body["messages"] == [{"role": "user", "content": "Reply with OK only."}]
            assert body["tools"] == [] and body["stream"]
            if body["model"] == "deepseek-v4.1-flash":
                return httpx.Response(401, json={"error": "private-server-error"})
            stream = Stream()
            streams.append(stream)
            return httpx.Response(200, stream=stream)

        location = resolve_data_dir(str(tmp_path / "data"))
        app = RpcApplication(location, credential(), None)
        app.http.transport = httpx.MockTransport(respond)
        task = None
        try:
            await app.dispatch(
                "initialize", {"app_version": "0", "protocol_version": 4, "data_schema_version": 1}
            )
            initial = await app.dispatch("connections.get", {})
            assert len(initial.models) == 2 and not requests
            assert all(row.last_test is None and not row.testing for row in initial.models)
            before = (location.root / "config.toml").read_bytes()
            glm = {"model_id": "glm-5.3-flash", "timeout_seconds": 2.0}
            task = asyncio.create_task(app.dispatch("connections.test_model", glm))
            async with asyncio.timeout(3):
                await entered.wait()
                running = await app.dispatch("connections.get", {})
                assert running.models[0].testing
                assert running.models[0].progress.first_text_ms is not None
                assert running.models[1].last_test is None
                with pytest.raises(AgentError) as duplicate:
                    await app.dispatch("connections.test_model", glm)
                assert duplicate.value.code == "MODEL_PROBE_BUSY"
                other = await app.dispatch(
                    "connections.test_model",
                    {"model_id": "deepseek-v4.1-flash", "timeout_seconds": 2.0},
                )
                assert other.models[0].testing and other.models[0].last_test is None
                assert other.models[0].progress.elapsed_ms > running.models[0].progress.elapsed_ms
                assert (
                    other.models[0].progress.last_data_ms == running.models[0].progress.last_data_ms
                )
                assert (
                    other.models[0].progress.received_bytes
                    == running.models[0].progress.received_bytes
                )
                failure = other.models[1].last_test
                assert failure.code == "AUTHENTICATION_FAILED"
                assert failure.progress.first_text_ms is None
                finish.set()
                result = await task
            assert result.models[0].last_test.code == "OK"
            assert result.models[0].last_test.progress.first_text_ms is not None
            assert result.models[1].last_test == failure
            assert requests == ["glm-5.3-flash", "deepseek-v4.1-flash"]
            assert result.last_request.model_id == "glm-5.3-flash"
            assert not result.active_requests and all(stream.closed for stream in streams)
            assert "connection-test-sentinel" not in result.model_dump_json()
            assert "private-server-error" not in result.model_dump_json()
            assert (location.root / "config.toml").read_bytes() == before
            assert not (location.root / "sessions").exists()
        finally:
            finish.set()
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
            await app.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("case", ["timeout", "cancel", "missing"])
def test_model_probe_failure_cleans_up_without_retries(tmp_path, case):
    """小数超时、取消和缺凭据保持模型结果明确且不重试。

    Bound failures without retries.
    """

    async def scenario():
        """在等待响应头时中断；缺凭据时禁止请求。

        Interrupt headers or reject missing keys.
        """
        entered = asyncio.Event()
        requests = []

        async def respond(request):
            """保持请求挂起直到取消，不发出真实网络请求。

            Stall a mock request until cancelled.
            """
            requests.append(request)
            entered.set()
            await asyncio.Event().wait()

        key = resolve_credential({}, lambda _: None, "win32") if case == "missing" else credential()
        app = RpcApplication(resolve_data_dir(str(tmp_path / "data")), key, None)
        app.http.transport = httpx.MockTransport(respond)
        try:
            await app.dispatch(
                "initialize", {"app_version": "0", "protocol_version": 4, "data_schema_version": 1}
            )
            task = asyncio.create_task(
                app.dispatch(
                    "connections.test_model",
                    {
                        "model_id": "glm-5.3-flash",
                        "timeout_seconds": 2.0 if case == "cancel" else 0.03,
                    },
                )
            )
            async with asyncio.timeout(3):
                if case == "cancel":
                    await entered.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    await task
            status = await app.dispatch("connections.get", {})
            row = status.models[0]
            assert (
                row.last_test.code
                == {
                    "timeout": "MODEL_REQUEST_TIMEOUT",
                    "cancel": "CANCELLED",
                    "missing": "CREDENTIAL_MISSING",
                }[case]
            )
            assert not row.testing and not status.active_requests
            assert status.models[1].last_test is None
            assert len(requests) == (0 if case == "missing" else 1)
        finally:
            await app.close()

    asyncio.run(scenario())


def test_rpc_settings_probe_and_restart_preserve_other_configuration(tmp_path, monkeypatch):
    """查看不联网，探测无密钥；保存失败不切换，模型保存和重启保留偏好。

    Status is offline, probes omit keys, and failed saves/model edits/restarts preserve policy.
    """

    async def scenario():
        """使用实际 RPC 服务与隔离存储，仅替换 HTTP 传输。

        Use real RPC with mock HTTP.
        """
        requests = []

        def respond(request):
            """只允许一次目录 GET 的公开头，无生成内容。

            Accept catalog GETs without credentials.
            """
            requests.append(request)
            assert request.method == "GET" and request.url.path == "/zen/go/v1/models"
            assert "authorization" not in request.headers and not request.content
            assert request.headers["user-agent"].startswith("my-coding-agent/")
            assert request.headers["x-opencode-session"]
            return httpx.Response(
                200, json={"data": [{"id": "glm-5.3-flash"}, {"id": "deepseek-v4.1-flash"}]}
            )

        location = resolve_data_dir(str(tmp_path / "data"))
        app = RpcApplication(location, credential(), None)
        app.http.transport = httpx.MockTransport(respond)
        initialization = {"app_version": "0", "protocol_version": 4, "data_schema_version": 1}
        try:
            await app.dispatch("initialize", initialization)
            before = await app.dispatch("connections.get", {})
            assert before.reuse_enabled and not before.client_created and not requests
            result = await app.dispatch("connections.test", {"timeout_seconds": 1})
            assert result.last_probe.code == "OK" and result.last_probe.models_confirmed
            assert result.last_probe.progress.response_complete
            assert result.last_probe.progress.first_text_ms is None
            assert result.last_request is None and result.client_created and len(requests) == 1
            released = await app.dispatch("connections.release", {})
            assert not released.client_created and len(requests) == 1

            settings = {"reuse_enabled": False, "probe_timeout_seconds": 0.5}
            updated = await app.dispatch("connections.configure", settings)
            assert updated.http.model_dump() == settings
            old = (location.root / "config.toml").read_bytes()

            def fail_save(value):
                """模拟写入失败，不修改文件。

                Fail before changing the configuration file.
                """
                raise AgentError("STORAGE_WRITE_FAILED", "sentinel write failure")

            with monkeypatch.context() as patch:
                patch.setattr(app.storage, "save_connections", fail_save)
                with pytest.raises(AgentError, match="sentinel"):
                    await app.dispatch("connections.configure", {**settings, "reuse_enabled": True})
            assert not app.http.status().reuse_enabled
            assert (location.root / "config.toml").read_bytes() == old
            await app.dispatch("config.update", {"model_id": "deepseek-v4.1-flash"})
            assert load_config(location).http.model_dump() == settings
            await app.dispatch("connections.test", {"timeout_seconds": 1})
            assert not app.http.status().client_created and len(requests) == 2
            report = await app.dispatch(
                "diagnostics.get", {"dev": False, "network": False, "write_probe": False}
            )
            assert not report.connections.reuse_enabled and len(requests) == 2
            assert "connection-test-sentinel" not in report.model_dump_json()
            network_report = await app.dispatch(
                "diagnostics.get",
                {
                    "dev": False,
                    "network": True,
                    "write_probe": False,
                    "network_timeout_seconds": 0.5,
                },
            )
            assert len(requests) == 3 and network_report.catalog_reachable == "ok"
            assert network_report.connections.last_probe.code == "OK"
            assert not network_report.connections.reuse_enabled
        finally:
            await app.close()
        restarted = RpcApplication(location, credential(), None)
        try:
            restored = await restarted.dispatch("initialize", initialization)
            assert restored.config.http.model_dump() == settings
            assert restored.config.model_id == "deepseek-v4.1-flash"
            assert not restarted.http.status().reuse_enabled
            assert not restarted.http.status().client_created
            assert restarted.http.status().last_probe is None
        finally:
            await restarted.close()

    asyncio.run(scenario())


def test_releasing_and_toggling_pool_does_not_interrupt_an_active_answer(tmp_path):
    """真实流式消费者在切换后继续完成，最后借用者释放旧客户端。

    A streaming consumer completes across policy changes; the last borrower closes its client.
    """

    async def scenario():
        """用受控 SSE 等待模拟未结束回答，避免真实模型请求。

        Hold an SSE answer locally.
        """
        finish = asyncio.Event()
        first_text = asyncio.Event()

        class Stream(httpx.AsyncByteStream):
            """在首字之后等待，结束时记录资源清理。

            Pause after text and track cleanup.
            """

            closed = False

            async def __aiter__(self):
                """分开发出首字和合法结束标记。

                Emit text separately from completion.
                """
                yield (
                    b'data: {"choices":[{"index":0,"delta":{"content":"ok"},'
                    b'"finish_reason":null}]}\n\n'
                )
                await finish.wait()
                yield (
                    b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}'
                    b"\n\ndata: [DONE]\n\n"
                )

            async def aclose(self):
                """确认退出响应时关闭流。

                Mark response cleanup.
                """
                self.closed = True

        stream = Stream()
        pool = ModelHttpPool(
            reuse_enabled=True,
            keepalive_expiry=None,
            drain_timeout_seconds=0.1,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)),
        )
        model = GoClient(credential(), "https://opencode.ai/zen/go/v1", pool)
        text = []

        async def receive(delta):
            """正文到达后开放切换操作。

            Allow controls after text actually arrives.
            """
            text.append(delta)
            first_text.set()

        task = asyncio.create_task(
            model.complete(
                model_id="glm-5.3-flash",
                session_id="test-session",
                messages=[],
                tools=[],
                limits=load_config(resolve_data_dir(str(tmp_path / "data"))).run,
                on_text=receive,
            )
        )
        try:
            async with asyncio.timeout(3):
                await first_text.wait()
                old_client = pool.client()
                await pool.set_reuse(False)
                assert pool.status().active_requests == 1 and pool.status().pending_release
                assert not old_client.is_closed and not stream.closed
                async with pool.borrow() as temporary:
                    assert temporary is not old_client
                    assert pool.status().active_requests == 2
                assert temporary.is_closed and not old_client.is_closed
                await pool.set_reuse(True)
                fresh_client = pool.client()
                assert fresh_client is not old_client
                await pool.release()
                assert fresh_client.is_closed and not old_client.is_closed
                finish.set()
                turn = await task
                assert turn.text == "ok" and text == ["ok"]
                assert old_client.is_closed and stream.closed
                assert pool.status().active_requests == 0 and not pool.status().pending_release
                assert pool.status().last_request.code == "OK"
                assert "connection-test-sentinel" not in pool.status().model_dump_json()
        finally:
            finish.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await pool.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("case", ["timeout", "auth", "invalid"])
def test_probe_errors_remain_distinct_and_bounded(case):
    """区分超时、目录要求认证和无效返回，不假称模型通过。

    Preserve distinct probe failures.
    """

    async def scenario():
        """只用本地替身制造响应或挂起。

        Produce errors or a stalled response locally.
        """

        async def respond(request):
            """构造指定故障，不访问外网。

            Construct the requested failure offline.
            """
            if case == "timeout":
                await asyncio.Event().wait()
            if case == "auth":
                return httpx.Response(401, json={"error": "private-response"})
            return httpx.Response(200, content=b"private-invalid-response")

        pool = ModelHttpPool(
            reuse_enabled=True,
            keepalive_expiry=None,
            drain_timeout_seconds=0.1,
            transport=httpx.MockTransport(respond),
        )
        try:
            status = await probe_connection(pool, 0.03)
            assert (
                status.last_probe.code
                == {
                    "timeout": "TIMEOUT",
                    "auth": "CATALOG_AUTH_REQUIRED",
                    "invalid": "INVALID_SERVICE_RESPONSE",
                }[case]
            )
            assert status.active_requests == 0
            assert "private" not in status.model_dump_json()
        finally:
            await pool.close()

    asyncio.run(scenario())
