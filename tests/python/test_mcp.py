"""真实 SDK 与锁定的浏览器服务兼容检查。 Real SDK and locked browser server checks."""

import asyncio
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from my_agent.mcp_client.types import McpParams, SaveMcpParams
from tests.python.test_goal_controller import app_at, create_session


@pytest.fixture
def counter_url():
    """本地单页不依赖外网。 Local counter without external network dependencies."""

    class Handler(BaseHTTPRequestHandler):
        """返回隔离计数器。 Serve an isolated counter."""

        def do_GET(self):
            """响应页面请求。 Respond with the counter page."""
            body = (
                b'<button onclick="n.textContent=Number(n.textContent)+1">Add</button>'
                b'<p id="n">0</p>'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            """隔离测试不输出请求日志。 Suppress test HTTP logs."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.skipif(
    os.environ.get("MY_AGENT_TEST_MCP") != "1",
    reason="Explicit local MCP subprocess check; no model requests.",
)
def test_sdk2_connects_to_playwright_server_and_closes(tmp_path, counter_url):
    """通过产品连接层验证协商、目录、调用和清理。

    Verify negotiation, discovery, a tool call and cleanup through the product adapter.
    """

    async def scenario():
        """隔离目录不读取个人会话。 Use isolated data without personal sessions."""
        async with app_at(tmp_path / "data", None) as app:
            created = await create_session(app, tmp_path / "project")
            params = McpParams(
                project_id=created.task.project_id,
                session_id=created.session.session_id,
            )
            service = app.sessions.mcp
            assert service is not None
            if os.environ.get("MY_AGENT_TEST_INSTALL_BROWSER") == "1":
                await service.install_browser(params)
            executable = os.environ.get("MY_AGENT_TEST_BROWSER")
            if executable:
                server = (
                    service.config()
                    .servers[0]
                    .model_copy(update={"browser_executable": executable})
                )
                await service.save(SaveMcpParams(**params.model_dump(), server=server))
            connection = await service.connect(params, "browser")
            listing = await connection.call("tools/list", {})
            assert any(t["name"] == "browser_navigate" for t in listing["tools"])
            page = await connection.call(
                "tools/call", {"name": "browser_navigate", "arguments": {"url": counter_url}}
            )
            page = await service.normalize(params, page)
            assert not page.get("isError"), page
            snapshot = "\n".join(c.get("text", "") for c in page["content"])
            match = re.search(r'button "Add".*?\[ref=([^\]]+)\]', snapshot)
            assert match, snapshot
            ref = match.group(1)
            clicked = await connection.call(
                "tools/call",
                {
                    "name": "browser_click",
                    "arguments": {"element": "Add button", "target": ref},
                },
            )
            assert not clicked.get("isError"), clicked
            value = await connection.call(
                "tools/call",
                {
                    "name": "browser_evaluate",
                    "arguments": {
                        "function": (
                            "() => { localStorage.setItem('m4', 'first'); "
                            "return document.querySelector('#n').textContent; }"
                        )
                    },
                },
            )
            assert not value.get("isError") and '"1"' in str(value), value
            shot = await connection.call(
                "tools/call",
                {
                    "name": "browser_take_screenshot",
                    "arguments": {"type": "png", "filename": "counter.png"},
                },
            )
            assert not shot.get("isError"), shot
            assert (service.artifacts_dir(params) / "counter.png").is_file()
            other = await app.sessions.create(params.project_id, "glm-5.3-flash")
            second = await service.connect(
                McpParams(project_id=params.project_id, session_id=other.session_id), "browser"
            )
            await second.call(
                "tools/call", {"name": "browser_navigate", "arguments": {"url": counter_url}}
            )
            isolated = await second.call(
                "tools/call",
                {
                    "name": "browser_evaluate",
                    "arguments": {"function": "() => localStorage.getItem('m4')"},
                },
            )
            assert not isolated.get("isError") and "null" in str(isolated), isolated
            pending = asyncio.create_task(
                connection.call(
                    "tools/call",
                    {
                        "name": "browser_wait_for",
                        "arguments": {"time": 5},
                    },
                )
            )
            await asyncio.sleep(0.2)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            await connection.call("tools/list", {})
            result = await connection.call("tools/call", {"name": "browser_close", "arguments": {}})
            assert not result.get("isError")
            assert connection.status == "connected"
            await connection.close()
            assert connection.task.done()
            assert connection.status == "closed"

    asyncio.run(asyncio.wait_for(scenario(), timeout=90))
