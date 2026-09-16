"""用本地 HTTP 验证实际连接复用和取消，不调用模型。 Test pooling/cancellation over local HTTP."""

import asyncio
import json
from uuid import uuid4

import httpx
from pydantic import SecretStr

from my_agent import bootstrap
from my_agent.config import resolve_data_dir
from my_agent.credentials import ResolvedCredential
from my_agent.models.http import ModelHttpPool
from my_agent.projects import ProjectService
from my_agent.rpc.dto import CredentialInfo
from my_agent.sessions.types import RequestStarted, RunAccepted
from my_agent.storage import Storage
from my_agent.worker import BusinessWorker


def test_backend_pool_reuses_connections_across_runs_and_recovers_after_cancel(
    tmp_path, monkeypatch
):
    """跨运行复用真实套接字；取消后重新连接；关闭无遗留。

    Reuse actual sockets across runs, reconnect after cancellation, and close cleanly.
    """

    async def scenario():
        """使用生产装配、会话和解析器，仅替换目标为隔离服务器。

        Use production composition/sessions/parser with an isolated server endpoint.
        """
        connections = 0
        requests = []
        handlers = set()
        waiting = asyncio.Event()

        async def serve(reader, writer):
            """分开发送 SSE DONE 与 HTTP EOF。 Serve distinct SSE DONE and HTTP EOF."""
            nonlocal connections
            connections += 1
            task = asyncio.current_task()
            handlers.add(task)
            try:
                while True:
                    try:
                        raw = await reader.readuntil(b"\r\n\r\n")
                    except asyncio.IncompleteReadError:
                        return
                    headers = {}
                    for line in raw.decode("ascii").split("\r\n")[1:]:
                        if ":" in line:
                            key, value = line.split(":", 1)
                            headers[key.lower()] = value.strip()
                    body = json.loads(await reader.readexactly(int(headers["content-length"])))
                    requests.append(headers["x-opencode-session"])
                    assert headers["authorization"] == "Bearer sentinel-only"
                    wait = body["messages"][-1]["content"] == "wait"
                    delta = (
                        {"reasoning_content": "private-reasoning"} if wait else {"content": "ok"}
                    )
                    packet = {
                        "choices": [
                            {"index": 0, "delta": delta, "finish_reason": None if wait else "stop"}
                        ]
                    }
                    payload = ("data: " + json.dumps(packet) + "\n\n").encode()
                    if not wait:
                        payload += b"data: [DONE]\n\n"
                    writer.write(
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                        b"Transfer-Encoding: chunked\r\n\r\n"
                    )
                    writer.write(f"{len(payload):x}\r\n".encode() + payload + b"\r\n")
                    await writer.drain()
                    if wait:
                        waiting.set()
                        await reader.read()
                        return
                    await asyncio.sleep(0)
                    writer.write(b"0\r\n\r\n")
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                handlers.discard(task)

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        pool = ModelHttpPool(
            reuse_enabled=True,
            keepalive_expiry=None,
            drain_timeout_seconds=0.2,
            transport=httpx.AsyncHTTPTransport(limits=httpx.Limits(keepalive_expiry=None)),
        )
        monkeypatch.setattr(bootstrap, "build_model_http", lambda: pool)
        monkeypatch.setattr(
            bootstrap,
            "MODEL_DEFAULTS",
            {"base_url": f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"},
        )
        storage = Storage(resolve_data_dir(str(tmp_path / "data")))
        worker = BusinessWorker()
        project = tmp_path / "project"
        project.mkdir()
        credential = ResolvedCredential(
            SecretStr("sentinel-only"),
            CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
        )
        service = bootstrap.build_sessions(storage, worker, credential)
        signals = []
        unsubscribe = service.subscribe(signals.append)
        try:
            async with asyncio.timeout(10):
                with storage.writer():
                    selected = ProjectService(storage).open(path=str(project)).active_project
                    session = await service.create(selected.project_id, "glm-5.3-flash")

                    async def run(prompt):
                        """经生产服务提交新运行。 Submit a run through the production service."""
                        await service.start(session.session_id, str(uuid4()), prompt, None)
                        await service.active.task
                        return await service.view(session.session_id)

                    first = await run("answer")
                    second = await run("again")
                    assert first.summary.run.status == second.summary.run.status == "completed"
                    assert connections == 1 and len(requests) == 2
                    assert first.model_progress.connect_ms is not None
                    assert second.model_progress.connect_ms is None
                    assert (
                        first.model_progress.response_complete
                        and second.model_progress.response_complete
                    )
                    await service.start(session.session_id, str(uuid4()), "wait", None)
                    task = service.active.task
                    await waiting.wait()
                    # 等待真实 reasoning 事件被解析后取消，避免仅测服务端发出。
                    # Wait for actual parsing before cancelling, rather than just server emission.
                    while not any(
                        s.model_progress and s.model_progress.phase == "reasoning" for s in signals
                    ):
                        await asyncio.sleep(0)
                    await service.cancel(service.active.run_id)
                    await task
                    cancelled = await service.view(session.session_id)
                    assert cancelled.summary.run.status == "cancelled"
                    assert cancelled.model_progress.first_text_ms is None
                    assert cancelled.model_progress.first_event_ms is not None
                    assert "private-reasoning" not in cancelled.model_dump_json()
                    recovered = await run("answer")
                    assert recovered.summary.run.status == "completed" and connections == 2
                    assert requests == [session.session_id] * 4
                    await pool.set_reuse(False)
                    disabled_first = await run("no-reuse")
                    disabled_second = await run("no-reuse-again")
                    assert connections == 4
                    assert disabled_first.model_progress.connect_ms is not None
                    assert disabled_second.model_progress.connect_ms is not None
                    assert not pool.status().client_created
                    await pool.set_reuse(True)
                    await run("reuse-enabled-again")
                    final_run = await run("reuse-confirmed")
                    assert connections == 5
                    http_client = pool.client()
                    await service.close()
                    assert http_client.is_closed
                    # 使用新服务恢复时序，验证不是仅靠内存或会话消息。
                    # Reload timing through a fresh service to verify durable recovery.
                    reloaded = bootstrap.build_sessions(storage, worker, credential)
                    saved = await reloaded.view(session.session_id)
                    assert (
                        saved.model_progress.first_text_ms == final_run.model_progress.first_text_ms
                    )
                    log = reloaded.store.load(session.session_id)
                    interrupted_id = str(uuid4())
                    reloaded.store.append(
                        log,
                        RunAccepted(
                            operation_id=str(uuid4()),
                            prompt="interrupted",
                            limits=saved.summary.run.limits,
                            requested_limits=None,
                        ),
                        interrupted_id,
                    )
                    reloaded.store.append(
                        log, RequestStarted(message_id=str(uuid4())), interrupted_id
                    )
                    interrupted = await reloaded.view(session.session_id)
                    assert interrupted.summary.run.status == "interrupted"
                    assert interrupted.model_progress is None
        finally:
            unsubscribe()
            await service.close()
            worker.close()
            server.close()
            await server.wait_closed()
            if handlers:
                await asyncio.wait_for(asyncio.gather(*handlers), 2)

    asyncio.run(scenario())
