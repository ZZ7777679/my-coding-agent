"""持久事实与公开视图分离。 Separate durable facts from public session views."""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.models.types import ModelData, ModelId, ModelProgress, ModelTurn, ToolCall, ToolResult
from my_agent.runtime.settings import RunLimits

SessionId = Annotated[
    str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
]
RunStatus = Literal[
    "running", "stopping", "completed", "failed", "cancelled", "budget_exceeded", "interrupted"
]


class SessionCreated(ModelData):
    """会话的不可变项目与模型身份。 Immutable project and model identity."""

    kind: Literal["session.created"] = "session.created"
    project_id: str
    model_id: ModelId


class RunAccepted(ModelData):
    """一次原子接纳事实包含输入、幂等标识与预算。 Atomic acceptance with input and budgets."""

    kind: Literal["run.accepted"] = "run.accepted"
    operation_id: SessionId
    prompt: str
    limits: RunLimits
    requested_limits: RunLimits | None


class RequestStarted(ModelData):
    """请求发出前计数并保存消息身份。 Count a request and persist its message ID before sending."""

    kind: Literal["request.started"] = "request.started"
    message_id: SessionId


class AssistantCommitted(ModelData):
    """完整回合事实，含仅供模型续接的原生字段。 Complete turn with private continuation."""

    kind: Literal["assistant.committed"] = "assistant.committed"
    message_id: SessionId
    turn: ModelTurn
    model_progress: ModelProgress | None = None


class ToolStarted(ModelData):
    """执行前保存工具意图。 Persist tool intent before execution."""

    kind: Literal["tool.started"] = "tool.started"
    call: ToolCall


class ToolCompleted(ModelData):
    """实际工具结果事实。 Fact containing the actual tool result."""

    kind: Literal["tool.completed"] = "tool.completed"
    result: ToolResult


class RunFinished(ModelData):
    """清理后的终态与公开错误。 Terminal state and public error after cleanup."""

    kind: Literal["run.finished"] = "run.finished"
    status: Literal["completed", "failed", "cancelled", "budget_exceeded", "interrupted"]
    code: str | None
    message: str | None
    model_progress: ModelProgress | None = None


FactData = Annotated[
    SessionCreated
    | RunAccepted
    | RequestStarted
    | AssistantCommitted
    | ToolStarted
    | ToolCompleted
    | RunFinished,
    Field(discriminator="kind"),
]


class Fact(ModelData):
    """版本化单行记录，序号区别于 RPC ID。 Versioned record with a sequence independent of RPC."""

    schema_version: Literal[1] = 1
    session_id: SessionId
    run_id: SessionId | None
    seq: Annotated[int, Field(ge=1)]
    at: str
    data: FactData


class RunView(ModelData):
    """公开运行计数；未知用量与未结束清理明确呈现。 Public counts and explicit unknown usage."""

    run_id: SessionId
    status: RunStatus
    requests: int
    tools: int
    input_tokens: int | None
    output_tokens: int | None
    limits: RunLimits
    code: str | None
    message: str | None


class SessionSummary(ModelData):
    """会话列表条目，不泄露原生模型状态。 Session list entry without native provider state."""

    session_id: SessionId
    project_id: str
    model_id: ModelId
    title: str
    created_at: str
    updated_at: str
    can_continue: bool
    issue: str | None
    run: RunView | None


class ChatEntry(ModelData):
    """显式投影的可公开历史记录。 Explicitly projected public history record."""

    seq: int
    run_id: SessionId | None
    message_id: SessionId | None
    kind: Literal["user", "assistant", "tool.started", "tool.completed", "run.finished"]
    text: str
    call: ToolCall | None
    result: ToolResult | None


class SessionView(ModelData):
    """有界快照含历史水位与实时预览。 Bounded snapshot with history watermark and live preview."""

    summary: SessionSummary
    entries: list[ChatEntry]
    before_seq: int | None
    watermark: int
    process_epoch: SessionId
    stream_message_id: SessionId | None
    stream_text: str
    delta_index: int
    model_progress: ModelProgress | None = None


class SessionPage(ModelData):
    """项目会话的游标页。 Cursor page of project sessions."""

    sessions: list[SessionSummary]
    next_cursor: str | None
    active_session_id: SessionId | None
    unavailable_count: Annotated[int, Field(ge=0)]


class SessionSignal(ModelData):
    """轻量通知：持久变更需要重取快照，文本按增量顺序接收。

    Lightweight notifications: resync durable changes and order transient text deltas.
    """

    session_id: SessionId
    run_id: SessionId | None
    process_epoch: SessionId
    kind: Literal["changed", "text.delta", "model.progress", "resync"]
    seq: int
    message_id: SessionId | None
    delta_index: int
    text: str
    model_progress: ModelProgress | None = None
