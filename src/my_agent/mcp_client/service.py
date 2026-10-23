"""连接生命周期归单个任务所有，MCP 调用不绕开现有运行语义。

Each connection has one lifecycle owner; MCP calls preserve existing run semantics.
"""

from __future__ import annotations

import asyncio
import base64
import re
import shutil
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx2
from mcp import Client
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from my_agent.errors import AgentError
from my_agent.execution.environments import inherited_environment
from my_agent.execution.windows import WindowsProcess
from my_agent.mcp_client.credentials import McpCredentials, McpSavedValues, environment_value
from my_agent.mcp_client.errors import public_error
from my_agent.mcp_client.oauth import McpOAuth, OAuthBearerAuth
from my_agent.mcp_client.presets import service_presets
from my_agent.mcp_client.types import (
    McpArtifact,
    McpArtifactParams,
    McpCatalog,
    McpConfig,
    McpControlParams,
    McpParams,
    McpServer,
    McpServerView,
    SaveMcpParams,
)
from my_agent.models.types import JsonObject
from my_agent.storage import read_document, write_document

if TYPE_CHECKING:
    from my_agent.sessions.service import SessionService


@dataclass
class Invocation:
    """一次完整协议调用和等待者。

    One protocol operation and its waiter."""

    method: str
    arguments: JsonObject
    result: asyncio.Future[JsonObject]


