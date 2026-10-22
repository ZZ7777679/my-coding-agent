"""真实本地 HTTP 协议的工具和资源检查。 Real local HTTP protocol tools and resources."""

import asyncio
import socket

import pytest
import uvicorn
from mcp.server import MCPServer

from my_agent.errors import AgentError
from my_agent.mcp_client.service import Connection
from my_agent.mcp_client.types import McpControlParams, McpParams, McpServer, SaveMcpParams
from tests.python.test_goal_controller import app_at, create_session


def test_streamable_http_tools_and_resources(tmp_path, monkeypatch):
    """不依赖外网、凭据或模型。 Exercise HTTP without external services or model credentials."""

    async def scenario():
        """通过真实传输验证生命周期。 Verify lifecycle over a real transport."""
        peer = MCPServer("Local fixture")

        @peer.tool()
        def add(a: int, b: int) -> int:
            """返回两数之和。 Return the sum."""
            return a + b

        @peer.resource("fixture://note")
        def note() -> str:
            """返回只读样本。 Return a read-only fixture."""
            return "fixture-resource"

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(peer.streamable_http_app(), log_level="error"))
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            while not server.started:
                if serving.done():
                    await serving
                    raise AssertionError("HTTP server failed to start")
                await asyncio.sleep(0.01)
            async with app_at(tmp_path / "data", None) as app:
                created = await create_session(app, tmp_path / "project")
                params = McpParams(
                    project_id=created.task.project_id, session_id=created.session.session_id
                )
                service = app.sessions.mcp
                await service.save(
                    SaveMcpParams(
                        **params.model_dump(),
                        server=McpServer(
                            server_id="fixture",
                            name="Local HTTP",
                            transport="http",
                            url=f"http://127.0.0.1:{port}/mcp",
                            all_projects=False,
                        ),
                    )
                )
                # 资源库可单独测试连接；项目需明确启用后才向模型提供工具。
                # Library testing is independent; only explicitly enabled projects expose tools.
                library = await service.connect(McpParams(), "fixture")
                await library.call("tools/list", {})
                with pytest.raises(AgentError, match="当前项目"):
                    await service.connect(params, "fixture")
                registered = next(s for s in service.config().servers if s.server_id == "fixture")
                await service.save(
                    SaveMcpParams(
                        server=registered.model_copy(
                            update={
                                "project_ids": [params.project_id],
                            }
                        )
                    )
                )
                connection = await service.connect(params, "fixture")
                listing = await connection.call("tools/list", {})
                assert any(t["name"] == "add" for t in listing["tools"])
                answer = await connection.call(
                    "tools/call", {"name": "add", "arguments": {"a": 2, "b": 3}}
                )
                assert not answer.get("isError") and "5" in str(answer)
                resources = await connection.call("resources/list", {})
                assert any(r["uri"] == "fixture://note" for r in resources["resources"])
                resource = await connection.call("resources/read", {"uri": "fixture://note"})
                assert resource["contents"][0]["text"] == "fixture-resource"
                # 只读发现可重建已关闭连接，不重放之前的工具。
                # Read-only discovery can replace a closed connection without replaying tools.
                await connection.close()
                unchanged = await service.connect(params, "fixture")
                assert unchanged is connection
                connection = await service.connect(params, "fixture", refresh_closed=True)
                assert connection is not unchanged
                refreshed = await connection.call("tools/list", {})
                assert any(t["name"] == "add" for t in refreshed["tools"])
                sid = created.session.session_id
                service.select_tools(sid, "fixture", connection.tools)
                other = await app.dispatch(
                    "sessions.create",
                    {
                        "project_id": params.project_id,
                        "model_id": "glm-5.3-flash",
                    },
                )
                other_params = params.model_copy(update={"session_id": other.session_id})
                second = await service.connect(other_params, "fixture")
                service.select_tools(other.session_id, "fixture", connection.tools)
                invoke = Connection._invoke
                entered = asyncio.Event()
                gate = asyncio.Event()

                async def slow_list(self, client, request):
                    """模拟慢目录，保留真实连接。 Delay listing while retaining real transport."""
                    if request.method == "tools/list":
                        entered.set()
                        await gate.wait()
                    return await invoke(self, client, request)

                monkeypatch.setattr(Connection, "_invoke", slow_list)
                catalog = await asyncio.wait_for(
                    service.control(
                        McpControlParams(
                            **params.model_dump(),
                            server_id="fixture",
                            action="refresh",
                        )
                    ),
                    1,
                )
                await entered.wait()
                assert (
                    next(v for v in catalog.servers if v.server.server_id == "fixture").status
                    == "refreshing"
                )
                # 移除必须关闭所有会话，不是只关设置页的一条连接。
                # Removing a registration closes every session, not only the settings connection.
                await service.control(
                    McpControlParams(
                        project_id=params.project_id,
                        server_id="fixture",
                        action="remove",
                    )
                )
                await asyncio.gather(*(task for _, task in list(service.controls.values())))
                assert connection.status == "closed"
                assert library.status == "closed"
                assert second.status == "closed" and not service.selected[sid]
                assert not service.selected[other.session_id]
        finally:
            server.should_exit = True
            await serving
            listener.close()

    asyncio.run(asyncio.wait_for(scenario(), 30))
