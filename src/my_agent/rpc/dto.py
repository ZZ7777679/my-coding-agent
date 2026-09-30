"""公开 JSON 契约；线路上的必需字段均显式提供。

Public JSON contracts with every required wire field supplied explicitly.
"""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    RootModel,
    StringConstraints,
    field_validator,
)

from my_agent.changes.types import ChangePage, ChangeView, GetChangeParams, ListChangesParams
from my_agent.collaboration.types import (
    ArrangeSessionWorkParams,
    CollaborationHistoryParams,
    CollaborationLink,
    CollaborationPage,
    CollaborationPageParams,
    CollaborationRequest,
    CollaborationRequestParams,
    ConnectSessionsParams,
    ControlCollaborationParams,
    PeerMessage,
    PeerMessagePage,
    SendMessageParams,
)
from my_agent.context.types import (
    ConfigureContextParams,
    ContextParams,
    ContextView,
    HistoryPage,
    HistoryParams,
)
from my_agent.delegation.types import (
    ConfigureWorkersParams,
    WorkerControlParams,
    WorkerPage,
    WorkerSessionParams,
)
from my_agent.errors import DataSource
from my_agent.execution.types import (
    BindEnvironmentParams,
    ChooseEnvironmentPathParams,
    EnvironmentCatalog,
    EnvironmentParams,
    EnvironmentProbe,
    EnvironmentProjectParams,
    ExecutionSettings,
    ExecutionStatus,
    GetProgramParams,
    ListProgramsParams,
    ProgramPage,
    ProgramParams,
    ProgramView,
    RemoveEnvironmentParams,
    SaveEnvironmentParams,
    SaveExecutionSettings,
)
from my_agent.goals.dto import ControlGoalParams, CreateGoalParams, ListGoalsParams
from my_agent.goals.types import GoalPage, GoalView
from my_agent.mcp_client.types import (
    McpArtifact,
    McpArtifactParams,
    McpCatalog,
    McpControlParams,
    McpParams,
    SaveMcpParams,
)
from my_agent.memory.types import (
    ConfigureMemoryParams,
    ForgetMemoryParams,
    ListMemoryParams,
    MaintainMemoryParams,
    MemoryPage,
    MemoryParams,
    SaveMemoryParams,
)
from my_agent.models.connections import (
    ConnectionProbeParams,
    ConnectionSettings,
    ConnectionStatus,
    ModelConnectionProbeParams,
)
from my_agent.models.types import ModelId as ModelId
from my_agent.runtime.modes import RunMode
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.trace import TraceDetail, TraceDetailParams, TracePage, TraceParams
from my_agent.sessions.types import (
    SessionId,
    SessionPage,
    SessionSignal,
    SessionSummary,
    SessionView,
)
from my_agent.skills.online_types import (
    OnlineSkillCancel,
    OnlineSkillDocument,
    OnlineSkillInspect,
    OnlineSkillInstall,
    OnlineSkillRead,
    OnlineSkillSearch,
    OnlineSkillStatus,
)
from my_agent.skills.site_types import (
    SkillSiteControl,
    SkillSiteLayout,
    SkillSiteSources,
    SkillSiteState,
)
from my_agent.skills.types import (
    EnableSkillParams,
    SaveSkillParams,
    SelectSkillsParams,
    SkillCatalog,
    SkillDocument,
    SkillParams,
    SkillReadParams,
)
from my_agent.tasks.types import (
    AssignSessionParams,
    CreateTaskParams,
    CreateTaskResult,
    TaskFields,
    TaskPage,
    TaskParams,
    TaskView,
    UpdateTaskParams,
)
from my_agent.web.types import OpenWebUrlParams, WebPageResult, WebSearchResult
from my_agent.workflow.templates import (
    ParseWorkflowParams,
    RemoveWorkflowParams,
    SaveWorkflowParams,
    UpdateTaskWorkflowParams,
    WorkflowCatalog,
    WorkflowTemplate,
)

