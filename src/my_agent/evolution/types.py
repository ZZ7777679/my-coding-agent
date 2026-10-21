"""自进化的公开数据，不包含运行服务或凭据。

Public evolution data without services or credentials.
"""

import json
from importlib.resources import files
from typing import Annotated, Literal

from pydantic import Field

from my_agent.execution.types import ProgramView, RunCommandArgs
from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData, ModelId, TokenUsage
from my_agent.runtime.settings import ModelLimits

_DEFAULTS = json.loads(files("my_agent").joinpath("defaults.json").read_text(encoding="utf-8"))[
    "evolution"
]

ResourceKind = Literal[
    "preference", "memory", "project_rule", "skill", "tool_guidance", "workstyle", "code"
]


class EvolutionSource(ModelData):
    """关联用户选择的事实，不复制整个会话。

    Reference selected facts without copying a session.
    """

    session_id: EntityId | None = None
    run_id: EntityId | None = None
    seq: Annotated[int, Field(ge=1)] | None = None
    diagnostic_id: EntityId | None = None
    scope: Literal["session", "run", "event"] | None = None
    through_seq: Annotated[int, Field(ge=1)] | None = None
    candidate_id: EntityId | None = None
    content_revision: int | None = None
    comparison_at: str | None = None
    candidate_status: str | None = None


class EvolutionRunsQuery(ModelData):
    """运行目录按轮分页，不受一轮工具数量影响。

    Page runs independently of how many tool events each run contains.
    """

    project_id: EntityId
    session_id: EntityId
    before_seq: int | None = None
    query: str = ""
    limit: Annotated[int, Field(ge=1, le=100)] = 20


class EvolutionRunItem(ModelData):
    """选择一轮所需的提问、状态、序号和事件数量。

    Prompt, status, positions and event counts needed to select a run.
    """

    run_id: EntityId
    seq: int
    through_seq: int
    prompt: str
    at: str
    status: str
    event_count: int


class EvolutionRunsPage(ModelData):
    """会话总范围与匹配运行页，正文仍按需读取。

    Session totals and matching run page, leaving bodies on demand.
    """

    session_id: EntityId
    title: str
    total_runs: int
    total_events: int
    matched_runs: int
    through_seq: int
    runs: list[EvolutionRunItem]
    before_seq: int | None


class EvolutionSelection(ModelData):
    """接纳时明确展开的选择范围；数量是事件数而非正文用量。

    Accepted selection scope; counts represent events rather than text usage.
    """

    source: EvolutionSource
    title: str
    event_count: int


class DiagnosticFrame(ModelData):
    """异常位置，不保存源码行或局部变量。

    Exception location without source lines or locals.
    """

    file: str
    line: int
    function: str


class EvolutionRecoveryResult(ModelData):
    """独立恢复脚本的事实结果。

    Factual output from the independent recovery entry.
    """

    candidate_id: EntityId
    at: str
    status: Literal["reverted", "changed"]
    path: str
    message: str


class DiagnosticEvent(ModelData):
    """一次诊断的实际原因和归属。

    Actual cause and ownership of one diagnostic.
    """

    diagnostic_id: EntityId
    at: str
    component: str
    level: Literal["warning", "error"]
    code: str
    message: str
    cause_code: str | None = None
    phase: str | None = None
    exception_types: list[str] = Field(default_factory=list)
    frames: list[DiagnosticFrame] = Field(default_factory=list)
    project_id: EntityId | None = None
    source: EvolutionSource = Field(default_factory=EvolutionSource)


class EvolutionScope(ModelData):
    """现场入口的范围身份，接纳时展开并冻结会话记录。

    Contextual scope identity, expanded and frozen when a review is accepted.
    """

    kind: Literal["project", "task", "session"]
    identity: EntityId


class EvolutionQuery(ModelData):
    """按项目与游标读取轻量记录。

    Read project records with a cursor.
    """

    project_id: EntityId
    origin: EvolutionScope | None = None
    before: str | None = None
    jobs_before: str | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 30


