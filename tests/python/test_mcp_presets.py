"""MCP 预设、凭据与实际 HTTP 边界的定向验证。

Focused MCP preset, credential and real HTTP boundary checks.
"""

import asyncio
import json
import os
import re
import socket
import sys

import httpx2
import pytest
import uvicorn
from mcp.server import MCPServer
from starlette.responses import PlainTextResponse

from my_agent.errors import AgentError
from my_agent.mcp_client.credentials import McpCredentials, environment_value
from my_agent.mcp_client.errors import public_error
from my_agent.mcp_client.presets import service_presets
from my_agent.mcp_client.types import McpAuth, McpControlParams, McpParams, McpServer, SaveMcpParams
from tests.python.test_goal_controller import app_at, create_session


@pytest.mark.skipif(sys.platform != "win32", reason="Real current-user Windows DPAPI")
def test_mcp_saved_credentials_and_presets(tmp_path):
    """验证真实加密、重启、删除与旧配置，不接触个人凭据。

    Exercise real encryption, reopening, removal and legacy config without personal credentials.
    """
    secret = "isolated-mcp-saved-token"

    async def scenario():
        """复用真实 RPC 装配，目录保持离线。

        Use real RPC composition while keeping catalogs offline."""
        async with app_at(tmp_path / "data", None) as app:
            mcp = app.sessions.mcp
            catalog = await app.dispatch("mcp.list", {})
            assert {p.preset_id for p in catalog.presets} == {"context7", "github"}
            assert [s.server.server_id for s in catalog.servers] == ["browser"]
            assert not mcp.connections
            preset = next(p for p in catalog.presets if p.preset_id == "github")
            config = preset.server.model_copy(update={"server_id": "account-one"})
            saved = await app.dispatch(
                "mcp.save", {"server": config.model_dump(), "credential_value": secret}
            )
            view = next(s for s in saved.servers if s.server.server_id == config.server_id)
            assert view.credential_status == "configured"
            assert secret not in saved.model_dump_json()
            assert mcp.http_headers(config)["authorization"] == f"Bearer {secret}"
            assert (
                mcp.http_headers(config)["x-mcp-toolsets"]
                == preset.server.headers["X-MCP-Toolsets"]
            )
            assert secret not in (tmp_path / "data" / "mcp.json").read_text(encoding="utf-8")
            encrypted = McpCredentials(tmp_path / "data")
            assert encrypted.read(config.server_id) == secret
            assert secret not in encrypted.path(config.server_id).read_text(encoding="utf-8")
            # 表单留空保存不能擦掉凭据。 Blank form saves must retain the stored token.
            await app.dispatch("mcp.save", {"server": config.model_dump()})
            assert encrypted.read(config.server_id) == secret
            old = McpServer.model_validate({"server_id": "old", "name": "Legacy stdio"})
            assert old.auth.source == "none" and old.headers == {}
        async with app_at(tmp_path / "data", None) as app:
            mcp = app.sessions.mcp
            config = mcp.config().servers[-1]
            assert mcp.http_headers(config)["authorization"] == f"Bearer {secret}"
            await app.dispatch(
                "mcp.save", {"server": config.model_dump(), "clear_credential": True}
            )
            assert mcp.catalog(McpParams()).servers[-1].credential_status == "missing"
            await app.dispatch(
                "mcp.save", {"server": config.model_dump(), "credential_value": secret}
            )
            await mcp.control(McpControlParams(server_id=config.server_id, action="remove"))
            assert not mcp.credentials.path(config.server_id).exists()

    asyncio.run(scenario())