class Connection:
    """在同一异步任务内进入和退出 SDK 的连接作用域。

    Enter and exit the SDK connection scope in the same asyncio task.
    """

    def __init__(self, server: McpServer, owner: McpService, params: McpParams) -> None:
        """保存启动快照并延迟握手。

        Snapshot launch settings and defer negotiation."""
        self.server, self.owner, self.params = server, owner, params
        self.queue: asyncio.Queue[Invocation | None] = asyncio.Queue()
        self.ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.status, self.error = "connecting", ""
        self.tools: list[JsonObject] = []
        self.credential_changed = False
        self.http_error: AgentError | None = None
        self.oauth_auth: OAuthBearerAuth | None = None
        self.task = asyncio.create_task(self._serve())

    async def _observe_response(self, response: httpx2.Response) -> None:
        """记录 POST 失败状态，避免 SDK 转成通用 RPC 错误后丢失认证原因。

        Retain POST failure status before the SDK turns it into a generic RPC error.
        """
        if response.request.method == "POST" and response.status_code >= 400:
            try:
                response.raise_for_status()
            except httpx2.HTTPStatusError as exc:
                self.http_error = public_error(exc, connecting=self.status == "connecting")

    async def _invoke(self, client: Client, request: Invocation) -> JsonObject:
        """把 SDK 的公开响应转为工具数据。

        Convert public SDK results to tool data."""
        args = request.arguments
        if request.method == "tools/list":
            # 资源服务可以完全不提供工具，不把正常能力缺省当成连接失败。
            # Resource-only servers need no tools; absent capability is not a failed connection.
            if client.server_capabilities.tools is None:
                self.tools = []
                return {"tools": []}
            all_tools: list[JsonObject] = []
            cursor = None
            while True:
                page = await client.list_tools(cursor=cursor, cache_mode="bypass")
                all_tools.extend(tool.model_dump(mode="json", by_alias=True) for tool in page.tools)
                cursor = page.next_cursor
                if cursor is None:
                    break
            self.tools = all_tools
            return {"tools": [tool for tool in all_tools]}
        if request.method == "tools/call":
            arguments = args.get("arguments", {})
            result = await client.call_tool(
                str(args["name"]), arguments if isinstance(arguments, dict) else {}
            )
            return result.model_dump(mode="json", by_alias=True)
        if request.method == "resources/list":
            resource_cursor = args.get("cursor")
            result_resources = await client.list_resources(
                cursor=resource_cursor if isinstance(resource_cursor, str) else None
            )
            return result_resources.model_dump(mode="json", by_alias=True)
        if request.method == "resources/templates/list":
            template_cursor = args.get("cursor")
            templates = await client.list_resource_templates(
                cursor=template_cursor if isinstance(template_cursor, str) else None,
                cache_mode="bypass",
            )
            return templates.model_dump(mode="json", by_alias=True)
        resource = await client.read_resource(str(args["uri"]))
        return resource.model_dump(mode="json", by_alias=True)

    async def _serve(self) -> None:
        """串行处理连接调用；取消不自动重放操作。

        Serialize calls without replay after cancellation."""
        try:
            async with AsyncExitStack() as stack:
                if self.server.transport in {"http", "sse"}:
                    headers = await self.owner.sessions.worker.call(
                        self.owner.http_headers, self.server
                    )
                    if self.server.auth.source == "oauth":
                        self.oauth_auth = OAuthBearerAuth(self.owner.oauth, self.server)
                    if self.server.transport == "http":
                        http = await stack.enter_async_context(
                            httpx2.AsyncClient(
                                headers=headers,
                                auth=self.oauth_auth,
                                timeout=self.server.timeout_seconds,
                                event_hooks={"response": [self._observe_response]},
                            )
                        )
                        transport = streamable_http_client(self.server.url, http_client=http)
                    else:
                        transport = sse_client(
                            self.server.url,
                            headers=headers,
                            auth=self.oauth_auth,
                            timeout=self.server.timeout_seconds,
                            sse_read_timeout=self.server.timeout_seconds,
                        )
                    client = Client(
                        transport,
                        mode=self.server.protocol_mode,
                        read_timeout_seconds=self.server.timeout_seconds,
                        input_required_max_rounds=0,
                        cache=None,
                    )
                else:
                    launch = await self.owner.sessions.worker.call(
                        self.owner.launch, self.server, self.params
                    )
                    # stderr 不混入 JSONL，也不回显到模型。
                    # Keep server stderr out of JSONL and model responses.
                    client = Client(
                        launch,
                        mode=self.server.protocol_mode,
                        read_timeout_seconds=self.server.timeout_seconds,
                        input_required_max_rounds=0,
                        cache=None,
                    )
                async with client:
                    self.status = "connected"
                    self.ready.set_result(None)
                    while (request := await self.queue.get()) is not None:
                        if request.result.cancelled():
                            continue
                        self.http_error = None
                        if self.oauth_auth:
                            self.oauth_auth.error = None
                        operation = asyncio.create_task(self._invoke(client, request))

                        def cancel_operation(
                            future: asyncio.Future[JsonObject],
                            task: asyncio.Task[JsonObject] = operation,
                        ) -> None:
                            """取消等待时取消实际调用。

                            Cancel the operation with its waiter."""
                            if future.cancelled():
                                task.cancel()

                        request.result.add_done_callback(cancel_operation)
                        try:
                            async with asyncio.timeout(self.server.timeout_seconds):
                                value = await operation
                            if not request.result.done():
                                request.result.set_result(value)
                        except asyncio.CancelledError:
                            # HTTP Auth 失败会令 SDK 取消任务组；保留实际认证错误给调用者。
                            # The SDK cancels its task group on Auth failure; preserve that cause.
                            auth_error = self.oauth_auth.error if self.oauth_auth else None
                            if auth_error and not request.result.done():
                                self.error = f"{auth_error.code}: {auth_error.message}"
                                request.result.set_exception(auth_error)
                                raise
                            # 单次调用取消可保留连接；连接所有者的取消必须退出。
                            # A call may be cancelled independently; owner cancellation must exit.
                            if self.task.cancelling() or not request.result.cancelled():
                                request.result.cancel()
                                raise
                        except Exception as exc:
                            # 协议边界记录错误类别，不回显可能含凭据的异常正文。
                            # Record the exception type, not secret-bearing text.
                            failure = (self.oauth_auth.error if self.oauth_auth else None) or (
                                self.http_error or public_error(exc, connecting=False)
                            )
                            self.error = f"{failure.code}: {failure.message}"
                            if not request.result.done():
                                request.result.set_exception(failure)
        except asyncio.CancelledError:
            auth_error = self.oauth_auth.error if self.oauth_auth else None
            if auth_error and not self.ready.done():
                self.error = f"{auth_error.code}: {auth_error.message}"
                self.ready.set_exception(auth_error)
            raise
        except Exception as exc:
            failure = (self.oauth_auth.error if self.oauth_auth else None) or (
                self.http_error or public_error(exc, connecting=True)
            )
            self.error = f"{failure.code}: {failure.message}"
            if not self.ready.done():
                self.ready.set_exception(failure)
        finally:
            self.status = "failed" if self.error else "closed"
            if not self.ready.done():
                self.ready.cancel()
            while not self.queue.empty():
                pending = self.queue.get_nowait()
                if pending and not pending.result.done():
                    pending.result.set_exception(
                        AgentError("MCP_CONNECTION_CLOSED", "MCP 连接已关闭。")
                    )

    async def call(self, method: str, arguments: JsonObject) -> JsonObject:
        """调用者取消会传递给真实操作。

        Propagate caller cancellation to the actual operation."""
        await asyncio.shield(self.ready)
        if self.task.done():
            raise AgentError("MCP_CONNECTION_CLOSED", self.error or "连接已关闭，请重新连接。")
        result: asyncio.Future[JsonObject] = asyncio.get_running_loop().create_future()
        await self.queue.put(Invocation(method, arguments, result))
        return await result

    async def close(self) -> None:
        """结束宿主连接及其子进程。

        Close the owned connection and subprocess."""
        if not self.task.cancelling():
            self.task.cancel()
        # 连续点击控制不应再次打断 SDK 正在进行的资源清理。
        # Repeated controls must not interrupt SDK cleanup already in progress.
        await asyncio.shield(asyncio.gather(self.task, return_exceptions=True))