class EvolutionBudget(ModelLimits):
    """单次改进作业的独立预算，默认值不读取普通对话设置。

    Independent per-job budgets, defaulted without reading ordinary chat settings.
    """

    max_requests: Annotated[int, Field(ge=1)] | None = _DEFAULTS["budget"]["max_requests"]
    max_tools: Annotated[int, Field(ge=1)] | None = _DEFAULTS["budget"]["max_tools"]
    max_seconds: Annotated[int, Field(ge=1)] | None = _DEFAULTS["budget"]["max_seconds"]
    request_timeout_seconds: Annotated[int, Field(ge=1)] | None = _DEFAULTS["budget"][
        "request_timeout_seconds"
    ]
    max_output_tokens: Annotated[int, Field(ge=1)] | None = _DEFAULTS["budget"]["max_output_tokens"]
    max_context_bytes: Annotated[int, Field(ge=4096)] | None = _DEFAULTS["budget"][
        "max_context_bytes"
    ]
    max_response_bytes: Annotated[int, Field(ge=1024)] | None = _DEFAULTS["budget"][
        "max_response_bytes"
    ]


class EvolutionSettings(ModelData):
    """项目的复盘与采用选择，不影响普通任务。

    Project learning choices do not gate normal work.
    """

    project_id: EntityId
    automatic_review: bool = False
    auto_apply: list[ResourceKind] = Field(default_factory=list)
    model_id: ModelId = "deepseek-v4.1-flash"
    input_chars: Annotated[int, Field(ge=1)] | None = _DEFAULTS["input_chars"]
    budget: EvolutionBudget = Field(default_factory=EvolutionBudget)


class SaveEvolutionFeedback(ModelData):
    """最小反馈只需要项目与文字。

    Minimal feedback needs a project and text.
    """

    project_id: EntityId
    feedback_id: EntityId
    text: Annotated[str, Field(min_length=1)]
    kind: Literal["problem", "success", "instruction"] = "problem"
    source: EvolutionSource = Field(default_factory=EvolutionSource)
    sources: list[EvolutionSource] = Field(default_factory=list)
    target: "EvolutionTarget | None" = None
    origin: EvolutionScope | None = None


class EvolutionFeedback(SaveEvolutionFeedback):
    """保留原反馈及时间，候选不改写用户意见。

    Preserve feedback and time independently of candidates.
    """

    created_at: str
    review_job_id: EntityId | None = None
    contextual_sources: list[EvolutionSource] = Field(default_factory=list)


class EvolutionTarget(ModelData):
    """明确资源身份，路径由所选项目解析。

    Explicit resource identity resolved against the project.
    """

    kind: ResourceKind
    identity: str
    scope: Literal["user", "project"] = "project"


class EvolutionComparison(ModelData):
    """实际比较或人工反馈，未知不伪造评分。

    Actual comparison or feedback without invented scores.
    """

    at: str
    summary: str
    outcome: Literal["not_checked", "improved", "unchanged", "regressed", "inconclusive"]
    method: Literal["user", "model", "execution"] = "user"
    source: EvolutionSource = Field(default_factory=EvolutionSource)
    content_revision: Annotated[int, Field(ge=1)] | None = None


class EvolutionResourceReference(ModelData):
    """实际读过的资源身份和版本，不由模型声明阅读事实。

    Identity and version of an actually read resource, supplied by the host.
    """

    target: EvolutionTarget
    version: str | None = None


class EvolutionCandidate(ModelData):
    """修改版本与采用事实，独立于原业务结果。

    Candidate revision and adoption separate from task outcomes.
    """

    candidate_id: EntityId
    review_job_id: EntityId | None = None
    finding_id: str | None = None
    project_id: EntityId
    title: str
    rationale: str
    target: EvolutionTarget
    before: str | None = None
    after: str
    feedback_ids: list[EntityId] = Field(default_factory=list)
    sources: list[EvolutionSource] = Field(default_factory=list)
    resource_sources: list[EvolutionResourceReference] = Field(default_factory=list)
    status: Literal["draft", "applied", "reverted", "partial"] = "draft"
    comparisons: list[EvolutionComparison] = Field(default_factory=list)
    revision: int = 1
    content_revision: Annotated[int, Field(ge=1)] = 1
    created_at: str
    updated_at: str
    applied_at: str | None = None
    message: str = ""
    pending_action: Literal["apply", "revert"] | None = None
    change_ids: list[EntityId] = Field(default_factory=list)
    recovery_directory: str | None = None
    model_id: ModelId | None = None
    usage: TokenUsage = Field(
        default_factory=lambda: TokenUsage(input_tokens=None, output_tokens=None)
    )