def test_mcp_environment_and_error_classification(monkeypatch):
    """环境来源与已知错误保留区别，异常原文不泄露。

    Distinguish environment sources and failures without exposing raw exceptions."""
    monkeypatch.setenv("MCP_TEST_REFERENCE", "process-value")
    monkeypatch.setattr(
        "my_agent.mcp_client.credentials.read_windows_user", lambda name: "user-value"
    )
    assert environment_value("MCP_TEST_REFERENCE") == "process-value"
    monkeypatch.delenv("MCP_TEST_REFERENCE")
    if sys.platform == "win32":
        assert environment_value("MCP_TEST_REFERENCE") == "user-value"
    monkeypatch.setattr("my_agent.mcp_client.credentials.read_windows_user", lambda name: None)
    with pytest.raises(AgentError) as missing:
        environment_value("MCP_TEST_REFERENCE")
    assert missing.value.code == "MCP_CREDENTIAL_MISSING"
    for status, code in [
        (401, "MCP_AUTH_REQUIRED"),
        (403, "MCP_ACCESS_DENIED"),
        (429, "MCP_RATE_LIMITED"),
    ]:
        request = httpx2.Request("POST", "https://example.invalid/mcp")
        failure = httpx2.HTTPStatusError(
            "secret-response", request=request, response=httpx2.Response(status, request=request)
        )
        exposed = public_error(ExceptionGroup("outer", [failure]), connecting=True)
        assert exposed.code == code and "secret-response" not in exposed.message
    assert public_error(httpx2.ConnectTimeout("secret"), connecting=True).code == "MCP_TIMEOUT"
    assert public_error(httpx2.ConnectError("secret"), connecting=True).code == "MCP_NETWORK_ERROR"


def test_mcp_http_authentication_scope_and_reconnect(tmp_path, monkeypatch):
    """真实 HTTP 验证凭据装配、401、快照更新与项目启用。

    Verify auth assembly, HTTP 401, snapshot refresh and project scope over real HTTP.
    """

    async def scenario():
        """样本服务不回显令牌，只检查请求是否携带正确认证。

        The fixture validates authentication without echoing the credential."""
        peer = MCPServer("MCP authentication fixture")
        received = []

        @peer.tool()
        def ping() -> str:
            """返回公开状态。 Return public status."""
            return "authenticated-fixture"

        inner = peer.streamable_http_app()

        async def endpoint(scope, receive, send):
            """真实认证响应，不模拟 MCP 握手本身。

            Serve real authentication responses without mocking MCP negotiation."""
            if scope["type"] == "http":
                headers = dict(scope["headers"])
                if headers.get(b"authorization") != b"Bearer isolated-http-token":
                    await PlainTextResponse("private-response-must-not-leak", status_code=401)(
                        scope, receive, send
                    )
                    return
                received.append(headers.get(b"x-mcp-toolsets"))
            await inner(scope, receive, send)

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(endpoint, log_level="error"))
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            while not server.started:
                if serving.done():
                    await serving
                    raise AssertionError("fixture did not start")
                await asyncio.sleep(0.01)
            async with app_at(tmp_path / "data", None) as app:
                created = await create_session(app, tmp_path / "project")
                mcp = app.sessions.mcp
                config = McpServer(
                    server_id="http-fixture",
                    name="Fixture",
                    transport="http",
                    url=f"http://127.0.0.1:{listener.getsockname()[1]}/mcp",
                    all_projects=False,
                    headers={"X-MCP-Toolsets": "repos,issues"},
                )
                await mcp.save(SaveMcpParams(server=config))
                with pytest.raises(AgentError) as denied:
                    await mcp.connect(McpParams(), config.server_id)
                assert denied.value.code == "MCP_AUTH_REQUIRED"
                catalog = mcp.catalog(McpParams())
                assert "401" in catalog.servers[-1].error
                assert "private-response" not in catalog.model_dump_json()
                monkeypatch.setenv("MCP_TEST_AUTH", "isolated-http-token")
                config.auth = McpAuth(source="environment", env_var="MCP_TEST_AUTH")
                await mcp.save(SaveMcpParams(server=config))
                await mcp.control(McpControlParams(server_id=config.server_id, action="connect"))
                await asyncio.gather(*(t for _, t in list(mcp.controls.values())))
                connection = await mcp.connect(McpParams(), config.server_id)
                result = await connection.call("tools/call", {"name": "ping", "arguments": {}})
                assert "authenticated-fixture" in str(result) and not result.get("isError")
                assert received and all(value == b"repos,issues" for value in received)
                config.headers = {"X-MCP-Toolsets": "issues"}
                await mcp.save(SaveMcpParams(server=config))
                assert mcp.catalog(McpParams()).servers[-1].needs_reconnect
                await mcp.control(McpControlParams(server_id=config.server_id, action="connect"))
                await asyncio.gather(*(t for _, t in list(mcp.controls.values())))
                assert not mcp.catalog(McpParams()).servers[-1].needs_reconnect
                assert received[-1] == b"issues"
                params = McpParams(
                    project_id=created.task.project_id, session_id=created.session.session_id
                )
                with pytest.raises(AgentError):
                    await mcp.connect(params, config.server_id)
                config.project_ids = [created.task.project_id]
                await mcp.save(SaveMcpParams(server=config))
                scoped = await mcp.connect(params, config.server_id)
                await scoped.call("tools/list", {})
                mcp.select_tools(created.session.session_id, config.server_id, scoped.tools)
                assert mcp.selected[created.session.session_id]
                config.project_ids = []
                await mcp.save(SaveMcpParams(server=config))
                await asyncio.gather(*(t for _, t in list(mcp.controls.values())))
                assert not mcp.selected[created.session.session_id]
        finally:
            server.should_exit = True
            await serving
            listener.close()

    asyncio.run(asyncio.wait_for(scenario(), 35))


