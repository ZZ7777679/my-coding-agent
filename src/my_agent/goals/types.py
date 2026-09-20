"""Goal 的用户控制、持久事实与公开投影。 Goal controls, durable facts and public projections."""

from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData
from my_agent.runtime.settings import RunLimits
from my_agent.workflow.types import (
    Description,
    HumanQuestion,
    WorkId,
    WorkItem,
    WorkMethod,
    WorkReport,
)

GoalStatus = Literal[
    "active",
    "paused",
    "waiting",
    "failed",
    "budget_exceeded",
    "interrupted",
    "completed",
    "cancelled",
]


@dataclass(frozen=True)
class GoalRunBinding:
    """装配层传入的运行归属；不是模型工具或公共开始参数。

    A trusted orchestration binding, not a model tool or public run-start parameter.
    """

    goal_id: str
    role: Literal["work", "question"]
    work: WorkItem | None = None


class GoalBudget(ModelData):
    """累计预算可留空，Run 仍使用自身限额，不引入固定续跑次数。

    Optional cumulative budgets coexist with run limits without a fixed continuation count.
    """

    max_requests: Annotated[int, Field(ge=1)] | None = None
    max_tools: Annotated[int, Field(ge=1)] | None = None
    max_active_seconds: Annotated[float, Field(gt=0)] | None = None


class GoalCriterion(ModelData):
    """用户确定的完成条件；报告可按需引用，不能改写条件。

    A user-defined criterion optionally referenced, never rewritten, by model results.
    """

    criterion_id: WorkId
    description: Description


class GoalDefinition(ModelData):
    """用户目标的不可变定义；身份同时用于幂等接纳。

    An immutable user goal whose identity also supports idempotent acceptance.
    """

    goal_id: EntityId
    objective: Description
    criteria: Annotated[list[GoalCriterion], Field(min_length=1)]
    budget: GoalBudget
    limits: RunLimits | None = None
    method: WorkMethod = "implement"

    @model_validator(mode="after")
    def unique_criteria(self) -> Self:
        """完成条件身份唯一且稳定。 Criterion identities must be unique and stable."""
        if len({item.criterion_id for item in self.criteria}) != len(self.criteria):
            raise ValueError("Duplicate goal criterion identities")
        return self


class GoalCreated(GoalDefinition):
    """会话内的创建事实，不直接用作公共 RPC 参数。

    A creation fact inside the session, distinct from public RPC parameters.
    """

    kind: Literal["goal.created"] = "goal.created"


class GoalControl(ModelData):
    """明确用户操作，HITL 回答必须关联具体问题。

    Explicit user control; a HITL answer must name its question.
    """

    kind: Literal["goal.control"] = "goal.control"
    goal_id: EntityId
    operation_id: EntityId
    expected_revision: Annotated[int, Field(ge=1)]
    action: Literal["resume", "pause", "cancel", "budget", "answer"]
    budget: GoalBudget | None = None
    question_id: EntityId | None = None
    answer: Description | None = None

    @model_validator(mode="after")
    def action_fields(self) -> Self:
        """仅接受本操作需要的字段，不隐藏预算变更或代答。

        Accept only fields needed by the action, without hidden budget changes or answers.
        """
        if (self.action == "budget") != (self.budget is not None):
            raise ValueError("Only a budget action accepts a budget")
        if self.action == "answer":
            if self.question_id is None or self.answer is None:
                raise ValueError("An answer requires the exact question and answer text")
        elif self.question_id is not None or self.answer is not None:
            raise ValueError("Only an answer action accepts question fields")
        return self


class GoalSettled(ModelData):
    """控制器确认已保存 Run 的结果；任务同步故障也必须停止。

    The controller acknowledges a durable run result, stopping on task-sync failure too.
    """

    kind: Literal["goal.settled"] = "goal.settled"
    goal_id: EntityId
    result_seq: Annotated[int, Field(ge=1)]
    sync_error: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class GoalStopped(ModelData):
    """运行之外的宿主故障 / 重启事实，不伪造模型结果。

    A host failure or restart outside a run, never a fabricated model result.
    """

    kind: Literal["goal.stopped"] = "goal.stopped"
    goal_id: EntityId
    status: Literal["failed", "interrupted", "budget_exceeded"]
    code: Annotated[str, Field(min_length=1, max_length=128)]


class GoalInputQueued(ModelData):
    """普通插话持久排队，操作身份随后与回答 Run 关联。

    Persist an ordinary question whose operation identity later links to its answering run.
    """

    kind: Literal["goal.input"] = "goal.input"
    goal_id: EntityId
    operation_id: EntityId
    prompt: Annotated[str, Field(min_length=1, max_length=64000, pattern=r"\S")]
    requested_limits: RunLimits | None = None


class GoalInputView(ModelData):
    """尚未开始回答的输入，不把排队显示成已执行。

    Input still waiting for an answer, never displayed as already executed.
    """

    operation_id: EntityId
    prompt: str


class GoalUsage(ModelData):
    """从真实开始事实累计；未知耗时单独预留，不计离线时长。

    Count durable starts; reserve unknown durations separately without charging offline time.
    """

    requests: Annotated[int, Field(ge=0)] = 0
    tools: Annotated[int, Field(ge=0)] = 0
    active_seconds: Annotated[float, Field(ge=0)] = 0
    reserved_seconds: Annotated[float, Field(ge=0)] = 0
    uncertain_run_ids: list[EntityId] = Field(default_factory=list)
    input_tokens: Annotated[int, Field(ge=0)] | None = None
    output_tokens: Annotated[int, Field(ge=0)] | None = None


class GoalView(ModelData):
    """目标状态和累计用量，不以完成 Goal 自动完成 Task。

    Goal state and cumulative usage, independent of task completion.
    """

    goal_id: EntityId
    session_id: EntityId
    revision: Annotated[int, Field(ge=1)]
    objective: str
    criteria: list[GoalCriterion]
    budget: GoalBudget
    status: GoalStatus
    code: str | None
    usage: GoalUsage
    question: HumanQuestion | None = None
    last_report: WorkReport | None = None
    last_result_seq: int | None = None
    pending_inputs: list[GoalInputView] = Field(default_factory=list)


class GoalPage(ModelData):
    """按创建事实倒序分页，旧目标不被新目标覆盖。

    Page goals by descending creation sequence without overwriting older objectives.
    """

    goals: list[GoalView]
    before_seq: Annotated[int, Field(ge=1)] | None
