"""工作项、成果引用与 HITL 的严格契约。

Strict work, evidence and HITL contracts.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData

WorkId = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")]
Description = Annotated[str, Field(min_length=1, max_length=16000, pattern=r"\S")]
WorkMethod = Literal["discuss", "plan", "implement", "diagnose", "review", "handoff"]


class EventRef(ModelData):
    """模型提供的可选会话引用；报告自身的来源由宿主另行记录。

    Optional model-supplied references; the host records the report's own provenance separately.
    """

    session_id: EntityId
    run_id: EntityId
    seq: Annotated[int, Field(ge=1)]


class EvidenceRef(EventRef):
    """模型声明的来源类别与用途，不等同于宿主验证通过。

    Model-declared source kinds and uses are not host-verified success.
    """

    kind: Literal["tool_result", "assistant", "user"]
    expectation: Literal["observed", "succeeded"] = "observed"


class HumanQuestion(ModelData):
    """需用户答复的具体问题及影响，不把闲聊或超时当作回答。

    A specific question and its impact, never answered by chatter or elapsed time.
    """

    question_id: EntityId
    question: Description
    impact: Description
    options: list[Annotated[str, Field(min_length=1, max_length=1024, pattern=r"\S")]] = Field(
        default_factory=list
    )


class WorkItem(ModelData):
    """一个有意义的工作单元；依赖和反馈不等同于单个工具调用。

    A meaningful work unit with dependencies and feedback, not an individual tool call.
    """

    work_id: WorkId
    title: Annotated[str, Field(min_length=1, max_length=512, pattern=r"\S")]
    scope: Description
    status: Literal["planned", "in_progress", "completed", "waiting"]
    depends_on: list[WorkId] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    feedback_from: list[EvidenceRef] = Field(default_factory=list)
    method: WorkMethod = "implement"
    stage_id: str | None = None


class CriterionResult(ModelData):
    """模型逐项判断，明确未满足、未验证与等待用户验收。

    Per-criterion model judgments distinguish unmet, unchecked and user acceptance.
    """

    criterion_id: WorkId
    status: Literal["met", "unmet", "not_checked", "needs_user"]
    explanation: Description
    evidence: list[EvidenceRef] = Field(default_factory=list)


class SharedDecision(ModelData):
    """本任务内需共享的决定，明确区分用户要求和建议。

    Task-local decisions distinguish user direction from proposals.
    """

    text: Description
    status: Literal["user_confirmed", "proposal"] = "user_confirmed"


class WorkReport(ModelData):
    """一次完整工作运行的结构化结果；不会自行改变用户目标或任务状态。

    A structured work-run result that never changes the user's objective or task status.
    """

    summary: Description
    outcome: Literal["continue", "complete", "wait", "return"]
    next_action: Annotated[str, Field(max_length=16000)] = ""
    next_work_id: WorkId | None = None
    criteria: list[CriterionResult] = Field(default_factory=list)
    work_items: list[WorkItem] = Field(default_factory=list)
    question: HumanQuestion | None = None
    decisions: list[SharedDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_result(self) -> Self:
        """只检查记录身份和 HITL 形状，不审判进度或证据是否充分。

        Check record identities and HITL shape, not the sufficiency of progress or evidence.
        """
        if len({item.work_id for item in self.work_items}) != len(self.work_items):
            raise ValueError("Duplicate work identities in one report")
        if len({item.criterion_id for item in self.criteria}) != len(self.criteria):
            raise ValueError("Duplicate criterion identities")
        if (self.outcome == "wait") != (self.question is not None):
            raise ValueError("Waiting requires a question; other outcomes cannot contain one")
        return self


class SourcedWorkItem(ModelData):
    """宿主附加来源，保留模型判断与事实出处的区别。

    Host-attached provenance distinguishes a model judgment from its source facts.
    """

    item: WorkItem
    source: EventRef


class MemberProgress(ModelData):
    """各成员最新报告与宿主来源。

    Each member's latest report and host provenance.
    """

    report: WorkReport
    source: EventRef
    updated_at: str


class SourcedDecision(ModelData):
    """共同决定保留聊天来源，不覆盖用户手写字段。

    Shared decisions retain sources without replacing user fields.
    """

    decision: SharedDecision
    source: EventRef


class TaskWork(ModelData):
    """任务当前工作图与最近一次报告，历史在任务版本日志保留。

    Current task work graph and latest report; task revisions preserve history.
    """

    items: list[SourcedWorkItem] = Field(default_factory=list)
    last_report: WorkReport | None = None
    source: EventRef | None = None
    members: list[MemberProgress] = Field(default_factory=list)
    decisions: list[SourcedDecision] = Field(default_factory=list)
