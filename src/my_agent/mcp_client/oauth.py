"""MCP OAuth 独立登录与共享令牌；工具请求不自动重放。

Separate MCP OAuth login and shared tokens without replaying tool requests.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urlencode, urlsplit, urlunsplit

import httpx2
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthMetadata,
    OAuthToken,
)
from mcp_types import LATEST_PROTOCOL_VERSION
from pydantic import AnyUrl, Field, SecretStr, ValidationError

from my_agent import __version__
from my_agent.errors import AgentError
from my_agent.mcp_client.credentials import McpCredentials, environment_value
from my_agent.mcp_client.errors import public_error
from my_agent.mcp_client.oauth_callback import OAuthCallback
from my_agent.mcp_client.types import McpOAuthConfig, McpOAuthView, McpServer
from my_agent.models.types import ModelData
from my_agent.worker import BusinessWorker


class _SdkLogFilter(logging.Filter):
    """SDK 异常可能包含授权码或令牌正文，只保留事件类别。

    SDK exceptions may contain codes or token bodies; retain the event category only.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """仅脱敏 OAuth SDK 日志，业务错误由公开状态提供。

        Sanitize OAuth SDK logs; public state carries actionable failures."""
        record.msg, record.args = "MCP OAuth SDK event (%s)", (record.levelname,)
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


for _logger in ("mcp.client.auth.oauth2", "mcp.client.auth.utils"):
    logging.getLogger(_logger).addFilter(_SdkLogFilter())


