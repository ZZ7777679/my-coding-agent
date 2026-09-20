"""纯事实投影与转移校验；没有启动模型、程序或恢复副作用。

Pure fact projection and transition checks without starting models, programs or replayed effects.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from my_agent.errors import AgentError
from my_agent.goals.ledger import check_budget, usage
from my_agent.goals.types import (
    GoalBudget,
    GoalControl,
    GoalCreated,
    GoalInputQueued,
    GoalInputView,
    GoalSettled,
    GoalStatus,
    GoalStopped,
    GoalView,
)
from my_agent.sessions.types import Fact, ProgressSynced, RunAccepted, RunFinished
from my_agent.workflow.types import HumanQuestion, WorkReport

GOAL_FACTS = (GoalCreated, GoalControl, GoalSettled, GoalStopped, GoalInputQueued)
TERMINAL_GOALS = {"completed", "cancelled"}


@dataclass
class GoalState:
    """内部投影可变状态；对外返回严格只读数据，定义始终保留原值。

    Mutable internal projection with immutable original definition and strict public data.
    """

    definition: GoalCreated
    revision: int = 1
    last_control_revision: int = 1
    status: GoalStatus = "paused"
    code: str | None = "GOAL_CREATED"
    budget: GoalBudget = field(default_factory=GoalBudget)
    question: HumanQuestion | None = None
    last_report: WorkReport | None = None
    last_result_seq: int | None = None
    operations: set[str] = field(default_factory=set)
    results: set[int] = field(default_factory=set)


def _control(state: GoalState, control: GoalControl, facts: Sequence[Fact]) -> None:
    """用户控制只改变状态 / 预算，不改目标；HITL 不能被 resume 绕过。

    User controls change state or budgets, not objectives; resume cannot bypass HITL.
    """
    if control.operation_id in state.operations:
        raise AgentError("GOAL_DUPLICATE_OPERATION", "目标操作已保存，不应重复追加。")
    # 结算只更新结果 / 用量，不能让用户正在编辑的预算无端冲突；用户控制仍严格防覆盖。
    # Settlement never edits budgets; stale budget edits may cross it, but never another control.
    budget_across_settlement = (
        control.action == "budget"
        and state.last_control_revision <= control.expected_revision < state.revision
    )
    if control.expected_revision != state.revision and not budget_across_settlement:
        raise AgentError("GOAL_VERSION_CONFLICT", "Goal 状态已变化，请重新载入。")
    if state.status in TERMINAL_GOALS:
        raise AgentError("GOAL_TERMINAL", "该 Goal 已结束；新的目标应由用户重新创建。")
    if control.action in {"resume", "answer"}:
        starts = {
            fact.run_id
            for fact in facts
            if isinstance(fact.data, RunAccepted) and fact.data.goal_id == control.goal_id
        }
        ends = {fact.run_id for fact in facts if isinstance(fact.data, RunFinished)}
        if starts - ends:
            raise AgentError("GOAL_RUN_BUSY", "上次 Goal 运行尚未清理或核对，不能重叠接续。")
    if control.action == "budget":
        if control.budget is None:
            raise AgentError("GOAL_CONTROL_INVALID", "缺少新的累计预算。")
        state.budget = control.budget
    elif control.action == "resume":
        if state.question is not None:
            raise AgentError("GOAL_NEEDS_ANSWER", "请先回答此 Goal 当前等待的具体问题。")
        if state.status == "active":
            raise AgentError("GOAL_ALREADY_ACTIVE", "Goal 已在运行，不重复接续。")
        state.status, state.code = "active", None
    elif control.action == "pause":
        if state.status == "paused":
            raise AgentError("GOAL_ALREADY_PAUSED", "Goal 已暂停。")
        state.status, state.code = "paused", "USER_PAUSED"
    elif control.action == "cancel":
        state.status, state.code, state.question = "cancelled", "USER_CANCELLED", None
    elif control.action == "answer":
        if state.question is None or state.question.question_id != control.question_id:
            raise AgentError("GOAL_QUESTION_MISMATCH", "答复不对应当前等待的问题。")
        state.status, state.code, state.question = "active", None, None
    state.operations.add(control.operation_id)
    state.revision += 1
    state.last_control_revision = state.revision


def _settle(state: GoalState, event: GoalSettled, facts: Sequence[Fact]) -> None:
    """仅从已保存的对应 Run 推导结果，不从模型完成措辞推断。

    Derive outcomes only from the matching durable run, never a model's completion wording.
    """
    if event.result_seq in state.results or (
        state.last_result_seq is not None and event.result_seq <= state.last_result_seq
    ):
        raise AgentError("GOAL_RESULT_CONFLICT", "该运行结果已处理或早于当前结果。")
    result = next((fact for fact in facts if fact.seq == event.result_seq), None)
    if result is None or not isinstance(result.data, RunFinished):
        raise AgentError("GOAL_RESULT_MISSING", "Goal 结果必须引用已保存的运行终态。")
    start = next(
        (
            fact.data
            for fact in facts
            if fact.run_id == result.run_id and isinstance(fact.data, RunAccepted)
        ),
        None,
    )
    if start is None or start.goal_id != event.goal_id:
        raise AgentError("GOAL_RESULT_MISMATCH", "运行结果不属于该 Goal。")
    end = result.data
    if (
        end.report is not None
        and event.sync_error is None
        and not any(
            isinstance(fact.data, ProgressSynced) and fact.data.result_seq == result.seq
            for fact in facts
        )
    ):
        raise AgentError("GOAL_PROGRESS_PENDING", "运行结果尚未同步到共同进度，Goal 不能自动接续。")
    if end.report is not None:
        if start.goal_role == "work":
            state.last_report = end.report
        if (
            start.goal_role == "work"
            and end.report.question is not None
            and state.status != "cancelled"
        ):
            state.question = end.report.question
    state.results.add(event.result_seq)
    state.last_result_seq = event.result_seq
    state.revision += 1
    # 取消 / 暂停发生在执行中时，迟到结果仍留档，但不能推翻用户控制。
    # Late execution results remain visible without overriding user pause or cancellation.
    if state.status != "active":
        return
    if event.sync_error is not None:
        state.status, state.code = "failed", event.sync_error
    elif end.status == "failed":
        state.status, state.code = "failed", end.code
    elif end.status == "budget_exceeded":
        state.status, state.code = "budget_exceeded", end.code
    elif end.status == "interrupted":
        state.status, state.code = "interrupted", end.code
    elif end.status == "cancelled":
        state.status, state.code = "paused", end.code
    elif start.goal_role == "question":
        # 回答普通插话不完成或更换 Goal，控制器再接续原工作。
        # An ordinary answer neither completes nor replaces the goal.
        state.code = None
    elif end.checkpoint:
        state.code = None
    elif end.report is None:
        # 普通正文结束只结束一个回合；仍有活动 Goal 时继续，不把漏报当执行故障。
        # A text-only turn ends one round; an active goal continues without a report-failure gate.
        state.code = None
    elif end.report.outcome == "complete":
        state.status, state.code = "completed", None
    elif end.report.outcome == "wait":
        state.status, state.code, state.question = "waiting", "HITL", end.report.question
    elif end.report.outcome == "continue":
        state.code = None


def states(facts: Sequence[Fact]) -> dict[str, GoalState]:
    """按原始顺序重建并校验所有局部目标，不修复或重放记录。

    Rebuild and validate local goals in order without repairing or replaying records.
    """
    goals: dict[str, GoalState] = {}
    for index, fact in enumerate(facts):
        event = fact.data
        if not isinstance(event, GOAL_FACTS):
            continue
        if fact.run_id is not None:
            raise AgentError("GOAL_FACT_INVALID", "Goal 控制事实不能冒充运行工具记录。")
        if isinstance(event, GoalCreated):
            if event.goal_id in goals:
                raise AgentError("GOAL_EXISTS", "Goal 身份重复。")
            if any(state.status not in TERMINAL_GOALS for state in goals.values()):
                raise AgentError("GOAL_UNFINISHED", "当前会话已有未结束 Goal，请先取消或完成。")
            goals[event.goal_id] = GoalState(event, budget=event.budget)
            continue
        state = goals.get(event.goal_id)
        if state is None:
            raise AgentError("GOAL_NOT_FOUND", "Goal 记录不存在。")
        if isinstance(event, GoalControl):
            _control(state, event, facts[:index])
        elif isinstance(event, GoalSettled):
            _settle(state, event, facts[:index])
        elif isinstance(event, GoalStopped):
            if state.status != "active":
                raise AgentError("GOAL_NOT_ACTIVE", "Goal 已停止，不重复记录宿主停止。")
            state.status, state.code = event.status, event.code
            state.revision += 1
        elif isinstance(event, GoalInputQueued):
            if state.status != "active" or state.question is not None:
                raise AgentError("GOAL_NOT_ACTIVE", "Goal 当前不能接收自动接续的插话。")
            if any(
                isinstance(prior.data, (GoalInputQueued, RunAccepted))
                and prior.data.operation_id == event.operation_id
                for prior in facts[:index]
            ):
                raise AgentError("OPERATION_CONFLICT", "插话操作标识已经使用。")
    return goals


def validate_goal_fact(facts: Sequence[Fact], proposed: Fact) -> None:
    """保存前复用相同投影校验，失败不会改写原日志。

    Reuse projection validation before persistence, preserving the original journal on failure.
    """
    states([*facts, proposed])


def validate_goal_run(facts: Sequence[Fact], accepted: RunAccepted) -> None:
    """Run 只能关联已明确激活的目标，普通输入不能隐式接续等待 / 失败。

    Associate runs only with explicitly active goals, never implicitly resuming stopped work.
    """
    if accepted.goal_id is None:
        if accepted.goal_role is not None:
            raise AgentError("GOAL_RUN_INVALID", "普通运行不能伪造 Goal 角色。")
        return
    state = states(facts).get(accepted.goal_id)
    # 完成报告与插话可能同时到达；已接纳的问题仍可回答，并继续累计预算。
    # A queued question may race with completion; answer accepted input under the same budget.
    answering_completed = (
        accepted.goal_role == "question" and state is not None and state.status == "completed"
    )
    if (
        state is None
        or (state.status != "active" and not answering_completed)
        or state.question is not None
    ):
        raise AgentError("GOAL_NOT_ACTIVE", "请先明确接续 Goal 或回答其等待问题。")
    if accepted.goal_role is None:
        raise AgentError("GOAL_RUN_INVALID", "关联 Goal 的运行必须说明工作或普通插话。")
    if accepted.goal_role == "question":
        queued = next(
            (
                item
                for item in pending_inputs(facts, accepted.goal_id)
                if item.operation_id == accepted.operation_id
            ),
            None,
        )
        if (
            queued is None
            or queued.prompt != accepted.prompt
            or queued.requested_limits != accepted.requested_limits
        ):
            raise AgentError("GOAL_INPUT_MISMATCH", "回答运行必须对应已保存的普通插话。")
        if accepted.mode != "plan" or accepted.plan_document is not None:
            raise AgentError("GOAL_INPUT_READ_ONLY", "普通插话仅回答和读取，执行需明确切换模式。")
    previous = {
        fact.run_id
        for fact in facts
        if isinstance(fact.data, RunAccepted) and fact.data.goal_id == accepted.goal_id
    }
    settled = {
        fact.run_id
        for fact in facts
        if isinstance(fact.data, RunFinished) and fact.seq in state.results
    }
    if previous - settled:
        raise AgentError("GOAL_RESULT_PENDING", "请先核对并同步上一次 Goal 的结果，再启动新工作。")
    consumed = usage(facts, accepted.goal_id)
    check_budget(state.budget, consumed, requests=1)
    allowance = float(accepted.limits.max_seconds)
    if state.budget.max_active_seconds is not None:
        allowance = min(
            allowance,
            state.budget.max_active_seconds - consumed.active_seconds - consumed.reserved_seconds,
        )
    requested_time = accepted.active_time_limit_seconds or accepted.limits.max_seconds
    if requested_time > allowance:
        raise AgentError("BUDGET_GOAL_TIME", "本次运行时限超过 Goal 剩余活跃时间预算。")


def views(
    facts: Sequence[Fact],
    *,
    live_goals: set[str] | None = None,
    live_seconds: dict[str, float] | None = None,
) -> list[GoalView]:
    """恢复只展示中断状态；必须有当前控制器句柄才显示 active。

    Recovery displays interruption; active status requires a current controller handle.
    """
    result: list[GoalView] = []
    if not facts:
        return result
    for identity, state in states(facts).items():
        interrupted = state.status == "active" and identity not in (live_goals or set())
        result.append(
            GoalView(
                goal_id=identity,
                session_id=facts[0].session_id,
                revision=state.revision,
                objective=state.definition.objective,
                criteria=state.definition.criteria,
                budget=state.budget,
                status="interrupted" if interrupted else state.status,
                code="PROCESS_INTERRUPTED" if interrupted else state.code,
                usage=usage(facts, identity, live_seconds=live_seconds),
                question=state.question,
                last_report=state.last_report,
                last_result_seq=state.last_result_seq,
                pending_inputs=[
                    GoalInputView(operation_id=item.operation_id, prompt=item.prompt)
                    for item in pending_inputs(facts, identity)
                ],
            )
        )
    return result


def pending_inputs(facts: Sequence[Fact], goal_id: str) -> list[GoalInputQueued]:
    """以实际 Run 接纳作为消费边界，重启不默默丢弃未处理输入。

    Consume queued input only through durable run acceptance; retain pending input on restart.
    """
    accepted = {fact.data.operation_id for fact in facts if isinstance(fact.data, RunAccepted)}
    return [
        fact.data
        for fact in facts
        if isinstance(fact.data, GoalInputQueued)
        and fact.data.goal_id == goal_id
        and fact.data.operation_id not in accepted
    ]
