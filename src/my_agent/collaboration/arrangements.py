"""用户主动交接与独立 Review，复用已有协作队列和执行身份。

User-initiated handoff and independent review using the collaboration queue and run identities.
"""

import asyncio
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from my_agent.changes.store import ChangeStore
from my_agent.collaboration.types import (
    ArrangeSessionWorkParams,
    CollaborationLink,
    CollaborationRequest,
    CollaborationRequestParams,
    SessionWorkBrief,
)
from my_agent.config import load_config
from my_agent.errors import AgentError
from my_agent.goals.state import states
from my_agent.goals.types import GoalControl
from my_agent.sessions.projection import summarize
from my_agent.sessions.store import SessionLog
from my_agent.sessions.types import RunAccepted
from my_agent.storage import utc_now
from my_agent.tasks.store import TaskStore

if TYPE_CHECKING:
    from my_agent.collaboration.service import CollaborationService


class SessionArrangements:
    """保存用户安排，停止指定责任并生成来源简报，不增加摘要模型。

    Save user arrangements, stop specified responsibility and build briefs without summary models.
    """

    def __init__(
        self, collaboration: "CollaborationService", tasks: TaskStore, changes: ChangeStore
    ) -> None:
        """注入已有数据服务，不建立第二套运行时。

        Inject existing data services without introducing another runtime.
        """
        self.collaboration = collaboration
        self.sessions = collaboration.sessions
        self.worker = self.sessions.worker
        self.tasks, self.changes = tasks, changes

    async def create(self, params: ArrangeSessionWorkParams) -> CollaborationRequest:
        """先保存明确用户安排，返回准备状态；重复发送不重复停止或运行。

        Save the explicit user arrangement first; repeated submission never restarts work.
        """
        async with self.collaboration.lock, self.sessions.lock:
            if self.sessions.closing:
                raise AgentError("APP_CLOSING", "应用正在退出，不再接纳工作安排。")
            task_id = await self.collaboration._pair_locked(
                params.source_session_id, params.target_session_id
            )
            records = await self.worker.call(self.collaboration.store.requests)
            previous = next(
                (item for item in records if item.request_id == params.operation_id), None
            )
            if previous is not None:
                if previous.arrangement != params:
                    raise AgentError("OPERATION_CONFLICT", "该操作标识已用于其他安排。")
                return previous
            log = await self.sessions._load(params.source_session_id)
            if params.transfer_goal_id and params.transfer_goal_id not in states(log.facts):
                raise AgentError("GOAL_NOT_FOUND", "要交接的 Goal 不属于来源会话。")
            if params.transfer_run_id and not any(
                fact.run_id == params.transfer_run_id and isinstance(fact.data, RunAccepted)
                for fact in log.facts
            ):
                raise AgentError("RUN_NOT_FOUND", "要交接的运行不属于来源会话。")
            now = utc_now()
            value = CollaborationRequest(
                request_id=params.operation_id,
                task_id=task_id,
                params=CollaborationRequestParams(
                    operation_id=params.operation_id,
                    source_session_id=params.source_session_id,
                    target_session_id=params.target_session_id,
                    objective=params.objective,
                    mode="plan" if params.kind == "review" else "normal",
                ),
                scope=params.objective,
                status="preparing",
                reason="正在准备用户安排的交接 / 审查。",
                arrangement=params,
                created_at=now,
                updated_at=now,
            )
            await self.collaboration._save(value)
            self.collaboration._start()
            return value

    async def prepare(self, request: CollaborationRequest) -> CollaborationRequest:
        """仅停止所选 Goal / Run，清理后保存真实简报与读取关系。

        Stop only the selected goal/run, then capture facts and the recipient's read agreement.
        """
        params = request.arrangement
        if params is None:
            raise AgentError("COLLABORATION_INVALID", "该记录没有用户工作安排。")
        waiters: list[asyncio.Task[None]] = []
        async with self.sessions.lock:
            task_id = await self.collaboration._pair_locked(
                params.source_session_id, params.target_session_id
            )
            if task_id != request.task_id:
                raise AgentError("COLLABORATION_SCOPE", "会话任务已改变，请重新安排交接。")
            # 先验证任务可读，再停止工作，保存失败仍保留原记录与明确状态。
            # Validate before stopping; failures retain records and explicit status.
            await self.worker.call(self.tasks.get, task_id)
            log = await self.sessions._load(params.source_session_id)
            active = self.sessions.active_for(log.session_id)
            goals = self.sessions.goals
            if params.transfer_goal_id:
                if goals is None:
                    raise AgentError("GOAL_UNAVAILABLE", "Goal 服务不可用。")
                state = states(log.facts).get(params.transfer_goal_id)
                if state is None:
                    raise AgentError("GOAL_NOT_FOUND", "来源 Goal 不存在。")
                if state.status == "active":
                    await self.worker.call(
                        goals.journal.control,
                        log,
                        GoalControl(
                            goal_id=params.transfer_goal_id,
                            operation_id=str(
                                uuid5(NAMESPACE_URL, request.request_id + ":handoff-pause")
                            ),
                            expected_revision=state.revision,
                            action="pause",
                        ),
                    )
                driver = goals._cancel_work(log.session_id, params.transfer_goal_id)
                if driver is not None:
                    waiters.append(driver)
                if (
                    active
                    and active.goal
                    and active.goal.goal_id == params.transfer_goal_id
                    and active.task
                ):
                    waiters.append(active.task)
                self.sessions.signal_log(log)
            elif params.transfer_run_id and active and active.run_id == params.transfer_run_id:
                if active.goal and goals:
                    state = states(log.facts)[active.goal.goal_id]
                    if state.status == "active":
                        await self.worker.call(
                            goals.journal.control,
                            log,
                            GoalControl(
                                goal_id=active.goal.goal_id,
                                operation_id=str(
                                    uuid5(NAMESPACE_URL, request.request_id + ":handoff-pause")
                                ),
                                expected_revision=state.revision,
                                action="pause",
                            ),
                        )
                    driver = goals._cancel_work(log.session_id, active.goal.goal_id)
                    if driver is not None:
                        waiters.append(driver)
                active.stop.set()
                active.cancel.set()
                if active.task:
                    waiters.append(active.task)
                self.sessions.signal_log(log)
        # 不持会话锁等待清理；交付服务继续由应用生命周期管理。
        # Await cleanup outside the session lock; retained services keep their app lifetime.
        if waiters:
            await asyncio.gather(*(asyncio.shield(task) for task in set(waiters)))
        async with self.sessions.lock:
            task_id = await self.collaboration._pair_locked(
                params.source_session_id, params.target_session_id
            )
            if task_id != request.task_id:
                raise AgentError("COLLABORATION_SCOPE", "准备期间会话归属已改变。")
            log = await self.sessions._load(params.source_session_id)
            task = await self.worker.call(self.tasks.get, task_id)
            summary = summarize(log, active=self.sessions.active_for(log.session_id) is not None)
            source_run = summary.run
            selected_start = next(
                (
                    fact
                    for fact in reversed(log.facts)
                    if isinstance(fact.data, RunAccepted)
                    and (
                        fact.run_id == params.transfer_run_id
                        if params.transfer_run_id
                        else fact.data.goal_id == params.transfer_goal_id
                        if params.transfer_goal_id
                        else False
                    )
                ),
                None,
            )
            if selected_start is not None:
                end = next(
                    (
                        fact.seq
                        for fact in log.facts[selected_start.seq :]
                        if isinstance(fact.data, RunAccepted)
                    ),
                    len(log.facts) + 1,
                )
                source_run = summarize(SessionLog(log.session_id, log.facts[: end - 1])).run
            goal_id = params.transfer_goal_id or (summary.run.goal_id if summary.run else None)
            brief = SessionWorkBrief(
                task=task,
                source_session_id=log.session_id,
                source_watermark=len(log.facts),
                source_goal=self.sessions.goals._view(log, goal_id)
                if self.sessions.goals and goal_id
                else None,
                source_run=source_run,
                changes=await self.worker.call(self.changes.list, log.session_id, None, 20),
                captured_at=utc_now(),
                inherited_context=await self.sessions.contexts.capture(
                    log,
                    source_run.limits.max_context_bytes
                    if source_run
                    else load_config(self.sessions.store.storage.location).run.max_context_bytes,
                )
                if params.context_mode == "inherit" and self.sessions.contexts
                else "",
            )
            # 用户安排本身已明确接收方可读来源；不再要求第二次权限确认。
            # The user's arrangement permits reading the source without a second confirmation.
            link = await self.worker.call(
                self.collaboration.store.link, params.target_session_id, params.source_session_id
            )
            if link is None or not link.enabled or link.task_id != task_id:
                await self.worker.call(
                    self.collaboration.store.save_link,
                    CollaborationLink(
                        source_session_id=params.target_session_id,
                        target_session_id=params.source_session_id,
                        scope=params.objective,
                        task_id=task_id,
                        mode="plan",
                        updated_at=utc_now(),
                    ),
                )
            return request.model_copy(
                update={
                    "brief": brief,
                    "status": "queued",
                    "reason": None,
                    "source_run_id": source_run.run_id if source_run else None,
                }
            )
