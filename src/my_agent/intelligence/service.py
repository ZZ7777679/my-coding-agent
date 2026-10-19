"""共享 stdio LSP，缺失只影响代码理解。

Shared stdio LSP; absence affects intelligence only.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlsplit

from pydantic import JsonValue

from my_agent.errors import AgentError
from my_agent.execution.environments import EnvironmentStore, execution_environment
from my_agent.intelligence.types import (
    IntelligenceParams,
    LanguageConfiguration,
    LanguageDocumentSnapshot,
    LanguageQuery,
    LanguageResult,
    LanguageServer,
    LanguageServerCatalog,
    LanguageServerState,
    SaveLanguageServers,
)
from my_agent.models.types import JsonObject
from my_agent.storage import Storage, read_document, utc_now, write_document
from my_agent.worker import BusinessWorker


class LspConnection:
    """持有一个项目服务的请求、文档版本和通知。

    Own requests, document versions and notifications for one project server.
    """

    def __init__(self, process: asyncio.subprocess.Process, timeout: float) -> None:
        """开始消费两条输出，避免服务阻塞。

        Drain both output streams to prevent server stalls.
        """
        self.process = process
        self.timeout = timeout
        self.pending: dict[int, asyncio.Future[JsonValue]] = {}
        self.next_id = 0
        self.documents: dict[str, int] = {}
        self.diagnostics: dict[str, JsonValue] = {}
        self.diagnostic_versions: dict[str, int | None] = {}
        self.diagnostics_changed = asyncio.Event()
        self.document_lock = asyncio.Lock()
        self.configuration: JsonObject = {}
        self.lock = asyncio.Lock()
        self.reader = asyncio.create_task(self._read())
        self.stderr = asyncio.create_task(self._drain())

    async def send(self, message: JsonObject) -> None:
        """按 Content-Length 帧写入，不使用 JSONL。

        Write Content-Length frames, not JSONL.
        """
        stream = self.process.stdin
        if stream is None or self.process.returncode is not None:
            raise AgentError("LSP_DISCONNECTED", "语言服务已退出。")
        payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
        async with self.lock:
            stream.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload)
            await stream.drain()

    async def notify(self, method: str, params: JsonObject) -> None:
        """发送无需返回的协议通知。

        Send a protocol notification without a response.
        """
        await self.send({"jsonrpc": "2.0", "method": method, "params": params})

    async def request(self, method: str, params: JsonObject) -> JsonValue:
        """请求在取消时通知服务，不留下悬空 Future。

        Notify cancellation and remove pending futures.
        """
        self.next_id += 1
        identity = self.next_id
        future: asyncio.Future[JsonValue] = asyncio.get_running_loop().create_future()
        self.pending[identity] = future
        try:
            await self.send({"jsonrpc": "2.0", "id": identity, "method": method, "params": params})
            return await asyncio.wait_for(future, self.timeout)
        except (TimeoutError, asyncio.CancelledError):
            await self.notify("$/cancelRequest", {"id": identity})
            raise
        finally:
            self.pending.pop(identity, None)

    async def _read(self) -> None:
        """读取标准帧并回应服务请求；断开使待处理请求真实失败。

        Read frames and server requests; fail pending requests on disconnect.
        """
        stdout = self.process.stdout
        if stdout is None:
            return
        try:
            while True:
                headers = await stdout.readuntil(b"\r\n\r\n")
                length = next(
                    int(line.split(b":", 1)[1])
                    for line in headers.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                )
                value: object = json.loads(await stdout.readexactly(length))
                if not isinstance(value, dict):
                    raise ValueError("LSP message must be an object")
                identity = value.get("id")
                if "method" in value:
                    method = value.get("method")
                    params = value.get("params", {})
                    if method == "textDocument/publishDiagnostics" and isinstance(params, dict):
                        uri_key = self.document_key(str(params.get("uri")))
                        self.diagnostics[uri_key] = cast(JsonValue, params.get("diagnostics", []))
                        version = params.get("version")
                        self.diagnostic_versions[uri_key] = (
                            version if isinstance(version, int) else None
                        )
                        self.diagnostics_changed.set()
                        self.diagnostics_changed = asyncio.Event()
                    if identity is not None:
                        result: JsonValue = None
                        if method == "workspace/configuration" and isinstance(params, dict):
                            result = [
                                self.configuration_section(item.get("section"))
                                if isinstance(item, dict)
                                else None
                                for item in params.get("items", [])
                            ]
                        await self.send(
                            {"jsonrpc": "2.0", "id": cast(JsonValue, identity), "result": result}
                        )
                elif isinstance(identity, int) and identity in self.pending:
                    future = self.pending[identity]
                    if not future.done():
                        if "error" in value:
                            error = value["error"]
                            code = error.get("code") if isinstance(error, dict) else None
                            future.set_exception(
                                AgentError(
                                    "LSP_METHOD_NOT_SUPPORTED"
                                    if code == -32601
                                    else "LSP_REQUEST_FAILED",
                                    "语言服务不支持此查询。"
                                    if code == -32601
                                    else "语言服务拒绝此查询，请查看服务配置与文档位置。",
                                )
                            )
                        else:
                            # JSON 解析已保证值为 JSON 类型，转换仅位于协议边界。
                            # JSON decoding guarantees JSON values; the cast stays at this boundary.
                            future.set_result(cast(JsonValue, value.get("result")))
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            ValueError,
            OSError,
            StopIteration,
        ):
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(
                        AgentError("LSP_DISCONNECTED", "语言服务连接中断或返回了无效帧。")
                    )

    def configuration_section(self, section: object) -> JsonValue:
        """按服务所请求的小节返回保存设置，不暴露进程环境。

        Return requested saved settings sections without exposing the process environment.
        """
        value: JsonValue = self.configuration
        if not isinstance(section, str) or not section:
            return value
        for part in section.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    @staticmethod
    def document_key(uri: str) -> str:
        """统一服务文件 URI 编码，保留实际平台的大小写规则。

        Normalize server file URI encoding while retaining platform case semantics.
        """
        parsed = urlsplit(uri)
        path = unquote(parsed.path)
        return os.path.normcase(path) if parsed.scheme == "file" else uri

    async def published_diagnostics(self, uri: str, version: int) -> JsonValue:
        """等待当前文档版本的实际通知，不把旧诊断当草稿结果。

        Wait for actual diagnostics for this document version rather than returning stale
        results.
        """

        uri = self.document_key(uri)

        async def wait() -> JsonValue:
            """只等待服务事件，不轮询进程或模型。

            Wait on service events without process or model polling.
            """
            while uri not in self.diagnostics or (
                self.diagnostic_versions.get(uri) is not None
                and self.diagnostic_versions[uri] != version
            ):
                event = self.diagnostics_changed
                await event.wait()
            return self.diagnostics[uri]

        return await asyncio.wait_for(wait(), self.timeout)

    async def _drain(self) -> None:
        """消费诊断输出，不把源码或环境写入通用日志。

        Drain diagnostics without logging source or environment.
        """
        if self.process.stderr is not None:
            while await self.process.stderr.read(65536):
                continue

    async def close(self) -> None:
        """先请求正常关闭，仍存活则结束自有服务。

        Request shutdown then terminate the owned server if needed.
        """
        if self.process.returncode is None:
            try:
                await asyncio.wait_for(self.request("shutdown", {}), 2)
                await self.notify("exit", {})
                await asyncio.wait_for(self.process.wait(), 2)
            except (AgentError, OSError, TimeoutError):
                if self.process.returncode is None:
                    self.process.kill()
                    await self.process.wait()
        self.reader.cancel()
        self.stderr.cancel()
        await asyncio.gather(self.reader, self.stderr, return_exceptions=True)


class IntelligenceService:
    """惰性项目语言服务，编辑器和 Agent 共用同一连接。

    Lazy project language services shared by editor and agent.
    """

    def __init__(
        self, storage: Storage, environments: EnvironmentStore, worker: BusinessWorker
    ) -> None:
        """不在构造或应用启动时启动任何服务。

        Do not launch servers during construction or application startup.
        """
        self.storage, self.environments, self.worker = storage, environments, worker
        self.path = storage.root / "language-servers.json"
        self.connections: dict[tuple[str, str], LspConnection] = {}
        self.states: dict[tuple[str, str], LanguageServerState] = {}
        self.lock = asyncio.Lock()

    def _configuration(self) -> LanguageConfiguration:
        """缺失配置采用入口相对默认，损坏保留错误。

        Use entry-relative defaults for absence, preserve corruption errors.
        """
        return (
            read_document(self.path, LanguageConfiguration)
            if self.path.exists()
            else LanguageConfiguration()
        )

    def _settings(self, project_id: str) -> SaveLanguageServers:
        """默认使用已锁定仓库资源，不猜 cwd 或安装包。

        Use locked repository resources without guessing cwd or installing packages.
        """
        saved = next(
            (p for p in self._configuration().projects if p.project_id == project_id), None
        )
        if saved is not None:
            return saved
        package = Path(__file__).resolve().parents[3] / "apps" / "desktop" / "node_modules"
        return SaveLanguageServers(
            project_id=project_id,
            servers=[
                LanguageServer(
                    server_id="pyright",
                    languages=["python"],
                    program="node",
                    arguments=[str(package / "pyright/dist/pyright-langserver.js"), "--stdio"],
                ),
                LanguageServer(
                    server_id="typescript",
                    languages=["typescript", "javascript", "typescriptreact", "javascriptreact"],
                    program="node",
                    arguments=[str(package / "typescript/bin/tsc"), "--lsp", "-stdio"],
                ),
            ],
        )

    async def catalog(self, params: IntelligenceParams) -> LanguageServerCatalog:
        """查询登记与真实状态，不启动服务。

        Read registrations and real states without starting servers.
        """
        await self.worker.call(self.environments.project_root, params.project_id)
        settings = await self.worker.call(self._settings, params.project_id)
        return LanguageServerCatalog(
            **settings.model_dump(),
            states=[
                self.states.get(
                    (params.project_id, s.server_id),
                    LanguageServerState(server_id=s.server_id, status="not_started"),
                )
                for s in settings.servers
            ],
        )

    async def configure(self, params: SaveLanguageServers) -> LanguageServerCatalog:
        """保存项目配置并关闭旧连接，新请求使用新配置。

        Save project settings and close old connections for subsequent queries.
        """
        await self.worker.call(self.environments.project_root, params.project_id)

        def save() -> None:
            """单写者原子保存，不碰项目配置。

            Atomically save through the single writer without project changes.
            """
            self.storage.require_writer()
            current = self._configuration()
            write_document(
                self.path,
                LanguageConfiguration(
                    projects=[p for p in current.projects if p.project_id != params.project_id]
                    + [params]
                ),
            )

        await self.worker.call(save)
        async with self.lock:
            for key in list(self.connections):
                if key[0] == params.project_id:
                    await self.connections.pop(key).close()
                    self.states.pop(key, None)
        return await self.catalog(IntelligenceParams(project_id=params.project_id))

    async def _connect(
        self, project_id: str, language: str
    ) -> tuple[LanguageServer, LspConnection, Path]:
        """按语言选登记并真实初始化；故障不影响其他业务。

        Select and initialize a registered server without gating other work.
        """
        settings = await self.worker.call(self._settings, project_id)
        server = next((s for s in settings.servers if s.enabled and language in s.languages), None)
        if server is None:
            raise AgentError(
                "LSP_NOT_CONFIGURED", "该语言没有启用的语言服务，请在代码理解设置中登记。"
            )
        root = await self.worker.call(self.environments.project_root, project_id)
        key = (project_id, server.server_id)
        async with self.lock:
            old = self.connections.get(key)
            if old is not None and old.process.returncode is None and not old.reader.done():
                return server, old, root
            if old is not None:
                await old.close()
            try:
                view, _, _ = await self.worker.call(self.environments.selected, project_id)
                env = execution_environment(view)
                if Path(server.program).name.lower() in {"node", "node.exe"} and server.arguments:
                    script = Path(server.arguments[0])
                    if script.is_absolute() and not script.is_file():
                        raise AgentError(
                            "LSP_NOT_INSTALLED",
                            "登记的语言服务文件不存在，请安装对应服务或修改命令。普通文件工具仍可使用。",
                        )
                process = await asyncio.create_subprocess_exec(
                    server.program,
                    *server.arguments,
                    cwd=root,
                    env=env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
                connection = LspConnection(process, settings.timeout_seconds)
                configuration = server.settings or (
                    {"python": {"pythonPath": view.interpreter}} if view.interpreter else {}
                )
                connection.configuration = configuration
                self.connections[key] = connection
                await connection.request(
                    "initialize",
                    {
                        "processId": os.getpid(),
                        "rootUri": root.as_uri(),
                        "capabilities": {
                            "textDocument": {"synchronization": {"dynamicRegistration": False}},
                            "workspace": {"configuration": True},
                        },
                        "initializationOptions": server.initialization_options,
                        "workspaceFolders": [{"uri": root.as_uri(), "name": root.name}],
                    },
                )
                await connection.notify("initialized", {})
                if configuration:
                    await connection.notify(
                        "workspace/didChangeConfiguration", {"settings": configuration}
                    )
                self.states[key] = LanguageServerState(server_id=server.server_id, status="running")
                return server, connection, root
            except asyncio.CancelledError:
                # 初始化尚未完成的连接不能留给下次查询复用；已启动进程由此处收尾。
                # Never reuse an incomplete initialization; clean up its owned process here.
                partial_connection = self.connections.pop(key, None)
                if partial_connection is not None:
                    await asyncio.shield(partial_connection.close())
                raise
            except (OSError, AgentError, TimeoutError) as exc:
                self.states[key] = LanguageServerState(
                    server_id=server.server_id,
                    status="failed",
                    message="语言服务启动或初始化失败。",
                )
                if key in self.connections:
                    await self.connections.pop(key).close()
                if isinstance(exc, FileNotFoundError) or (
                    isinstance(exc, AgentError) and exc.code == "LSP_NOT_INSTALLED"
                ):
                    raise AgentError(
                        "LSP_NOT_INSTALLED",
                        "登记的语言服务尚未安装或文件不存在，请检查命令。普通文件与聊天能力仍可使用。",
                    ) from exc
                raise AgentError(
                    "LSP_UNAVAILABLE",
                    "语言服务无法启动或初始化，请检查已登记命令。普通文件与聊天能力仍可使用。",
                ) from exc

    async def query(self, params: LanguageQuery) -> LanguageResult:
        """传递当前磁盘或草稿，查询后标明版本与来源。

        Query disk or draft text and label its version and provenance.
        """
        server, connection, root = await self._connect(params.project_id, params.language)
        # 同一连接的文本通知与查询成对串行，避免另一个草稿覆盖本次材料。
        # Serialize text notifications with their query so another draft cannot replace this input.
        async with connection.document_lock:
            try:
                return await self._query_document(params, server, connection, root)
            except TimeoutError as exc:
                raise AgentError("LSP_TIMEOUT", "语言服务查询超时，请检查服务状态。") from exc

    async def _query_document(
        self, params: LanguageQuery, server: LanguageServer, connection: LspConnection, root: Path
    ) -> LanguageResult:
        """持文档锁同步材料并取得同一版本结果。

        Synchronize material and retrieve results from that version under the document lock.
        """
        path = (root / params.path).resolve()
        if not path.is_relative_to(root):
            raise AgentError("PATH_DENIED", "语言服务文档需要位于当前项目内。")
        content = params.content
        if content is None:
            try:
                content = await self.worker.call(self._read_text, path)
            except FileNotFoundError as exc:
                raise AgentError(
                    "FILE_NOT_FOUND", "语言服务文档不存在，请修正路径后重试。"
                ) from exc
            except (OSError, UnicodeError) as exc:
                raise AgentError("FILE_UNAVAILABLE", "无法读取语言服务文档。") from exc
        uri = path.as_uri()
        if params.action == "diagnostics":
            uri_key = connection.document_key(uri)
            connection.diagnostics.pop(uri_key, None)
            connection.diagnostic_versions.pop(uri_key, None)
        version = max(params.version, connection.documents.get(uri, 0) + 1)
        if uri in connection.documents:
            await connection.notify(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": uri, "version": version},
                    "contentChanges": [{"text": content}],
                },
            )
        else:
            await connection.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": params.language,
                        "version": version,
                        "text": content,
                    }
                },
            )
        connection.documents[uri] = version
        request: JsonObject = {
            "textDocument": {"uri": uri},
            "position": {"line": params.line, "character": params.character},
        }
        if params.action in {"symbols", "diagnostics"}:
            request.pop("position")
        if params.action == "references":
            request["context"] = {"includeDeclaration": True}
        if params.action == "rename":
            if not params.new_name:
                raise AgentError("INVALID_TOOL_ARGUMENTS", "重命名需要提供 new_name。")
            request["newName"] = params.new_name
        if params.action == "diagnostics":
            try:
                result = await connection.request("textDocument/diagnostic", request)
            except AgentError as exc:
                if exc.code != "LSP_METHOD_NOT_SUPPORTED":
                    raise
                # 只在服务明确不支持 pull 时使用真实 push 结果，实际故障保持失败。
                # Use actual push results for an unsupported pull; preserve real failures.
                result = await connection.published_diagnostics(uri, version)
        else:
            method = "documentSymbol" if params.action == "symbols" else params.action
            result = await connection.request("textDocument/" + method, request)
        return LanguageResult(
            project_id=params.project_id,
            server_id=server.server_id,
            path=path.relative_to(root).as_posix(),
            action=params.action,
            source="draft" if params.content is not None else "disk",
            version=version,
            content=content,
            result=result,
            observed_at=utc_now(),
            rename_documents=await self._rename_documents(
                result, path, content, params.content is not None, version, root
            )
            if params.action == "rename"
            else [],
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        """读取 UTF-8 正文并保留原换行，供编辑基线核对。

        Read UTF-8 text while preserving line endings for editing baselines.
        """
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return stream.read()

    async def _rename_documents(
        self,
        result: JsonValue,
        current_path: Path,
        current_content: str,
        draft: bool,
        version: int,
        root: Path,
    ) -> list[LanguageDocumentSnapshot]:
        """返回每个改动目标的基线，不因一个缺失目标阻断其他建议。

        Return target baselines without blocking other suggestions for a missing target.
        """
        if not isinstance(result, dict):
            return []
        uris: list[str] = []
        changes = result.get("changes")
        if isinstance(changes, dict):
            uris.extend(changes)
        document_changes = result.get("documentChanges")
        if isinstance(document_changes, list):
            for change in document_changes:
                if isinstance(change, dict):
                    document = change.get("textDocument")
                    if isinstance(document, dict) and isinstance(document.get("uri"), str):
                        uris.append(str(document["uri"]))
        snapshots: list[LanguageDocumentSnapshot] = []
        seen: set[Path] = set()
        for uri in dict.fromkeys(uris):
            parsed = urlsplit(uri)
            decoded = unquote(parsed.path)
            if os.name == "nt" and len(decoded) > 2 and decoded[0] == "/" and decoded[2] == ":":
                decoded = decoded[1:]
            if parsed.netloc:
                decoded = "//" + parsed.netloc + "/" + decoded.lstrip("/")
            try:
                target = Path(decoded).resolve()
                if parsed.scheme != "file" or not target.is_relative_to(root):
                    snapshots.append(
                        LanguageDocumentSnapshot(
                            path=uri,
                            content=None,
                            source="disk",
                            version=None,
                            error="PATH_DENIED · 重命名目标不属于当前项目。",
                        )
                    )
                    continue
                if target in seen:
                    continue
                seen.add(target)
                relative = target.relative_to(root).as_posix()
                if target == current_path:
                    snapshots.append(
                        LanguageDocumentSnapshot(
                            path=relative,
                            content=current_content,
                            source="draft" if draft else "disk",
                            version=version,
                        )
                    )
                else:
                    try:
                        text = await self.worker.call(self._read_text, target)
                        snapshots.append(
                            LanguageDocumentSnapshot(
                                path=relative, content=text, source="disk", version=None
                            )
                        )
                    except (OSError, UnicodeError):
                        snapshots.append(
                            LanguageDocumentSnapshot(
                                path=relative,
                                content=None,
                                source="disk",
                                version=None,
                                error="FILE_UNAVAILABLE · 无法读取重命名目标，未应用该文件。",
                            )
                        )
            except (OSError, ValueError):
                snapshots.append(
                    LanguageDocumentSnapshot(
                        path=uri,
                        content=None,
                        source="disk",
                        version=None,
                        error="PATH_UNAVAILABLE · 无法解析重命名目标，未应用该文件。",
                    )
                )
        return snapshots

    async def close(self) -> None:
        """退出时清理所有自有语言服务，不恢复执行。

        Close owned servers on exit without replaying execution.
        """
        connections, self.connections = list(self.connections.values()), {}
        results = await asyncio.gather(*(c.close() for c in connections), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                logging.getLogger(__name__).warning("LSP_CLOSE_FAILED: %s", type(result).__name__)
