"""短控制请求与长运行分离的 RPC 装配。

RPC composition separating control from long runs.
"""

import asyncio
import logging
from contextlib import ExitStack

from pydantic import BaseModel

from my_agent import __version__
from my_agent.attachments.types import AttachmentParams
from my_agent.bootstrap import build_model_http, build_sessions
from my_agent.changes.store import ChangeStore
from my_agent.changes.types import GetChangeParams, ListChangesParams
from my_agent.collaboration.types import (
    ArrangeSessionWorkParams,
    CollaborationHistoryParams,
    CollaborationPageParams,
    CollaborationRequestParams,
    ConnectSessionsParams,
    ControlCollaborationParams,
    SendMessageParams,
)
from my_agent.config import DEFAULTS, MODEL_DEFAULTS, DataLocation, ModelConfig, load_config
from my_agent.context.types import ConfigureContextParams, ContextParams, HistoryParams
from my_agent.credentials import ResolvedCredential, resolve_credential
from my_agent.delegation.types import (
    ConfigureWorkersParams,
    WorkerControlParams,
    WorkerSessionParams,
)
from my_agent.diagnostics import diagnose
from my_agent.errors import AgentError
from my_agent.evolution.diagnostics import DiagnosticHandler
from my_agent.execution.environments import EnvironmentStore
from my_agent.execution.sandbox import SandboxLease
from my_agent.execution.service import ProgramService
from my_agent.execution.store import ProgramStore
from my_agent.execution.types import (
    BindEnvironmentParams,
    EnvironmentParams,
    EnvironmentProjectParams,
    ExecutionStatus,
    GetProgramParams,
    ListProgramsParams,
    ProgramParams,
    RemoveEnvironmentParams,
    SaveEnvironmentParams,
    SaveExecutionSettings,
)
from my_agent.goals.dto import ControlGoalParams, CreateGoalParams, ListGoalsParams
from my_agent.goals.types import GoalControl, GoalCreated
from my_agent.mcp_client.types import (
    McpArtifactParams,
    McpControlParams,
    McpParams,
    SaveMcpParams,
)
from my_agent.memory.types import (
    ConfigureMemoryParams,
    ForgetMemoryParams,
    ListMemoryParams,
    MaintainMemoryParams,
    MemoryParams,
    MemoryQuery,
    SaveMemoryParams,
)
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
    RelocateProjectParams,
    SessionParams,
    StartRunParams,
    UpdateConfigParams,
)
from my_agent.rpc.m5_routes import M5_METHODS, dispatch_m5
from my_agent.rpc.m6_routes import M6_METHODS, dispatch_m6
from my_agent.rpc.m7_routes import M7_METHODS, dispatch_m7
from my_agent.runtime.tools import ToolContext
from my_agent.sessions.trace import TraceDetailParams, TraceParams, trace_detail, trace_page
from my_agent.skills.online import OnlineSkills
from my_agent.skills.online_types import (
    OnlineSkillCancel,
    OnlineSkillInspect,
    OnlineSkillInstall,
    OnlineSkillRead,
    OnlineSkillSearch,
)
from my_agent.skills.types import (
    EnableSkillParams,
    SaveSkillParams,
    SelectSkillsParams,
    SkillParams,
    SkillReadParams,
)
from my_agent.spaces.types import (
    BindSpaceMemberParams,
    SaveSpaceLayoutParams,
    SaveSpaceParams,
    SpaceParams,
    SpaceStartParams,
)
from my_agent.storage import Storage
from my_agent.tasks.types import AssignSessionParams, CreateTaskParams, TaskParams, UpdateTaskParams
from my_agent.worker import BusinessWorker
from my_agent.workflow.templates import (
    ParseWorkflowParams,
    RemoveWorkflowParams,
    SaveWorkflowParams,
    UpdateTaskWorkflowParams,
    WorkflowTemplate,
    WorkflowTemplates,
)