class EvolutionFinding(ModelData):
    """由证据得到的问题及相关目标，不代表已经验证根因。

    Evidence-based finding and related targets, without claiming a verified root cause.
    """

    finding_id: str
    title: str
    explanation: str
    category: Literal["rule", "preference", "skill", "tool_usage", "implementation", "unknown"]
    targets: list[EvolutionTarget] = Field(default_factory=list)
    sources: list[EvolutionSource] = Field(default_factory=list)
    resources: list[EvolutionTarget] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class EvolutionCoverage(ModelData):
    """只统计选中 Trace 正文的实际阅读情况，目录不计作阅读。

    Count actual reading of selected Trace bodies, excluding index-only access.
    """

    selected: int = 0
    read: int = 0
    complete: int = 0
    unread: int = 0


class EvolutionJob(ModelData):
    """后台改进任务有独立状态和成本。

    Background improvement has independent state and cost.
    """

    job_id: EntityId
    project_id: EntityId
    origin: EvolutionScope | None = None
    status: Literal["running", "completed", "failed", "cancelled", "interrupted"]
    candidate_id: EntityId | None = None
    candidate_ids: list[EntityId] = Field(default_factory=list)
    review_job_id: EntityId | None = None
    mode: Literal["investigate", "propose"] = "propose"
    findings: list[EvolutionFinding] = Field(default_factory=list)
    summary: str = ""
    response_text: str = ""
    message: str = ""
    requests: int = 0
    # 旧作业未记录预算，保留未知；新作业在接纳时冻结，不随设置变动。
    # Legacy budgets remain unknown; new jobs freeze them at acceptance.
    budget: EvolutionBudget | None = None
    updated_at: str = ""
    accepted_at: str = ""
    request: "GenerateEvolutionCandidate | None" = None
    experiment_directory: str | None = None
    programs: list[ProgramView] = Field(default_factory=list)
    omitted_paths: list[str] = Field(default_factory=list)
    details_available: bool = False
    review_input: "EvolutionInput | None" = None
    usage: TokenUsage = Field(
        default_factory=lambda: TokenUsage(input_tokens=None, output_tokens=None)
    )


class EvolutionCandidateSummary(ModelData):
    """列表不携带补丁与资源全文。

    List entries omit patches and resource bodies.
    """

    candidate_id: EntityId
    title: str
    target: EvolutionTarget
    status: str
    updated_at: str
    message: str
    content_revision: int = 1
    comparison: EvolutionComparison | None = None


class EvolutionPage(ModelData):
    """桌面概览保留局部读取问题。

    Desktop overview retains individual read issues.
    """

    settings: EvolutionSettings
    feedback: list[EvolutionFeedback] = Field(default_factory=list)
    candidates: list[EvolutionCandidateSummary] = Field(default_factory=list)
    diagnostics: list[DiagnosticEvent] = Field(default_factory=list)
    jobs: list[EvolutionJob] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    next_cursor: str | None = None
    jobs_next_cursor: str | None = None


class EvolutionResourceQuery(ModelData):
    """读取当前资源或准备新资源。

    Read a current resource or prepare a new one.
    """

    project_id: EntityId
    target: EvolutionTarget


class EvolutionResource(ModelData):
    """实际资源正文与版本线索。

    Actual resource content and version information.
    """

    target: EvolutionTarget
    content: str | None
    label: str
    version: str | None = None
    reference_content: str | None = None


class GenerateEvolutionCandidate(ModelData):
    """从问题与证据开始调查，或对明确资源生成候选。

    Investigate evidence first, or propose changes to an explicit resource.
    """

    project_id: EntityId
    origin: EvolutionScope | None = None
    target: EvolutionTarget | None = None
    mode: Literal["investigate", "propose"] = "propose"
    review_job_id: EntityId | None = None
    finding_ids: list[str] = Field(default_factory=list)
    feedback_ids: list[EntityId] = Field(default_factory=list)
    candidate_ids: list[EntityId] = Field(default_factory=list)
    instruction: str = ""
    sources: list[EvolutionSource] = Field(default_factory=list)