class McpService:
    """管理连接、工具选择与浏览器产物。

    Manage connections, tool selection and browser artifacts."""

    def __init__(self, sessions: SessionService) -> None:
        """初始化内存目录，不启动任何服务器。

        Initialize catalogs without launching servers."""
        self.sessions = sessions
        self.root = sessions.store.storage.root
        self.path = self.root / "mcp.json"
        self.credentials = McpCredentials(self.root)
        self.saved_values = McpSavedValues(self.root)
        self.oauth = McpOAuth(
            McpCredentials(self.root, directory_name="mcp-oauth"), sessions.worker
        )
        self.connections: dict[tuple[str, str, str], Connection] = {}
        self.selected: dict[str, dict[str, tuple[str, JsonObject]]] = {}
        self.transports: dict[str, str] = {}
        self.controls: dict[tuple[str, str, str], tuple[str, asyncio.Task[None]]] = {}
        self.control_errors: dict[tuple[str, str, str], str] = {}
        self.install_task: asyncio.Task[None] | None = None
        self.install_error = ""

    def config(self) -> McpConfig:
        """只有缺失配置使用默认浏览器条目。

        Default only a missing configuration."""
        config = (
            read_document(self.path, McpConfig)
            if self.path.exists()
            else McpConfig(
                servers=[
                    McpServer(
                        server_id="browser",
                        name="临时浏览器",
                        transport="browser",
                        description="Open and operate web pages in a temporary visible browser.",
                    )
                ]
            )
        )
        # 目录读取更新展示快照，关闭连接后也能过滤不兼容定义；实际调用仍读取当前配置。
        # Refresh display metadata even without connections; execution still reads current config.
        self.transports = {server.server_id: server.transport for server in config.servers}
        return config

    @staticmethod
    def references(refs: dict[str, str]) -> dict[str, str]:
        """只解析明确指定的环境凭据。

        Resolve explicitly named environment references only."""
        return {target: environment_value(name) for target, name in refs.items()}

    def http_headers(self, server: McpServer) -> dict[str, str]:
        """按显式来源组装认证头，旧引用保持原值语义。

        Assemble auth headers while preserving legacy reference values verbatim.
        """
        headers = httpx2.Headers(server.headers)
        headers.update(self.saved_values.values(server, "headers"))
        auth = server.auth
        refs = {
            name: value
            for name, value in server.header_refs.items()
            if not (auth.source == "oauth" and name.lower() == "authorization")
        }
        headers.update(self.references(refs))
        if auth.source == "oauth":
            # OAuth 令牌由专用 Auth 注入，不能把旧 Authorization 配置带去授权握手。
            # Dedicated OAuth Auth supplies tokens, never a stale Authorization header.
            headers.pop("Authorization", None)
        elif auth.source != "none":
            token = (
                environment_value(auth.env_var)
                if auth.source == "environment"
                else self.credentials.read(server.server_id)
            )
            headers[auth.header] = f"{auth.prefix} {token}" if auth.prefix else token
        return dict(headers)

    def credential_state(
        self, server: McpServer
    ) -> tuple[Literal["not_required", "configured", "missing", "unavailable"], str]:
        """只显示配置是否存在；认证是否有效由真实连接决定。

        Report credential presence; only a real connection can validate authentication.
        """
        try:
            self.saved_values.values(server, "env")
            self.saved_values.values(server, "headers")
            if server.transport in {"http", "sse"} and server.auth.source == "oauth":
                if self.oauth.credentials.path(server.server_id).is_file():
                    return "configured", "已保存 OAuth 登录；连接时检查到期并按需刷新。"
                return "missing", "尚未登录，请点击“登录授权”。"
            references = (
                server.header_refs if server.transport in {"http", "sse"} else server.env_refs
            )
            self.references(references)
            if server.transport in {"http", "sse"} and server.auth.source == "environment":
                environment_value(server.auth.env_var)
                return "configured", f"已找到环境变量 {server.auth.env_var}；认证待连接确认。"
            if server.transport in {"http", "sse"} and server.auth.source == "saved":
                if self.credentials.path(server.server_id).is_file():
                    return "configured", "已加密保存令牌；认证待连接确认。"
                return "missing", "尚未保存令牌，可编辑连接配置。"
            if server.stored_env or server.stored_headers:
                return "configured", "已加密保存连接变量；实际可用性待连接确认。"
            if references:
                return "configured", "已找到所引用的环境变量；认证待连接确认。"
            return "not_required", "未配置认证；是否允许匿名访问以服务响应为准。"
        except AgentError as exc:
            return (
                "missing" if exc.code == "MCP_CREDENTIAL_MISSING" else "unavailable",
                exc.message,
            )

    def key(self, params: McpParams, server_id: str) -> tuple[str, str, str]:
        """每个项目 / 会话拥有独立连接。

        Scope connections to project and session."""
        return params.project_id or "global", params.session_id or "settings", server_id

    def artifacts_dir(self, params: McpParams) -> Path:
        """产物归应用数据根，不写目标项目。

        Store artifacts in app data, not project files."""
        if self.sessions.skills is None:
            raise AgentError("MCP_UNAVAILABLE", "项目资源服务不可用。")
        if params.project_id:
            self.sessions.skills.project_root(params.project_id)
        return (
            self.root
            / "browser-artifacts"
            / (params.project_id or "global")
            / (params.session_id or "settings")
        )

    def catalog(self, params: McpParams) -> McpCatalog:
        """只读实际状态，目录查询不连接网络。

        Read status without network activity."""
        try:
            servers = self.config().servers
        except AgentError as exc:
            return McpCatalog(
                servers=[],
                presets=service_presets(),
                issues=[f"MCP 配置不可用：{exc.code}；原文件保留。"],
            )
        views = []
        sandboxed = bool(
            params.project_id
            and self.sessions.read_roots
            and self.sessions.read_roots(params.project_id) is not None
        )
        for server in servers:
            key = self.key(params, server.server_id)
            connection = self.connections.get(key)
            control = self.controls.get(key)
            status = connection.status if connection else "not_connected"
            if control and not control[1].done():
                status = control[0]
            issue = self.control_errors.get(key, connection.error if connection else "")
            unsupported = sandboxed and server.transport == "stdio"
            if unsupported:
                status = "unsupported_execution_mode"
                issue = self.stdio_sandbox_message()
            credential_status, credential_message = self.credential_state(server)
            presentation = {
                "name",
                "description",
                "enabled",
                "project_ids",
                "all_projects",
                "preset_id",
            }
            changed = bool(
                connection
                and connection.status == "connected"
                and (
                    connection.credential_changed
                    or connection.server.model_dump(exclude=presentation)
                    != server.model_dump(exclude=presentation)
                )
            )
            views.append(
                McpServerView(
                    server=server,
                    status="failed" if issue and not control and not unsupported else status,
                    error=issue,
                    tools=connection.tools if connection else [],
                    credential_status=credential_status,
                    credential_message=credential_message,
                    needs_reconnect=changed,
                    oauth=self.oauth.view(server)
                    if server.transport in {"http", "sse"} and server.auth.source == "oauth"
                    else None,
                )
            )
        directory = self.artifacts_dir(params)
        artifacts = sorted(
            p.name
            for p in directory.glob("*")
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        )
        return McpCatalog(
            servers=views,
            artifacts=artifacts,
            installing_browser=bool(self.install_task and not self.install_task.done()),
            install_error=self.install_error,
            presets=service_presets(),
        )

    def _save_config(self, params: SaveMcpParams) -> None:
        """保存配置；已有连接继续使用启动快照。

        Save configuration without replacing live snapshots."""
        config = self.config()
        # 凭据文件与配置分别原子保存，不宣称跨文件事务。
        # Credential and config files are atomic individually, not a cross-file transaction.
        if params.credential_value is not None:
            self.credentials.save(params.server.server_id, params.credential_value)
        elif params.clear_credential:
            self.credentials.remove(params.server.server_id)
        self.saved_values.save(params.server, params.connection_values)
        config.servers = [s for s in config.servers if s.server_id != params.server.server_id]
        config.servers.append(params.server)
        write_document(self.path, config)

    async def save(self, params: SaveMcpParams) -> McpCatalog:
        """保存后撤下停用或越出项目范围的连接与工具。

        Remove disabled/out-of-scope connections and schemas after persisting settings.
        """
        pending = self.oauth.logins.get(params.server.server_id)
        if pending and (
            pending.server.url != params.server.url
            or pending.server.auth != params.server.auth
            or not params.server.enabled
        ):
            await self.oauth.cancel(params.server.server_id)
            self.oauth.logins.pop(params.server.server_id, None)
        await self.sessions.worker.call(self._save_config, params)
        server = params.server
        if (
            params.credential_value is not None
            or params.clear_credential
            or params.connection_values is not None
        ):
            for key, connection in self.connections.items():
                if key[2] == server.server_id:
                    connection.credential_changed = True
        for project, session, identity in list(self.connections.keys() | self.controls.keys()):
            if identity == server.server_id and (
                not server.enabled
                or (
                    session != "settings"
                    and (server.project_ids or not server.all_projects)
                    and project not in server.project_ids
                )
            ):
                self._schedule_control(
                    McpControlParams(
                        project_id=None if project == "global" else project,
                        session_id=None if session == "settings" else session,
                        server_id=identity,
                        action="close",
                    )
                )
        if not server.enabled:
            self._forget_tools(server.server_id)
        return await self.sessions.worker.call(self.catalog, params)

    def _forget_tools(self, server_id: str, session_id: str | None = None) -> None:
        """移除引用，不修改既有调用事实。

        Remove selected schemas while preserving past call facts.
        """
        for session, selected in self.selected.items():
            if session_id is None or session == session_id:
                self.selected[session] = {
                    name: binding for name, binding in selected.items() if binding[0] != server_id
                }

    def server(self, params: McpParams, identity: str) -> McpServer:
        """解析当前项目启用的服务。

        Resolve a server enabled for this project."""
        server = next((s for s in self.config().servers if s.server_id == identity), None)
        if (
            server is None
            or not server.enabled
            or (
                params.session_id is not None
                and (server.project_ids or not server.all_projects)
                and params.project_id not in server.project_ids
            )
        ):
            raise AgentError("INVALID_TOOL_ARGUMENTS", "服务未启用或不适用于当前项目。")
        return server

    def launch(self, server: McpServer, params: McpParams) -> StdioServerParameters:
        """继承正常工具环境并显式加入服务所需引用。

        Inherit tool environment plus explicit references."""
        env = inherited_environment()
        env.update(self.saved_values.values(server, "env"))
        env.update(self.references(server.env_refs))
        command, arguments = server.command, list(server.arguments)
        if self.sessions.skills is None:
            raise AgentError("MCP_UNAVAILABLE", "项目资源服务不可用。")
        cwd = (
            self.sessions.skills.project_root(params.project_id) if params.project_id else self.root
        )
        if server.cwd:
            configured_cwd = Path(server.cwd.replace("${workspaceFolder}", str(cwd)))
            cwd = configured_cwd if configured_cwd.is_absolute() else cwd / configured_cwd
        if server.transport == "browser":
            package = (
                Path(__file__).resolve().parents[3]
                / "apps"
                / "desktop"
                / "node_modules"
                / "@playwright"
                / "mcp"
                / "cli.js"
            )
            command = server.command or shutil.which("node") or ""
            if not package.is_file() or not command:
                raise AgentError(
                    "BROWSER_UNAVAILABLE", "请安装锁定的 Playwright MCP 依赖并指定 Node。"
                )
            directory = self.artifacts_dir(params)
            directory.mkdir(parents=True, exist_ok=True)
            cwd = directory
            env["PLAYWRIGHT_BROWSERS_PATH"] = str(self.root / "browser-runtime")
            arguments = [
                str(package),
                "--isolated",
                "--browser",
                "chromium",
                "--output-dir",
                str(directory),
                "--image-responses",
                "omit",
                "--file-paths",
                "absolute",
            ]
            if server.browser_executable:
                arguments += ["--executable-path", server.browser_executable]
        if not command:
            raise AgentError("MCP_UNAVAILABLE", "请指定服务程序。")
        return StdioServerParameters(command=command, args=arguments, env=env, cwd=str(cwd))

    @staticmethod
    def stdio_sandbox_message() -> str:
        """目录与调用共用可行动说明，不建议为可选服务关闭沙箱。

        Share actionable catalog/call guidance without suggesting disabling the sandbox.
        """
        return (
            "普通本地 MCP 尚未接入项目沙箱，未派发调用。"
            "可继续用文件工具、沙箱命令，或已配置的浏览器／远端 MCP；无需额外授权。"
        )

    async def connect(
        self, params: McpParams, identity: str, *, refresh_closed: bool = False
    ) -> Connection:
        """复用相同会话连接；只读发现可恢复已关闭连接，不重放之前的工具。

        Reuse a connection; discovery may restore a closed one without replaying prior tools.
        """
        server = await self.sessions.worker.call(self.server, params, identity)
        if server.transport == "stdio" and params.project_id and self.sessions.read_roots:
            roots = await self.sessions.worker.call(self.sessions.read_roots, params.project_id)
            if roots is not None:
                raise AgentError(
                    "SANDBOX_ENTRY_UNAVAILABLE",
                    self.stdio_sandbox_message(),
                )
        key = self.key(params, identity)
        connection = self.connections.get(key)
        if connection and connection.task.done() and refresh_closed:
            self.connections.pop(key, None)
            connection = None
        if connection is None:
            connection = Connection(server, self, params)
            self.connections[key] = connection
        await asyncio.shield(connection.ready)
        return connection

    async def control(self, params: McpControlParams) -> McpCatalog:
        """用户显式连接、关闭、移除或安装浏览器。

        Explicit connection and browser actions."""
        if params.action == "remove":
            config = await self.sessions.worker.call(self.config)
            existing = next((s for s in config.servers if s.server_id == params.server_id), None)
            if existing:
                await self.oauth.cancel(existing.server_id)
                # 先关闭使用令牌的连接，再删除记录，避免在途刷新重新写回。
                # Close token users before deletion so in-flight refresh cannot recreate records.
                await self._close_server_connections(existing.server_id)
                await self.oauth.logout(existing.server_id)
                await self.sessions.worker.call(self.credentials.remove, existing.server_id)
                await self.sessions.worker.call(
                    self.saved_values.credentials.remove, existing.server_id
                )
            config.servers = [s for s in config.servers if s.server_id != params.server_id]
            await self.sessions.worker.call(write_document, self.path, config)
            self._forget_tools(params.server_id)
            for project, session, identity in list(self.connections.keys() | self.controls.keys()):
                if identity == params.server_id:
                    self._schedule_control(
                        McpControlParams(
                            project_id=None if project == "global" else project,
                            session_id=None if session == "settings" else session,
                            server_id=identity,
                            action="close",
                        )
                    )
        elif params.action == "install_browser":
            if not self.install_task or self.install_task.done():
                self.install_error = ""
                self.install_task = asyncio.create_task(self._install_browser_job(params))
        elif params.action == "oauth_cancel":
            pending = [
                task
                for key, (status, task) in self.controls.items()
                if key[2] == params.server_id and status == "authenticating"
            ]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await self.oauth.cancel(params.server_id)
        else:
            self._schedule_control(params)
        return await self.sessions.worker.call(self.catalog, params)

    def _schedule_control(self, params: McpControlParams) -> None:
        """网络操作异步执行，普通 RPC 不等待握手或子进程退出。

        Keep network and process shutdown outside the short desktop RPC deadline.
        """
        key = self.key(params, params.server_id)
        previous = self.controls.get(key)
        if previous and not previous[1].done():
            if params.action == "refresh":
                return
            previous[1].cancel()
        self.control_errors.pop(key, None)
        if params.action != "refresh":
            self._forget_tools(params.server_id, params.session_id or "settings")
        status = {
            "connect": "connecting",
            "refresh": "refreshing",
            "close": "closing",
            "oauth_login": "authenticating",
            "oauth_logout": "closing",
        }
        task = asyncio.create_task(self._control_job(params, previous[1] if previous else None))
        self.controls[key] = status[params.action], task

    async def _close_server_connections(self, identity: str) -> None:
        """退出登录关闭此服务全部会话连接，避开当前控制任务。

        Logout closes all service connections without cancelling its own control task.
        """
        tasks = [
            task
            for key, (_, task) in self.controls.items()
            if key[2] == identity and task is not asyncio.current_task()
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for key, connection in list(self.connections.items()):
            if key[2] == identity:
                await connection.close()
                self.connections.pop(key, None)
                self.control_errors.pop(key, None)

    async def _control_job(
        self, params: McpControlParams, previous: asyncio.Task[None] | None
    ) -> None:
        """显式操作仅运行一次，错误留在服务状态中。

        Run an explicit operation once and retain its error in server status.
        """
        key = self.key(params, params.server_id)
        try:
            if previous:
                await asyncio.gather(previous, return_exceptions=True)
            if params.action in {"oauth_login", "oauth_logout"}:
                config = await self.sessions.worker.call(self.config)
                auth_server = next(
                    (s for s in config.servers if s.server_id == params.server_id), None
                )
                if auth_server is None:
                    raise AgentError("MCP_UNAVAILABLE", "此服务已移除。")
                if params.action == "oauth_logout":
                    await self.oauth.cancel(auth_server.server_id)
                    await self._close_server_connections(auth_server.server_id)
                    await self.oauth.logout(auth_server.server_id)
                    self._forget_tools(auth_server.server_id)
                    return
                if (
                    auth_server.transport not in {"http", "sse"}
                    or auth_server.auth.source != "oauth"
                ):
                    raise AgentError(
                        "MCP_OAUTH_UNAVAILABLE", "请先把远程服务的认证方式设为 OAuth。"
                    )
                await (await self.oauth.start(auth_server))
                oauth_view = self.oauth.view(auth_server)
                if oauth_view.status != "authorized":
                    if oauth_view.error:
                        self.control_errors[key] = oauth_view.error
                    return
                # 登录成功仅做本次所选连接的握手与目录检查，不调用业务工具。
                # Successful login checks this connection and catalog without business tool calls.
                if not auth_server.enabled:
                    return
                current = self.controls.get(key)
                if current:
                    self.controls[key] = "connecting", current[1]
                params = params.model_copy(update={"action": "connect"})
            if params.action in {"close", "connect"}:
                if connection := self.connections.get(key):
                    await connection.close()
                    self.connections.pop(key, None)
            if params.action in {"connect", "refresh"}:
                connection = await self.connect(params, params.server_id)
                await connection.call("tools/list", {})
                # 已选择工具刷新为服务当前定义；消失的工具不再发送。
                # Refresh selected schemas and drop tools removed by the server.
                selected = self.selected.get(params.session_id or "settings", {})
                latest = {str(tool["name"]): tool for tool in connection.tools}
                for name, (server, tool) in list(selected.items()):
                    if server == params.server_id:
                        if str(tool["name"]) in latest:
                            selected[name] = server, latest[str(tool["name"])]
                        else:
                            del selected[name]
        except AgentError as exc:
            self.control_errors[key] = exc.message
        except (OSError, ValueError) as exc:
            self.control_errors[key] = f"MCP 操作失败：{type(exc).__name__}；未自动重试。"
        finally:
            current = self.controls.get(key)
            if current and current[1] is asyncio.current_task():
                self.controls.pop(key, None)

    async def _install_browser_job(self, params: McpParams) -> None:
        """长安装作业单独运行，状态查询不会被 RPC 超时切断。

        Run installation separately so RPC deadlines do not misreport installation status.
        """
        try:
            await self.install_browser(params)
        except AgentError as exc:
            self.install_error = exc.message
        except (OSError, ValueError) as exc:
            self.install_error = f"浏览器安装失败：{type(exc).__name__}。"

    async def install_browser(self, params: McpParams) -> McpCatalog:
        """使用已锁定的 Playwright 安装器，输出保存到应用目录。

        Use the locked Playwright installer and save its output under app data.
        """
        package = (
            Path(__file__).resolve().parents[3]
            / "apps"
            / "desktop"
            / "node_modules"
            / "@playwright"
            / "mcp"
            / "cli.js"
        )
        node = shutil.which("node")
        if not node or not package.is_file():
            raise AgentError("BROWSER_UNAVAILABLE", "请先安装仓库锁定依赖并配置 Node。")
        env = inherited_environment()
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(self.root / "browser-runtime")
        log = self.root / "browser-install.log"
        with log.open("wb") as output:
            process = await self.sessions.worker.call(
                WindowsProcess,
                [node, str(package), "install-browser", "chromium", "--no-shell"],
                self.root,
                env,
                1024 * 1024,
            )
            try:
                while (code := process.poll()) is None:
                    chunks, _ = process.drain()
                    for _, data in chunks:
                        output.write(data)
                    await asyncio.sleep(0.1)
            finally:
                await self.sessions.worker.call(process.finish, 5)
                chunks, _ = process.drain()
                for _, data in chunks:
                    output.write(data)
        if code:
            raise AgentError(
                "BROWSER_INSTALL_FAILED", "浏览器安装失败，详情在数据目录 browser-install.log。"
            )
        return await self.sessions.worker.call(self.catalog, params)

    def select_tools(
        self, session_id: str, server_id: str, tools: list[JsonObject]
    ) -> list[JsonObject]:
        """稳定工具身份保留原名，按需加入当前会话目录。

        Preserve original names behind stable identities in the selected session catalog.
        """
        selected = self.selected.setdefault(session_id, {})
        result: list[JsonObject] = []
        for tool in tools:
            name = str(tool["name"])
            identity = "mcp_" + uuid5(NAMESPACE_URL, server_id + ":" + name).hex
            selected[identity] = server_id, tool
            result.append(
                {
                    "name": identity,
                    "original_name": name,
                    "description": tool.get("description", ""),
                }
            )
        return result

    def artifact(self, params: McpArtifactParams) -> McpArtifact:
        """只读取本会话图片，不支持任意本地路径。

        Read owned session images, never arbitrary paths."""
        root = self.artifacts_dir(params).resolve()
        path = (root / params.artifact_id).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() not in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        }:
            raise AgentError("ARTIFACT_UNAVAILABLE", "图片不属于该会话。")
        try:
            with path.open("rb") as stream:
                stream.seek(params.offset)
                data = stream.read(48000)
            end = params.offset + len(data)
            return McpArtifact(
                mime_type="image/" + ({".jpg": "jpeg"}.get(path.suffix, path.suffix[1:])),
                data=base64.b64encode(data).decode("ascii"),
                next_offset=end if end < path.stat().st_size else None,
            )
        except OSError as exc:
            raise AgentError("ARTIFACT_UNAVAILABLE", "图片不存在或无法读取。") from exc

    async def normalize(self, params: McpParams, value: JsonObject) -> JsonObject:
        """图片外置，文本与结构化结果保留。

        Externalize images, preserving text and structured data."""
        content = value.get("content")
        if not isinstance(content, list):
            return value
        images: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_value = item.get("text")
                if isinstance(text_value, str):
                    directory = self.artifacts_dir(params).resolve()
                    for match in re.finditer(
                        r"\[[^\]\r\n]+\]\(([^\r\n]+\.(?:png|jpe?g|webp))\)",
                        text_value,
                        re.IGNORECASE,
                    ):
                        path = Path(match.group(1))
                        path = (path if path.is_absolute() else directory / path).resolve()
                        if path.is_relative_to(directory):
                            images.append(path.relative_to(directory).as_posix())
                    snapshot = re.search(r"\[Snapshot\]\(([^\r\n]+\.ya?ml)\)", text_value)
                    if snapshot:
                        directory = self.artifacts_dir(params).resolve()
                        path = Path(snapshot.group(1))
                        path = (path if path.is_absolute() else directory / path).resolve()
                        if path.is_relative_to(directory):
                            # 上游返回的快照属于工具结果；与结果一起归档和缩短。
                            # Archive and shorten upstream snapshots with ordinary tool output.
                            try:
                                body = await self.sessions.worker.call(path.read_text, "utf-8")
                                item["text"] = text_value + "\nPage snapshot:\n" + body
                            except (OSError, UnicodeError) as exc:
                                item["text"] = (
                                    text_value + f"\nSnapshot unreadable: {type(exc).__name__}"
                                )
            if (
                isinstance(item, dict)
                and item.get("type") == "image"
                and isinstance(item.get("data"), str)
            ):
                directory = self.artifacts_dir(params)
                directory.mkdir(parents=True, exist_ok=True)
                suffix = {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(
                    str(item.get("mimeType")), ".png"
                )
                identity = str(uuid4()) + suffix
                image_data = item.get("data")
                if not isinstance(image_data, str):
                    continue
                await self.sessions.worker.call(
                    (directory / identity).write_bytes, base64.b64decode(image_data)
                )
                item.clear()
                item.update({"type": "text", "text": "Image artifact: " + identity})
                images.append(identity)
        if images:
            value["mcp_artifacts"] = list(dict.fromkeys(images))
            value["image_inputs"] = [
                {
                    "artifact_id": identity,
                    "read_tool": "view_image",
                    "read_arguments": {
                        "path": str((self.artifacts_dir(params) / identity).resolve()),
                        "purpose": "Inspect the browser screenshot",
                    },
                    "note": "Saved only; call view_image to send original pixels to the model.",
                }
                for identity in dict.fromkeys(images)
            ]
        return value

    async def close(self) -> None:
        """关闭全部连接；不在下次启动重放。

        Close connections without replay on restart."""
        await self.oauth.close()
        tasks = [task for _, task in self.controls.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.controls.clear()
        await asyncio.gather(*(connection.close() for connection in self.connections.values()))
        self.connections.clear()
        if self.install_task and not self.install_task.done():
            self.install_task.cancel()
            await asyncio.gather(self.install_task, return_exceptions=True)
