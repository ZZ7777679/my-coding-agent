"""显式公开历史投影，绝不暴露 provider 原生字段。

Public projections exclude native provider data.
"""

from my_agent.sessions.store import SessionLog
from my_agent.sessions.types import (
    AssistantCommitted,
    ChatEntry,
    RequestStarted,
    RunAccepted,
    RunFinished,
    RunView,
    SessionCreated,
    SessionSummary,
    ToolCompleted,
    ToolStarted,
)


def summarize(log: SessionLog, *, active: bool = False, stopping: bool = False) -> SessionSummary:
    """从事实推导状态，重启未结束任务显示中断。

    Derive state; unfinished old runs are interrupted.
    """
    header = log.facts[0].data if log.facts else None
    if not isinstance(header, SessionCreated):
        from my_agent.errors import AgentError

        raise AgentError("SESSION_DAMAGED", "会话头损坏，无法确认项目；原文件已保留。")
    accepted = next(
        (fact for fact in reversed(log.facts) if isinstance(fact.data, RunAccepted)), None
    )
    run: RunView | None = None
    if (
        accepted is not None
        and isinstance(accepted.data, RunAccepted)
        and accepted.run_id is not None
    ):
        tail = log.facts[accepted.seq :]
        finished = next(
            (fact.data for fact in reversed(tail) if isinstance(fact.data, RunFinished)), None
        )
        turns = [fact.data.turn for fact in tail if isinstance(fact.data, AssistantCommitted)]
        requests = sum(isinstance(fact.data, RequestStarted) for fact in tail)
        usage_known = len(turns) == requests
        input_known = usage_known and all(turn.usage.input_tokens is not None for turn in turns)
        output_known = usage_known and all(turn.usage.output_tokens is not None for turn in turns)
        run = RunView(
            run_id=accepted.run_id,
            status=("stopping" if stopping else "running")
            if active
            else (finished.status if finished else "interrupted"),
            requests=requests,
            tools=sum(isinstance(fact.data, ToolStarted) for fact in tail),
            input_tokens=sum(turn.usage.input_tokens or 0 for turn in turns)
            if input_known
            else None,
            output_tokens=sum(turn.usage.output_tokens or 0 for turn in turns)
            if output_known
            else None,
            limits=accepted.data.limits,
            code=finished.code if finished else (None if active else "PROCESS_INTERRUPTED"),
            message=finished.message
            if finished
            else (None if active else "上次运行已中断，未自动重放。"),
        )
    _, complete = log.context()
    first_prompt = next(
        (f.data.prompt for f in log.facts if isinstance(f.data, RunAccepted)), "新会话"
    )
    return SessionSummary(
        session_id=log.session_id,
        project_id=header.project_id,
        model_id=header.model_id,
        title=first_prompt.replace("\n", " ")[:80],
        created_at=log.facts[0].at,
        updated_at=log.facts[-1].at,
        can_continue=complete and not active,
        issue=log.issue or (None if complete or active else "UNPAIRED_TOOL_CALLS"),
        run=run,
    )


def entries(log: SessionLog, before_seq: int | None) -> tuple[list[ChatEntry], int | None]:
    """按页倒选历史，限制字节数与条数，保持原顺序。

    Page history by bytes/count in original order.
    """
    result: list[ChatEntry] = []
    size = 0
    cursor: int | None = None
    for fact in reversed(log.facts):
        if before_seq is not None and fact.seq >= before_seq:
            continue
        data = fact.data
        entry: ChatEntry | None = None
        common = {
            "seq": fact.seq,
            "run_id": fact.run_id,
            "message_id": None,
            "call": None,
            "result": None,
        }
        if isinstance(data, RunAccepted):
            entry = ChatEntry.model_validate({**common, "kind": "user", "text": data.prompt})
        elif isinstance(data, AssistantCommitted):
            entry = ChatEntry.model_validate(
                {
                    **common,
                    "kind": "assistant",
                    "message_id": data.message_id,
                    "text": data.turn.text,
                }
            )
        elif isinstance(data, ToolStarted):
            entry = ChatEntry.model_validate(
                {**common, "kind": "tool.started", "call": data.call, "text": ""}
            )
        elif isinstance(data, ToolCompleted):
            entry = ChatEntry.model_validate(
                {**common, "kind": "tool.completed", "result": data.result, "text": ""}
            )
        elif isinstance(data, RunFinished):
            entry = ChatEntry.model_validate(
                {**common, "kind": "run.finished", "text": data.message or data.status}
            )
        if entry is None:
            continue
        length = len(entry.model_dump_json().encode("utf-8"))
        if result and (len(result) >= 40 or size + length > 350000):
            cursor = result[-1].seq
            break
        size += length
        result.append(entry)
    return list(reversed(result)), cursor
