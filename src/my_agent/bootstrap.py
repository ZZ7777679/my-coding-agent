"""显式装配共享会话核心。

Explicit composition of the shared session core.
"""

import json
import logging
import threading
from uuid import uuid4

from my_agent.attachments.service import AttachmentService
from my_agent.changes.store import ChangeStore
from my_agent.checkpoints.service import RollbackService
from my_agent.checkpoints.tools import RollbackTools
from my_agent.collaboration.arrangements import SessionArrangements
from my_agent.collaboration.service import CollaborationService
from my_agent.collaboration.store import CollaborationStore
from my_agent.collaboration.tools import CollaborationTools
from my_agent.config import DEFAULTS, MODEL_DEFAULTS, load_config
from my_agent.context.service import ContextService
from my_agent.context.tools import ContextTools
from my_agent.context.window import task_context
from my_agent.credentials import ResolvedCredential, resolve_credential
from my_agent.delegation.service import DelegationService
from my_agent.delegation.tools import WorkerTools
from my_agent.documents.service import DocumentService
from my_agent.errors import AgentError
from my_agent.execution.environments import EnvironmentStore
from my_agent.execution.service import ProgramService
from my_agent.execution.store import ProgramStore
from my_agent.execution.types import ListProgramsParams
from my_agent.goals.service import GoalService
from my_agent.intelligence.service import IntelligenceService
from my_agent.intelligence.tools import IntelligenceTools
from my_agent.local_git.service import LocalGitService
from my_agent.local_git.tools import GitTools
from my_agent.mcp_client.service import McpService
from my_agent.mcp_client.tools import McpTools
from my_agent.memory.service import MemoryService
from my_agent.memory.tools import MemoryTools
from my_agent.models.go import GoClient
from my_agent.models.http import ModelHttpPool
from my_agent.models.native_search import NativeSearchClient
from my_agent.projects import ProjectService
from my_agent.runtime.context import ContextMaterial, SharedContext
from my_agent.runtime.tools import ToolContext
from my_agent.sessions.artifacts import ArtifactInspector
from my_agent.sessions.projection import summarize
from my_agent.sessions.recovery import RecoveryService
from my_agent.sessions.service import SessionService
from my_agent.sessions.store import SessionLog, SessionStore
from my_agent.skills.service import SkillService
from my_agent.skills.tools import SkillTools
from my_agent.spaces.context import member_context
from my_agent.spaces.service import SpaceService
from my_agent.spaces.store import SpaceStore
from my_agent.spaces.team_service import SpaceTeamService
from my_agent.spaces.team_tools import SpaceTeamTools
from my_agent.spaces.work_graph import work_items
from my_agent.storage import Storage
from my_agent.tasks.service import TaskService
from my_agent.tasks.store import TaskStore
from my_agent.terminals.service import TerminalService
from my_agent.terminals.tools import TerminalTools
from my_agent.tools.files import FileCoordinator, FileTools
from my_agent.tools.programs import ProjectTools
from my_agent.tools.web import WebTools
from my_agent.web.fetch import PageFetcher
from my_agent.web.types import WebSettings
from my_agent.worker import BusinessWorker
from my_agent.workflow.types import WorkItem


def build_model_http() -> ModelHttpPool:
    """集中装配连接清理默认值，不探测或覆盖用户网络。

    Compose pooled HTTP defaults without detecting or overriding user networking.
    """
    http = ModelHttpPool(
        reuse_enabled=DEFAULTS["http"]["reuse_enabled"],
        keepalive_expiry=DEFAULTS["http"]["keepalive_expiry_seconds"],
        drain_timeout_seconds=DEFAULTS["http"]["response_drain_timeout_seconds"],
    )
    return http


