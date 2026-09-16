"""单写者 JSONL 会话存储，损坏前缀只读。

Single-writer JSONL storage with preserved corrupt tails.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from my_agent.errors import AgentError
from my_agent.models.types import JsonObject
from my_agent.sessions.types import (
    AssistantCommitted,
    Fact,
    FactData,
    RequestStarted,
    RunAccepted,
    RunFinished,
    SessionCreated,
    SessionId,
    ToolCompleted,
    ToolStarted,
)
from my_agent.storage import Storage, utc_now

SESSION_ID = TypeAdapter(SessionId)
MAX_FACT_BYTES = 1048576
MAX_SESSION_BYTES = 64 * 1024 * 1024


@dataclass
class SessionLog:
    """已确认事实前缀及不可写原因。 Confirmed fact prefix and any read-only reason."""

    session_id: str
    facts: list[Fact]
    issue: str | None = None

    def context(self) -> tuple[list[JsonObject], bool]:
        """从完整事实组装历史，未配对工具使续接失效。

        Build history; unpaired tools prevent reuse.
        """
        messages: list[JsonObject] = []
        pending: set[str] = set()
        for fact in self.facts:
            data = fact.data
            if isinstance(data, RunAccepted):
                if pending:
                    return messages, False
                messages.append({"role": "user", "content": data.prompt})
            elif isinstance(data, AssistantCommitted):
                if pending:
                    return messages, False
                messages.append(data.turn.native)
                pending.update(call.tool_call_id for call in data.turn.tool_calls)
            elif isinstance(data, ToolCompleted):
                if data.result.tool_call_id not in pending:
                    return messages, False
                pending.remove(data.result.tool_call_id)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": data.result.tool_call_id,
                        "content": data.result.content,
                    }
                )
        return messages, not pending and self.issue is None


class SessionStore:
    """所有方法由受控业务线程调用，使用已有数据根写锁。

    Called on the controlled business worker under the existing data-root writer lock.
    """

    def __init__(self, storage: Storage) -> None:
        """绑定位置，不提前创建目录。 Bind locations without creating directories."""
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
                total = 0
                while raw := stream.readline(MAX_FACT_BYTES + 1):
                    total += len(raw)
                    if (
                        len(raw) > MAX_FACT_BYTES
                        or total > MAX_SESSION_BYTES
                        or not raw.endswith(b"\n")
                    ):
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
        if isinstance(fact.data, SessionCreated) or fact.run_id is None:
            raise invalid
        accepted = next((f for f in reversed(log.facts) if isinstance(f.data, RunAccepted)), None)
        if isinstance(fact.data, RunAccepted):
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
        tail = log.facts[accepted.seq :]
        if any(isinstance(f.data, RunFinished) for f in tail):
            raise invalid
        if isinstance(fact.data, AssistantCommitted):
            if (
                not tail
                or not isinstance(tail[-1].data, RequestStarted)
                or tail[-1].data.message_id != fact.data.message_id
            ):
                raise invalid
        if isinstance(fact.data, ToolStarted):
            turn = next(
                (f.data for f in reversed(tail) if isinstance(f.data, AssistantCommitted)), None
            )
            if turn is None or fact.data.call not in turn.turn.tool_calls:
                raise invalid
        if isinstance(fact.data, ToolCompleted):
            if (
                not tail
                or not isinstance(tail[-1].data, ToolStarted)
                or tail[-1].data.call.tool_call_id != fact.data.result.tool_call_id
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
                path.parent.mkdir(parents=True, exist_ok=False)
            with path.open("ab" if log.facts else "xb") as stream:
                if stream.tell() + len(raw) > MAX_SESSION_BYTES:
                    raise AgentError("SESSION_CAPACITY", "会话达到存储容量，请新建会话。")
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
