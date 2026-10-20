"""任务版本与公开契约，不含模型原生历史。

Task versions and public contracts without native history.
"""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.models.types import ModelData, ModelId
from my_agent.sessions.types import SessionId, SessionSummary
from my_agent.workflow.style_types import WorkStyle
from my_agent.workflow.templates import TaskWorkflow
from my_agent.workflow.types import TaskWork


class TaskFields(ModelData):
    """用户维护的共同信息；成果字段仅表示用户记录。

    User-maintained shared facts and artifact notes.
    """

    title: Annotated[str, Field(min_length=1, max_length=256, pattern=r"\S")]
    goal: Annotated[str, Field(min_length=1, max_length=16000, pattern=r"\S")]
    constraints: Annotated[str, Field(max_length=16000)] = ""
    progress: Annotated[str, Field(max_length=16000)] = ""
    decisions: Annotated[str, Field(max_length=16000)] = ""
    unresolved: Annotated[str, Field(max_length=16000)] = ""
    artifacts: Annotated[str, Field(max_length=16000)] = ""
    status: Literal["active", "completed", "archived"] = "active"


class CreateTaskParams(ModelData):
    """一次创建操作同时预留首会话身份，重试不重复创建。

    Reserve the first session for idempotent creation.
    """

    operation_id: SessionId
    project_id: str
    model_id: ModelId
    fields: TaskFields
    workflow_template_id: str | None = "builtin:personal"
    workstyle_id: SessionId | None = None
    use_project_workstyle: bool = True


class TaskParams(ModelData):
    """任务查询身份。 Task lookup identity."""

    task_id: SessionId


class UpdateTaskParams(TaskParams):
    """以版本和操作 ID 防止旧页面覆盖新结论。 Guard edits with a revision and operation identity."""

    operation_id: SessionId
    expected_revision: Annotated[int, Field(ge=1)]
    fields: TaskFields


class TaskView(ModelData):
    """任务当前版本与可追溯来源。 Current task revision with traceable provenance."""

    task_id: SessionId
    project_id: str
    revision: Annotated[int, Field(ge=1)]
    fields: TaskFields
    created_at: str
    updated_at: str
    source: Literal["user", "run_report"]
    initial_session_id: SessionId
    initial_model_id: ModelId
    work: TaskWork = Field(default_factory=TaskWork)
    workflow: TaskWorkflow | None = None
    workstyle: WorkStyle | None = None


class TaskFact(ModelData):
    """不可变任务版本；旧版本为用户纠正保留依据。

    Immutable versions retain superseded user facts.
    """

    schema_version: Literal[1] = 1
    operation_id: SessionId
    expected_revision: Annotated[int, Field(ge=0)]
    view: TaskView


class TaskSummary(ModelData):
    """树列表仅包含显示所需字段，详细共同信息按需读取。

    Navigation metadata; shared details load on demand.
    """

    task_id: SessionId
    project_id: str
    title: str
    status: Literal["active", "completed", "archived"]
    revision: int


class TaskPage(ModelData):
    """按项目分页；损坏任务单独计数，不冒充空任务。

    Project page with explicit unreadable records.
    """

    tasks: list[TaskSummary]
    next_cursor: SessionId | None
    unavailable_count: int


class CreateTaskResult(ModelData):
    """分开表达任务保存与首会话创建，失败可显式接续。

    Distinguish task saving from session creation.
    """

    task: TaskView
    session: SessionSummary | None
    session_error: str | None


class AssignSessionParams(ModelData):
    """用户设置会话归属与分工；不授予跨会话访问权限。

    User-defined membership, not history access grants.
    """

    session_id: SessionId
    task_id: SessionId
    operation_id: SessionId
    role: Annotated[str, Field(max_length=4096)] = ""
    scope: Annotated[str, Field(max_length=16000)] = ""
