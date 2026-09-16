"""短控制请求与长运行分离的 RPC 装配。 RPC composition separating control from long runs."""

import asyncio
from contextlib import ExitStack

from pydantic import BaseModel

from my_agent import __version__
from my_agent.bootstrap import build_model_http, build_sessions
from my_agent.config import DEFAULTS, MODEL_DEFAULTS, DataLocation, ModelConfig, load_config
from my_agent.credentials import ResolvedCredential, resolve_credential
from my_agent.diagnostics import diagnose
from my_agent.errors import AgentError
from my_agent.models.connection_probe import probe_connection
from my_agent.models.connections import (
    ConnectionProbeParams,
    ConnectionSettings,
    ConnectionStatus,
    ModelConnectionProbeParams,
)
from my_agent.models.go import GoClient
from my_agent.models.model_probe import ModelConnectionTests
from my_agent.projects import ProjectService
from my_agent.rpc.dto import (
    ActiveRunResult,
    AppInfo,
    CancelRunParams,
    CreateSessionParams,
    DiagnosticCheck,
    DiagnosticsParams,
    EmptyParams,
    GetSessionParams,
    InitializeParams,
    InitializeResult,
    ListSessionsParams,
    OpenProjectById,
    OpenProjectParams,
    SessionParams,
    StartRunParams,
    UpdateConfigParams,
)
from my_agent.sessions.projection import summarize
from my_agent.storage import Storage
from my_agent.worker import BusinessWorker


