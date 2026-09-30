"""持久事实与公开视图分离。

Separate durable facts from public session views.
"""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.delegation.types import DelegatedUsage
from my_agent.execution.types import ProgramView
from my_agent.goals.types import (
    GoalControl,
    GoalCreated,
    GoalInputQueued,
    GoalSettled,
    GoalStopped,
    GoalView,
)
from my_agent.identifiers import EntityId
from my_agent.models.types import (
    ModelData,
    ModelId,
    ModelProgress,
    ModelTurn,
    TokenUsage,
    ToolCall,
    ToolResult,
)
from my_agent.runtime.context import ContextManifest
from my_agent.runtime.modes import RunMode
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.recovery_types import SessionRecovered
from my_agent.web.types import WebPageResult, WebSearchResult
from my_agent.workflow.types import WorkId, WorkMethod, WorkReport

SessionId = EntityId

RunStatus = Literal[
    "running", "stopping", "completed", "failed", "cancelled", "budget_exceeded", "interrupted"
]


class SessionCreated(ModelData):
    """会话的不可变项目与初始模型选择。

    Immutable project and initial model selection.
    """

    kind: Literal["session.created"] = "session.created"
    project_id: str
    model_id: ModelId
    task_id: SessionId | None = None
    creation_operation_id: SessionId | None = None
    role: str = ""
    scope: str = ""
    initial_mode: RunMode = "plan"
    worker_owner_session_id: SessionId | None = None
    inherited_context: str = ""


class SessionAssigned(ModelData):
    """用户修改归属与分工，追加事实而不重写旧对话。

    Append user membership changes without rewriting chats.
    """

    kind: Literal["session.assigned"] = "session.assigned"
    operation_id: SessionId
    task_id: SessionId
    role: str
    scope: str


class SessionModelChanged(ModelData):
    """用户选择后续请求的模型，保留原会话与历史。

    Select the next model without replacing history.
    """

    kind: Literal["session.model_changed"] = "session.model_changed"
    operation_id: SessionId
    model_id: ModelId


class RunAccepted(ModelData):
    """一次原子接纳事实包含输入、幂等标识与预算。

    Atomic acceptance with input and budgets.
    """

    kind: Literal["run.accepted"] = "run.accepted"
    operation_id: SessionId
    prompt: str
    limits: RunLimits
    requested_limits: RunLimits | None
    mode: RunMode = "plan"
    plan_document: str | None = None
    goal_id: SessionId | None = None
    goal_role: Literal["work", "question"] | None = None
    active_time_limit_seconds: Annotated[float, Field(gt=0)] | None = None
    work_id: WorkId | None = None
    method: WorkMethod | None = None
    method_version: str | None = None
    collaboration_id: SessionId | None = None


class RequestStarted(ModelData):
    """请求发出前计数并保存消息身份。

    Count a request and persist its message ID before sending.
    """

    kind: Literal["request.started"] = "request.started"
    message_id: SessionId
    model_id: ModelId | None = None
    task_id: SessionId | None = None
    task_revision: Annotated[int, Field(ge=1)] | None = None
    context: ContextManifest | None = None


class AuxiliaryStarted(ModelData):
    """工具内辅助模型请求在发送前入账，不改变主对话配对。

    Charge an auxiliary model request before sending without changing chat pairing.
    """

    kind: Literal["auxiliary.started"] = "auxiliary.started"
    request_id: SessionId
    tool_call_id: str
    model_id: ModelId
    purpose: Literal["web_search", "compaction"] = "web_search"


class AuxiliaryCompleted(ModelData):
    """保存辅助请求实际用量，失败或中断未报告用量保持未知。

    Store reported auxiliary usage; failed or interrupted requests remain unknown.
    """

    kind: Literal["auxiliary.completed"] = "auxiliary.completed"
    request_id: SessionId
    usage: TokenUsage


class AssistantCommitted(ModelData):
    """完整回合事实，含仅供模型续接的原生字段。

    Complete turn with private continuation.
    """

    kind: Literal["assistant.committed"] = "assistant.committed"
    message_id: SessionId
    model_id: ModelId | None = None
    turn: ModelTurn
    model_progress: ModelProgress | None = None


class ToolStarted(ModelData):
    """执行前保存工具意图。

    Persist tool intent before execution.
    """

    kind: Literal["tool.started"] = "tool.started"
    call: ToolCall


class ToolCompleted(ModelData):
    """实际工具结果事实。

    Fact containing the actual tool result.
    """

    kind: Literal["tool.completed"] = "tool.completed"
    result: ToolResult


class ToolSkipped(ModelData):
    """明确未执行的调用，与实际完成区分。

    Explicitly skipped calls, distinct from completed work.
    """

    kind: Literal["tool.skipped"] = "tool.skipped"
    result: ToolResult


class RunWaitChanged(ModelData):
    """协作等待是运行内持久事实，区别于 HITL。

    Collaboration waits are durable run facts, distinct from HITL.
    """

    kind: Literal["run.wait_changed"] = "run.wait_changed"
    request_id: SessionId | None
    waited_seconds: Annotated[float, Field(ge=0)] = 0.0


