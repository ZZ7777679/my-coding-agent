"""从会话事实计算 Goal 账本，不维护可分歧的另一份计数。

Derive goal ledgers from session facts without a divergent counter store.
"""

from collections.abc import Sequence

from my_agent.delegation.types import DelegatedUsage
from my_agent.errors import AgentError
from my_agent.goals.types import GoalBudget, GoalUsage
from my_agent.sessions.types import (
    AssistantCommitted,
    AuxiliaryCompleted,
    AuxiliaryStarted,
    Fact,
    RequestFailed,
    RequestStarted,
    RunAccepted,
    RunFinished,
    ToolStarted,
)


def usage(
    facts: Sequence[Fact], goal_id: str, *, live_seconds: dict[str, float] | None = None
) -> GoalUsage:
    """累计相关 Run；崩溃未知耗时按该 Run 已授权时限预留，明确标为未知。

    Aggregate runs; reserve the authorized run duration after a crash and label it unknown.
    Live monotonic elapsed time replaces that reservation only for confirmed live runs.
    """
    accepted = {
        fact.run_id: fact.data
        for fact in facts
        if isinstance(fact.data, RunAccepted) and fact.data.goal_id == goal_id
    }
    relevant = [fact for fact in facts if fact.run_id in accepted and fact.run_id is not None]
    ends = {fact.run_id: fact.data for fact in relevant if isinstance(fact.data, RunFinished)}
    requests = sum(isinstance(fact.data, (RequestStarted, AuxiliaryStarted)) for fact in relevant)
    delegated = [fact.data for fact in relevant if isinstance(fact.data, DelegatedUsage)]
    requests += sum(item.requests for item in delegated)
    tokens = [
        fact.data.turn.usage for fact in relevant if isinstance(fact.data, AssistantCommitted)
    ]
    tokens.extend(fact.data.usage for fact in relevant if isinstance(fact.data, AuxiliaryCompleted))
    tokens.extend(
        fact.data.usage
        for fact in relevant
        if isinstance(fact.data, RequestFailed) and fact.data.usage is not None
    )
    tokens.extend(
        fact.data.failed_request_usage
        for fact in relevant
        if isinstance(fact.data, RunFinished) and fact.data.failed_request_usage is not None
    )
    tokens.extend(item.usage for item in delegated if item.usage is not None)
    complete_usage = requests == len(tokens)
    measured = 0.0
    reserved = 0.0
    uncertain: list[str] = []
    for run_id, start in accepted.items():
        if run_id is None:
            continue
        end = ends.get(run_id)
        if end is not None and end.elapsed_seconds is not None:
            measured += end.elapsed_seconds
        elif end is None and live_seconds is not None and run_id in live_seconds:
            measured += live_seconds[run_id]
        else:
            # 不用 UTC 时间差推算崩溃耗时，避免把离线数小时算成工作。
            # Never infer crashed runtime from UTC timestamps that include offline hours.
            reserved += start.active_time_limit_seconds or start.limits.max_seconds or 0
            uncertain.append(run_id)
    return GoalUsage(
        requests=requests,
        tools=sum(isinstance(fact.data, ToolStarted) for fact in relevant)
        + sum(item.tools for item in delegated),
        active_seconds=measured + sum(item.active_seconds for item in delegated),
        reserved_seconds=reserved,
        uncertain_run_ids=uncertain,
        input_tokens=sum(item.input_tokens or 0 for item in tokens)
        if complete_usage and all(item.input_tokens is not None for item in tokens)
        else None,
        output_tokens=sum(item.output_tokens or 0 for item in tokens)
        if complete_usage and all(item.output_tokens is not None for item in tokens)
        else None,
    )


def check_budget(
    budget: GoalBudget, consumed: GoalUsage, *, requests: int = 0, tools: int = 0
) -> None:
    """调用前检查累计余额，调大预算不会清零已发生用量。

    Check cumulative allowance before an operation; increasing limits never resets usage.
    """
    if budget.max_requests is not None and consumed.requests + requests > budget.max_requests:
        raise AgentError("BUDGET_GOAL_REQUESTS", "Goal 累计请求预算已用完，可调整后明确继续。")
    if budget.max_tools is not None and consumed.tools + tools > budget.max_tools:
        raise AgentError("BUDGET_GOAL_TOOLS", "Goal 累计工具预算已用完，可调整后明确继续。")
    if (
        budget.max_active_seconds is not None
        and consumed.active_seconds + consumed.reserved_seconds >= budget.max_active_seconds
    ):
        raise AgentError(
            "BUDGET_GOAL_TIME", "Goal 累计活跃时间预算已用完；未知耗时已单独预留，请核对后调整。"
        )
