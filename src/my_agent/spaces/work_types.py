"""任务工作图的编辑与执行契约。

Contracts for task work graphs and execution.
"""

from pydantic import Field

from my_agent.goals.types import GoalBudget, GoalView
from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData
from my_agent.spaces.team_types import SpaceChatView
from my_agent.spaces.types import SpaceParams
from my_agent.tasks.types import TaskView
from my_agent.workflow.types import WorkId, WorkItem


class SaveWorkGraphParams(SpaceParams):
    """编辑任务定义，版本冲突保留草稿。

    Edit task definitions with draft-preserving revisions.
    """

    operation_id: EntityId
    expected_revision: int = Field(ge=1)
    items: list[WorkItem]
    owner_changes: dict[WorkId, EntityId | None] = Field(default_factory=dict)


class StartWorkGraphParams(SpaceParams):
    """用户选择工作范围与执行方式。

    Explicitly select work scope and execution mode.
    """

    operation_id: EntityId
    work_ids: list[WorkId] = Field(min_length=1)
    member_id: EntityId
    continuous: bool = False
    instruction: str = ""
    budget: GoalBudget = Field(default_factory=GoalBudget)


class WorkGraphView(ModelData):
    """工作定义、最新进度和已有运行引用。

    Definitions, progress and existing execution references.
    """

    task: TaskView
    items: list[WorkItem]
    suggested_items: list[WorkItem]
    activity: SpaceChatView
    goals: list[GoalView] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
