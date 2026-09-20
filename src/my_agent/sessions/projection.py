"""显式公开历史投影，绝不暴露 provider 原生字段。

Public projections exclude native provider data.
"""

from pydantic import TypeAdapter, ValidationError

from my_agent.execution.types import ProgramView
from my_agent.goals.state import TERMINAL_GOALS
from my_agent.goals.state import views as goal_views
from my_agent.goals.types import GoalControl, GoalCreated, GoalInputQueued, GoalSettled
from my_agent.models.types import ModelId
from my_agent.sessions.recovery_types import SessionRecovered
from my_agent.sessions.store import SessionLog
from my_agent.sessions.types import (
    AssistantCommitted,
    AuxiliaryCompleted,
    AuxiliaryStarted,
    ChatEntry,
    ProgressSynced,
    RequestStarted,
    RunAccepted,
    RunFinished,
    RunView,
    SessionAssigned,
    SessionCreated,
    SessionModelChanged,
    SessionSummary,
    ToolCompleted,
    ToolSkipped,
    ToolStarted,
)
from my_agent.web.types import WebPageResult, WebSearchResult

WEB_RESULT: TypeAdapter[WebSearchResult | WebPageResult] = TypeAdapter(
    WebSearchResult | WebPageResult
)


def selected_model(log: SessionLog) -> ModelId:
    """读取最近用户选择；旧会话沿用创建时的模型。 Use the latest choice or the initial model."""
    for fact in reversed(log.facts):
        if isinstance(fact.data, (SessionCreated, SessionModelChanged)):
            return fact.data.model_id
    from my_agent.errors import AgentError

    raise AgentError("SESSION_DAMAGED", "会话头损坏，无法读取模型选择。")


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
    synced = {fact.data.result_seq for fact in log.facts if isinstance(fact.data, ProgressSynced)}
    pending = {
        fact.seq
        for fact in log.facts
        if isinstance(fact.data, RunFinished) and fact.data.report is not None
    } - synced
    if (
        accepted is not None
        and isinstance(accepted.data, RunAccepted)
        and accepted.run_id is not None
    ):
        tail = log.facts[accepted.seq :]
        finished = next(
            (fact.data for fact in reversed(tail) if isinstance(fact.data, RunFinished)), None
        )
        tokens = [
            fact.data.turn.usage for fact in tail if isinstance(fact.data, AssistantCommitted)
        ]
        tokens.extend(fact.data.usage for fact in tail if isinstance(fact.data, AuxiliaryCompleted))
        requests = sum(isinstance(fact.data, (RequestStarted, AuxiliaryStarted)) for fact in tail)
        usage_known = len(tokens) == requests
        input_known = usage_known and all(item.input_tokens is not None for item in tokens)
        output_known = usage_known and all(item.output_tokens is not None for item in tokens)
        run = RunView(
            run_id=accepted.run_id,
            status=("stopping" if stopping else "running")
            if active
            else (finished.status if finished else "interrupted"),
            requests=requests,
            tools=sum(isinstance(fact.data, ToolStarted) for fact in tail),
            input_tokens=sum(item.input_tokens or 0 for item in tokens) if input_known else None,
            output_tokens=sum(item.output_tokens or 0 for item in tokens) if output_known else None,
            limits=accepted.data.limits,
            mode=accepted.data.mode,
            plan_document=accepted.data.plan_document,
            goal_id=accepted.data.goal_id,
            goal_role=accepted.data.goal_role,
            work_id=accepted.data.work_id,
            method=accepted.data.method,
            method_version=accepted.data.method_version,
            code=finished.code if finished else (None if active else "PROCESS_INTERRUPTED"),
            message=finished.message
            if finished
            else (None if active else "上次运行已中断，未自动重放。"),
            progress_sync="pending"
            if any(fact.seq in pending for fact in tail)
            else "synced"
            if any(fact.seq in synced for fact in tail)
            else "none",
        )
    _, complete = log.context()
    membership = next(
        (f.data for f in reversed(log.facts) if isinstance(f.data, SessionAssigned)), header
    )
    first_request = next(
        (f.data for f in log.facts if isinstance(f.data, (GoalCreated, RunAccepted))), None
    )
    if isinstance(first_request, GoalCreated):
        first_prompt = first_request.objective
    elif isinstance(first_request, RunAccepted):
        # 协作包装提示属于运行信息，不用它充当用户导航标题。
        # Internal collaboration prompts should not become user-facing navigation titles.
        first_prompt = (
            membership.role.strip() or "协作会话"
            if first_request.collaboration_id
            else first_request.prompt
        )
    else:
        first_prompt = "新会话"
    return SessionSummary(
        session_id=log.session_id,
        project_id=header.project_id,
        model_id=selected_model(log),
        title=first_prompt.replace("\n", " ")[:80],
        created_at=log.facts[0].at,
        updated_at=log.facts[-1].at,
        can_continue=complete and not active,
        issue=log.issue
        or (None if complete or active else "UNPAIRED_TOOL_CALLS")
        or ("PROGRESS_SYNC_PENDING" if pending else None),
        run=run,
        task_id=membership.task_id,
        role=membership.role,
        scope=membership.scope,
        mode=run.mode if run else header.initial_mode,
    )


