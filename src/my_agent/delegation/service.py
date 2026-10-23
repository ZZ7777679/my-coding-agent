"""复用会话执行核心的可选内部 worker。

Optional internal workers reusing the existing session execution core.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from my_agent.delegation.types import (
    DelegatedUsage,
    SpawnWorkerArgs,
    WorkerFailure,
    WorkerPage,
    WorkerRecord,
    WorkerSettings,
)
from my_agent.errors import AgentError
from my_agent.goals.ledger import check_budget, usage
from my_agent.goals.state import states
from my_agent.models.types import JsonObject
from my_agent.runtime.settings import minimum_limit
from my_agent.sessions.projection import selected_model, summarize
from my_agent.sessions.store import SessionLog
from my_agent.sessions.types import (
    AssistantCommitted,
    AuxiliaryCompleted,
    AuxiliaryStarted,
    FactData,
    RequestFailed,
    RequestStarted,
    RunAccepted,
    RunFinished,
    SessionSignal,
    ToolCompleted,
    ToolSkipped,
    ToolStarted,
)
from my_agent.storage import read_document, utc_now, write_document

if TYPE_CHECKING:
    from my_agent.sessions.service import ActiveRun, SessionService


class DelegationService:
    """按父安排调度，子历史保留但不成为侧栏用户会话。

    Schedule by parent assignment; retained child histories are not sidebar user sessions.
    """

    def __init__(self, sessions: "SessionService") -> None:
        """复用现有存储线程与模型工厂。

        Reuse the existing storage worker and model factory.
        """
        self.sessions = sessions
        self.root = sessions.store.storage.root / "delegation"
        self.settings: dict[str, WorkerSettings] = {}
        self.records: dict[str, WorkerRecord] = {}
        self.drivers: dict[str, asyncio.Task[None]] = {}
        self.changed = asyncio.Event()
        self.loaded = False
        self.closed = False
        self.failures: dict[str, AgentError] = {}
        self.watcher: asyncio.Task[None] | None = None
        self.unsubscribe = sessions.subscribe(self._signal)

    def _notify(self) -> None:
        """唤醒现有等待者，后续等待使用新事件。

        Wake current waiters and rearm the event for subsequent waits.
        """
        self.changed.set()
        self.changed = asyncio.Event()

    def _signal(self, event: SessionSignal) -> None:
        """真实状态变化唤醒队列，不对流式文本忙轮询。

        Wake queues on durable state changes, never on streamed text.
        """
        if event.kind == "changed":
            self._notify()
            for record in self.records.values():
                if event.session_id in {record.session_id, record.owner_session_id}:
                    for identity in (record.session_id, record.owner_session_id):
                        active = self.sessions.active_for(identity)
                        if active:
                            active.budget_changed.set()

    async def prepare(self, session_id: str, *, required: bool = True) -> WorkerSettings:
        """读取委派配置；普通对话允许可选配置失效，显式访问保留原错误。

        Chat tolerates unavailable delegation settings; explicit access reports the error.
        """
        if session_id not in self.settings:
            path = self.sessions.store.path(session_id).with_name("workers.json")
            try:
                settings = (
                    await self.sessions.worker.call(read_document, path, WorkerSettings)
                    if path.exists()
                    else WorkerSettings()
                )
            except AgentError as exc:
                if required or exc.code not in {"DATA_INVALID", "DATA_UNAVAILABLE"}:
                    raise
                logging.getLogger(__name__).warning(
                    "WORKER_SETTINGS_UNAVAILABLE code=%s session=%s", exc.code, session_id
                )
                # 不保存或缓存临时关闭状态，查看仍报告原错误，修正文件后可重新加载。
                # Do not cache/save fallback state; keep errors visible and allow repair reloads.
                return WorkerSettings()
            self.settings[session_id] = settings
        return self.settings[session_id]

    async def _load(self) -> None:
        """重启时保留记录，进行中状态标为中断而不重放。

        Retain records after restart, marking unfinished work interrupted without replay.
        """
        if self.loaded:
            return

        def read_all() -> list[WorkerRecord]:
            """读取自己的记录目录。

            Read the owned record directory.
            """
            return [
                read_document(path, WorkerRecord) for path in (self.root / "records").glob("*.json")
            ]

        for record in await self.sessions.worker.call(read_all):
            if record.status in {"queued", "running"}:
                record.status, record.code = "interrupted", "PROCESS_INTERRUPTED"
            self.records[record.worker_id] = record
        self.loaded = True

    async def page(self, session_id: str) -> WorkerPage:
        """返回当前会话的子卡片，查看不启动模型。

        Return the owner's worker cards without starting models.
        """
        await self.sessions._load(session_id)
        await self._load()
        settings = await self.prepare(session_id)
        for value in self.records.values():
            if value.owner_session_id != session_id:
                continue
            await self._refresh_record(value)
        return WorkerPage(
            settings=settings,
            workers=sorted(
                [item for item in self.records.values() if item.owner_session_id == session_id],
                key=lambda item: item.created_at,
                reverse=True,
            ),
        )

    async def _refresh_record(self, value: WorkerRecord) -> None:
        """从原日志还原用量、最近动作与部分正文，不额外调用模型或重写旧历史。

        Recover usage, latest activity and partial prose from facts without a model or log rewrite.
        """
        try:
            log = await self.sessions._load(value.session_id)
        except AgentError as exc:
            value.history_issue = f"{exc.code}: {exc.message}"
            return
        value.history_issue = None
        self._restore_failure_from_log(value, log)
        value.requests = sum(
            isinstance(f.data, (RequestStarted, AuxiliaryStarted)) for f in log.facts
        )
        value.tools = sum(isinstance(f.data, ToolStarted) for f in log.facts)
        value.active_seconds = sum(
            f.data.elapsed_seconds or 0 for f in log.facts if isinstance(f.data, RunFinished)
        )
        child = self.sessions.active_for(value.session_id)
        if child and not any(
            f.run_id == child.run_id and isinstance(f.data, RunFinished) for f in log.facts
        ):
            value.active_seconds += child.active_seconds()
        current = [f for f in log.facts if value.run_id and f.run_id == value.run_id]
        value.last_seq = current[-1].seq if current else None
        value.last_event_at = current[-1].at if current else None
        finished = next(
            (f.data for f in reversed(current) if isinstance(f.data, RunFinished)), None
        )
        value.model_progress = (
            child.progress_snapshot() if child else (finished.model_progress if finished else None)
        )
        last_tool = next(
            (f.data.call for f in reversed(current) if isinstance(f.data, ToolStarted)), None
        )
        value.last_tool = last_tool.name if last_tool else None
        result = next(
            (
                f.data
                for f in reversed(current)
                if isinstance(f.data, (ToolCompleted, ToolSkipped))
                and last_tool
                and f.data.result.tool_call_id == last_tool.tool_call_id
            ),
            None,
        )
        value.last_tool_status = (
            "skipped"
            if isinstance(result, ToolSkipped)
            else "failed"
            if result and result.result.is_error
            else "completed"
            if result
            else "running"
            if last_tool
            else None
        )
        answer = next(
            (
                f.data.turn.text
                for f in reversed(current)
                if isinstance(f.data, AssistantCommitted) and f.data.turn.text
            ),
            "",
        )
        # 取消也走这一条收尾；不把先前成功运行的回答当成本次成果。
        # Cancellation uses the same harvest; never reuse an earlier run's answer as this result.
        value.result = (
            finished.partial_text if finished and finished.partial_text else answer
        ) or (finished.report.summary if finished and finished.report else "")

    async def configure(self, session_id: str, settings: WorkerSettings) -> WorkerPage:
        """关闭只拒绝新委派，已有子任务由其停止入口控制。

        Disabling stops new admission; existing workers have explicit stop controls.
        """
        await self.sessions._load(session_id)
        path = self.sessions.store.path(session_id).with_name("workers.json")
        await self.sessions.worker.call(write_document, path, settings)
        self.settings[session_id] = settings
        self._notify()
        return await self.page(session_id)

    async def budget_snapshot(self, session_id: str) -> JsonObject:
        """读取当前安排的父子总账与余额；None 是不限，不进行成本预测或预检拦截。

        Read current parent/child totals and remaining caps; None means unlimited, with no gate.
        """
        child = self.child_record(session_id)
        owner_id = child.owner_session_id if child else session_id
        log = await self.sessions._load(owner_id)
        summary = summarize(log)
        run = summary.run
        if run is None:
            return {"run_id": None}
        active = self.sessions.active_for(owner_id)
        goal = states(log.facts).get(run.goal_id) if run.goal_id else None
        current = [f for f in log.facts if f.run_id == run.run_id]
        parent_seconds = (
            active.active_seconds()
            if active and active.run_id == run.run_id
            else next(
                (
                    f.data.elapsed_seconds
                    for f in reversed(current)
                    if isinstance(f.data, RunFinished)
                ),
                None,
            )
        )
        child_seconds = sum(
            f.data.active_seconds for f in current if isinstance(f.data, DelegatedUsage)
        ) + self.live_seconds(owner_id, run_id=run.run_id)
        seconds = parent_seconds + child_seconds if parent_seconds is not None else None
        result: JsonObject = {
            "run_id": run.run_id,
            "parent": {
                "requests": run.requests - run.child_requests,
                "tools": run.tools - run.child_tools,
                "active_seconds": parent_seconds,
            },
            "children": {
                "requests": run.child_requests,
                "tools": run.child_tools,
                "active_seconds": child_seconds,
            },
            "total": {"requests": run.requests, "tools": run.tools, "active_seconds": seconds},
            "limits": {
                "requests": run.limits.max_requests,
                "tools": run.limits.max_tools,
                "active_seconds": run.limits.max_seconds,
            },
            "remaining": {
                "requests": max(0, run.limits.max_requests - run.requests)
                if run.limits.max_requests is not None
                else None,
                "tools": max(0, run.limits.max_tools - run.tools)
                if run.limits.max_tools is not None
                else None,
                "active_seconds": max(0.0, run.limits.max_seconds - seconds)
                if run.limits.max_seconds is not None and seconds is not None
                else None,
            },
            "note": "Shared assignment totals. null limits mean unlimited. Concurrent work "
            "sums agent active seconds, not wall time. Counts are observed, not reserved.",
        }
        if goal and run.goal_id:
            result["goal"] = {
                "goal_id": run.goal_id,
                "limits": goal.budget.model_dump(mode="json"),
                "usage": usage(
                    log.facts,
                    run.goal_id,
                    live_seconds={run.run_id: parent_seconds}
                    if active and parent_seconds is not None
                    else None,
                ).model_dump(mode="json"),
            }
        return result

    async def save(self, value: WorkerRecord) -> None:
        """原子保存后通知来源会话。

        Notify the owner after atomically saving a record.
        """

        def persist() -> None:
            """保存单条内部工作状态。

            Save one internal worker record.
            """
            path = self.root / "records" / f"{UUID(value.worker_id)}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            write_document(path, value)

        await self.sessions.worker.call(persist)
        self.records[value.worker_id] = value
        self.sessions.signal_log(await self.sessions._load(value.owner_session_id))

    def child_record(self, session_id: str) -> WorkerRecord | None:
        """按内部执行身份查原安排。

        Look up the original assignment by internal execution identity.
        """
        return next((item for item in self.records.values() if item.session_id == session_id), None)

    @staticmethod
    def _restore_failure_from_log(value: WorkerRecord, log: SessionLog) -> None:
        """旧记录按对应子运行补读原因，不将中间回答当作错误或重写历史。

        Read matching run failures without treating prose as errors or rewriting history.
        """
        if value.status not in {"failed", "budget_exceeded"} or value.failure is not None:
            return
        finished = next(
            (
                fact.data
                for fact in reversed(log.facts)
                if fact.run_id == value.run_id and isinstance(fact.data, RunFinished)
            ),
            None,
        )
        if finished:
            value.failure = WorkerFailure(
                code=finished.code or value.code or "WORKER_FAILED",
                message=finished.message or "子任务失败，未保存详细原因。",
                cause_code=finished.cause_code,
                phase=finished.failure_phase,
                diagnostic_id=finished.diagnostic_id,
            )

    @staticmethod
    def _failure_error(value: WorkerRecord) -> AgentError:
        """传播失败事实与原诊断，部分成果不充当错误说明。

        Propagate failure facts and the original diagnostic, never partial output as the reason.
        """
        failure = value.failure
        return AgentError(
            failure.code if failure else value.code or "WORKER_FAILED",
            failure.message if failure else "子任务失败，未保存详细原因。",
            cause_code=failure.cause_code if failure else None,
            phase=failure.phase if failure else None,
            diagnostic_id=failure.diagnostic_id if failure else None,
        )

    async def spawn(
        self, owner: "ActiveRun", assignment: SpawnWorkerArgs, identity: str
    ) -> WorkerRecord:
        """开关开启时接纳有限子任务，不创建正式会话。

        Admit bounded work when enabled without creating a formal user session.
        """
        await self._load()
        settings = await self.prepare(owner.log.session_id)
        if self.child_record(owner.log.session_id):
            raise AgentError(
                "WORKER_CONTEXT_UNSUPPORTED", "内部子任务不能递归拆分，请由父会话安排并行工作。"
            )
        if not settings.enabled:
            raise AgentError("WORKERS_DISABLED", "此会话尚未开启子 Agent。")
        if owner.mode == "plan" and assignment.mode != "plan":
            raise AgentError("TOOL_NOT_ALLOWED", "Plan 模式的子任务同样只读，请使用 plan 子任务。")
        if identity in self.records:
            return self.records[identity]
        parent = summarize(owner.log)
        inherited = ""
        if assignment.context_mode == "inherit":
            contexts = self.sessions.contexts
            if contexts:
                inherited = await contexts.capture(owner.log, owner.limits.max_context_bytes)
        session = await self.sessions.create(
            parent.project_id,
            selected_model(owner.log),
            task_id=parent.task_id,
            role=assignment.role,
            scope=assignment.scope,
            worker_owner_session_id=parent.session_id,
            inherited_context=inherited,
        )
        if self.sessions.memory:
            parent_memory = await self.sessions.worker.call(
                self.sessions.memory.store.state, parent.session_id, len(owner.log.facts)
            )
            await self.sessions.memory.configure(
                session.session_id,
                parent_memory.settings.model_copy(update={"automatic": False}),
            )
        value = WorkerRecord(
            worker_id=identity,
            session_id=session.session_id,
            owner_session_id=parent.session_id,
            owner_run_id=owner.run_id,
            goal_id=owner.goal.goal_id if owner.goal else None,
            model_id=selected_model(owner.log),
            assignment=assignment,
            status="queued",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        await self.save(value)
        self.drivers[identity] = asyncio.create_task(self._drive(value, assignment.objective))
        self._watch_owners()
        return value

    def _watch_owners(self) -> None:
        """使用事件检查暂停与取消，避免等待下一次模型回包。

        Observe pause/cancellation by events instead of waiting for another model response.
        """
        if self.watcher is None or self.watcher.done():
            self.watcher = asyncio.create_task(self._watch())

    async def _watch(self) -> None:
        """原安排停止时及时回收其孩子。

        Promptly reap children whose original assignment has stopped.
        """
        while self.drivers and not self.closed:
            changed = self.changed
            for identity in list(self.drivers):
                record = self.records[identity]
                try:
                    await self._owner(record)
                except AgentError:
                    await self.stop(record.owner_session_id, identity)
            if self.drivers:
                await changed.wait()

    async def _owner(self, value: WorkerRecord) -> tuple["ActiveRun | None", RunAccepted]:
        """原 Goal 仍活动时允许插话期间子工作继续，不以新 Run 重置账本。

        Let children continue during questions while the original goal is active, without
        resetting budgets.

        """
        log = await self.sessions._load(value.owner_session_id)
        accepted = next(
            (
                fact.data
                for fact in log.facts
                if fact.run_id == value.owner_run_id and isinstance(fact.data, RunAccepted)
            ),
            None,
        )
        if accepted is None:
            raise AgentError("WORKER_OWNER_MISSING", "原委派运行不存在。")
        active = self.sessions.active_for(value.owner_session_id)
        if value.goal_id:
            state = states(log.facts).get(value.goal_id)
            if not state or state.status != "active":
                raise AgentError("CANCELLED", "原 Goal 已停止，子工作停止。")
        elif active is None or active.run_id != value.owner_run_id or active.stop.is_set():
            raise AgentError("CANCELLED", "原运行已停止，子工作停止。")
        return active, accepted

    async def _drive(self, value: WorkerRecord, prompt: str) -> None:
        """等待并发槽后运行同一核心，失败不自动重派。

        Run the shared core after a slot is available, without automatic retries.
        """
        try:
            while True:
                changed = self.changed
                _, accepted = await self._owner(value)
                running = sum(
                    item.status == "running" and item.owner_session_id == value.owner_session_id
                    for item in self.records.values()
                )
                if running < self.settings[value.owner_session_id].concurrency:
                    break
                await changed.wait()
            value.status = "running"
            await self.save(value)
            started = await self.sessions.start(
                value.session_id,
                str(uuid4()),
                prompt,
                accepted.limits,
                mode="plan" if value.assignment.role == "research" else value.assignment.mode,
            )
            value.run_id = started.run.run_id if started.run else None
            await self.save(value)
            child = self.sessions.active_for(value.session_id)
            if child and child.task:
                await asyncio.shield(child.task)
            log = await self.sessions._load(value.session_id)
            summary = summarize(log)
            value.status = (
                summary.run.status
                if summary.run
                and summary.run.status
                in {"completed", "failed", "budget_exceeded", "cancelled", "interrupted"}
                else "failed"
            )
            value.code = summary.run.code if summary.run else "WORKER_NO_RESULT"
            self._restore_failure_from_log(value, log)
        except asyncio.CancelledError:
            value.status, value.code = "cancelled", "CANCELLED"
            owner = self.sessions.active_for(value.owner_session_id)
            cause = owner.dependency_error if owner else None
            value.failure = WorkerFailure(
                code="CANCELLED",
                message=(
                    "应用退出，子任务已停止，已保存成果仍可读取。"
                    if self.closed
                    else f"原安排因 {cause.code} 停止：{cause.message}"
                    if cause
                    else "子任务或原安排已被停止，已保存成果仍可读取。"
                ),
                cause_code="APP_CLOSED" if self.closed else cause.code if cause else None,
                phase="worker_cancel",
            )
        except AgentError as exc:
            value.status = (
                "cancelled"
                if exc.code == "CANCELLED"
                else "budget_exceeded"
                if exc.code.startswith("BUDGET_")
                else "failed"
            )
            value.code = exc.code
            if value.status in {"failed", "budget_exceeded", "cancelled"}:
                value.failure = WorkerFailure(
                    code=exc.code,
                    message=exc.message,
                    cause_code=exc.cause_code,
                    phase=exc.phase,
                    diagnostic_id=exc.diagnostic_id,
                )
        except Exception as exc:
            logging.getLogger(__name__).error(
                "WORKER_INTERNAL type=%s worker=%s", type(exc).__name__, value.worker_id
            )
            value.status, value.code = "failed", "WORKER_INTERNAL"
            value.failure = WorkerFailure(
                code="WORKER_INTERNAL", message="子任务内部错误，已停止。"
            )
        finally:
            child = self.sessions.active_for(value.session_id)
            if child:
                child.stop.set()
                child.cancel.set()
                if child.task:
                    await asyncio.gather(child.task, return_exceptions=True)
            await self._refresh_record(value)
            value.updated_at = utc_now()
            await self.save(value)
            self.drivers.pop(value.worker_id, None)
            if value.status in {"failed", "budget_exceeded"}:
                error = self._failure_error(value)
                owner = self.sessions.active_for(value.owner_session_id)
                # 迟到的子失败只属于原安排，不能停止后来启动的其他运行。
                # Late child failures belong to their assignment, never an unrelated later run.
                if owner and (
                    owner.run_id == value.owner_run_id
                    or (
                        value.goal_id is not None
                        and owner.goal
                        and owner.goal.goal_id == value.goal_id
                    )
                ):
                    owner.dependency_error = error
                    owner.stop.set()
                    owner.cancel.set()
                elif value.goal_id:
                    self.failures[value.goal_id] = error

    def live_seconds(
        self, owner_id: str, *, run_id: str | None = None, goal_id: str | None = None
    ) -> float:
        """只累计尚未入账的子运行活跃时间。

        Sum only child active time not yet committed to the ledger.
        """
        total = 0.0
        for value in self.records.values():
            if (
                value.owner_session_id != owner_id
                or (run_id and value.owner_run_id != run_id)
                or (goal_id and value.goal_id != goal_id)
            ):
                continue
            child = self.sessions.active_for(value.session_id)
            if child and not any(
                fact.run_id == child.run_id and isinstance(fact.data, RunFinished)
                for fact in child.log.facts
            ):
                total += child.active_seconds()
        return total

    def child_remaining(self, child: "ActiveRun") -> float | None:
        """所有孩子共享原 Run 与 Goal 的实际剩余时间。

        All children share the original run and goal's actual remaining time.
        """
        value = self.child_record(child.log.session_id)
        if not value:
            return None
        parent = self.sessions.active_for(value.owner_session_id)
        driver = self.sessions.goals.driver(value.owner_session_id) if self.sessions.goals else None
        log = parent.log if parent else driver.log if driver else None
        if log is None:
            return 0.0
        relevant = [fact for fact in log.facts if fact.run_id == value.owner_run_id]
        start = next((fact.data for fact in relevant if isinstance(fact.data, RunAccepted)), None)
        if start is None:
            return 0.0
        own = (
            parent.active_seconds()
            if parent and parent.run_id == value.owner_run_id
            else next(
                (
                    fact.data.elapsed_seconds or 0
                    for fact in relevant
                    if isinstance(fact.data, RunFinished)
                ),
                0.0,
            )
        )
        delegated = sum(
            fact.data.active_seconds for fact in relevant if isinstance(fact.data, DelegatedUsage)
        )
        remaining = (
            (
                start.limits.max_seconds
                - own
                - delegated
                - self.live_seconds(value.owner_session_id, run_id=value.owner_run_id)
            )
            if start.limits.max_seconds is not None
            else None
        )
        if value.goal_id:
            state = states(log.facts)[value.goal_id]
            if state.budget.max_active_seconds is not None:
                consumed = usage(
                    log.facts,
                    value.goal_id,
                    live_seconds={parent.run_id: parent.active_seconds()} if parent else None,
                )
                remaining = minimum_limit(
                    remaining,
                    state.budget.max_active_seconds
                    - consumed.active_seconds
                    - consumed.reserved_seconds
                    - self.live_seconds(value.owner_session_id, goal_id=value.goal_id),
                )
        return max(0.0, remaining) if remaining is not None else None

    def rate(self, active: "ActiveRun") -> int:
        """并行时间按各工作单元活跃秒数相加，不计算被动等待。

        Concurrent time is the sum of worker active seconds, excluding passive waits.
        """
        record = self.child_record(active.log.session_id)
        owner_id = record.owner_session_id if record else active.log.session_id
        owner = self.sessions.active_for(owner_id)
        rate = int(owner is not None and owner.wait_started_at is None)
        for item in self.records.values():
            child = self.sessions.active_for(item.session_id)
            if item.owner_session_id == owner_id and child and child.wait_started_at is None:
                rate += 1
        return rate

    async def charge_locked(self, child: "ActiveRun", data: FactData) -> None:
        """会话锁内按真实请求 / 工具事实给父安排入账。

        Charge the assignment from real child request/tool facts while holding the session lock.
        """
        value = self.child_record(child.log.session_id)
        if value is None:
            return
        requests = int(isinstance(data, (RequestStarted, AuxiliaryStarted)))
        tools = int(isinstance(data, ToolStarted))
        tokens = (
            data.turn.usage
            if isinstance(data, AssistantCommitted)
            else data.usage
            if isinstance(data, (AuxiliaryCompleted, RequestFailed))
            else data.failed_request_usage
            if isinstance(data, RunFinished)
            else None
        )
        seconds = child.active_seconds() if isinstance(data, RunFinished) else 0.0
        if not requests and not tools and tokens is None and not seconds:
            return
        owner_log = await self.sessions._load(value.owner_session_id)
        if requests or tools:
            _, accepted = await self._owner(value)
            own_facts = [fact for fact in owner_log.facts if fact.run_id == value.owner_run_id]
            requested = sum(
                isinstance(fact.data, (RequestStarted, AuxiliaryStarted)) for fact in own_facts
            )
            executed = sum(isinstance(fact.data, ToolStarted) for fact in own_facts)
            delegated = [fact.data for fact in own_facts if isinstance(fact.data, DelegatedUsage)]
            if (
                accepted.limits.max_requests is not None
                and requested + sum(item.requests for item in delegated) + requests
                > accepted.limits.max_requests
            ):
                raise AgentError("BUDGET_REQUESTS", "父安排与子任务的共同请求预算已用完。")
            if (
                accepted.limits.max_tools is not None
                and executed + sum(item.tools for item in delegated) + tools
                > accepted.limits.max_tools
            ):
                raise AgentError("BUDGET_TOOLS", "父安排与子任务的共同工具预算已用完。")
            if value.goal_id:
                state = states(owner_log.facts)[value.goal_id]
                parent = self.sessions.active_for(value.owner_session_id)
                consumed = usage(
                    owner_log.facts,
                    value.goal_id,
                    live_seconds={parent.run_id: parent.active_seconds()} if parent else None,
                )
                consumed = consumed.model_copy(
                    update={
                        "active_seconds": consumed.active_seconds
                        + self.live_seconds(value.owner_session_id, goal_id=value.goal_id)
                    }
                )
                check_budget(state.budget, consumed, requests=requests, tools=tools)
        await self.sessions.worker.call(
            self.sessions.store.append,
            owner_log,
            DelegatedUsage(
                worker_id=value.worker_id,
                source_run_id=child.run_id,
                source_seq=len(child.log.facts) + 1,
                requests=requests,
                tools=tools,
                active_seconds=seconds,
                usage=tokens,
            ),
            value.owner_run_id,
        )
        self.sessions.signal_log(owner_log)

    async def result(self, owner_id: str, identity: str, *, wait: bool) -> WorkerRecord:
        """事件等待可被用户插话打断，完整历史仍可从卡片读取。

        Event waits yield to user questions; complete histories remain readable from cards.
        """
        await self._load()
        value = self.records.get(identity)
        if value is None or value.owner_session_id != owner_id:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "此子任务不属于当前会话。")
        owner = self.sessions.active_for(owner_id)
        try:
            while wait and value.status in {"queued", "running"}:
                changed = self.changed
                if owner and (owner.stop.is_set() or owner.yield_requested):
                    break
                if owner:
                    await self.sessions.set_wait(owner, identity)
                await changed.wait()
            await self._refresh_record(value)
            return value
        finally:
            if owner:
                await self.sessions.set_wait(owner, None)

    async def stop(self, owner_id: str, identity: str) -> WorkerPage:
        """停止单个真实子工作，其他正式会话不受影响。

        Stop one child without affecting unrelated formal sessions.
        """
        await self.result(owner_id, identity, wait=False)
        task = self.drivers.get(identity)
        if task:
            if not task.cancelling():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return await self.page(owner_id)

    async def continue_work(self, owner: "ActiveRun", identity: str, prompt: str) -> WorkerRecord:
        """活动孩子只收补充，终态孩子复用历史启动明确新工作。

        Active children receive supplements; finished children reuse history for explicit new work.
        """
        value = await self.result(owner.log.session_id, identity, wait=False)
        if value.status in {"queued", "running"}:
            value.pending_messages.append(prompt)
            await self.save(value)
            return value
        if not (await self.prepare(owner.log.session_id)).enabled:
            raise AgentError("WORKERS_DISABLED", "此会话尚未开启子 Agent，不能接纳新的子任务工作。")
        value.owner_run_id = owner.run_id
        value.goal_id = owner.goal.goal_id if owner.goal else None
        value.status, value.result, value.code = "queued", "", None
        value.failure, value.run_id = None, None
        value.pending_messages = []
        await self.save(value)
        self.drivers[identity] = asyncio.create_task(self._drive(value, prompt))
        self._watch_owners()
        return value

    async def inbox(self, session_id: str) -> str:
        """补充在子请求边界可见，来源仍标为协作者。

        Supplements become visible at child request boundaries as collaborator data.
        """
        value = self.child_record(session_id)
        if value is None or not value.pending_messages:
            return ""
        return (
            "\nSupplements from the parent assignment (within the original task scope):\n"
            + json.dumps(value.pending_messages, ensure_ascii=False)
        )

    async def finish_owner(self, active: "ActiveRun", yielded: bool) -> None:
        """Goal 插话保留子工作；普通结束等待结果，停止取消子工作。

        Preserve children across goal questions; completion awaits results and stopping
        cancels them.

        """
        if active.goal and active.goal.role == "question" and active.dependency_error is None:
            return
        owned = [
            item
            for item in self.records.values()
            if item.owner_session_id == active.log.session_id
            and (
                item.goal_id == active.goal.goal_id
                if active.goal
                else item.owner_run_id == active.run_id
            )
        ]
        if yielded and active.goal:
            return
        for item in owned:
            if active.stop.is_set():
                await self.stop(active.log.session_id, item.worker_id)
            else:
                result = await self.result(active.log.session_id, item.worker_id, wait=True)
                if (
                    result.status in {"failed", "budget_exceeded"}
                    and result.owner_run_id == active.run_id
                ):
                    raise self._failure_error(result)

    async def close(self) -> None:
        """退出时取消所有子工作，重启不自动续跑。

        Cancel all children on exit without automatically resuming after restart.
        """
        self.closed = True
        if self.watcher:
            self.watcher.cancel()
            await asyncio.gather(self.watcher, return_exceptions=True)
        tasks = list(self.drivers.values())
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.unsubscribe()