class EvolutionMaterial(ModelData):
    """一份实际参考材料及其来源，正文是本次纳入的部分。

    One reference with provenance and the exact included content.
    """

    kind: Literal["feedback", "memory", "trace", "diagnostic", "index", "resource", "improvement"]
    title: str
    source: EvolutionSource = Field(default_factory=EvolutionSource)
    content: str
    total_chars: int
    truncated: bool = False
    offset: int = 0
    resource: EvolutionResourceReference | None = None


class EvolutionInput(ModelData):
    """预览与复盘共用的材料结构；作业保存接纳时的快照。

    Shared preview/review input; jobs retain the accepted snapshot.
    """

    resource: EvolutionResource | None = None
    instruction: str
    materials: list[EvolutionMaterial] = Field(default_factory=list)
    input_chars: int | None
    included_chars: int = 0
    omitted_materials: int = 0
    prepared_at: str
    selections: list[EvolutionSelection] = Field(default_factory=list)
    trace_count: int = 0
    coverage: EvolutionCoverage = Field(default_factory=EvolutionCoverage)
    screening: list["EvolutionEpisode"] = Field(default_factory=list)
    episode_count: int = 0


class EvolutionEpisode(ModelData):
    """本地筛选线索，不将排序或重复现象冒充模型结论。

    Local screening leads, never a claim of model findings or verified causes.
    """

    title: str
    reasons: list[str]
    count: int
    representative: EvolutionSource
    related: list[EvolutionSource] = Field(default_factory=list)
    excerpt: str = ""


class SaveEvolutionCandidate(ModelData):
    """保存用户可编辑的候选正文。

    Save editable candidate content.
    """

    project_id: EntityId
    candidate_id: EntityId
    title: str
    rationale: str
    after: str
    revision: int


class CreateEvolutionCandidate(EvolutionResourceQuery):
    """从当前真实资源创建人工草稿。

    Create a draft from the actual current resource.
    """

    title: str
    rationale: str = ""
    after: str
    feedback_ids: list[EntityId] = Field(default_factory=list)


class CompareEvolutionCandidate(ModelData):
    """保存评价及证据，未执行的检查不生成结果。

    Record evaluation and evidence, not invented checks.
    """

    project_id: EntityId
    candidate_id: EntityId
    summary: str
    outcome: Literal["improved", "unchanged", "regressed", "inconclusive"]
    source: EvolutionSource = Field(default_factory=EvolutionSource)


class EvolutionCatalogItem(ModelData):
    """可选资源的名称和身份。

    Display names and identities of available resources.
    """

    target: EvolutionTarget
    label: str


class EvolutionCatalog(ModelData):
    """不携带资源全文的目录。

    Resource directory without full content.
    """

    items: list[EvolutionCatalogItem]
    issues: list[str] = Field(default_factory=list)


class EvolutionControl(ModelData):
    """操作一个明确候选，不操作整个项目。

    Control an explicit candidate, not the whole project.
    """

    project_id: EntityId
    candidate_id: EntityId
    action: Literal["apply", "revert"]


class EvolutionCandidateParams(ModelData):
    """读取单个候选，详情按需加载。

    Load one candidate on demand.
    """

    project_id: EntityId
    candidate_id: EntityId


class EvolutionExperimentParams(EvolutionCandidateParams):
    """同一命令在原版与候选副本各执行一次。

    Run the same command once against each isolated baseline/candidate copy.
    """

    command: RunCommandArgs
    exclude: list[str] = Field(
        default_factory=lambda: [
            ".git",
            ".venv",
            "node_modules",
            ".artifacts",
            "__pycache__",
            ".env",
            ".env.*",
        ]
    )


class EvolutionJobControl(ModelData):
    """停止一个明确维护任务。

    Stop one explicit maintenance job.
    """

    project_id: EntityId
    job_id: EntityId


EVOLUTION_TYPES = (
    EvolutionQuery,
    EvolutionSettings,
    SaveEvolutionFeedback,
    EvolutionFeedback,
    EvolutionPage,
    EvolutionResourceQuery,
    EvolutionResource,
    GenerateEvolutionCandidate,
    SaveEvolutionCandidate,
    EvolutionCandidate,
    EvolutionControl,
    EvolutionJobControl,
    EvolutionJob,
    EvolutionCandidateParams,
    CreateEvolutionCandidate,
    CompareEvolutionCandidate,
    EvolutionCatalog,
    EvolutionExperimentParams,
    EvolutionInput,
    EvolutionRunsQuery,
    EvolutionRunsPage,
)