@pytest.mark.skipif(
    os.environ.get("MY_AGENT_TEST_MCP_SERVICES") != "1", reason="Explicit public network check"
)
def test_context7_anonymous_tool_discovery_live(tmp_path):
    """匿名服务经产品工具发现与调用，不读取个人账号凭据。

    Discover and call the anonymous service through product tools without personal credentials.
    """
    import threading
    from uuid import uuid4

    from my_agent.config import DEFAULTS
    from my_agent.mcp_client.tools import McpTools
    from my_agent.models.types import ToolCall
    from my_agent.runtime.settings import RunLimits
    from my_agent.runtime.tools import ToolContext
    from my_agent.tools.read_only import ReadTools

    async def scenario():
        """仅在新隔离根登记 Context7，真实读取 React 文档。

        Register only Context7 in a new isolated root and read actual React documentation.
        """
        async with app_at(tmp_path / "data", None) as app:
            created = await create_session(app, tmp_path / "project")
            context = ToolContext(
                tmp_path / "project",
                RunLimits.model_validate(DEFAULTS["run"]),
                threading.Event(),
                created.task.project_id,
                created.session.session_id,
                str(uuid4()),
                "normal",
                None,
            )
            server = next(p.server for p in service_presets() if p.preset_id == "context7")
            server = server.model_copy(update={"project_ids": [created.task.project_id]})
            assert server.auth.source == "none"
            await app.sessions.mcp.save(SaveMcpParams(server=server))
            tools = McpTools(
                context, ReadTools(context.root, context.limits, context.stop), app.sessions.mcp
            )
            discovered = await tools.execute(
                ToolCall(
                    tool_call_id=str(uuid4()),
                    name="discover_mcp_tools",
                    arguments={
                        "server_id": server.server_id,
                        "names": ["resolve-library-id", "query-docs"],
                    },
                )
            )
            assert not discovered.is_error, discovered.content
            lookup = next(
                t["function"]
                for t in tools.definitions()
                if t["function"]["description"].startswith("context7/resolve-library-id:")
            )
            result = await tools.execute(
                ToolCall(
                    tool_call_id=str(uuid4()),
                    name=lookup["name"],
                    arguments={"libraryName": "react", "query": "React useState counter"},
                )
            )
            report = {
                "anonymous": True,
                "discovery_ok": not discovered.is_error,
                "lookup_ok": not result.is_error,
                "result": json.loads(result.content),
            }
            text = "\n".join(
                item.get("text", "")
                for item in report["result"].get("content", [])
                if item.get("type") == "text"
            )
            match = re.search(r"Context7-compatible library ID:\s*(/\S+)", text)
            assert match, "No library identity in actual lookup result"
            docs_tool = next(
                t["function"]
                for t in tools.definitions()
                if t["function"]["description"].startswith("context7/query-docs:")
            )
            docs = await tools.execute(
                ToolCall(
                    tool_call_id=str(uuid4()),
                    name=docs_tool["name"],
                    arguments={"libraryId": match.group(1), "query": "React useState counter"},
                )
            )
            report["docs_ok"] = not docs.is_error
            (tmp_path / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            assert not result.is_error, result.content
            assert not docs.is_error, docs.content

    asyncio.run(asyncio.wait_for(scenario(), 100))


@pytest.mark.skipif(
    os.environ.get("MY_AGENT_TEST_MCP_SERVICES") != "1", reason="Explicit public network check"
)
def test_mcp_public_services_live(tmp_path):
    """只读外网检查，未配置 GitHub 凭据时明确记录未验收。

    Check external services read-only, recording unverified GitHub auth when unconfigured.
    """

    async def scenario():
        """使用真实生产连接层，不发送项目代码或模型请求。

        Use production connections without sending project code or model requests."""
        report = {}
        async with app_at(tmp_path / "data", None) as app:
            mcp = app.sessions.mcp
            for preset in service_presets():
                config = preset.server
                config.timeout_seconds = 40
                try:
                    environment_value(preset.suggested_env)
                    has_credential = True
                except AgentError:
                    has_credential = False
                if has_credential:
                    config.auth = McpAuth(source="environment", env_var=preset.suggested_env)
                elif preset.preset_id == "github":
                    report["github"] = {
                        "status": "not_checked",
                        "reason": "GITHUB_MCP_TOKEN not configured",
                    }
                    continue
                await mcp.save(SaveMcpParams(server=config))
                try:
                    connection = await mcp.connect(McpParams(), config.server_id)
                    await connection.call("tools/list", {})
                    names = [tool["name"] for tool in connection.tools]
                    report[preset.preset_id] = {
                        "status": "connected",
                        "tools": names,
                        "auth": "environment" if has_credential else "anonymous",
                    }
                    if preset.preset_id == "context7":
                        result = await connection.call(
                            "tools/call",
                            {
                                "name": "resolve-library-id",
                                "arguments": {
                                    "libraryName": "react",
                                    "query": "React useState reference",
                                },
                            },
                        )
                        report["context7"]["query_ok"] = not result.get("isError")
                        assert not result.get("isError"), "Context7 lookup returned a tool error"
                        text = "\n".join(
                            item.get("text", "")
                            for item in result.get("content", [])
                            if isinstance(item, dict) and item.get("type") == "text"
                        )
                        match = re.search(r"Context7-compatible library ID:\s*(/\S+)", text)
                        assert match, "Lookup did not provide a library identity"
                        docs = await connection.call(
                            "tools/call",
                            {
                                "name": "query-docs",
                                "arguments": {
                                    "libraryId": match.group(1),
                                    "query": "Increment a counter using React useState",
                                },
                            },
                        )
                        report["context7"]["docs_ok"] = not docs.get("isError")
                        report["context7"]["library_id"] = match.group(1)
                        assert not docs.get("isError"), (
                            "Context7 documentation returned a tool error"
                        )
                except AgentError as exc:
                    report[preset.preset_id] = {
                        "status": "failed",
                        "code": exc.code,
                        "message": exc.message,
                    }
        (tmp_path / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False))
        assert report.get("context7", {}).get("status") == "connected", report

    asyncio.run(asyncio.wait_for(scenario(), 100))
