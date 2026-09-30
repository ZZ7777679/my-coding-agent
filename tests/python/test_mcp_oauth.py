"""隔离真实 HTTP / SDK / DPAPI 的 OAuth 接续检查。

Isolated OAuth continuity checks using real HTTP, SDK and Windows DPAPI.
"""

import asyncio
import json
import os
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx2
import pytest
from mcp.client.auth.utils import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
    extract_resource_metadata_from_www_auth,
)
from mcp.shared.auth import OAuthMetadata, ProtectedResourceMetadata

from my_agent.errors import AgentError
from my_agent.mcp_client.types import (
    McpAuth,
    McpControlParams,
    McpOAuthConfig,
    McpParams,
    McpServer,
    SaveMcpParams,
)
from tests.python.test_goal_controller import app_at
from tests.support.mcp_oauth_fixture import serve_oauth


async def await_authorization(mcp, server):
    """等待可交互状态，提前失败则立即显示公开错误。

    Wait for an interactive state and fail immediately on a public error."""
    async with asyncio.timeout(5):
        while True:
            view = mcp.oauth.view(server)
            if view.status == "failed":
                raise AssertionError(view.error)
            if view.authorization_url:
                return view
            await asyncio.sleep(0.01)


async def complete_login(mcp, server, http):
    """本地批准合成账号，SDK 验证 PKCE / issuer 并自动测试 MCP 连接。

    Approve a fixture account; the SDK checks PKCE/issuer before MCP connection testing."""
    await mcp.control(McpControlParams(server_id=server.server_id, action="oauth_login"))
    view = await await_authorization(mcp, server)
    parsed = urlsplit(view.authorization_url)
    result = await http.get(
        f"{parsed.scheme}://{parsed.netloc}/approve?{parsed.query}", follow_redirects=True
    )
    assert result.status_code == 200 and "My Coding Agent" in result.text
    await asyncio.gather(*(task for _, task in list(mcp.controls.values())))
    assert mcp.oauth.view(server).status == "authorized", mcp.oauth.view(server).error
    assert mcp.catalog(McpParams()).servers[-1].status == "connected"


def test_mcp_oauth_login_refresh_restart_and_logout(tmp_path):
    """首次授权、真实工具、并发刷新、重启、失败不重放及退出。

    Test login, tools, concurrent refresh, restart, no replay on failure and logout."""

    async def scenario():
        """隔离应用数据和授权服务，不访问外网或模型。

        Isolate app data and authorization without external services or models."""
        async with serve_oauth() as peer, httpx2.AsyncClient() as http:
            config = McpServer(
                server_id="oauth-fixture",
                name="OAuth fixture",
                transport="http",
                url=f"{peer.url}/mcp",
                auth=McpAuth(source="oauth"),
            )
            async with app_at(tmp_path / "data", None) as app:
                mcp = app.sessions.mcp
                await mcp.save(SaveMcpParams(server=config))
                await complete_login(mcp, config, http)
                assert peer.registrations == 1
                connection = await mcp.connect(McpParams(), config.server_id)
                answer = await connection.call(
                    "tools/call", {"name": "read_status", "arguments": {}}
                )
                assert "oauth-fixture-ready" in str(answer) and peer.calls == 1
                record = mcp.oauth._read(config)
                secrets = [record.tokens.access_token, record.tokens.refresh_token]
                for path in (tmp_path / "data").rglob("*.json"):
                    text = path.read_text(encoding="utf-8")
                    assert all(token not in text for token in secrets if token)
                assert all(
                    token not in mcp.catalog(McpParams()).model_dump_json()
                    for token in secrets
                    if token
                )
                record.expires_at = time.time() - 1
                mcp.oauth._write(config.server_id, record)
                tokens = await asyncio.gather(*(mcp.oauth.access_token(config) for _ in range(3)))
                assert len(set(tokens)) == 1 and peer.refreshes == 1
                assert mcp.oauth._read(config).tokens.refresh_token == record.tokens.refresh_token
                record = mcp.oauth._read(config)
                record.expires_at = time.time() - 1
                mcp.oauth._write(config.server_id, record)
            async with app_at(tmp_path / "data", None) as app:
                mcp = app.sessions.mcp
                assert mcp.oauth.view(config).status == "stored"
                connection = await mcp.connect(McpParams(), config.server_id)
                await connection.call("tools/list", {})
                assert peer.refreshes == 2 and peer.registrations == 1
                before = peer.rejected_posts
                peer.reject = True
                with pytest.raises(AgentError):
                    await connection.call("tools/call", {"name": "read_status", "arguments": {}})
                assert peer.rejected_posts == before + 1
                assert peer.calls == 1 and peer.registrations == 1
                peer.reject = False
                changed = config.model_copy(update={"url": peer.url + "/another"})
                with pytest.raises(AgentError, match="重新登录"):
                    await mcp.oauth.access_token(changed)
                await mcp.control(
                    McpControlParams(server_id=config.server_id, action="oauth_logout")
                )
                await asyncio.gather(*(task for _, task in list(mcp.controls.values())))
                assert not mcp.oauth.credentials.path(config.server_id).exists()
                assert not mcp.connections
                assert mcp.oauth.view(config).status == "not_logged_in"

    asyncio.run(asyncio.wait_for(scenario(), 30))