def _check_url(url: str) -> None:
    """OAuth 凭据仅经 HTTPS 或本机回环传输。

    Send OAuth credentials over HTTPS or loopback only."""
    parsed = urlsplit(url)
    if (
        parsed.username
        or parsed.password
        or not (
            parsed.scheme == "https"
            or (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"})
        )
    ):
        raise AgentError("MCP_OAUTH_URL", "OAuth 地址需要 HTTPS；本机回调 / 本地测试可用 HTTP。")


class OAuthRecord(ModelData):
    """整个记录加密保存；绝对到期时间不会随重启延后。

    Encrypt the whole record; absolute expiry does not restart with the app.
    """

    server_url: str
    config: McpOAuthConfig
    client: OAuthClientInformationFull = Field(repr=False)
    tokens: OAuthToken = Field(repr=False)
    metadata: OAuthMetadata
    resource: str
    expires_at: float | None = None


class _LoginStorage:
    """SDK 本次登录的内存存储，成功后才替换已有凭据。

    Stage SDK login state in memory; replace saved credentials only on success.
    """

    def __init__(self, client: OAuthClientInformationFull | None) -> None:
        """可接收显式登记身份，不复用旧动态登记的回调端口。

        Accept a provisioned identity without reusing stale dynamic callback ports."""
        self.client = client
        self.tokens: OAuthToken | None = None

    async def get_tokens(self) -> OAuthToken | None:
        """新登录不带旧访问令牌。

        Start a new login without the previous access token."""
        return None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        """暂存换取的令牌。

        Stage exchanged tokens."""
        self.tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        """提供客户端登记身份。

        Supply the registered client identity."""
        return self.client

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        """暂存服务返回的登记，不向前端暴露秘密。

        Stage registration without exposing client secrets to the UI."""
        self.client = client_info


@dataclass
class _Login:
    """一个服务身份同一时刻只有一项登录作业。

    Own at most one interactive login per service identity."""

    server: McpServer
    view: McpOAuthView
    task: asyncio.Task[None] | None = None


class OAuthBearerAuth(httpx2.Auth):
    """正常工具只发送一次，刷新发生在发送之前。

    Send normal tool requests once, refreshing only before dispatch.
    """

    def __init__(self, manager: McpOAuth, server: McpServer) -> None:
        """复用服务令牌管理器与连接配置快照。

        Reuse the token manager with the connection's configuration snapshot."""
        self.manager, self.server = manager, server
        self.error: AgentError | None = None

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        """注入当前令牌；401 / 403 原样交回 MCP 错误处理。

        Inject the token and leave 401/403 to normal MCP error handling."""
        self.error = None
        try:
            token = await self.manager.access_token(self.server)
        except Exception as exc:
            self.error = public_error(exc, connecting=False)
            raise self.error from exc
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


class McpOAuth:
    """独立授权作业、加密记录和跨会话串行刷新。

    Manage login jobs, encrypted records and serialized refresh across sessions.
    """

    def __init__(self, credentials: McpCredentials, worker: BusinessWorker) -> None:
        """不主动联网、不读取其他应用的凭据。

        Do not connect eagerly or import other applications' credentials."""
        self.credentials, self.worker = credentials, worker
        self.logins: dict[str, _Login] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    def lock(self, identity: str) -> asyncio.Lock:
        """同服务的并发请求共享刷新互斥。

        Share a refresh lock for requests using the same service."""
        return self.locks.setdefault(identity, asyncio.Lock())

    def view(self, server: McpServer) -> McpOAuthView:
        """目录只读内存 / 文件存在性，不解密或联网。

        Read in-memory state/file presence without decrypting or connecting."""
        login = self.logins.get(server.server_id)
        if login:
            return login.view.model_copy(deep=True)
        return McpOAuthView(
            status="stored"
            if self.credentials.path(server.server_id).is_file()
            else "not_logged_in"
        )

    async def start(self, server: McpServer) -> asyncio.Task[None]:
        """只响应明确登录操作，后台等待不占用短 RPC。

        Start only on explicit login, waiting outside the short RPC deadline."""
        await self.cancel(server.server_id)
        login = _Login(server, McpOAuthView(status="discovering"))
        self.logins[server.server_id] = login
        login.task = asyncio.create_task(self._login(login))
        return login.task

    async def _login(self, login: _Login) -> None:
        """按 SDK 授权流程获取令牌，取消保留原记录。

        Run SDK authorization; cancellation preserves the previous stored record."""
        server, view = login.server, login.view
        callback = OAuthCallback()
        try:
            _check_url(server.url)
            async with asyncio.timeout(server.auth.oauth.login_timeout_seconds):
                view.redirect_uri = await callback.start(server.auth.oauth.callback_port)
                record = await self._authorize(server, view, callback)
                async with self.lock(server.server_id):
                    await self.worker.call(self._write, server.server_id, record)
                view.status, view.expires_at = "authorized", record.expires_at
                view.scope = record.tokens.scope or ""
        except asyncio.CancelledError:
            view.status = "cancelled"
            raise
        except TimeoutError:
            view.status = "failed"
            view.error = "MCP_OAUTH_TIMEOUT: 登录等待超时，可重新登录或调整登录等待时间。"
        except Exception as exc:
            failure = public_error(exc, connecting=True)
            view.status = "failed"
            view.error = f"{failure.code}: {failure.message}"
        finally:
            view.authorization_url = ""
            await callback.close()

    async def _authorize(
        self, server: McpServer, view: McpOAuthView, callback: OAuthCallback
    ) -> OAuthRecord:
        """SDK 负责发现 / PKCE / state / issuer；仅驱动一次无业务副作用的握手。

        Let the SDK handle discovery/PKCE/state/issuer using a side-effect-free handshake.
        """
        config = server.auth.oauth
        secret = (
            await self.worker.call(environment_value, config.client_secret_env)
            if config.client_secret_env
            else None
        )
        client_info = (
            OAuthClientInformationFull(
                client_id=config.client_id,
                client_secret=secret,
                token_endpoint_auth_method=config.token_auth_method,
            )
            if config.client_id
            else None
        )
        storage = _LoginStorage(client_info)

        async def redirect(url: str) -> None:
            """将浏览器入口与作用域提供给管理界面。

            Expose a browser link and scopes to the management UI."""
            _check_url(url)
            parsed = urlsplit(url)
            query = parse_qs(parsed.query)
            callback.state = query.get("state", [""])[0]
            if config.scope.strip():
                # 显式 scope 覆盖默认请求；同步 SDK 用于省略 scope 的令牌响应。
                # Explicit scopes override defaults and inform omitted-scope token responses.
                query["scope"] = [config.scope.strip()]
                provider.context.client_metadata.scope = config.scope.strip()
                url = urlunsplit(parsed._replace(query=urlencode(query, doseq=True)))
            view.scope = query.get("scope", [""])[0]
            view.authorization_url, view.status = url, "awaiting_user"

        async def receive() -> AuthorizationCodeResult:
            """回调成功不等于登录完成，继续显示换取令牌。

            A received callback is not completed login; show the token exchange."""
            result = await callback.wait()
            view.authorization_url, view.status = "", "exchanging"
            return result

        provider = OAuthClientProvider(
            server_url=server.url,
            client_metadata=OAuthClientMetadata(
                client_name="My Coding Agent",
                redirect_uris=[AnyUrl(callback.uri)],
                token_endpoint_auth_method=config.token_auth_method,
                scope=config.scope or None,
            ),
            storage=storage,
            redirect_handler=redirect,
            callback_handler=receive,
            client_metadata_url=config.client_metadata_url or None,
        )
        probe = httpx2.Request(
            "POST",
            server.url,
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": "oauth-login",
                "method": "initialize",
                "params": {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "my-coding-agent", "version": __version__},
                },
            },
        )
        flow = provider.async_auth_flow(probe)
        try:
            request = await anext(flow)
            async with httpx2.AsyncClient(timeout=server.timeout_seconds) as http:
                while True:
                    # 换取令牌后无需重发 initialize，更不会执行任何工具。
                    # Once tokens exist, stop before replaying initialize; never execute tools.
                    if request is probe and storage.tokens:
                        break
                    _check_url(str(request.url))
                    # GitHub 等服务根据 Accept 决定令牌响应格式，SDK 读取 JSON。
                    # Providers such as GitHub negotiate token format; the SDK reads JSON.
                    request.headers.setdefault("Accept", "application/json")
                    incoming = await http.send(request, stream=True)
                    response = incoming
                    try:
                        if request is not probe:
                            await response.aread()
                        else:
                            # 匿名服务可能返回长期 SSE，授权探测只需要状态与认证头。
                            # Anonymous SSE may stay open; only headers are needed here.
                            response = httpx2.Response(
                                response.status_code,
                                headers=response.headers,
                                request=request,
                                content=b"",
                            )
                    finally:
                        await incoming.aclose()
                    try:
                        request = await flow.asend(response)
                    except StopAsyncIteration:
                        break
        finally:
            await flow.aclose()
        if not storage.tokens or not storage.client or not provider.context.oauth_metadata:
            raise AgentError(
                "MCP_OAUTH_UNSUPPORTED",
                "此地址未完成 OAuth 授权；请检查 OAuth 专用地址，或使用匿名 / API Key。",
            )
        return OAuthRecord(
            server_url=server.url,
            config=config,
            client=storage.client.model_copy(update={"client_secret": None})
            if config.client_secret_env
            else storage.client,
            tokens=storage.tokens,
            metadata=provider.context.oauth_metadata,
            resource=provider.context.get_resource_url(),
            expires_at=self._expiry(storage.tokens),
        )

    @staticmethod
    def _expiry(tokens: OAuthToken) -> float | None:
        """只使用服务返回的令牌寿命，不猜测固定到期时间。

        Use the server-reported lifetime without guessing a fixed expiry."""
        return time.time() + tokens.expires_in if tokens.expires_in is not None else None

    def _write(self, identity: str, record: OAuthRecord) -> None:
        """加密完整授权记录，普通配置无令牌。

        Encrypt the entire authorization record; normal config has no tokens."""
        self.credentials.save(identity, SecretStr(record.model_dump_json()))

    def _read(self, server: McpServer) -> OAuthRecord:
        """读取绑定同一端点与客户端的记录，不把旧授权迁给新服务。

        Read credentials bound to this endpoint/client without transferring authorization."""
        if not self.credentials.path(server.server_id).is_file():
            raise AgentError("MCP_OAUTH_LOGIN_REQUIRED", "请在 MCP 管理中登录此服务。")
        try:
            record = OAuthRecord.model_validate_json(self.credentials.read(server.server_id))
        except ValidationError as exc:
            raise AgentError(
                "MCP_OAUTH_STORAGE", "OAuth 记录无法读取，请重新登录；原文件保留。"
            ) from exc
        # 等待时间 / 回调端口不改变令牌归属；端点、客户端和 scope 才需要新授权。
        # Wait/port settings do not change token ownership; endpoint/client/scope do.
        excluded = {"login_timeout_seconds", "callback_port"}
        if record.server_url != server.url or record.config.model_dump(
            exclude=excluded
        ) != server.auth.oauth.model_dump(exclude=excluded):
            raise AgentError(
                "MCP_OAUTH_LOGIN_REQUIRED", "地址或 OAuth 身份 / 权限已修改，请重新登录。"
            )
        return record

    async def access_token(self, server: McpServer) -> str:
        """多个会话共享到期刷新；失效时要求登录，不重放工具。

        Share expiry refresh across sessions; require login on invalid credentials."""
        async with self.lock(server.server_id):
            record = await self.worker.call(self._read, server)
            if record.expires_at is not None and time.time() >= record.expires_at:
                if not record.tokens.refresh_token:
                    raise AgentError(
                        "MCP_OAUTH_LOGIN_REQUIRED", "登录已到期，请在 MCP 管理中重新登录。"
                    )
                await self._refresh(server, record)
                await self.worker.call(self._write, server.server_id, record)
            return record.tokens.access_token

    async def _refresh(self, server: McpServer, record: OAuthRecord) -> None:
        """单次标准 refresh_token 交换，保留未轮换的刷新令牌。

        Exchange refresh_token once, preserving a non-rotated refresh token."""
        url = str(record.metadata.token_endpoint)
        _check_url(url)
        data = {
            "grant_type": "refresh_token",
            "refresh_token": record.tokens.refresh_token or "",
            "client_id": record.client.client_id,
            "resource": record.resource,
        }
        secret = record.client.client_secret
        if server.auth.oauth.client_secret_env:
            secret = await self.worker.call(environment_value, server.auth.oauth.client_secret_env)
        auth = None
        method = record.client.token_endpoint_auth_method
        if method == "client_secret_post" and secret:
            data["client_secret"] = secret
        elif method == "client_secret_basic" and secret:
            auth = httpx2.BasicAuth(quote(record.client.client_id, safe=""), quote(secret, safe=""))
        async with httpx2.AsyncClient(timeout=server.timeout_seconds, auth=auth) as http:
            response = await http.post(url, data=data, headers={"Accept": "application/json"})
            if response.status_code in {400, 401, 403}:
                raise AgentError(
                    "MCP_OAUTH_LOGIN_REQUIRED", "OAuth 刷新被拒绝，请重新登录；工具未发送。"
                )
            response.raise_for_status()
            try:
                tokens = OAuthToken.model_validate_json(response.content)
            except ValidationError as exc:
                raise AgentError("MCP_OAUTH_TOKEN", "服务返回的刷新令牌响应无效。") from exc
        tokens.refresh_token = tokens.refresh_token or record.tokens.refresh_token
        if tokens.scope is None:
            tokens.scope = record.tokens.scope
        record.tokens, record.expires_at = tokens, self._expiry(tokens)

    async def cancel(self, identity: str) -> None:
        """取消当前登录，保留已有加密记录。

        Cancel the active login while keeping existing encrypted credentials."""
        login = self.logins.get(identity)
        if login and login.task and not login.task.done():
            login.task.cancel()
            await asyncio.gather(login.task, return_exceptions=True)

    async def logout(self, identity: str) -> None:
        """只移除本机登录，不宣称已在服务商撤销授权。

        Remove local login without claiming remote grant revocation."""
        await self.cancel(identity)
        async with self.lock(identity):
            await self.worker.call(self.credentials.remove, identity)
        self.logins.pop(identity, None)

    async def close(self) -> None:
        """退出时清理临时回调，保留重启所需凭据。

        Close callbacks on exit while keeping restart credentials."""
        await asyncio.gather(*(self.cancel(identity) for identity in list(self.logins)))
