"""单写者 JSONL 会话存储，损坏前缀只读。

Single-writer JSONL storage with preserved corrupt tails.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from my_agent.delegation.types import DelegatedUsage
from my_agent.errors import AgentError
from my_agent.goals.ledger import check_budget, usage
from my_agent.goals.state import (
    GOAL_FACTS,
    TERMINAL_GOALS,
    states,
    validate_goal_fact,
    validate_goal_run,
)
from my_agent.goals.types import GoalControl, GoalCreated
from my_agent.models.types import JsonObject
from my_agent.runtime.messages import tool_result_message
from my_agent.sessions.pairing import pending_tools
from my_agent.sessions.recovery_types import SessionRecovered
from my_agent.sessions.types import (
    AssistantCommitted,
    AuxiliaryCompleted,
    AuxiliaryStarted,
    Fact,
    FactData,
    ProgressSynced,
    RequestStarted,
    RunAccepted,
    RunFinished,
    RunWaitChanged,
    SessionAssigned,
    SessionCreated,
    SessionId,
    SessionModelChanged,
    ToolCompleted,
    ToolSkipped,
    ToolStarted,
)
from my_agent.storage import Storage, utc_now

SESSION_ID = TypeAdapter(SessionId)
MAX_FACT_BYTES = 1048576


@dataclass
class SessionLog:
    """已确认事实前缀及不可写原因。

    Confirmed fact prefix and any read-only reason.
    """

    session_id: str
    facts: list[Fact]
    issue: str | None = None

    def context(self, positions: list[int] | None = None) -> tuple[list[JsonObject], bool]:
        """组装完整历史并标明已结束目标，未配对工具使续接失效。

        Build history with ended goals marked as history; unpaired tools prevent reuse.
        """
        messages: list[JsonObject] = []
        pending: set[str] = set()
        ended = {
            identity: state.status
            for identity, state in states(self.facts).items()
            if state.status in TERMINAL_GOALS
        }
        for fact in self.facts:
            before_count = len(messages)
            data = fact.data
            if isinstance(data, SessionCreated) and data.inherited_context:
                messages.append(
                    {
                        "role": "user",
                        "content": "Inherited source material only. "
                        "Do not continue the source's goal or replay its tools; the new assignment "
                        "below is your current objective.\n" + data.inherited_context,
                    }
                )
            if isinstance(data, GoalCreated):
                if pending:
                    return messages, False
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Historical local goal ({ended[data.goal_id]}). "
                            "This goal has ended; keep its results as context, "
                            "not as an instruction to continue working: "
                            if data.goal_id in ended
                            else "Local goal: "
                        )
                        + json.dumps(
                            {
                                "objective": data.objective,
                                "criteria": [item.model_dump() for item in data.criteria],
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
            elif isinstance(data, GoalControl) and data.action == "answer":
                if pending:
                    return messages, False
                messages.append(
                    {
                        "role": "user",
                        "content": "HITL answer: "
                        + json.dumps(
                            {
                                "question_id": data.question_id,
                                "answer": data.answer,
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
            elif isinstance(data, RunAccepted):
                if pending:
                    return messages, False
                # 只标注已结束目标的旧工作指令，后续用户消息保持原样。
                # Mark past goal work without changing the user's subsequent request.
                prefix = (
                    f"Historical work request for a {ended[data.goal_id]} goal "
                    "(not a current instruction):\n"
                    if data.goal_id in ended and data.goal_role == "work"
                    else ""
                )
                references = (
                    "\nSaved attachment references (read_attachment to reread originals): "
                    + ", ".join(data.attachment_ids)
                    if data.attachment_ids else ""
                )
                messages.append({"role": "user", "content": prefix + data.prompt + references})
            elif isinstance(data, AssistantCommitted):
                if pending:
                    return messages, False
                messages.append(data.turn.native)
                pending.update(call.tool_call_id for call in data.turn.tool_calls)
            elif isinstance(data, SessionRecovered):
                for item in data.items:
                    if item.tool_call_id not in pending:
                        return messages, False
                    pending.remove(item.tool_call_id)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": item.tool_call_id,
                            "content": json.dumps(
                                {
                                    "code": "INTERRUPTED_RESULT_RECONCILED",
                                    "observation": item.observation.model_dump(mode="json"),
                                    "message": "Original response unavailable. The user requested "
                                    "session recovery. This is an observation, not a replay. "
                                    "Do not replay "
                                    "old effects; inspect current state before new work.",
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
            elif isinstance(data, (ToolCompleted, ToolSkipped)):
                if data.result.tool_call_id not in pending:
                    return messages, False
                pending.remove(data.result.tool_call_id)
                messages.append(tool_result_message(fact))
            if positions is not None:
                positions.extend([fact.seq] * (len(messages) - before_count))
        return messages, not pending and self.issue is None


class SessionStore:
    """所有方法由受控业务线程调用，使用已有数据根写锁。

    Called on the controlled business worker under the existing data-root writer lock.
    """

    def __init__(self, storage: Storage) -> None:
        """绑定位置，不提前创建目录。

        Bind locations without creating directories.
        """
        self.storage = storage
        self.root = storage.root / "sessions"

    def path(self, session_id: str) -> Path:
        """严格验证文件标识并拒绝存储目录链接。

        Validate IDs and reject linked storage directories.
        """
        try:
            SESSION_ID.validate_python(session_id, strict=True)
        except ValidationError as exc:
            raise AgentError("SESSION_NOT_FOUND", "会话标识不正确。") from exc
        directory = self.root / session_id
        path = directory / "events.jsonl"
        if directory.resolve() != directory or path.resolve() != path:
            raise AgentError("SESSION_STORAGE_INVALID", "会话存储路径含有不支持的链接。")
        return path

    def load(self, session_id: str) -> SessionLog:
        """保留可验证前缀，损坏或超限记录不重置、不续写。

        Preserve confirmed prefixes without repair.
        """
        path = self.path(session_id)
        log = SessionLog(session_id, [])
        try:
            with path.open("rb") as stream:
                while raw := stream.readline(MAX_FACT_BYTES + 1):
                    if len(raw) > MAX_FACT_BYTES or not raw.endswith(b"\n"):
                        log.issue = "SESSION_DAMAGED_OR_TOO_LARGE"
                        break
                    try:
                        fact = Fact.model_validate_json(raw)
                        self._validate_next(log, fact)
                    except (ValidationError, AgentError):
                        log.issue = "SESSION_DAMAGED"
                        break
                    log.facts.append(fact)
            if not log.facts:
                log.issue = log.issue or "SESSION_EMPTY"
            return log
        except FileNotFoundError as exc:
            raise AgentError("SESSION_NOT_FOUND", "会话记录不存在。") from exc
        except OSError as exc:
            raise AgentError("SESSION_UNAVAILABLE", "无法读取该会话，其他会话仍可使用。") from exc

    @staticmethod
    def _validate_next(log: SessionLog, fact: Fact) -> None:
        """校验序号、运行边界与工具配对顺序。

        Validate sequences, run boundaries and tool pairing.
        """
        invalid = AgentError("SESSION_DAMAGED", "会话事实顺序不一致。")
        if fact.session_id != log.session_id or fact.seq != len(log.facts) + 1:
            raise invalid
        if not log.facts:
            if not isinstance(fact.data, SessionCreated) or fact.run_id is not None:
                raise invalid
            return
        if isinstance(fact.data, (SessionAssigned, SessionModelChanged)):
            if fact.run_id is not None:
                raise invalid
            return
        if isinstance(fact.data, GOAL_FACTS):
            validate_goal_fact(log.facts, fact)
            return
        if isinstance(fact.data, SessionRecovered):
            recovered = fact.data
            pending = pending_tools(log.facts)
            if (
                not pending
                or any(item.run_id != fact.run_id for item in pending)
                or not any(
                    item.run_id == fact.run_id and isinstance(item.data, RunFinished)
                    for item in log.facts
                )
                or any(
                    isinstance(item.data, SessionRecovered)
                    and item.data.operation_id == recovered.operation_id
                    for item in log.facts
                )
                or [
                    (item.turn_seq, item.call.tool_call_id, item.call.name, item.started_seq)
                    for item in pending
                ]
                != [
                    (item.turn_seq, item.tool_call_id, item.tool_name, item.started_seq)
                    for item in recovered.items
                ]
                or any(
                    (item.started_seq is None) != (item.observation.state == "not_started")
                    for item in recovered.items
                )
            ):
                raise invalid
            return
        if isinstance(fact.data, ProgressSynced):
            data = fact.data
            source = next((item for item in log.facts if item.seq == data.result_seq), None)
            membership = next(
                (
                    item.data
                    for item in reversed(log.facts)
                    if item.seq < data.result_seq
                    and isinstance(item.data, (SessionCreated, SessionAssigned))
                ),
                None,
            )
            if (
                fact.run_id is not None
                or source is None
                or not isinstance(source.data, RunFinished)
                or (data.task_id is None) != (data.task_revision is None)
                or membership is None
                or data.task_id != membership.task_id
                or any(
                    isinstance(item.data, ProgressSynced)
                    and item.data.result_seq == data.result_seq
                    for item in log.facts
                )
            ):
                raise invalid
            return
        if isinstance(fact.data, SessionCreated) or fact.run_id is None:
            raise invalid
        if isinstance(fact.data, DelegatedUsage):
            if not any(
                item.run_id == fact.run_id and isinstance(item.data, RunAccepted)
                for item in log.facts
            ):
                raise invalid
            return
        accepted = next((f for f in reversed(log.facts) if isinstance(f.data, RunAccepted)), None)
        if isinstance(fact.data, RunAccepted):
            validate_goal_run(log.facts, fact.data)
            if not log.context()[1]:
                raise AgentError("SESSION_READ_ONLY", "历史有未核对工具结果，不能自动重放或续跑。")
            if accepted and not any(
                isinstance(f.data, RunFinished) for f in log.facts[accepted.seq :]
            ):
                raise invalid
            if any(
                isinstance(f.data, RunAccepted)
                and (f.run_id == fact.run_id or f.data.operation_id == fact.data.operation_id)
                for f in log.facts
            ):
                raise invalid
            return
        if accepted is None or fact.run_id != accepted.run_id:
            raise invalid
        # 控制事实可以穿插在网络 / 工具等待期间，不破坏完整执行事实的配对。
        # Controls may arrive while awaiting a model or tool without breaking execution pairing.
        tail = [item for item in log.facts[accepted.seq :] if item.run_id == fact.run_id]
        if any(isinstance(f.data, RunFinished) for f in tail):
            raise invalid
        if isinstance(fact.data, RunWaitChanged):
            return
        delegated = [item.data for item in tail if isinstance(item.data, DelegatedUsage)]
        tail = [
            item for item in tail if not isinstance(item.data, (RunWaitChanged, DelegatedUsage))
        ]
        # 辅助请求入同一账本，但不打断主模型调用与工具结果的配对顺序。
        # Auxiliary calls share the ledger without disrupting main/tool execution pairing.
        auxiliary = [
            item for item in tail if isinstance(item.data, (AuxiliaryStarted, AuxiliaryCompleted))
        ]
        tail = [
            item
            for item in tail
            if not isinstance(item.data, (AuxiliaryStarted, AuxiliaryCompleted))
        ]
        if isinstance(fact.data, (RequestStarted, AuxiliaryStarted)):
            count = (
                sum(isinstance(item.data, RequestStarted) for item in tail)
                + sum(isinstance(item.data, AuxiliaryStarted) for item in auxiliary)
                + sum(item.requests for item in delegated)
            )
            if (
                isinstance(accepted.data, RunAccepted)
                and count >= accepted.data.limits.max_requests
            ):
                raise AgentError(
                    "BUDGET_REQUESTS", "本次运行的模型请求预算已用完（包含辅助搜索）。"
                )
        if isinstance(fact.data, RunFinished) and fact.data.status == "completed":
            if not log.context()[1] or (
                tail and isinstance(tail[-1].data, (RequestStarted, ToolStarted))
            ):
                raise AgentError(
                    "RUN_RESULT_UNCONFIRMED", "在途模型 / 工具尚无完整结果，不能宣布完成。"
                )
        if isinstance(fact.data, RunFinished):
            ended = fact.data
            if ended.failed_request_id is not None or ended.failed_request_usage is not None:
                if (
                    ended.status == "completed"
                    or not tail
                    or not isinstance(tail[-1].data, RequestStarted)
                    or tail[-1].data.message_id != ended.failed_request_id
                ):
                    raise invalid
        if isinstance(fact.data, RunFinished) and fact.data.checkpoint:
            if (
                not isinstance(accepted.data, RunAccepted)
                or accepted.data.goal_role != "work"
                or fact.data.status != "completed"
                or fact.data.report is not None
            ):
                raise AgentError("GOAL_CHECKPOINT_INVALID", "只有完整 Goal 工作边界可以让出执行。")
        if (
            isinstance(fact.data, (RequestStarted, AuxiliaryStarted, ToolStarted))
            and isinstance(accepted.data, RunAccepted)
            and accepted.data.goal_id is not None
        ):
            active_goal = states(log.facts)[accepted.data.goal_id]
            if active_goal.status != "active" and not (
                active_goal.status == "completed" and accepted.data.goal_role == "question"
            ):
                raise AgentError("GOAL_NOT_ACTIVE", "Goal 已停止，不能发出新请求或执行新工具。")
            # 持久边界核对次数；活跃时间由持有单调时钟的控制器核对。
            # The durable boundary checks counts; the live controller checks monotonic time.
            check_budget(
                active_goal.budget.model_copy(update={"max_active_seconds": None}),
                usage(log.facts, accepted.data.goal_id),
                requests=int(isinstance(fact.data, (RequestStarted, AuxiliaryStarted))),
                tools=int(isinstance(fact.data, ToolStarted)),
            )
        if isinstance(fact.data, AuxiliaryStarted):
            if (
                fact.data.purpose == "web_search"
                and (
                    not tail
                    or not isinstance(tail[-1].data, ToolStarted)
                    or tail[-1].data.call.tool_call_id != fact.data.tool_call_id
                    or tail[-1].data.call.name != fact.data.purpose
                )
                or any(
                    isinstance(item.data, AuxiliaryStarted)
                    and item.data.request_id == fact.data.request_id
                    for item in log.facts
                )
            ):
                raise invalid
        if isinstance(fact.data, AuxiliaryCompleted):
            start = next(
                (
                    item.data
                    for item in reversed(auxiliary)
                    if isinstance(item.data, AuxiliaryStarted)
                    and item.data.request_id == fact.data.request_id
                ),
                None,
            )
            if (
                start is None
                or (
                    start.purpose == "web_search"
                    and (
                        not tail
                        or not isinstance(tail[-1].data, ToolStarted)
                        or tail[-1].data.call.tool_call_id != start.tool_call_id
                    )
                )
                or any(
                    isinstance(item.data, AuxiliaryCompleted)
                    and item.data.request_id == fact.data.request_id
                    for item in auxiliary
                )
            ):
                raise invalid
        if isinstance(fact.data, RequestStarted):
            if tail and isinstance(tail[-1].data, (RequestStarted, ToolStarted)):
                raise invalid
            if not log.context()[1]:
                raise invalid
            if any(
                isinstance(item.data, RequestStarted)
                and item.data.message_id == fact.data.message_id
                for item in log.facts
            ):
                raise invalid
        if isinstance(fact.data, AssistantCommitted):
            if (
                not tail
                or not isinstance(tail[-1].data, RequestStarted)
                or tail[-1].data.message_id != fact.data.message_id
            ):
                raise invalid
            identifiers = [call.tool_call_id for call in fact.data.turn.tool_calls]
            if len(set(identifiers)) != len(identifiers):
                raise invalid
        if isinstance(fact.data, ToolStarted):
            turn = next(
                (f.data for f in reversed(tail) if isinstance(f.data, AssistantCommitted)), None
            )
            if turn is None or fact.data.call not in turn.turn.tool_calls:
                raise invalid
            if isinstance(tail[-1].data, ToolStarted):
                raise invalid
            current_turn = next(
                item for item in reversed(tail) if isinstance(item.data, AssistantCommitted)
            )
            identifier = fact.data.call.tool_call_id
            if any(
                (isinstance(item.data, ToolStarted) and item.data.call.tool_call_id == identifier)
                or (
                    isinstance(item.data, (ToolCompleted, ToolSkipped))
                    and item.data.result.tool_call_id == identifier
                )
                for item in log.facts[current_turn.seq :]
            ):
                raise invalid
        if isinstance(fact.data, ToolCompleted):
            if (
                not tail
                or not isinstance(tail[-1].data, ToolStarted)
                or tail[-1].data.call.tool_call_id != fact.data.result.tool_call_id
            ):
                raise invalid
        if isinstance(fact.data, ToolSkipped):
            last_turn = next(
                (f for f in reversed(tail) if isinstance(f.data, AssistantCommitted)), None
            )
            if last_turn is None or not isinstance(last_turn.data, AssistantCommitted):
                raise invalid
            identifier = fact.data.result.tool_call_id
            after_turn = log.facts[last_turn.seq :]
            if (
                not fact.data.result.is_error
                or identifier not in {c.tool_call_id for c in last_turn.data.turn.tool_calls}
                or any(
                    (isinstance(f.data, ToolStarted) and f.data.call.tool_call_id == identifier)
                    or (
                        isinstance(f.data, (ToolCompleted, ToolSkipped))
                        and f.data.result.tool_call_id == identifier
                    )
                    for f in after_turn
                )
            ):
                raise invalid

    def append(self, log: SessionLog, data: FactData, run_id: str | None) -> Fact:
        """先 fsync 关键事实，再更新内存；保存异常后禁止追加。

        Fsync critical facts before memory updates; prohibit appends after uncertain writes.
        """
        self.storage.require_writer()
        if log.issue:
            raise AgentError("SESSION_READ_ONLY", "会话记录不完整，请新建会话。")
        fact = Fact(
            session_id=log.session_id,
            run_id=run_id,
            seq=len(log.facts) + 1,
            at=utc_now(),
            data=data,
        )
        self._validate_next(log, fact)
        raw = (fact.model_dump_json() + "\n").encode("utf-8")
        if len(raw) > MAX_FACT_BYTES:
            raise AgentError("SESSION_RECORD_LIMIT", "会话单条记录超过存储容量。")
        path = self.path(log.session_id)
        try:
            if not log.facts:
                # 先前创建仅留下空目录时可接续；xb 仍拒绝覆盖任何已有日志。
                # Recover a previously created empty directory; xb still protects existing logs.
                path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("ab" if log.facts else "xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            log.facts.append(fact)
            return fact
        except OSError as exc:
            log.issue = "SESSION_SAVE_FAILED"
            raise AgentError(
                "SESSION_SAVE_FAILED", "保存会话失败，运行已停止；原文件已保留。"
            ) from exc