def build_sessions(
    storage: Storage,
    worker: BusinessWorker,
    credential: ResolvedCredential,
    *,
    http: ModelHttpPool | None = None,
    programs: ProgramService | None = None,
) -> SessionService:
    """入口持锁后注入生产组件；用户环境凭据可在新运行前刷新。

    Inject production components after entry-point locking; refresh user credentials per run.
    """
    if http is None:
        http = build_model_http()
        http.reuse_enabled = load_config(storage.location).http.reuse_enabled
    shared_http = http
    tasks = TaskStore(storage)
    spaces = SpaceStore(storage)
    changes = ChangeStore(storage)
    files = FileCoordinator()
    execution = programs or ProgramService(EnvironmentStore(storage), ProgramStore(storage), worker)
    web = WebSettings.model_validate(DEFAULTS["web"])
    fetcher = PageFetcher()

    def context_loader(log: SessionLog) -> SharedContext | None:
        """按本会话归属装配共同事实，保留来源和版本。

        Compose shared facts with ownership, source and revision.
        """
        summary = summarize(log)
        if summary.task_id is None:
            return None
        task = tasks.get(summary.task_id)
        if task.project_id != summary.project_id:
            raise AgentError("TASK_PROJECT_MISMATCH", "任务与会话项目归属不一致。")
        programs = execution.store.list(
            ListProgramsParams(project_id=summary.project_id, session_id=summary.session_id)
        )
        # 带入已有登记状态，不做额外进程 / 网络探测或把状态改变设为审批门槛。
        # Supply saved states without extra process/network probes or approval gates.
        program_context = {
            "programs": [
                {
                    "program_id": item.program_id,
                    "kind": item.kind,
                    "status": item.status,
                    "url": item.url,
                    "finished_at": item.finished_at,
                }
                for item in programs.programs
            ],
            "more": programs.next_cursor is not None,
            "unavailable_count": programs.unavailable_count,
        }
        extra_text = ""
        extra_materials: tuple[ContextMaterial, ...] = ()
        # 空间是可选任务资料，读取故障只提示该资料缺失，不阻断原会话。
        # Optional space failures omit that material without blocking the original session.
        try:
            record = spaces.get(task.task_id)
            extra = (
                member_context(record.view, log.session_id, task) if record is not None else None
            )
            if extra is not None:
                extra_text, material = extra
                extra_materials = (material,)
        except AgentError as exc:
            logging.getLogger(__name__).warning("Optional space context unavailable: %s", exc.code)
            extra_text = "\nCollaboration-space material unavailable: " + exc.code
        return SharedContext(
            task.task_id,
            task.revision,
            task_context(
                task, load_config(storage.location).run.max_context_bytes // 8, log.session_id
            )
            + "\nSession role: "
            + summary.role
            + "\nSession scope: "
            + summary.scope
            + "\nCurrent saved managed-program states (newer than historical tool results; "
            "use read_program for live detail, do not assume stopped services are running):\n"
            + json.dumps(program_context, ensure_ascii=False),
            additional_text=extra_text,
            additional_materials=extra_materials,
        )

    def model_factory() -> GoClient:
        """进程凭据优先保持，其他来源按既定规则刷新。

        Preserve process credentials, refresh other sources.
        """
        current = credential if credential.info.source == "process" else resolve_credential()
        return GoClient(current, str(MODEL_DEFAULTS["base_url"]), shared_http)

    async def sync_report(session_id: str, result_seq: int) -> tuple[str, int] | None:
        """从已保存 Run 幂等更新任务，不额外请求模型。

        Idempotently update a task from a saved run without extra model requests.
        """
        updated = await worker.call(tasks.record_report, session_id, result_seq)
        return (updated.task_id, updated.revision) if updated is not None else None

    sessions = SessionService(
        SessionStore(storage),
        ProjectService(storage),
        worker,
        model_factory,
        close_model=shared_http.close,
        context_loader=context_loader,
        tool_factory=lambda context: WebTools(
            context,
            ProjectTools(context, FileTools(context, changes, worker, files), execution),
            NativeSearchClient(model_factory(), web.search_model_id),
            fetcher,
            web,
        ),
        finish_run=execution.finish_run,
        close_execution=execution.close,
        sync_report=sync_report,
        read_roots=execution.environments.read_roots,
    )
    sessions.file_coordinator = files
    attachments = AttachmentService(sessions)
    sessions.attachments = attachments

    def shared_work(log: SessionLog) -> list[WorkItem]:
        """读取当前任务图用于依赖判断，不将无关积压变成 Goal 授权。

        Load current task dependencies without treating unrelated backlog as goal authorization.
        """
        summary = summarize(log)
        if summary.task_id is None:
            return []
        task = tasks.get(summary.task_id)
        if task.project_id != summary.project_id:
            raise AgentError("TASK_PROJECT_MISMATCH", "工作图不属于当前项目。")
        record = spaces.get(task.task_id)
        return work_items(task, record.view) if record else [item.item for item in task.work.items]

    sessions.goals = GoalService(sessions, work_loader=shared_work)
    sessions.recovery = RecoveryService(sessions, ArtifactInspector(changes, execution, worker))
    collaboration = CollaborationService(sessions, CollaborationStore(storage))
    collaboration.arrangements = SessionArrangements(collaboration, tasks, changes)
    sessions.collaboration = collaboration
    project_tools = sessions.tool_factory
    sessions.tool_factory = lambda context: CollaborationTools(
        context, project_tools(context), collaboration, changes
    )
    contexts = ContextService(sessions)
    sessions.contexts = contexts
    collaborating_tools = sessions.tool_factory
    memory = MemoryService(sessions)
    sessions.memory = memory
    delegation = DelegationService(sessions)
    sessions.delegations = delegation
    sessions.tool_factory = lambda context: MemoryTools(
        context, ContextTools(context, collaborating_tools(context), contexts), memory, tasks
    )
    knowledge_tools = sessions.tool_factory
    sessions.tool_factory = lambda context: WorkerTools(
        context, knowledge_tools(context), delegation
    )
    skills = SkillService(sessions)
    sessions.skills = skills
    worker_tools = sessions.tool_factory
    sessions.tool_factory = lambda context: SkillTools(context, worker_tools(context), skills)
    mcp = McpService(sessions)
    sessions.mcp = mcp
    skill_tools = sessions.tool_factory
    sessions.tool_factory = lambda context: McpTools(context, skill_tools(context), mcp)
    task_service = TaskService(tasks, sessions, worker)
    space_service = SpaceService(spaces, task_service, sessions, worker, collaboration)
    team = SpaceTeamService(space_service)
    intelligence = IntelligenceService(storage, execution.environments, worker)
    terminals = TerminalService(execution.environments, storage, worker)
    local_git = LocalGitService(execution.environments, worker)

    async def document_context(session_id: str) -> ToolContext:
        """人工文件入口共用项目、运行配置和来源；CLI 与 RPC 不复制此规则。

        Share project/settings/provenance resolution for human files across CLI and RPC.
        """
        view = await sessions.view(session_id)
        root = await sessions.validate_project(view.summary.project_id)
        config = await worker.call(load_config, storage.location)
        return ToolContext(
            root=root,
            limits=config.run,
            stop=threading.Event(),
            project_id=view.summary.project_id,
            session_id=session_id,
            run_id=str(uuid4()),
            mode="normal",
            plan_document=None,
        )

    sessions.tasks = task_service
    sessions.spaces = space_service
    sessions.team = team
    sessions.intelligence = intelligence
    sessions.terminals = terminals
    sessions.local_git = local_git
    sessions.documents = DocumentService(storage, changes, worker, files, document_context)
    mcp_tools = sessions.tool_factory
    sessions.tool_factory = lambda context: SpaceTeamTools(
        context,
        IntelligenceTools(
            context,
            GitTools(context, TerminalTools(context, mcp_tools(context), terminals), local_git),
            intelligence,
            attachments,
        ),
        team,
    )
    existing_tools = sessions.tool_factory
    rollback = RollbackService(sessions)
    sessions.tool_factory = lambda context: RollbackTools(
        context, existing_tools(context), rollback
    )
    from my_agent.evolution.diagnostics import DiagnosticStore
    from my_agent.evolution.service import EvolutionService
    from my_agent.evolution.tools import EvolutionTools

    sessions.diagnostics = DiagnosticStore(storage)
    sessions.evolution = EvolutionService(sessions, sessions.diagnostics)
    evolution_service = sessions.evolution
    previous_tools = sessions.tool_factory
    sessions.tool_factory = lambda context: EvolutionTools(
        context, previous_tools(context), evolution_service
    )
    return sessions
