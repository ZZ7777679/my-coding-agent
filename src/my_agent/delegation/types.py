"""子工作单元与共同计量契约。

Worker and shared accounting contracts.
"""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData, ModelId, ModelProgress, TokenUsage
from my_agent.runtime.modes import RunMode


class WorkerSettings(ModelData):
    """默认关闭；并发是可调资源配置。

    Disabled by default; concurrency is an adjustable resource setting.
    """

    enabled: bool = False
    concurrency: Annotated[int, Field(ge=1)] = 2


class WorkerSessionParams(ModelData):
    """用户会话中的子工作入口。

    Worker access within an owning user session.
    """

    session_id: EntityId


class ConfigureWorkersParams(WorkerSessionParams):
    """保存下一次委派的能力开关。

    Save delegation settings for subsequent assignments.
    """

    settings: WorkerSettings


class SpawnWorkerArgs(ModelData):
    """一个独立、有边界的子任务；不要求收益评分。

    One bounded independent assignment, without benefit scores.
    """

    objective: Annotated[str, Field(min_length=1, max_length=16000)]
    name: str = Field(default="", description="Short work/role name for the worker card.")
    scope: str = ""
    role: Literal["implement", "research"] = "research"
    context_mode: Literal["isolated", "inherit"] = "isolated"
    mode: RunMode = "plan"


class WorkerFailure(ModelData):
    """子运行的真实失败原因，与部分成果分开保存。

    Preserve the child run's actual failure separately from partial output.
    """

    code: str
    message: str
    cause_code: str | None = None
    phase: str | None = None
    diagnostic_id: EntityId | None = None


class WorkerRecord(ModelData):
    """完整内部身份、原安排与结果入口。

    Internal identity, original assignment and result references.
    """

    worker_id: EntityId
    session_id: EntityId
    owner_session_id: EntityId
    owner_run_id: EntityId
    goal_id: EntityId | None
    model_id: ModelId
    assignment: SpawnWorkerArgs
    status: Literal[
        "queued", "running", "completed", "failed", "cancelled", "interrupted", "budget_exceeded"
    ]
    run_id: EntityId | None = None
    result: str = ""
    code: str | None = None
    failure: WorkerFailure | None = None
    created_at: str
    updated_at: str
    pending_messages: list[str] = Field(default_factory=list)
    requests: int = 0
    tools: int = 0
    active_seconds: float = 0.0
    last_seq: int | None = None
    last_event_at: str | None = None
    last_tool: str | None = None
    last_tool_status: Literal["running", "completed", "failed", "skipped"] | None = None
    model_progress: ModelProgress | None = None
    history_issue: str | None = None


class WorkerControlParams(WorkerSessionParams):
    """按已知身份停止或继续内部工作。

    Stop or continue identified internal work.
    """

    worker_id: EntityId
    action: Literal["stop", "continue"]
    prompt: str = ""


class WorkerPage(ModelData):
    """子卡片列表，不进入左侧正式会话树。

    Worker cards, excluded from the formal session tree.
    """

    settings: WorkerSettings
    workers: list[WorkerRecord]


class DelegatedUsage(ModelData):
    """镜像实际子工作消耗到原安排；不表示第二次模型调用。

    Mirror actual child usage to its assignment, never a second provider request.
    """

    kind: Literal["delegated.usage"] = "delegated.usage"
    worker_id: EntityId
    source_run_id: EntityId
    source_seq: int
    requests: int = 0
    tools: int = 0
    active_seconds: float = 0.0
    usage: TokenUsage | None = None