class RunFinished(ModelData):
    """清理后的终态与公开错误。

    Terminal state and public error after cleanup.
    """

    kind: Literal["run.finished"] = "run.finished"
    status: Literal["completed", "failed", "cancelled", "budget_exceeded", "interrupted"]
    code: str | None
    message: str | None
    model_progress: ModelProgress | None = None
    # 仅记录宿主单调时钟测得的活跃耗时，旧日志 / 崩溃未知时保留 None。
    # Record host-measured monotonic active time; old logs and crashes remain unknown.
    elapsed_seconds: Annotated[float, Field(ge=0)] | None = None
    # 失败响应仍可报告真实计量；显式关联未提交请求，不制造完整模型回合。
    # Failed responses can report usage; link the unanswered request without a complete turn.
    failed_request_id: SessionId | None = None
    failed_request_usage: TokenUsage | None = None
    report: WorkReport | None = None
    # 宿主只在完整配对边界让出执行；不是模型自行宣布一个工作单元完成。
    # Only the host yields at a paired boundary; this is not a model's completion claim.
    checkpoint: bool = False


class ProgressSynced(ModelData):
    """报告已同步到共享进度的确认；不将跨文件保存冒充事务。

    Acknowledge report synchronization without claiming a cross-file transaction.
    """

    kind: Literal["progress.synced"] = "progress.synced"
    result_seq: Annotated[int, Field(ge=1)]
    task_id: SessionId | None
    task_revision: Annotated[int, Field(ge=1)] | None


FactData = Annotated[
    SessionCreated
    | SessionAssigned
    | SessionModelChanged
    | RunAccepted
    | RequestStarted
    | AuxiliaryStarted
    | AuxiliaryCompleted
    | AssistantCommitted
    | ToolStarted
    | ToolCompleted
    | ToolSkipped
    | RunFinished
    | RunWaitChanged
    | DelegatedUsage
    | ProgressSynced
    | GoalCreated
    | GoalControl
    | GoalSettled
    | GoalStopped
    | GoalInputQueued
    | SessionRecovered,
    Field(discriminator="kind"),
]


class Fact(ModelData):
    """版本化单行记录，序号区别于 RPC ID。

    Versioned record with a sequence independent of RPC.
    """

    schema_version: Literal[1] = 1
    session_id: SessionId
    run_id: SessionId | None
    seq: Annotated[int, Field(ge=1)]
    at: str
    data: FactData


class RunView(ModelData):
    """公开运行计数；未知用量与未结束清理明确呈现。

    Public counts and explicit unknown usage.
    """

    run_id: SessionId
    status: RunStatus
    requests: int
    tools: int
    input_tokens: int | None
    output_tokens: int | None
    limits: RunLimits
    code: str | None
    message: str | None
    mode: RunMode = "plan"
    plan_document: str | None = None
    progress_sync: Literal["none", "pending", "synced"] = "none"
    goal_id: SessionId | None = None
    goal_role: Literal["work", "question"] | None = None
    work_id: WorkId | None = None
    method: WorkMethod | None = None
    method_version: str | None = None
    waiting_for: SessionId | None = None
    waited_seconds: float = 0.0


class SessionSummary(ModelData):
    """会话列表条目，不泄露原生模型状态。

    Session list entry without native provider state.
    """

    session_id: SessionId
    project_id: str
    model_id: ModelId
    title: str
    created_at: str
    updated_at: str
    can_continue: bool
    issue: str | None
    run: RunView | None
    task_id: SessionId | None = None
    role: str = ""
    scope: str = ""
    mode: RunMode = "plan"


class ChatEntry(ModelData):
    """显式投影的可公开历史记录。

    Explicitly projected public history record.
    """

    seq: int
    run_id: SessionId | None
    message_id: SessionId | None
    kind: Literal[
        "user",
        "assistant",
        "tool.started",
        "tool.completed",
        "tool.skipped",
        "run.finished",
        "goal.event",
        "collaboration.request",
        "session.recovered",
    ]
    text: str
    reasoning: str = ""
    model_id: ModelId | None = None
    call: ToolCall | None
    result: ToolResult | None
    web_result: WebSearchResult | WebPageResult | None = None
    program_result: ProgramView | None = None
    goal_result: GoalView | None = None


class SessionView(ModelData):
    """有界快照含历史水位与实时预览。

    Bounded snapshot with history watermark and live preview.
    """

    summary: SessionSummary
    entries: list[ChatEntry]
    before_seq: int | None
    watermark: int
    process_epoch: SessionId
    stream_message_id: SessionId | None
    stream_model_id: ModelId | None = None
    stream_text: str
    stream_reasoning: str = ""
    delta_index: int
    model_progress: ModelProgress | None = None


class SessionPage(ModelData):
    """项目会话的游标页。

    Cursor page of project sessions.
    """

    sessions: list[SessionSummary]
    next_cursor: str | None
    active_session_ids: list[SessionId]
    unavailable_count: Annotated[int, Field(ge=0)]


class SessionSignal(ModelData):
    """轻量通知：持久变更需要重取快照，文本按增量顺序接收。

    Lightweight notifications: resync durable changes and order transient text deltas.
    """

    session_id: SessionId
    run_id: SessionId | None
    process_epoch: SessionId
    kind: Literal["changed", "text.delta", "reasoning.delta", "model.progress", "resync"]
    seq: int
    message_id: SessionId | None
    delta_index: int
    text: str
    model_progress: ModelProgress | None = None
