"""本地 OAuth / MCP 样本；只处理隔离测试的合成授权。

Local OAuth/MCP fixture accepting synthetic test authorization only.
"""

import asyncio
import base64
import hashlib
import html
import secrets
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlencode

import uvicorn
from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.types import Receive, Scope, Send


class OAuthFixture:
    """提供发现、登记、PKCE、刷新与实际工具，记录次数而非请求秘密。

    Serve discovery, registration, PKCE, refresh and tools, recording counts not secrets.
    """

    def __init__(self) -> None:
        """令牌只存在于本次隔离实例内存。

        Keep fixture tokens in this isolated instance's memory."""
        self.url = ""
        self.tokens: set[str] = set()
        self.refresh_tokens: set[str] = set()
        self.codes: dict[str, dict[str, str]] = {}
        self.registrations = 0
        self.refreshes = 0
        self.calls = 0
        self.rejected_posts = 0
        self.reject = False
        self.refuse_refresh = False
        self.expiry = 3600
        self.peer = MCPServer("OAuth fixture")

        @self.peer.tool()
        def read_status() -> str:
            """返回确定样本并计数。 Return deterministic data and count calls."""
            self.calls += 1
            return "oauth-fixture-ready"

        self.inner = self.peer.streamable_http_app()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """路由授权请求；MCP 协议由实际 SDK 服务处理。

        Route authorization requests; the real SDK serves MCP messages."""
        if scope["type"] != "http":
            await self.inner(scope, receive, send)
            return
        request = Request(scope, receive)
        route = request.url.path
        if route == "/.well-known/oauth-protected-resource":
            response = JSONResponse(
                {
                    "resource": f"{self.url}/mcp",
                    "authorization_servers": [self.url],
                    "scopes_supported": ["docs:read"],
                }
            )
        elif route == "/.well-known/oauth-authorization-server":
            response = JSONResponse(
                {
                    "issuer": self.url,
                    "authorization_endpoint": f"{self.url}/authorize",
                    "token_endpoint": f"{self.url}/token",
                    "registration_endpoint": f"{self.url}/register",
                    "response_types_supported": ["code"],
                    "code_challenge_methods_supported": ["S256"],
                    "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
                    "authorization_response_iss_parameter_supported": True,
                }
            )
        elif route == "/register":
            data = await request.json()
            self.registrations += 1
            response = JSONResponse({**data, "client_id": f"fixture-{self.registrations}"}, 201)
        elif route == "/authorize":
            link = "/approve?" + request.url.query
            response = HTMLResponse(f'<a href="{html.escape(link)}">Authorize fixture</a>')
        elif route == "/approve":
            query = dict(request.query_params)
            code = secrets.token_urlsafe(24)
            self.codes[code] = query
            response = RedirectResponse(
                query["redirect_uri"]
                + "?"
                + urlencode(
                    {
                        "code": code,
                        "state": query["state"],
                        "iss": self.url,
                    }
                )
            )
        elif route == "/token":
            if request.headers.get("accept") != "application/json":
                await JSONResponse({"error": "json_response_must_be_requested"}, 406)(
                    scope, receive, send
                )
                return
            form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
            if form.get("grant_type") == "refresh_token":
                self.refreshes += 1
                if self.refuse_refresh or form.get("refresh_token") not in self.refresh_tokens:
                    response = JSONResponse({"error": "invalid_grant"}, 400)
                else:
                    token = "fixture-access-" + secrets.token_urlsafe(20)
                    self.tokens.add(token)
                    # 故意不返回新 refresh_token，检查旧值接续。 Omit rotation to test preservation.
                    response = JSONResponse(
                        {"access_token": token, "token_type": "Bearer", "expires_in": self.expiry}
                    )
            else:
                code = self.codes.pop(form.get("code", ""), None)
                digest = hashlib.sha256(form.get("code_verifier", "").encode()).digest()
                challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
                valid = (
                    code
                    and code["code_challenge"] == challenge
                    and (
                        form.get("redirect_uri") == code["redirect_uri"]
                        and form.get("client_id") == code["client_id"]
                        and form.get("resource") == f"{self.url}/mcp"
                    )
                )
                if form.get("client_id") == "fixture-static":
                    valid = valid and form.get("client_secret") == "fixture-client-secret"
                if not valid:
                    response = JSONResponse({"error": "invalid_grant"}, 400)
                else:
                    token = "fixture-access-" + secrets.token_urlsafe(20)
                    refresh = "fixture-refresh-" + secrets.token_urlsafe(20)
                    self.tokens.add(token)
                    self.refresh_tokens.add(refresh)
                    response = JSONResponse(
                        {
                            "access_token": token,
                            "refresh_token": refresh,
                            "token_type": "Bearer",
                            "expires_in": self.expiry,
                        }
                    )
        else:
            token = request.headers.get("authorization", "").removeprefix("Bearer ")
            if self.reject or token not in self.tokens:
                if request.method == "POST":
                    self.rejected_posts += 1
                response = JSONResponse(
                    {"error": "unauthorized"},
                    401,
                    headers={
                        "WWW-Authenticate": (
                            f'Bearer resource_metadata="{self.url}'
                            '/.well-known/oauth-protected-resource", scope="docs:read"'
                        )
                    },
                )
            else:
                await self.inner(scope, receive, send)
                return
        await response(scope, receive, send)


@asynccontextmanager
async def serve_oauth() -> AsyncIterator[OAuthFixture]:
    """绑定随机回环端口并在退出时关闭真实服务。

    Bind an OS-selected loopback port and close the real server on exit."""
    fixture = OAuthFixture()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        fixture.url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(fixture, log_level="error", access_log=False))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("OAuth fixture did not start")
                await asyncio.sleep(0.01)
            yield fixture
        finally:
            server.should_exit = True
            await task


async def main() -> None:
    """桌面测试只接收服务地址，不打印合成令牌。

    Report only the service URL to desktop tests, never fixture tokens."""
    async with serve_oauth() as fixture:
        print(fixture.url, flush=True)
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