@pytest.mark.skipif(
    os.environ.get("MY_AGENT_TEST_MCP_OAUTH_DISCOVERY") != "1",
    reason="Explicit public OAuth discovery only; no registration or personal login",
)
def test_mcp_oauth_discovery_live(tmp_path):
    """仅读取公开发现信息，不登记客户端、不登录真实账号。

    Read public discovery only, without registering clients or authenticating real accounts.
    """

    async def scenario():
        """按 SDK 同一发现顺序核实两个官方服务。

        Follow the SDK discovery order for the two official services."""
        report = {}
        urls = {
            "context7": "https://mcp.context7.com/mcp/oauth",
            "github": "https://api.githubcopilot.com/mcp/",
        }
        async with httpx2.AsyncClient(timeout=30) as http:
            for name, url in urls.items():
                request = http.build_request(
                    "POST",
                    url,
                    headers={
                        "Accept": "application/json, text/event-stream",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": "discovery",
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2026-07-28",
                            "capabilities": {},
                            "clientInfo": {"name": "my-coding-agent-test", "version": "0"},
                        },
                    },
                )
                response = await http.send(request, stream=True)
                try:
                    assert response.status_code == 401
                    resource_url = extract_resource_metadata_from_www_auth(response)
                finally:
                    await response.aclose()
                resource = None
                for endpoint in build_protected_resource_metadata_discovery_urls(resource_url, url):
                    print(f"{name} resource metadata: {endpoint}", flush=True)
                    page = await http.get(endpoint)
                    if page.status_code == 200:
                        resource = ProtectedResourceMetadata.model_validate_json(page.content)
                        break
                assert resource is not None and resource.authorization_servers
                metadata = None
                for endpoint in build_oauth_authorization_server_metadata_discovery_urls(
                    str(resource.authorization_servers[0]), url
                ):
                    print(f"{name} authorization metadata: {endpoint}", flush=True)
                    page = await http.get(endpoint)
                    if page.status_code == 200:
                        metadata = OAuthMetadata.model_validate_json(page.content)
                        break
                assert metadata is not None
                report[name] = {
                    "resource": str(resource.resource),
                    "issuer": str(metadata.issuer),
                    "authorization_endpoint": str(metadata.authorization_endpoint),
                    "token_endpoint": str(metadata.token_endpoint),
                    "dynamic_registration": metadata.registration_endpoint is not None,
                    "client_metadata_document": metadata.client_id_metadata_document_supported,
                    "token_auth_methods": metadata.token_endpoint_auth_methods_supported,
                    "pkce": metadata.code_challenge_methods_supported,
                }
                (tmp_path / "discovery.json").write_text(
                    json.dumps(report, indent=2), encoding="utf-8"
                )
        (tmp_path / "discovery.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))

    asyncio.run(asyncio.wait_for(scenario(), 150))


def test_mcp_oauth_cancel_denial_static_registration_and_expiry(tmp_path, monkeypatch):
    """错误回调不消耗登录；取消、拒绝、显式身份和刷新失败有明确状态。

    Verify wrong callbacks, cancellation, denial, provisioned identity and refresh failure."""
    monkeypatch.setenv("FIXTURE_OAUTH_CLIENT_SECRET", "fixture-client-secret")

    async def scenario():
        """真实走回调端口与 SDK 交换，无个人凭据。

        Exercise real callback ports and SDK exchanges without personal credentials."""
        async with (
            serve_oauth() as peer,
            httpx2.AsyncClient() as http,
            app_at(tmp_path / "data", None) as app,
        ):
            config = McpServer(
                server_id="static",
                name="Static",
                transport="http",
                url=peer.url + "/mcp",
                auth=McpAuth(
                    source="oauth",
                    oauth=McpOAuthConfig(
                        client_id="fixture-static",
                        client_secret_env="FIXTURE_OAUTH_CLIENT_SECRET",
                        token_auth_method="client_secret_post",
                        scope="docs:read",
                    ),
                ),
            )
            mcp = app.sessions.mcp
            await mcp.save(SaveMcpParams(server=config))
            await complete_login(mcp, config, http)
            assert peer.registrations == 0
            original = mcp.oauth._read(config)
            assert original.client.client_secret is None
            await mcp.control(McpControlParams(server_id=config.server_id, action="oauth_login"))
            view = await await_authorization(mcp, config)
            wrong = await http.get(view.redirect_uri + "?code=wrong&state=wrong")
            assert wrong.status_code == 400 and mcp.oauth.view(config).status == "awaiting_user"
            await mcp.control(McpControlParams(server_id=config.server_id, action="oauth_cancel"))
            assert mcp.oauth.view(config).status == "cancelled"
            assert mcp.oauth._read(config).tokens.access_token == original.tokens.access_token
            with pytest.raises(httpx2.ConnectError):
                await http.get(view.redirect_uri)
            await mcp.control(McpControlParams(server_id=config.server_id, action="oauth_login"))
            view = await await_authorization(mcp, config)
            state = parse_qs(urlsplit(view.authorization_url).query)["state"][0]
            await http.get(
                view.redirect_uri + "?" + urlencode({"error": "access_denied", "state": state})
            )
            await asyncio.gather(*(task for _, task in list(mcp.controls.values())))
            assert "MCP_OAUTH_DENIED" in mcp.oauth.view(config).error
            original.expires_at = time.time() - 1
            mcp.oauth._write(config.server_id, original)
            peer.refuse_refresh = True
            calls = peer.calls
            connection = await mcp.connect(McpParams(), config.server_id)
            with pytest.raises(AgentError, match="刷新被拒绝"):
                await connection.call("tools/call", {"name": "read_status", "arguments": {}})
            assert peer.calls == calls and peer.refreshes == 1

    asyncio.run(asyncio.wait_for(scenario(), 30))
