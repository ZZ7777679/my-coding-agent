"""复用事件投影生成完整的运行目录。 Build a complete run catalog from existing event projections."""

from my_agent.evolution.types import EvolutionRunItem, EvolutionRunsPage, EvolutionRunsQuery
from my_agent.sessions.projection import summarize
from my_agent.sessions.store import SessionLog
from my_agent.sessions.trace import trace_items
from my_agent.sessions.types import RunAccepted, RunFinished


def browse_runs(log: SessionLog, query: EvolutionRunsQuery) -> EvolutionRunsPage:
    """先按 Run 归组再分页，搜索整个会话中的提问。

    Group by Run before paging; search prompts across the entire session.
    """
    items = trace_items(log)
    counts: dict[str, int] = {}
    for item in items:
        if item.run_id:
            counts[item.run_id] = counts.get(item.run_id, 0) + 1
    finished = {
        fact.run_id: fact.data.status for fact in log.facts if isinstance(fact.data, RunFinished)
    }
    through = log.facts[-1].seq if log.facts else 0
    runs = [
        EvolutionRunItem(
            run_id=fact.run_id,
            seq=fact.seq,
            through_seq=through,
            prompt=fact.data.prompt,
            at=fact.at,
            status=finished.get(fact.run_id, "未记录结束"),
            event_count=counts.get(fact.run_id, 0),
        )
        for fact in log.facts
        if isinstance(fact.data, RunAccepted) and fact.run_id
    ]
    matched = [run for run in runs if query.query.casefold() in run.prompt.casefold()]
    earlier = [
        run for run in reversed(matched) if query.before_seq is None or run.seq < query.before_seq
    ]
    selected = earlier[: query.limit]
    return EvolutionRunsPage(
        session_id=log.session_id,
        title=summarize(log).title,
        total_runs=len(runs),
        total_events=len(items),
        matched_runs=len(matched),
        through_seq=through,
        runs=[run.model_copy(update={"prompt": run.prompt[:240]}) for run in selected],
        before_seq=selected[-1].seq if len(earlier) > len(selected) else None,
    )