Text = Annotated[str, StringConstraints(min_length=1, max_length=4096)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Timestamp = Annotated[
    str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
]


class DTO(BaseModel):
    """所有公开对象的严格校验基类，拒绝额外字段和隐式转换。

    Base for strictly validated public objects, rejecting extras and implicit coercion.
    """

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @field_validator(
        "protocol_version",
        "data_schema_version",
        "report_schema_version",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def reject_boolean_version(cls, value: object) -> object:
        """阻止布尔值按 Python 整数语义冒充协议版本。

        Prevent booleans from masquerading as numeric versions under Python integer semantics.
        """

        if isinstance(value, bool):
            raise ValueError("Version must be numeric")
        return value


class CredentialInfo(DTO):
    """仅公开凭据来源与存在状态；null 表示读取受限。

    Expose only credential source and presence; null means access was restricted.
    """

    env_var: Literal["OPENCODE_API_KEY"]
    source: Literal["process", "windows_user", "none", "restricted"]
    present: bool | None


class PublicConfig(DTO):
    """前端可见的模型配置，不携带凭据原值。

    Renderer-visible model configuration without credential values.
    """

    provider: Literal["opencode-go"]
    base_url: Literal["https://opencode.ai/zen/go/v1"]
    api: Literal["chat_completions"]
    model_id: ModelId
    allowed_models: list[ModelId]
    credential: CredentialInfo
    config_path: Text
    model_source: Literal["default", "user", "cli"]
    run: RunLimits
    http: ConnectionSettings


class UpdateConfigParams(DTO):
    """仅允许保存一个受支持的默认模型标识。

    Allow saving only one supported default model ID.
    """

    model_id: ModelId
    run: RunLimits | None = None


class StartupPathsParams(DTO):
    """描述下次启动的目录设置，不触发数据迁移或项目登记。

    Describe next-launch directories without migrating data or registering projects.
    """

    data_dir: Text
    project_dir: Text


class StartupPaths(StartupPathsParams):
    """区分已保存的下次启动设置与本次实际数据根。

    Distinguish saved next-launch paths from the current effective data root.
    """

    config_path: Text
    current_data_dir: Text


class RelocateProjectParams(DTO):
    """明确把已有项目身份绑定到新目录，保留会话与记忆。

    Explicitly rebind an existing project identity, retaining sessions and memory.
    """

    project_id: Identifier
    path: Text


class ChooseDirectoryParams(DTO):
    """限定受信目录选择器的用途，不接受任意系统操作。

    Limit the trusted directory picker to its declared purpose.
    """

    kind: Literal["data", "project"]


class DirectorySelection(DTO):
    """返回已选择目录；null 明确表示取消选择。

    Return the selected directory, with null explicitly representing cancellation.
    """

    path: Text | None


class ExportParams(DTO):
    """限定导出的公开文档类型，内容由后端提供。

    Select a public export category whose content comes from the backend.
    """

    kind: Literal["config", "projects", "diagnostics"]


class ExportResult(DTO):
    """返回成功导出的文件位置；null 表示用户取消。

    Return the exported file location, or null when the user cancels.
    """

    path: Text | None


class AppInfo(DTO):
    """展示应用版本、协议版本与当前实现阶段。

    Expose the application version, protocol version and implemented stage.
    """

    name: Text
    app_version: Text
    protocol_version: Literal[6]
    stage: Literal["M4"]


class StorageInfo(DTO):
    """展示实际数据根、配置来源和存储可用状态。

    Expose the effective data root, its source and storage availability.
    """

    data_dir: Text
    source: DataSource
    data_schema_version: Literal[1]
    status: Literal["ready", "not_initialized", "unavailable", "busy"]


class ProjectSummary(DTO):
    """公开项目记录及当前可用性，隐藏内部文件系统身份字段。

    Expose project metadata and availability without internal filesystem identity fields.
    """

    project_id: Identifier
    name: Text
    path: Text
    canonical_path: Text
    last_opened_at: Timestamp
    available: bool
    unavailable_code: Text | None


class ProjectsView(DTO):
    """同时返回当前项目与最近记录，允许初次启动为空。

    Return active and recent projects, allowing an empty first-launch state.
    """

    active_project: ProjectSummary | None
    recent_projects: list[ProjectSummary]


class DiagnosticCheck(DTO):
    """单项诊断的公开结论、影响与脱敏证据。

    Public outcome, impact and sanitized evidence for one diagnostic check.
    """

    check_id: Identifier
    status: Literal["ok", "warning", "error", "not_checked"]
    code: Text
    summary: Text
    remediation: str
    blocking: bool
    evidence: dict[str, str | bool | int | None]


class DiagnosticReport(DTO):
    """区分凭据存在与目录可达；M0 尚未验证认证或真实工具回合。

    Separate key presence and catalog access from auth and tool calls, unverified in M0.
    """

    report_schema_version: Literal[1]
    checked_at: Timestamp
    app_version: Text
    mode: list[Literal["local", "dev", "network", "write_probe"]]
    checks: list[DiagnosticCheck]
    credential_present: bool | None
    catalog_reachable: Literal["ok", "error", "not_checked"]
    authentication_verified: Literal["not_checked"]
    tool_roundtrip_verified: Literal["not_checked"]
    connections: ConnectionStatus | None = None


class InitializeParams(DTO):
    """前端声明的兼容性信息；应用版本与协议版本分别处理。

    Client compatibility information, keeping app and protocol versions distinct.
    """

    app_version: Text
    protocol_version: Literal[6]
    data_schema_version: Literal[1]


class InitializeResult(DTO):
    """返回初始化后的公开状态与当前实际支持的方法。

    Return initialized public state and the methods currently supported.
    """

    app: AppInfo
    storage: StorageInfo
    config: PublicConfig
    projects: ProjectsView
    capabilities: list[
        Literal[
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
            "workers.list",
            "workers.configure",
            "workers.control",
            "collaboration.message",
            "collaboration.messages",
            "projects.open",
            "projects.relocate",
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
            "tasks.create",
            "tasks.list",
            "tasks.get",
            "tasks.update",
            "tasks.ensure_session",
            "sessions.assign",
            "collaboration.list",
            "collaboration.connect",
            "collaboration.history",
            "collaboration.request",
            "collaboration.control",
            "collaboration.arrange",
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
        ]
    ]


class OpenProjectByPath(DTO):
    """通过用户选择的目录路径打开项目。

    Open a project using a user-selected directory path.
    """

    path: Text


class OpenProjectById(DTO):
    """通过已有项目标识恢复选择，并由服务重新验证目录。

    Restore a recorded project by ID and let the service revalidate its directory.
    """

    project_id: Identifier


class OpenProjectParams(RootModel[OpenProjectByPath | OpenProjectById]):
    """路径与已有标识二选一，禁止同时提交两种定位方式。

    Require either a path or an existing ID, never both.
    """

    model_config = ConfigDict(strict=True)


class EmptyParams(DTO):
    """表示不接受参数的方法，拒绝任何额外字段。

    Represent parameterless methods and reject every extra field.
    """

    pass


class DiagnosticsParams(DTO):
    """显式声明额外诊断选项，避免隐式联网或写入。

    Declare optional probes explicitly to prevent implicit networking or writes.
    """

    dev: bool
    network: bool
    write_probe: bool
    network_timeout_seconds: Annotated[float, Field(gt=0)] | None = None


class ErrorData(DTO):
    """RPC 错误的稳定业务码与修复说明。

    Stable application error code and remediation inside an RPC error.
    """

    code: Text
    remediation: str


class OperationError(DTO):
    """桌面操作使用的公开错误，不包含原始异常堆栈。

    Public desktop-operation error without a raw exception traceback.
    """

    code: Text
    message: Text
    remediation: str


class RpcError(DTO):
    """将 JSON-RPC 数字错误码与应用错误信息分开表达。

    Keep JSON-RPC numeric codes distinct from application error information.
    """

    code: Annotated[int, Field(ge=-(2**31), le=2**31 - 1)]
    message: Text
    data: ErrorData


class RpcRequest(DTO):
    """带关联标识的 JSON-RPC 请求；参数在方法分发时继续校验。

    JSON-RPC request with a correlation ID; method dispatch validates parameters further.
    """

    jsonrpc: Literal["2.0"]
    id: Identifier
    method: Text
    params: dict[str, JsonValue]


class RpcNotification(DTO):
    """不要求回复的 JSON-RPC 通知，不能与带标识请求混淆。

    JSON-RPC notification requiring no reply, distinct from an identified request.
    """

    jsonrpc: Literal["2.0"]
    method: Text
    params: dict[str, JsonValue]


class RpcSuccess(DTO):
    """关联请求标识与成功结果；具体结果仍需按方法校验。

    Associate a request ID with its result, which still needs method-specific validation.
    """

    jsonrpc: Literal["2.0"]
    id: Identifier
    result: JsonValue


class RpcFailure(DTO):
    """关联请求与公开错误；无法确定请求标识时允许 null。

    Associate a request with a public error, allowing null when its ID is unknown.
    """

    jsonrpc: Literal["2.0"]
    id: Identifier | None
    error: RpcError


class RpcResponse(RootModel[RpcSuccess | RpcFailure]):
    """成功与失败响应的严格联合，不接受混合结构。

    Strict union of success and failure responses, rejecting mixed envelopes.
    """

    model_config = ConfigDict(strict=True)


class SelectSessionModelParams(DTO):
    """选择既有会话的后续模型，不创建会话或发请求。

    Select a session's next model without creating sessions or sending requests.
    """

    session_id: SessionId
    operation_id: SessionId
    model_id: ModelId


class CreateSessionParams(DTO):
    """选择项目与模型，不发起运行。

    Select project and model without starting a run.
    """

    project_id: Identifier
    model_id: ModelId
    task_id: SessionId | None = None
    operation_id: SessionId | None = None
    role: Annotated[str, Field(max_length=4096)] = ""
    scope: Annotated[str, Field(max_length=16000)] = ""


class ListSessionsParams(DTO):
    """按项目分页会话列表。

    Page sessions by project.
    """

    project_id: Identifier
    cursor: SessionId | None
    limit: Annotated[int, Field(ge=1, le=100)]


class SessionParams(DTO):
    """限定会话身份。

    Constrain session identity.
    """

    session_id: SessionId


class GetSessionParams(SessionParams):
    """显式历史页游标，null 取最近一页。

    Explicit history cursor; null loads the latest page.
    """

    before_seq: Annotated[int, Field(ge=2)] | None


class StartRunParams(SessionParams):
    """幂等操作 ID 独立于 RPC ID。

    Idempotent operation identity is separate from RPC identity.
    """

    operation_id: SessionId
    prompt: Annotated[str, Field(min_length=1, max_length=64000)]
    limits: RunLimits | None
    mode: RunMode = "plan"
    plan_document: Annotated[str, Field(min_length=1, max_length=4096)] | None = None


class CancelRunParams(DTO):
    """只停止指定运行，不隐式停止其他任务。

    Cancel the specified run only.
    """

    run_id: SessionId


class ActiveRunResult(DTO):
    """各会话的活动运行列表，切换视图仍可逐项停止。

    Active runs per session remain independently stoppable across views.
    """

    sessions: list[SessionSummary]


class SessionEventNotification(DTO):
    """唯一支持的后端事件通知形状。

    The sole supported backend notification envelope.
    """

    jsonrpc: Literal["2.0"]
    method: Literal["session.event"]
    params: SessionSignal


PUBLIC_TYPES: dict[str, type[BaseModel]] = {
    model.__name__: model
    for model in (
        McpParams,
        SaveMcpParams,
        McpControlParams,
        McpCatalog,
        McpArtifactParams,
        McpArtifact,
        WorkflowCatalog,
        SaveWorkflowParams,
        RemoveWorkflowParams,
        UpdateTaskWorkflowParams,
        ParseWorkflowParams,
        WorkflowTemplate,
        SkillParams,
        SkillReadParams,
        SaveSkillParams,
        SelectSkillsParams,
        EnableSkillParams,
        SkillCatalog,
        SkillDocument,
        OnlineSkillCancel,
        OnlineSkillDocument,
        OnlineSkillInspect,
        OnlineSkillInstall,
        OnlineSkillRead,
        OnlineSkillSearch,
        OnlineSkillStatus,
        SkillSiteControl,
        SkillSiteLayout,
        SkillSiteState,
        SkillSiteSources,
        TraceParams,
        TraceDetailParams,
        TracePage,
        TraceDetail,
        WorkerSessionParams,
        ConfigureWorkersParams,
        WorkerControlParams,
        WorkerPage,
        SendMessageParams,
        PeerMessage,
        PeerMessagePage,
        MemoryParams,
        ListMemoryParams,
        SaveMemoryParams,
        ForgetMemoryParams,
        ConfigureMemoryParams,
        MaintainMemoryParams,
        MemoryPage,
        ContextParams,
        ConfigureContextParams,
        ContextView,
        HistoryParams,
        HistoryPage,
        AppInfo,
        CredentialInfo,
        PublicConfig,
        UpdateConfigParams,
        StartupPathsParams,
        StartupPaths,
        ChooseDirectoryParams,
        DirectorySelection,
        ExportParams,
        ExportResult,
        StorageInfo,
        ProjectSummary,
        ProjectsView,
        DiagnosticCheck,
        DiagnosticReport,
        ConnectionSettings,
        ConnectionProbeParams,
        ModelConnectionProbeParams,
        ConnectionStatus,
        InitializeParams,
        InitializeResult,
        OpenProjectParams,
        RelocateProjectParams,
        EmptyParams,
        DiagnosticsParams,
        RpcRequest,
        RpcNotification,
        RpcResponse,
        ErrorData,
        OperationError,
        RunLimits,
        CreateSessionParams,
        ListSessionsParams,
        SessionParams,
        GetSessionParams,
        StartRunParams,
        CancelRunParams,
        ActiveRunResult,
        CreateGoalParams,
        ListGoalsParams,
        ControlGoalParams,
        GoalPage,
        GoalView,
        SessionEventNotification,
        SessionSummary,
        SelectSessionModelParams,
        SessionView,
        SessionPage,
        SessionSignal,
        TaskFields,
        TaskView,
        TaskPage,
        TaskParams,
        CreateTaskParams,
        CreateTaskResult,
        UpdateTaskParams,
        AssignSessionParams,
        ChangePage,
        ChangeView,
        GetChangeParams,
        ListChangesParams,
        EnvironmentCatalog,
        EnvironmentProbe,
        EnvironmentProjectParams,
        SaveEnvironmentParams,
        RemoveEnvironmentParams,
        EnvironmentParams,
        BindEnvironmentParams,
        ExecutionSettings,
        SaveExecutionSettings,
        ListProgramsParams,
        ProgramParams,
        GetProgramParams,
        ProgramPage,
        ProgramView,
        ChooseEnvironmentPathParams,
        ExecutionStatus,
        OpenWebUrlParams,
        WebSearchResult,
        WebPageResult,
        CollaborationHistoryParams,
        CollaborationLink,
        CollaborationPage,
        CollaborationPageParams,
        CollaborationRequest,
        CollaborationRequestParams,
        ConnectSessionsParams,
        ControlCollaborationParams,
        ArrangeSessionWorkParams,
    )
}