class RpcApplication:
    """拥有业务写锁与服务，控制请求按需进入业务线程。

    Own the writer lock and composed services.
    """

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
        self.environments = EnvironmentStore(self.storage)
        self.programs = ProgramService(self.environments, ProgramStore(self.storage), self.worker)
        self.sessions = build_sessions(
            self.storage, self.worker, credential, http=self.http, programs=self.programs
        )
        tasks, spaces, team = self.sessions.tasks, self.sessions.spaces, self.sessions.team
        intelligence, terminals = self.sessions.intelligence, self.sessions.terminals
        local_git, documents = self.sessions.local_git, self.sessions.documents
        attachments = self.sessions.attachments
        if (
            tasks is None
            or spaces is None
            or team is None
            or intelligence is None
            or terminals is None
            or local_git is None
            or documents is None
            or attachments is None
        ):
            # 缺失的是装配不变量，不是 pywinpty、LSP 或 Git 的可用性门槛。
            # This is a composition invariant, not a pywinpty/LSP/Git availability gate.
            raise RuntimeError("M5 shared services were not composed")
        self.tasks, self.spaces, self.team = tasks, spaces, team
        self.intelligence, self.terminals = intelligence, terminals
        self.local_git, self.documents, self.attachments = local_git, documents, attachments
        self.online_skills = (
            OnlineSkills(self.sessions.skills, self.worker) if self.sessions.skills else None
        )
        self.changes = ChangeStore(self.storage)
        self.initialized = False
        self.stopping = False
        self.diagnostic_handler: DiagnosticHandler | None = None
        self.subscriptions: set[str] = set()
        self.diagnostic_lock = asyncio.Lock()
        self.connection_probe_lock = asyncio.Lock()
        self.connection_control_lock = asyncio.Lock()

    async def document_context(self, session_id: str) -> ToolContext:
        """
        人工文件操作复用已选项目和运行配置，来源不冒充模型执行。

        Human file actions reuse the selected project and run
        configuration without claiming model execution.
        """
        return await self.documents.resolve_context(session_id)

    async def test_connection(self, timeout_seconds: float) -> ConnectionStatus:
        """互斥手动探测，不阻塞模型取消或状态读取。

        Serialize probes, not run cancellation.
        """
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
        if self.initialized and self.diagnostic_handler is None and self.sessions.diagnostics:
            self.diagnostic_handler = DiagnosticHandler(self.sessions.diagnostics)
            logging.getLogger("my_agent").addHandler(self.diagnostic_handler)
        if method in M7_METHODS:
            if not self.initialized:
                raise AgentError("NOT_INITIALIZED", "请先初始化应用。")
            return await dispatch_m7(self, method, params)
        if method in M6_METHODS:
            if not self.initialized:
                raise AgentError("NOT_INITIALIZED", "请先初始化应用。")
            return await dispatch_m6(self, method, params)
        if method in M5_METHODS:
            if not self.initialized:
                raise AgentError("NOT_INITIALIZED", "请先初始化应用。")
            return await dispatch_m5(self, method, params)
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
                    try:
                        SandboxLease.recover(self.storage.root / "sandbox-leases")
                    except (AgentError, OSError) as exc:
                        # 可选隔离清理失败可见，不阻断普通本机工作。
                        # Surface optional isolation cleanup failures without blocking direct work.
                        self.environments.sandbox_issue = (
                            exc.message
                            if isinstance(exc, AgentError)
                            else "沙箱恢复记录或临时目录不可访问；记录保留，请检查目录权限。"
                        )
                    self.initialized = True
                return InitializeResult(
                    app=AppInfo(
                        name=DEFAULTS["app_name"],
                        app_version=__version__,
                        protocol_version=15,
                        stage="M8",
                    ),
                    storage=self.storage.info(),
                    config=config.public(self.credential.info),
                    projects=self.projects.view(),
                    capabilities=[
                        "spaces.work",
                        "spaces.work_graph",
                        "spaces.work_graph_save",
                        "spaces.work_graph_start",
                        "spaces.generate",
                        "spaces.chat_view",
                        "spaces.chat",
                        "spaces.start_round",
                        "spaces.stop",
                        "spaces.templates",
                        "spaces.template_save",
                        "spaces.template_copy",
                        "spaces.template_import",
                        "spaces.template_export",
                        "documents.list",
                        "documents.read",
                        "documents.search",
                        "documents.save",
                        "documents.drafts",
                        "documents.draft",
                        "documents.operate",
                        "documents.patch",
                        "documents.diff",
                        "documents.restore",
                        "terminals.list",
                        "terminals.open",
                        "terminals.read",
                        "terminals.write",
                        "terminals.resize",
                        "terminals.control",
                        "terminals.interrupt",
                        "terminals.stop",
                        "git.status",
                        "git.settings",
                        "git.configure",
                        "git.diff",
                        "git.stage",
                        "git.unstage",
                        "git.init",
                        "git.commit",
                        "git.history",
                        "intelligence.list",
                        "intelligence.configure",
                        "intelligence.query",
                        "attachments.import",
                        "attachments.chunk",
                        "attachments.read",
                        "spaces.get",
                        "spaces.save",
                        "spaces.start",
                        "spaces.bind",
                        "spaces.layout",
                        "workflows.parse",
                        "workflows.list",
                        "workflows.save",
                        "workflows.remove",
                        "tasks.workflow",
                        "mcp.list",
                        "mcp.save",
                        "mcp.control",
                        "mcp.artifact",
                        "trace.list",
                        "trace.detail",
                        "skills.list",
                        "skills.read",
                        "skills.save",
                        "skills.select",
                        "skills.enable",
                        "skills.online.search",
                        "skills.online.inspect",
                        "skills.online.status",
                        "skills.online.read",
                        "skills.online.install",
                        "skills.online.cancel",
                        "workers.list",
                        "workers.configure",
                        "workers.control",
                        "collaboration.message",
                        "collaboration.messages",
                        "projects.relocate",
                        "context.get",
                        "context.configure",
                        "context.compact",
                        "context.cancel",
                        "context.history",
                        "memory.list",
                        "memory.save",
                        "memory.forget",
                        "memory.configure",
                        "memory.maintain",
                        "memory.cancel",
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
                        "sessions.select_model",
                        "sessions.assign",
                        "collaboration.list",
                        "collaboration.connect",
                        "collaboration.history",
                        "collaboration.request",
                        "collaboration.control",
                        "collaboration.arrange",
                        "tasks.create",
                        "tasks.list",
                        "tasks.get",
                        "tasks.update",
                        "tasks.ensure_session",
                        "sessions.list",
                        "sessions.get",
                        "sessions.attach",
                        "sessions.detach",
                        "runs.start",
                        "runs.cancel",
                        "runs.active",
                        "goals.create",
                        "goals.list",
                        "goals.control",
                        "changes.list",
                        "changes.get",
                        "environments.list",
                        "environments.save",
                        "environments.remove",
                        "environments.probe",
                        "environments.bind",
                        "execution.configure",
                        "programs.list",
                        "programs.get",
                        "programs.stop",
                        "execution.status",
                    ],
                )

            result = await self.worker.call(initialize)
            await self.programs.recover()
            if self.sessions.collaboration is not None:
                await self.sessions.collaboration.recover()
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
        if method == "projects.relocate":
            relocation = RelocateProjectParams.model_validate(params)
            return await self.worker.call(
                self.projects.relocate, relocation.project_id, relocation.path
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
        if method == "sessions.select_model":
            from my_agent.rpc.dto import SelectSessionModelParams

            model_selection = SelectSessionModelParams.model_validate(params)
            return await self.sessions.select_model(
                model_selection.session_id, model_selection.operation_id, model_selection.model_id
            )
        if method == "sessions.create":
            create = CreateSessionParams.model_validate(params)
            return await self.tasks.create_session(
                create.project_id,
                create.model_id,
                create.task_id,
                create.operation_id,
                create.role,
                create.scope,
            )
        if method == "sessions.assign":
            return await self.tasks.assign(AssignSessionParams.model_validate(params))
        if method.startswith("collaboration."):
            collaboration = self.sessions.collaboration
            if collaboration is None:
                raise AgentError("COLLABORATION_UNAVAILABLE", "协作服务尚未装配。")
            if method == "collaboration.list":
                return await collaboration.page(CollaborationPageParams.model_validate(params))
            if method == "collaboration.connect":
                return await collaboration.connect(ConnectSessionsParams.model_validate(params))
            if method == "collaboration.history":
                return await collaboration.history(
                    CollaborationHistoryParams.model_validate(params)
                )
            if method == "collaboration.request":
                return await collaboration.submit(CollaborationRequestParams.model_validate(params))
            if method == "collaboration.control":
                return await collaboration.control(
                    ControlCollaborationParams.model_validate(params)
                )
            if method == "collaboration.arrange":
                if collaboration.arrangements is None:
                    raise AgentError("COLLABORATION_UNAVAILABLE", "交接服务尚未装配。")
                return await collaboration.arrangements.create(
                    ArrangeSessionWorkParams.model_validate(params)
                )
        if method == "spaces.get":
            return await self.spaces.get(SpaceParams.model_validate(params))
        if method == "spaces.save":
            return await self.spaces.save(SaveSpaceParams.model_validate(params))
        if method == "spaces.start":
            return await self.spaces.start(SpaceStartParams.model_validate(params))
        if method == "spaces.bind":
            return await self.spaces.bind(BindSpaceMemberParams.model_validate(params))
        if method == "spaces.layout":
            return await self.spaces.layout(SaveSpaceLayoutParams.model_validate(params))
        if method == "tasks.create":
            return await self.tasks.create(CreateTaskParams.model_validate(params))
        if method == "tasks.list":
            task_listing = ListSessionsParams.model_validate(params)
            return await self.worker.call(
                self.tasks.store.list,
                task_listing.project_id,
                task_listing.cursor,
                task_listing.limit,
            )
        if method in {"tasks.get", "tasks.ensure_session"}:
            task_params = TaskParams.model_validate(params)
            task = await self.worker.call(self.tasks.store.get, task_params.task_id)
            return (
                await self.tasks.first_session(task) if method == "tasks.ensure_session" else task
            )
        if method == "tasks.update":
            return await self.worker.call(
                self.tasks.store.update, UpdateTaskParams.model_validate(params)
            )
        if method == "workflows.parse":
            imported = ParseWorkflowParams.model_validate(params)
            return WorkflowTemplate.model_validate_json(imported.content)
        if method == "workflows.list":
            EmptyParams.model_validate(params)
            return await self.worker.call(WorkflowTemplates(self.storage.root).list)
        if method == "workflows.save":
            return await self.worker.call(
                WorkflowTemplates(self.storage.root).save, SaveWorkflowParams.model_validate(params)
            )
        if method == "workflows.remove":
            return await self.worker.call(
                WorkflowTemplates(self.storage.root).remove,
                RemoveWorkflowParams.model_validate(params),
            )
        if method == "tasks.workflow":
            return await self.worker.call(
                self.tasks.store.update_workflow, UpdateTaskWorkflowParams.model_validate(params)
            )
        if method.startswith("mcp.") and self.sessions.mcp:
            mcp = self.sessions.mcp
            if method == "mcp.list":
                return await self.worker.call(mcp.catalog, McpParams.model_validate(params))
            if method == "mcp.save":
                return await mcp.save(SaveMcpParams.model_validate(params))
            if method == "mcp.control":
                return await mcp.control(McpControlParams.model_validate(params))
            if method == "mcp.artifact":
                return await self.worker.call(
                    mcp.artifact, McpArtifactParams.model_validate(params)
                )
        if method.startswith("skills.") and self.sessions.skills:
            skills = self.sessions.skills
            if self.online_skills:
                online = self.online_skills
                if method == "skills.online.search":
                    return online.search(OnlineSkillSearch.model_validate(params))
                if method == "skills.online.inspect":
                    return online.inspect(OnlineSkillInspect.model_validate(params))
                if method == "skills.online.status":
                    EmptyParams.model_validate(params)
                    return online.status()
                if method == "skills.online.read":
                    return await self.worker.call(
                        online.read, OnlineSkillRead.model_validate(params)
                    )
                if method == "skills.online.install":
                    return online.install(OnlineSkillInstall.model_validate(params))
                if method == "skills.online.cancel":
                    return await online.cancel(OnlineSkillCancel.model_validate(params))
            if method == "skills.list":
                return await self.worker.call(skills.refresh, SkillParams.model_validate(params))
            if method == "skills.read":
                return await self.worker.call(skills.read, SkillReadParams.model_validate(params))
            if method == "skills.save":
                return await self.worker.call(skills.save, SaveSkillParams.model_validate(params))
            if method == "skills.select":
                return await self.worker.call(
                    skills.select, SelectSkillsParams.model_validate(params)
                )
            if method == "skills.enable":
                return await self.worker.call(
                    skills.enable, EnableSkillParams.model_validate(params)
                )
        if method == "trace.list":
            trace_options = TraceParams.model_validate(params)
            log = await self.sessions._load(trace_options.session_id)
            return await self.worker.call(
                trace_page, log, trace_options, self.sessions.store.path(log.session_id).parent
            )
        if method == "trace.detail":
            detail_options = TraceDetailParams.model_validate(params)
            log = await self.sessions._load(detail_options.session_id)
            return await self.worker.call(trace_detail, log, detail_options)
        if method == "sessions.list":
            listing = ListSessionsParams.model_validate(params)
            return await self.sessions.list(listing.project_id, listing.cursor, listing.limit)
        if method in {
            "context.get",
            "context.configure",
            "context.compact",
            "context.cancel",
            "context.history",
        }:
            contexts = self.sessions.contexts
            if contexts is None:
                raise AgentError("CONTEXT_UNAVAILABLE", "上下文服务不可用。")
            if method == "context.configure":
                context_options = ConfigureContextParams.model_validate(params)
                return await contexts.configure(
                    context_options.session_id, context_options.settings
                )
            if method == "context.history":
                history_options = HistoryParams.model_validate(params)
                log = await self.sessions._load(history_options.session_id)
                return await self.worker.call(contexts.store.history, log, history_options)
            context_id = ContextParams.model_validate(params).session_id
            if method == "context.compact":
                return await contexts.start(context_id)
            if method == "context.cancel":
                return await contexts.cancel(context_id)
            return await contexts.view(context_id)
        if method.startswith("memory."):
            memory = self.sessions.memory
            if memory is None:
                raise AgentError("MEMORY_UNAVAILABLE", "记忆服务不可用。")
            if method == "memory.list":
                memory_query = ListMemoryParams.model_validate(params)
                return await memory.page(
                    memory_query.session_id,
                    MemoryQuery.model_validate(memory_query.model_dump(exclude={"session_id"})),
                )
            if method == "memory.save":
                save_memory = SaveMemoryParams.model_validate(params)
                return await memory.save(
                    save_memory.session_id, save_memory.fields, save_memory.memory_id
                )
            if method == "memory.forget":
                forget_memory = ForgetMemoryParams.model_validate(params)
                return await memory.forget(forget_memory.session_id, forget_memory.memory_id)
            if method == "memory.configure":
                configure_memory = ConfigureMemoryParams.model_validate(params)
                return await memory.configure(
                    configure_memory.session_id, configure_memory.settings
                )
            if method == "memory.maintain":
                maintain_memory = MaintainMemoryParams.model_validate(params)
                return await memory.start(
                    maintain_memory.session_id,
                    maintain_memory.after_seq,
                    maintain_memory.source_ids,
                    maintain_memory.title,
                )
            if method == "memory.cancel":
                return await memory.cancel(MemoryParams.model_validate(params).session_id)
        if method in {"collaboration.message", "collaboration.messages"}:
            service = self.sessions.collaboration
            if service is None:
                raise AgentError("COLLABORATION_UNAVAILABLE", "协作服务未接入。")
            if method == "collaboration.message":
                return await service.send_message(SendMessageParams.model_validate(params))
            return await service.messages(CollaborationPageParams.model_validate(params))
        if method in {"workers.list", "workers.configure", "workers.control"}:
            delegation = self.sessions.delegations
            if delegation is None:
                raise AgentError("WORKERS_UNAVAILABLE", "内部子任务服务不可用。")
            if method == "workers.configure":
                options_workers = ConfigureWorkersParams.model_validate(params)
                return await delegation.configure(
                    options_workers.session_id, options_workers.settings
                )
            if method == "workers.control":
                control_worker = WorkerControlParams.model_validate(params)
                if control_worker.action == "stop":
                    return await delegation.stop(
                        control_worker.session_id, control_worker.worker_id
                    )
                active = self.sessions.active_for(control_worker.session_id)
                if active is None:
                    raise AgentError("RUN_NOT_ACTIVE", "请在当前会话明确发起接续，再安排子任务。")
                await delegation.continue_work(
                    active, control_worker.worker_id, control_worker.prompt
                )
                return await delegation.page(control_worker.session_id)
            return await delegation.page(WorkerSessionParams.model_validate(params).session_id)
        if method in {"sessions.get", "sessions.attach"}:
            get = GetSessionParams.model_validate(params)
            if method == "sessions.attach":
                # 活跃空间可以有多位成员；传输队列已有背压和重同步，不再限制视图人数。
                # Space members share the bounded transport queue and its resynchronization.
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
            for identity in start.attachment_ids:
                await self.worker.call(
                    self.attachments._read,
                    AttachmentParams(session_id=start.session_id, attachment_id=identity),
                )
            return await self.sessions.start(
                start.session_id,
                start.operation_id,
                start.prompt,
                start.limits,
                start.mode,
                start.plan_document,
                attachment_ids=start.attachment_ids,
            )
        if method in {"goals.create", "goals.list", "goals.control"}:
            goals = self.sessions.goals
            if goals is None:
                raise AgentError("GOAL_UNAVAILABLE", "Goal 控制器未装配。")
            if method == "goals.create":
                create_goal = CreateGoalParams.model_validate(params)
                for identity in create_goal.attachment_ids:
                    await self.worker.call(
                        self.attachments._read,
                        AttachmentParams(session_id=create_goal.session_id, attachment_id=identity),
                    )
                return await goals.create(
                    create_goal.session_id,
                    GoalCreated.model_validate(create_goal.model_dump(exclude={"session_id"})),
                )
            if method == "goals.list":
                return await goals.page(ListGoalsParams.model_validate(params))
            goal_control = ControlGoalParams.model_validate(params).root
            return await goals.control(
                goal_control.session_id,
                GoalControl.model_validate(goal_control.model_dump(exclude={"session_id"})),
            )
        if method == "environments.list":
            env_project = EnvironmentProjectParams.model_validate(params)
            return await self.worker.call(self.environments.catalog, env_project.project_id)
        if method == "environments.inspect_python":
            env_project = EnvironmentProjectParams.model_validate(params)
            if env_project.project_id is None:
                raise AgentError("PROJECT_REQUIRED", "请先选择项目，再查看本机 Python。")
            return await self.programs.inspect_python(env_project.project_id)
        if method == "execution.status":
            EmptyParams.model_validate(params)
            return ExecutionStatus(
                programs=[
                    p.record.summary for p in self.programs.owned.values() if not p.done.is_set()
                ],
                probe_count=len(self.programs.probes) + len(self.programs.python_inspections),
            )
        if method == "environments.save":
            return await self.worker.call(
                self.environments.save, SaveEnvironmentParams.model_validate(params)
            )
        if method == "environments.remove":
            return await self.worker.call(
                self.environments.remove, RemoveEnvironmentParams.model_validate(params)
            )
        if method == "environments.bind":
            return await self.worker.call(
                self.environments.bind, BindEnvironmentParams.model_validate(params)
            )
        if method == "execution.configure":
            return await self.worker.call(
                self.environments.settings, SaveExecutionSettings.model_validate(params)
            )
        if method == "environments.probe":
            return await self.programs.probe(EnvironmentParams.model_validate(params))
        if method == "programs.list":
            program_list = ListProgramsParams.model_validate(params)
            await self.worker.call(self.environments.project_root, program_list.project_id)
            return await self.programs.list(program_list)
        if method == "programs.get":
            return await self.programs.get(GetProgramParams.model_validate(params))
        if method == "programs.stop":
            return await self.programs.stop(ProgramParams.model_validate(params).program_id)
        if method == "changes.list":
            changes = ListChangesParams.model_validate(params)
            await self.sessions.view(changes.session_id)
            identities = [changes.session_id]
            if changes.scope == "task":
                if self.sessions.collaboration is None:
                    raise AgentError("COLLABORATION_UNAVAILABLE", "任务协作服务未装配。")
                identities = await self.sessions.collaboration.task_session_ids(changes.session_id)
            return await self.worker.call(
                self.changes.list_many,
                identities,
                changes.cursor,
                changes.limit,
                changes.path,
                changes.scope == "task",
            )
        if method == "changes.get":
            change = GetChangeParams.model_validate(params)
            await self.sessions.view(change.session_id)
            return await self.worker.call(
                self.changes.view, change.session_id, change.change_id, change.offset
            )
        if method == "runs.cancel":
            cancel = CancelRunParams.model_validate(params)
            return await self.sessions.cancel(cancel.run_id)
        if method == "runs.active":
            EmptyParams.model_validate(params)
            return ActiveRunResult(sessions=await self.sessions.active_summaries())
        raise AgentError("METHOD_NOT_FOUND", "不支持该方法。")

    async def close(self) -> None:
        """清理活动运行后在原业务线程释放写锁。

        Clean up runs before releasing the writer lock.
        """
        try:
            try:
                if self.online_skills:
                    await self.online_skills.close()
            finally:
                try:
                    await self.sessions.close()
                finally:
                    await asyncio.to_thread(
                        SandboxLease.close_all, self.storage.root / "sandbox-leases"
                    )
        finally:
            try:
                if self.diagnostic_handler:
                    logging.getLogger("my_agent").removeHandler(self.diagnostic_handler)
                    await asyncio.to_thread(self.diagnostic_handler.close)
                await self.worker.call(self.stack.close)
            finally:
                self.worker.close()