class RpcApplication:
    """拥有业务写锁与服务，控制请求按需进入业务线程。 Own the writer lock and composed services."""

    def __init__(
        self, location: DataLocation, credential: ResolvedCredential, model: str | None
    ) -> None:
        """延迟初始化文件，失败时仍能诊断。

        Defer file initialization and retain diagnostic access.
        """
        self.storage = Storage(location)
        self.projects = ProjectService(self.storage)
        self.worker = BusinessWorker()
        self.credential = credential
        self.model = model
        self.stack = ExitStack()
        self.http = build_model_http()
        self.model_tests = ModelConnectionTests(
            ModelConfig.model_validate(MODEL_DEFAULTS).allowed_models
        )
        self.sessions = build_sessions(self.storage, self.worker, credential, http=self.http)
        self.initialized = False
        self.stopping = False
        self.subscriptions: set[str] = set()
        self.diagnostic_lock = asyncio.Lock()
        self.connection_probe_lock = asyncio.Lock()
        self.connection_control_lock = asyncio.Lock()

    async def test_connection(self, timeout_seconds: float) -> ConnectionStatus:
        """互斥手动探测，不阻塞模型取消或状态读取。 Serialize probes, not run cancellation."""
        if self.connection_probe_lock.locked():
            raise AgentError("NETWORK_PROBE_BUSY", "已有连接测试正在运行，请等待结果。")
        async with self.connection_probe_lock:
            await probe_connection(self.http, timeout_seconds)
            return self.connection_status()

    def connection_status(self) -> ConnectionStatus:
        """合并共享池快照与按模型隔离的测试事实，不联网。

        Combine pool and per-model test snapshots without network access.
        """
        return self.http.status().model_copy(update={"models": self.model_tests.snapshot()})

    async def dispatch(self, method: str, params: dict[str, object]) -> BaseModel | None:
        """校验参数后执行短控制操作；模型任务另行运行。

        Validate and dispatch short control operations.
        """
        if method == "initialize":
            if (
                type(params.get("protocol_version")) is not int
                or params.get("protocol_version") != DEFAULTS["protocol_version"]
                or type(params.get("data_schema_version")) is not int
                or params.get("data_schema_version") != DEFAULTS["data_schema_version"]
            ):
                raise AgentError("PROTOCOL_MISMATCH", "前后端协议或数据版本不兼容。")
            InitializeParams.model_validate(params)

            def initialize() -> InitializeResult:
                """在业务线程获取写锁并装配握手事实。

                Acquire the writer lock and construct handshake facts.
                """
                config = load_config(self.storage.location, self.model)
                if not self.initialized:
                    self.stack.enter_context(self.storage.writer())
                    self.projects.initialize()
                    self.initialized = True
                return InitializeResult(
                    app=AppInfo(
                        name=DEFAULTS["app_name"],
                        app_version=__version__,
                        protocol_version=2,
                        stage="M1",
                    ),
                    storage=self.storage.info(),
                    config=config.public(self.credential.info),
                    projects=self.projects.view(),
                    capabilities=[
                        "initialize",
                        "projects.open",
                        "projects.list",
                        "config.get",
                        "config.update",
                        "diagnostics.get",
                        "connections.get",
                        "connections.configure",
                        "connections.release",
                        "connections.test",
                        "connections.test_model",
                        "shutdown",
                        "sessions.create",
                        "sessions.list",
                        "sessions.get",
                        "sessions.attach",
                        "sessions.detach",
                        "runs.start",
                        "runs.cancel",
                        "runs.active",
                    ],
                )

            result = await self.worker.call(initialize)
            await self.http.set_reuse(result.config.http.reuse_enabled)
            return result
        if method == "diagnostics.get":
            options = DiagnosticsParams.model_validate(params)
            if self.diagnostic_lock.locked():
                raise AgentError("DIAGNOSTICS_BUSY", "已有诊断正在运行。")
            async with self.diagnostic_lock:
                # 诊断不占业务线程；它的探测有独立超时，不能阻挡取消。
                # Diagnostics have independent timeouts and never occupy the business worker.
                credential = (
                    self.credential
                    if self.credential.info.source == "process"
                    else await asyncio.to_thread(resolve_credential)
                )
                report = await asyncio.to_thread(
                    diagnose,
                    dev=options.dev,
                    network=False,
                    write_probe=options.write_probe,
                    credential=credential,
                    storage=self.storage,
                    model=self.model,
                )
                if options.network:
                    status = await self.test_connection(
                        options.network_timeout_seconds
                        if options.network_timeout_seconds is not None
                        else DEFAULTS["http"]["probe_timeout_seconds"]
                    )
                    probe = status.last_probe
                    assert probe is not None  # 本次探测已记录 / recorded by probe
                    checks = [check for check in report.checks if check.check_id != "catalog"]
                    checks.append(
                        DiagnosticCheck(
                            check_id="catalog",
                            status="ok" if probe.code == "OK" else "error",
                            code=probe.code,
                            summary="已通过当前模型连接池完成一次无凭据目录探测。",
                            remediation=""
                            if probe.code == "OK"
                            else "查看连接池的最近探测阶段后重试。",
                            blocking=probe.code != "OK",
                            evidence={
                                "http_status": probe.http_status,
                                "models_confirmed": probe.models_confirmed,
                            },
                        )
                    )
                    if probe.code == "OK" and not probe.models_confirmed:
                        checks.append(
                            DiagnosticCheck(
                                check_id="catalog_models",
                                status="warning",
                                code="MODEL_NOT_CONFIRMED",
                                summary="目录尚未确认全部默认模型。",
                                remediation="查看模型配置和服务目录后重试。",
                                blocking=False,
                                evidence={},
                            )
                        )
                    report = report.model_copy(
                        update={
                            "checks": checks,
                            "mode": [
                                "local",
                                *(["dev"] if options.dev else []),
                                "network",
                                *(["write_probe"] if options.write_probe else []),
                            ],
                            "catalog_reachable": "ok" if probe.code == "OK" else "error",
                        }
                    )
                return report.model_copy(update={"connections": self.connection_status()})
        if method == "shutdown":
            EmptyParams.model_validate(params)
            self.stopping = True
            return None
        if not self.initialized:
            raise AgentError("NOT_INITIALIZED", "后端尚未完成初始化。")
        if method == "connections.get":
            EmptyParams.model_validate(params)
            return self.connection_status()
        if method == "connections.configure":
            settings = ConnectionSettings.model_validate(params)
            async with self.connection_control_lock:
                await self.worker.call(self.storage.save_connections, settings)
                await self.http.set_reuse(settings.reuse_enabled)
                config = await self.worker.call(load_config, self.storage.location, self.model)
                return config.public(self.credential.info)
        if method == "connections.release":
            EmptyParams.model_validate(params)
            async with self.connection_control_lock:
                await self.http.release()
                return self.connection_status()
        if method == "connections.test":
            probe_params = ConnectionProbeParams.model_validate(params)
            return await self.test_connection(probe_params.timeout_seconds)
        if method == "connections.test_model":
            model_probe = ModelConnectionProbeParams.model_validate(params)
            config = await self.worker.call(load_config, self.storage.location, self.model)
            credential = (
                self.credential
                if self.credential.info.source == "process"
                else await asyncio.to_thread(resolve_credential)
            )
            await self.model_tests.test(
                model_probe, GoClient(credential, config.model.base_url, self.http), config.run
            )
            return self.connection_status()
        if method == "projects.open":
            selection = OpenProjectParams.model_validate(params).root
            return await self.worker.call(
                self.projects.open,
                **(
                    {"project_id": selection.project_id}
                    if isinstance(selection, OpenProjectById)
                    else {"path": selection.path}
                ),
            )
        if method == "projects.list":
            EmptyParams.model_validate(params)
            return await self.worker.call(self.projects.view)
        if method in {"config.get", "config.update"}:
            if method == "config.update":
                update = UpdateConfigParams.model_validate(params)
                await self.worker.call(self.storage.save_model, update.model_id, update.run)
                self.model = None
            else:
                EmptyParams.model_validate(params)
            if self.credential.info.source != "process":
                self.credential = await asyncio.to_thread(resolve_credential)
            config = await self.worker.call(load_config, self.storage.location, self.model)
            return config.public(self.credential.info)
        if method == "sessions.create":
            create = CreateSessionParams.model_validate(params)
            return await self.sessions.create(create.project_id, create.model_id)
        if method == "sessions.list":
            listing = ListSessionsParams.model_validate(params)
            return await self.sessions.list(listing.project_id, listing.cursor, listing.limit)
        if method in {"sessions.get", "sessions.attach"}:
            get = GetSessionParams.model_validate(params)
            if method == "sessions.attach":
                if len(self.subscriptions) >= 8 and get.session_id not in self.subscriptions:
                    raise AgentError("SUBSCRIPTIONS_FULL", "会话订阅过多，请关闭旧视图。")
                self.subscriptions.add(get.session_id)
            try:
                return await self.sessions.view(get.session_id, get.before_seq)
            except Exception:
                if method == "sessions.attach":
                    self.subscriptions.discard(get.session_id)
                raise
        if method == "sessions.detach":
            detach = SessionParams.model_validate(params)
            self.subscriptions.discard(detach.session_id)
            return EmptyParams()
        if method == "runs.start":
            start = StartRunParams.model_validate(params)
            return await self.sessions.start(
                start.session_id, start.operation_id, start.prompt, start.limits
            )
        if method == "runs.cancel":
            cancel = CancelRunParams.model_validate(params)
            return await self.sessions.cancel(cancel.run_id)
        if method == "runs.active":
            EmptyParams.model_validate(params)
            active = self.sessions.active
            return ActiveRunResult(
                session=summarize(active.log, active=True, stopping=active.cancel.is_set())
                if active
                else None
            )
        raise AgentError("METHOD_NOT_FOUND", "不支持该方法。")

    async def close(self) -> None:
        """清理活动运行后在原业务线程释放写锁。 Clean up runs before releasing the writer lock."""
        await self.sessions.close()
        await self.http.close()
        await self.worker.call(self.stack.close)
        self.worker.close()
