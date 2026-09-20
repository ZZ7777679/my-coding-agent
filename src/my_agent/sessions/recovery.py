"""在用户发送 / 接续时核对中断，不增加单独确认或重放项目动作。

Reconcile on explicit send or resume, without separate confirmation or project-action replay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from my_agent.errors import AgentError
from my_agent.sessions.artifacts import ArtifactInspector
from my_agent.sessions.pairing import pending_tools
from my_agent.sessions.projection import summarize
from my_agent.sessions.recovery_types import (
    RecoveryItem,
    SessionRecovered,
)
from my_agent.sessions.store import SessionLog
from my_agent.sessions.types import RunAccepted, RunFinished

if TYPE_CHECKING:
    from my_agent.sessions.service import SessionService


class RecoveryService:
    """持会话执行锁核对当前结果，只追加观察，不启动新运行。

    Inspect under the session lock and append observations without running work.
    """

    def __init__(self, sessions: SessionService, inspector: ArtifactInspector) -> None:
        """复用生产会话和成果来源。 Reuse production sessions and artifact sources."""
        self.sessions, self.inspector = sessions, inspector

    def _idle(self, log: SessionLog) -> None:
        """活动 / 清理中不核对，不通过补充观察绕过损坏记录。

        Refuse active cleanup or damaged logs instead of bypassing them through recovery.
        """
        active = self.sessions.active_for(log.session_id)
        if (
            self.sessions.closing
            or (active and active.log.session_id == log.session_id)
            or (self.sessions.goals and self.sessions.goals.driver(log.session_id))
        ):
            raise AgentError("RUN_BUSY", "请等待此会话停止并清理后，再核对中断。")
        if log.issue:
            raise AgentError("SESSION_READ_ONLY", "原记录损坏或不可写，不能追加核对结果。")

    async def _inspect(self, log: SessionLog) -> list[RecoveryItem]:
        """核对同一会话的当前成果，将变化保留为观察而非恢复门槛。

        Inspect session artifacts, recording changes as observations instead of recovery gates.
        """
        self._idle(log)
        summary = summarize(log)
        root = await self.sessions.validate_project(summary.project_id)
        pending = pending_tools(log.facts)
        items = []
        for item in pending:
            start = next(
                fact.data
                for fact in log.facts
                if fact.run_id == item.run_id and isinstance(fact.data, RunAccepted)
            )
            observation = await self.inspector.pending(
                root, start.limits, summary.project_id, log.session_id, item
            )
            items.append(
                RecoveryItem(
                    turn_seq=item.turn_seq,
                    tool_call_id=item.call.tool_call_id,
                    tool_name=item.call.name,
                    started_seq=item.started_seq,
                    observation=observation,
                )
            )
        return items

    async def recover_locked(self, log: SessionLog, operation_id: str) -> None:
        """调用方持锁且已有发送 / 接续授权；只补历史，不执行旧工具。

        The caller holds the lock and explicit send/resume intent; only reconcile history.
        """
        if any(
            isinstance(fact.data, SessionRecovered) and fact.data.operation_id == operation_id
            for fact in log.facts
        ):
            return
        self._idle(log)
        items = await self._inspect(log)
        if not items:
            return
        run_id = pending_tools(log.facts)[0].run_id
        if not any(
            fact.run_id == run_id and isinstance(fact.data, RunFinished) for fact in log.facts
        ):
            await self.sessions.worker.call(
                self.sessions.store.append,
                log,
                RunFinished(
                    status="interrupted",
                    code="PROCESS_INTERRUPTED",
                    message="上次运行中断；已保留结果，未重放操作。",
                ),
                run_id,
            )
        await self.sessions.worker.call(
            self.sessions.store.append,
            log,
            SessionRecovered(operation_id=operation_id, items=items),
            run_id,
        )
        self.sessions.last_log = log
        self.sessions.signal_log(log)
