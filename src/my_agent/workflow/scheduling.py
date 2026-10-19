"""根据已保存工作依赖选择下一个完整单元，不领取其他任务积压。

Select the next complete unit from durable dependencies without taking unrelated backlog.
"""

from collections.abc import Sequence

from my_agent.runtime.modes import RunMode
from my_agent.sessions.types import Fact, RunAccepted, RunFinished
from my_agent.workflow.types import WorkItem, WorkMethod, WorkReport


def execution_mode(method: WorkMethod) -> RunMode:
    """讨论、规划与审查沿用只读能力，不随轮次改变。

    Keep discussion, planning and review read-only across execution rounds.
    """
    return "plan" if method in {"discuss", "plan", "review"} else "normal"


def select_work(facts: Sequence[Fact], goal_id: str, shared: Sequence[WorkItem]) -> WorkItem | None:
    """仅选择本 Goal 报告过且依赖已完成的工作，外部项只作为依赖事实。

    Select only goal-owned ready work; external work is referenced solely as dependency facts.
    """
    runs = {
        fact.run_id
        for fact in facts
        if isinstance(fact.data, RunAccepted)
        and fact.data.goal_id == goal_id
        and fact.data.goal_role == "work"
    }
    owned: dict[str, WorkItem] = {}
    latest: WorkReport | None = None
    for fact in facts:
        if (
            fact.run_id in runs
            and isinstance(fact.data, RunFinished)
            and fact.data.report is not None
        ):
            latest = fact.data.report
            owned.update((item.work_id, item) for item in latest.work_items)
    if not owned:
        return None
    # 任务共同记录可能带有其他会话的更新，不能只看旧 Goal 快照。
    # Shared task state may contain newer updates from other sessions, not just old goal snapshots.
    current = {**owned, **{item.work_id: item for item in shared}}
    candidates = [current[identity] for identity in owned]
    preferred = latest.next_work_id if latest else None
    if preferred in owned:
        candidates.sort(key=lambda item: item.work_id != preferred)
    for item in candidates:
        if item.status in {"planned", "in_progress"} and all(
            dependency in current and current[dependency].status == "completed"
            for dependency in item.depends_on
        ):
            return item
    # 图是进度提示；尚未就绪时回到原 Goal，让模型说明下一步或向用户提问。
    # Graphs guide progress; if none is ready, continue the goal and let the model plan or ask.
    return None
