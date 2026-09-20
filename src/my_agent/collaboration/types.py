"""协作约定与请求的公开记录，不含 provider 原生状态。

Public collaboration agreements and requests without provider-native state.
"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from my_agent.changes.types import ChangePage
from my_agent.goals.types import GoalView
from my_agent.models.types import ModelData
from my_agent.runtime.modes import RunMode
from my_agent.sessions.types import RunView, SessionId
from my_agent.tasks.types import TaskView

ScopeText = Annotated[str, Field(min_length=1, max_length=8000, pattern=r"\S")]


class ConnectSessionsParams(ModelData):
    """用户指定定向协作范围；禁用只影响后续访问。

    A user-defined directional agreement; disabling affects subsequent access.
    """

    source_session_id: SessionId
    target_session_id: SessionId
    scope: ScopeText
    mode: RunMode = "plan"
    enabled: bool = True


class CollaborationLink(ConnectSessionsParams):
    """会话访问约定，保存任务归属与修改时间。

    A session access agreement with task ownership and modification time.
    """

    task_id: SessionId
    updated_at: str


class CollaborationRequestParams(ModelData):
    """明确的协作工作和返回要求，操作 ID 用于幂等投递。

    A bounded assignment and return requirements with an idempotent operation ID.
    """

    operation_id: SessionId
    source_session_id: SessionId
    target_session_id: SessionId
    objective: ScopeText
    inputs: Annotated[str, Field(max_length=8000)] = ""
    expected_result: Annotated[str, Field(max_length=8000)] = ""
    mode: RunMode = "plan"


class ArrangeSessionWorkParams(ModelData):
    """用户主动交接 / 审查，停止身份只用于明确移交的工作。

    User-initiated handoff or review, with stop identities limited to transferred work.
    """

    operation_id: SessionId
    source_session_id: SessionId
    target_session_id: SessionId
    kind: Literal["handoff", "review"]
    objective: ScopeText
    notes: Annotated[str, Field(max_length=16000)] = ""
    transfer_goal_id: SessionId | None = None
    transfer_run_id: SessionId | None = None

    @model_validator(mode="after")
    def stop_scope(self) -> "ArrangeSessionWorkParams":
        """审查不停止来源工作，交接仅选一个实际身份。

        Review never stops source work; handoff selects one actual work identity.
        """
        if self.transfer_goal_id and self.transfer_run_id:
            raise ValueError("Select either a goal or a run to transfer")
        if self.kind == "review" and (self.transfer_goal_id or self.transfer_run_id):
            raise ValueError("Review does not transfer execution responsibility")
        return self


class SessionWorkBrief(ModelData):
    """从已保存事实生成简报；成果快照不是当前磁盘内容。

    A brief from durable facts; artifact snapshots are not current disk contents.
    """

    task: TaskView
    source_session_id: SessionId
    source_watermark: int
    source_goal: GoalView | None
    source_run: RunView | None
    changes: ChangePage
    captured_at: str


class CollaborationRequest(ModelData):
    """请求生命周期与精确运行来源，完成结果从运行事实读取。

    Request lifecycle and exact run provenance; results come from durable run facts.
    """

    schema_version: Literal[1] = 1
    request_id: SessionId
    task_id: SessionId
    params: CollaborationRequestParams
    scope: str
    source_run_id: SessionId | None = None
    parent_request_id: SessionId | None = None
    status: Literal["preparing", "queued", "running", "completed", "failed", "cancelled", "held"]
    reason: str | None = None
    target_run_id: SessionId | None = None
    result_seq: int | None = None
    result: str = ""
    created_at: str
    updated_at: str
    arrangement: ArrangeSessionWorkParams | None = None
    brief: SessionWorkBrief | None = None


class CollaborationPageParams(ModelData):
    """本会话的约定和请求分页。 Page this session's agreements and requests."""

    session_id: SessionId
    cursor: SessionId | None = None
    limit: Annotated[int, Field(ge=1, le=50)] = 20


class CollaborationPage(ModelData):
    """双方可见状态；约定方向不因展示而反转。

    Status visible to both parties without reversing access grants.
    """

    links: list[CollaborationLink]
    requests: list[CollaborationRequest]
    next_cursor: SessionId | None
    error: str | None = None


class CollaborationHistoryParams(ModelData):
    """按约定读取对方公开历史，保留分页与来源。

    Read permitted public history with pagination and provenance.
    """

    source_session_id: SessionId
    target_session_id: SessionId
    before_seq: Annotated[int, Field(ge=1)] | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 20


class ControlCollaborationParams(ModelData):
    """用户取消请求或明确恢复尚未启动的队列项。

    Cancel a request or explicitly release an unstarted held item.
    """

    request_id: SessionId
    action: Literal["cancel", "resume"]