def entries(log: SessionLog, before_seq: int | None) -> tuple[list[ChatEntry], int | None]:
    """按页倒选历史，限制字节数与条数，保持原顺序。

    Page history by bytes/count in original order.
    """
    result: list[ChatEntry] = []
    size = 0
    cursor: int | None = None
    ended_goals = {
        goal.goal_id: goal for goal in goal_views(log.facts) if goal.status in TERMINAL_GOALS
    }
    goal_anchors = {}
    for fact in log.facts:
        data = fact.data
        if isinstance(data, GoalControl) and data.action == "cancel":
            goal_anchors[data.goal_id] = fact.seq
        elif isinstance(data, GoalSettled):
            goal = ended_goals.get(data.goal_id)
            if goal is not None and goal.status == "completed":
                goal_anchors[data.goal_id] = fact.seq
    terminal_entries = {
        seq: ended_goals[identity]
        for identity, seq in goal_anchors.items()
        if identity in ended_goals
    }
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
        if fact.seq in terminal_entries:
            goal = terminal_entries[fact.seq]
            entry = ChatEntry.model_validate(
                {
                    **common,
                    "kind": "goal.event",
                    "text": "Goal · " + ("已取消" if goal.status == "cancelled" else "已完成"),
                    "goal_result": goal,
                }
            )
        elif isinstance(data, RunAccepted):
            if data.collaboration_id is not None:
                entry = ChatEntry.model_validate(
                    {
                        **common,
                        "kind": "collaboration.request",
                        "text": "协作请求 · " + data.collaboration_id + "\n" + data.prompt,
                    }
                )
            elif data.goal_role == "work":
                entry = ChatEntry.model_validate(
                    {
                        **common,
                        "kind": "goal.event",
                        "text": "Goal 工作单元" + (f" · {data.work_id}" if data.work_id else ""),
                    }
                )
            elif data.goal_role != "question":
                entry = ChatEntry.model_validate({**common, "kind": "user", "text": data.prompt})
        elif isinstance(data, GoalCreated):
            entry = ChatEntry.model_validate(
                {**common, "kind": "user", "text": "Goal：" + data.objective}
            )
        elif isinstance(data, GoalInputQueued):
            entry = ChatEntry.model_validate({**common, "kind": "user", "text": data.prompt})
        elif isinstance(data, GoalControl) and data.action == "answer":
            entry = ChatEntry.model_validate(
                {**common, "kind": "user", "text": "HITL 答复：" + (data.answer or "")}
            )
        elif isinstance(data, AssistantCommitted):
            entry = ChatEntry.model_validate(
                {
                    **common,
                    "kind": "assistant",
                    "message_id": data.message_id,
                    "text": data.turn.text,
                    "reasoning": data.turn.reasoning,
                    "model_id": data.model_id,
                }
            )
        elif isinstance(data, ToolStarted):
            entry = ChatEntry.model_validate(
                {**common, "kind": "tool.started", "call": data.call, "text": ""}
            )
        elif isinstance(data, (ToolCompleted, ToolSkipped)):
            web_result = None
            program_result = None
            started = next(
                (
                    item.data
                    for item in reversed(log.facts[: fact.seq - 1])
                    if item.run_id == fact.run_id
                    and isinstance(item.data, ToolStarted)
                    and item.data.call.tool_call_id == data.result.tool_call_id
                ),
                None,
            )
            program_call = (
                started.call
                if started is not None
                and started.call.name
                in {"run_command", "start_service", "read_program", "stop_program"}
                else None
            )
            if not data.result.is_error:
                if started is not None and started.call.name in {"web_search", "web_fetch"}:
                    try:
                        web_result = WEB_RESULT.validate_json(data.result.content)
                    except ValidationError:
                        # 历史不兼容时仍显示原工具正文，不伪造来源卡片。
                        # Keep raw historical output when it cannot form a valid source card.
                        pass
                if program_call is not None:
                    try:
                        program_result = ProgramView.model_validate_json(data.result.content)
                    except ValidationError:
                        # 旧结果仍能读正文；展示转换失败不影响任何执行。
                        # Fall back to the original result without gating execution.
                        pass
            entry = ChatEntry.model_validate(
                {
                    **common,
                    "kind": data.kind,
                    "result": data.result,
                    "web_result": web_result,
                    "call": program_call,
                    "program_result": program_result,
                    "text": "",
                }
            )
        elif isinstance(data, SessionRecovered):
            entry = ChatEntry.model_validate(
                {
                    **common,
                    "kind": data.kind,
                    "text": "已核对中断结果；保留未知，未重放旧操作。\n"
                    + "\n".join(
                        f"{item.tool_name}: {item.observation.message}"
                        + (f" · {item.observation.path}" if item.observation.path else "")
                        + (
                            f" · 当前状态 {item.observation.current_status}"
                            if item.observation.current_status
                            else ""
                        )
                        for item in data.items
                    ),
                }
            )
        elif isinstance(data, RunFinished):
            question = data.report.question if data.report else None
            entry = ChatEntry.model_validate(
                {
                    **common,
                    "kind": "run.finished",
                    "text": (data.message or (data.report.summary if data.report else data.status))
                    + (
                        f"\n等待答复：{question.question}\n影响：{question.impact}"
                        if question
                        else ""
                    ),
                }
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
