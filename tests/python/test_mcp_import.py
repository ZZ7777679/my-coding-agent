"""通用 MCP 导入后端：真实传输、新旧模式、凭据保存与资源读取。

Real MCP transports, protocol modes, credential persistence and resource reads.
"""

import asyncio
import socket
import sys
from pathlib import Path

import pytest
import uvicorn
from mcp.server import MCPServer
from mcp.server.lowlevel import Server
from mcp.types import ListResourcesResult, ReadResourceResult, Resource, TextResourceContents
from starlette.responses import PlainTextResponse

from my_agent.mcp_client.types import McpControlParams, McpParams
from tests.python.test_goal_controller import app_at, create_session


@pytest.mark.parametrize("transport", ["http", "sse", "stdio", "resources"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_import_transports_credentials_resources(tmp_path, transport, mode):
    """隔离样本经过生产服务连接，不访问外网或个人数据。

    Connect isolated peers through production services without external accounts.
    """

    async def scenario():
        """启动需要认证的远程样本或本地进程。

        Start an authenticated remote peer or local process."""
        peer = MCPServer("Imported remote")

        @peer.tool()
        def ping() -> str:
            """返回连通结果。 Return a connectivity result."""
            return "pong"

        @peer.resource("fixture://note")
        def note() -> str:
            """返回只读资源。 Return a read-only resource."""
            return "import-resource"

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        if transport == "resources":

            async def list_only_resources(ctx, params):
                """只声明资源，真实省略 tools 能力。

                Advertise resources without a tools capability."""
                return ListResourcesResult(resources=[Resource(uri="fixture://note", name="note")])

            async def read_only_resource(ctx, params):
                """返回资源正文。 Return resource contents."""
                return ReadResourceResult(
                    contents=[TextResourceContents(uri=params.uri, text="import-resource")]
                )

            resource_server = Server(
                "Resources only",
                on_list_resources=list_only_resources,
                on_read_resource=read_only_resource,
            )
            inner = resource_server.streamable_http_app()
        else:
            inner = peer.sse_app() if transport == "sse" else peer.streamable_http_app()

        async def authenticated(scope, receive, send):
            """验证合成多认证头，不回显秘密。 Check synthetic headers without echoing secrets."""
            if scope["type"] == "http":
                headers = dict(scope["headers"])
                if (
                    headers.get(b"authorization") != b"Bearer isolated-http-token"
                    or headers.get(b"x-api-key") != b"isolated-header-token"
                ):
                    await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
                    return
            await inner(scope, receive, send)

        host = uvicorn.Server(uvicorn.Config(authenticated, log_level="error"))
        serving = asyncio.create_task(host.serve(sockets=[listener]))
        root = tmp_path / "data"
        try:
            while not host.started:
                if serving.done():
                    await serving
                    raise AssertionError("Fixture failed to start")
                await asyncio.sleep(0.01)
            async with app_at(root, None) as app:
                created = await create_session(app, tmp_path / "project")
                project_id = created.task.project_id
                config = {
                    "server_id": "imported",
                    "name": "Imported",
                    "transport": "http" if transport == "resources" else transport,
                    "protocol_mode": mode,
                    "all_projects": False,
                    "project_ids": [project_id],
                }
                if transport == "stdio":
                    config.update(
                        {
                            "command": sys.executable,
                            "arguments": [
                                str(Path(__file__).parents[1] / "support/mcp_import_fixture.py")
                            ],
                            "cwd": "${workspaceFolder}",
                            "stored_env": ["MCP_IMPORT_TOKEN"],
                        }
                    )
                    values = {"env": {"MCP_IMPORT_TOKEN": "isolated-local-token"}}
                    token = None
                else:
                    endpoint = "sse" if transport == "sse" else "mcp"
                    config.update(
                        {
                            "url": f"http://127.0.0.1:{listener.getsockname()[1]}/{endpoint}",
                            "auth": {"source": "saved"},
                            "stored_headers": ["X-Api-Key"],
                        }
                    )
                    values = {"headers": {"X-Api-Key": "isolated-header-token"}}
                    token = "isolated-http-token"
                catalog = await app.dispatch(
                    "mcp.save",
                    {
                        "server": config,
                        "credential_value": token,
                        "connection_values": values,
                    },
                )
                assert "isolated-" not in catalog.model_dump_json()
                assert not app.sessions.mcp.connections
                for path in [root / "mcp.json", *(root / "mcp-connection-values").glob("*.json")]:
                    assert "isolated-" not in path.read_text(encoding="utf-8")

            # 重开服务后才连接，证明凭据与配置均从磁盘恢复。
            # Connect after reopening to prove credentials and settings survive restart.
            async with app_at(root, None) as app:
                service = app.sessions.mcp
                params = McpParams(project_id=project_id)
                connection = await service.connect(params, "imported")
                tools = await connection.call("tools/list", {})
                tool = "check_environment" if transport == "stdio" else "ping"
                if transport == "resources":
                    assert tools["tools"] == [] and connection.status == "connected"
                else:
                    assert any(item["name"] == tool for item in tools["tools"])
                    result = await connection.call("tools/call", {"name": tool, "arguments": {}})
                    assert not result.get("isError")
                if transport == "stdio":
                    assert result["structuredContent"]["configured"] is True
                    assert Path(result["structuredContent"]["cwd"]) == tmp_path / "project"
                resources = await connection.call("resources/list", {})
                assert any(item["uri"] == "fixture://note" for item in resources["resources"])
                read = await connection.call("resources/read", {"uri": "fixture://note"})
                assert read["contents"][0]["text"] == "import-resource"
                registered = service.config().servers[-1]
                # 普通编辑不擦除变量，公开配置始终只暴露名称。
                # Ordinary edits retain values; public configuration exposes names only.
                await app.dispatch(
                    "mcp.save", {"server": registered.model_dump(), "connection_values": {}}
                )
                assert service.saved_values.values(
                    registered, "env" if transport == "stdio" else "headers"
                )
                await service.control(McpControlParams(server_id="imported", action="remove"))
                assert not service.saved_values.credentials.path("imported").exists()
                assert not service.credentials.path("imported").exists()
        finally:
            host.should_exit = True
            await serving
            listener.close()

    asyncio.run(asyncio.wait_for(scenario(), 35))
