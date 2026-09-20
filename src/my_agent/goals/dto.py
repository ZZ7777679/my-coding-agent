"""桌面 Goal 控制契约，操作分支使用标准 JSON Schema 联合。

Desktop goal controls expressed as standard JSON Schema unions of distinct actions.
"""

from typing import Annotated, Literal

from pydantic import Field, RootModel

from my_agent.goals.types import GoalBudget, GoalDefinition
from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData
from my_agent.workflow.types import Description


class CreateGoalParams(GoalDefinition):
    """由用户在既有会话创建目标，不创建正式会话。

    Create a user goal in an existing session without creating a formal session.
    """

    session_id: EntityId


class ListGoalsParams(ModelData):
    """按事实游标读取有界目标列表。 Read bounded goals by fact cursor."""

    session_id: EntityId
    before_seq: Annotated[int, Field(ge=1)] | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 10


class GoalControlIdentity(ModelData):
    """版本和操作身份分别防止覆盖与重复执行。

    A revision prevents overwrite while an operation identity prevents duplicate execution.
    """

    session_id: EntityId
    goal_id: EntityId
    operation_id: EntityId
    expected_revision: Annotated[int, Field(ge=1)]


class GoalStateControl(GoalControlIdentity):
    """无附带预算或答复的状态控制。 State controls without hidden budgets or answers."""

    action: Literal["resume", "pause", "cancel"]


class GoalBudgetControl(GoalControlIdentity):
    """明确替换累计预算，不自动接续。 Explicitly replace cumulative budgets without resuming."""

    action: Literal["budget"]
    budget: GoalBudget


class GoalAnswerControl(GoalControlIdentity):
    """只回答指定 HITL 问题，不把普通问题当成答复。

    Answer only the named HITL question, never interpreting ordinary chatter as an answer.
    """

    action: Literal["answer"]
    question_id: EntityId
    answer: Description


class ControlGoalParams(RootModel[GoalStateControl | GoalBudgetControl | GoalAnswerControl]):
    """三个互斥分支使 Python 与桌面校验器都拒绝错误字段组合。

    Three disjoint branches let both Python and desktop reject invalid field combinations.
    """
