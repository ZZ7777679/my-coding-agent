"""CLI 与桌面共用的会话、运行与订阅服务。 Shared session, run and subscription service."""

import asyncio
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from my_agent.config import load_config
from my_agent.errors import AgentError
from my_agent.goals.ledger import check_budget, usage
from my_agent.goals.state import states
from my_agent.goals.types import GoalInputQueued, GoalRunBinding
from my_agent.models.types import ModelClient, ModelId, ModelProgress
from my_agent.projects import ProjectService
from my_agent.runtime.context import SharedContext
from my_agent.runtime.loop import run_loop
from my_agent.runtime.modes import RunMode, system_prompt
from my_agent.runtime.settings import RunLimits
from my_agent.runtime.tools import ToolContext, ToolExecutor
from my_agent.sessions.projection import entries, selected_model, summarize
from my_agent.sessions.store import SessionLog, SessionStore
from my_agent.sessions.types import (
    AssistantCommitted,
    AuxiliaryStarted,
    Fact,
    FactData,
    ProgressSynced,
    RequestStarted,
    RunAccepted,
    RunFinished,
    SessionAssigned,
    SessionCreated,
    SessionModelChanged,
    SessionPage,
    SessionSignal,
    SessionSummary,
    SessionView,
    ToolStarted,
)
from my_agent.worker import BusinessWorker
from my_agent.workflow.methods import MethodResource, load_method
from my_agent.workflow.tools import WorkflowTools
from my_agent.workflow.types import WorkMethod

if TYPE_CHECKING:
    from my_agent.collaboration.service import CollaborationService
    from my_agent.goals.service import GoalService
    from my_agent.sessions.recovery import RecoveryService


@dataclass
class ActiveRun:
    """单个运行的内存状态；文本预览不等于已提交事实。 Live state; preview text is not durable."""

    log: SessionLog
    run_id: str
    limits: RunLimits
    mode: RunMode
    plan_document: str | None
    goal: GoalRunBinding | None = None
    time_limit_seconds: float | None = None
    method: MethodResource | None = None
    started_at: float = field(default_factory=time.monotonic)
    stop: threading.Event = field(default_factory=threading.Event)
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    message_id: str | None = None
    model_id: ModelId | None = None
    text: str = ""
    reasoning: str = ""
    delta_index: int = 0
    task: asyncio.Task[None] | None = None
    fatal_error: str | None = None
    model_progress: ModelProgress | None = None
    progress_at: float | None = None
    sync_error: str | None = None
    yield_requested: bool = False
    budget_changed: asyncio.Event = field(default_factory=asyncio.Event)
    collaboration_id: str | None = None

    def progress_snapshot(self) -> ModelProgress | None:
        """只推进本地等待时钟，不伪造新的收包或模型活动。

        Advance only the local waiting clock, never received-data or model-activity timestamps.
        """
        progress = self.model_progress
        if (
            progress is None
            or self.progress_at is None
            or progress.phase == "completed"
            or self.stop.is_set()
        ):
            return progress
        return progress.model_copy(
            update={
                "elapsed_ms": progress.elapsed_ms + (time.monotonic() - self.progress_at) * 1000
            }
        )


class SessionService:
    """每个会话独立运行，持久写入短时串行；订阅不触发模型请求。

    Run sessions independently with serialized durable writes; subscriptions never call models.
    """

    def __init__(
        self,
        store: SessionStore,
        projects: ProjectService,
        worker: BusinessWorker,
        model_factory: Callable[[], ModelClient],
        *,
        tool_factory: Callable[[ToolContext], ToolExecutor],
        close_model: Callable[[], Awaitable[None]] | None = None,
        context_loader: Callable[[SessionLog], SharedContext | None] | None = None,
        finish_run: Callable[[str], Awaitable[None]] | None = None,
        close_execution: Callable[[], Awaitable[None]] | None = None,
        sync_report: Callable[[str, int], Awaitable[tuple[str, int] | None]] | None = None,
    ) -> None:
        """显式注入组件，不在运行时创建 provider。

        Inject components without runtime provider construction.
        """
        self.store = store
        self.projects = projects
        self.worker = worker
        self.model_factory = model_factory
        self.tool_factory = tool_factory
        self.close_model = close_model
        self.context_loader = context_loader
        self.finish_run = finish_run
        self.close_execution = close_execution
        self.sync_report = sync_report
        self.epoch = str(uuid4())
        self.active_runs: dict[str, ActiveRun] = {}
        self.lock = asyncio.Lock()
        self.listeners: list[Callable[[SessionSignal], None]] = []
        self.last_log: SessionLog | None = None
        self.goals: GoalService | None = None
        self.recovery: RecoveryService | None = None
        self.collaboration: CollaborationService | None = None
        self.closing = False

    def active_for(self, session_id: str) -> ActiveRun | None:
        """按会话取真实运行句柄，不依赖当前 UI 选择。

        Look up a live run by session, independently of the current UI selection.
        """
        return self.active_runs.get(session_id)

    async def active_summaries(self) -> list[SessionSummary]:
        """一致读取全部活动会话，取消仍按精确 Run ID 路由。

        Snapshot all active sessions consistently; cancellation still targets an exact run ID.
        """
        async with self.lock:
            return [
                summarize(active.log, active=True, stopping=active.cancel.is_set())
                for active in self.active_runs.values()
            ]

    def signal_log(self, log: SessionLog) -> None:
        """发布会话元数据变化，不绑定某次 Run，仍带真实会话水位。

        Signal session metadata independently of a run, retaining the real watermark.
        """
        signal = SessionSignal(
            session_id=log.session_id,
            run_id=None,
            process_epoch=self.epoch,
            kind="changed",
            seq=len(log.facts),
            message_id=None,
            delta_index=0,
            text="",
        )
        for listener in tuple(self.listeners):
            listener(signal)

    def subscribe(self, listener: Callable[[SessionSignal], None]) -> Callable[[], None]:
        """注册内存事件回调，返回注销入口。

        Subscribe to memory events and return an unsubscribe hook.
        """
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener) if listener in self.listeners else None

    def _signal(self, active: ActiveRun, kind: str = "changed", text: str = "") -> None:
        """发布轻量事件；接收端负责有界队列与缺口重同步。 Publish signals for bounded consumers."""
        signal = SessionSignal.model_validate(
            {
                "session_id": active.log.session_id,
                "run_id": active.run_id,
                "process_epoch": self.epoch,
                "kind": kind,
                "seq": len(active.log.facts),
                "message_id": active.message_id,
                "delta_index": active.delta_index,
                "text": text,
                "model_progress": active.progress_snapshot(),
            }
        )
        for listener in tuple(self.listeners):
            listener(signal)

    async def _load(self, session_id: str) -> SessionLog:
        """活动或刚结束会话复用内存，其余从事实恢复。

        Reuse live state or recover persisted facts.
        """
        active = self.active_for(session_id)
        if active is not None:
            return active.log
        driver = self.goals.driver(session_id) if self.goals else None
        if driver is not None:
            return driver.log
        if self.last_log and self.last_log.session_id == session_id:
            return self.last_log
        return await self.worker.call(self.store.load, session_id)

    async def validate_project(self, project_id: str) -> Path:
        """重新核实登记身份，不把当前 cwd 当项目。 Revalidate registered identity, never use cwd."""
        index = await self.worker.call(self.projects.read)
        record = next((p for p in index.projects if p.project_id == project_id), None)
        if record is None:
            raise AgentError("PROJECT_NOT_FOUND", "请先选择项目。")
        summary = await self.worker.call(self.projects.summary, record)
        if not summary.available:
            raise AgentError(
                summary.unavailable_code or "PROJECT_UNAVAILABLE", "项目目录失效，请重新选择。"
            )
        return Path(summary.canonical_path)

    async def create(
        self,
        project_id: str,
        model_id: ModelId,
        *,
        session_id: str | None = None,
        operation_id: str | None = None,
        task_id: str | None = None,
        role: str = "",
        scope: str = "",
    ) -> SessionSummary:
        """验证项目后保存会话头，不调用模型。 Validate the project and persist a session header."""
        async with self.lock:
            await self.validate_project(project_id)
            identity = session_id or str(uuid4())
            header = SessionCreated(
                project_id=project_id,
                model_id=model_id,
                task_id=task_id,
                creation_operation_id=operation_id,
                role=role,
                scope=scope,
                initial_mode="normal",
            )
            if self.store.path(identity).exists():
                existing = await self._load(identity)
                if not existing.facts or existing.facts[0].data.model_dump(
                    exclude={"initial_mode"}
                ) != header.model_dump(exclude={"initial_mode"}):
                    raise AgentError("OPERATION_CONFLICT", "该创建标识已用于其他会话。")
                active = self.active_for(identity)
                return summarize(
                    existing,
                    active=active is not None,
                    stopping=bool(active and active.cancel.is_set()),
                )
            log = SessionLog(identity, [])
            await self.worker.call(
                self.store.append,
                log,
                header,
                None,
            )
            return summarize(log)

    async def assign(
        self, session_id: str, project_id: str, assignment: SessionAssigned
    ) -> SessionSummary:
        """空闲时追加用户归属；幂等重试不重复写入。

        Append idle-session membership with idempotent retries.
        """
        async with self.lock:
            log = await self._load(session_id)
            summary = summarize(log)
            if summary.project_id != project_id:
                raise AgentError("TASK_PROJECT_MISMATCH", "会话和任务必须属于同一个项目。")
            for fact in log.facts:
                if (
                    isinstance(fact.data, SessionAssigned)
                    and fact.data.operation_id == assignment.operation_id
                ):
                    if fact.data != assignment:
                        raise AgentError("OPERATION_CONFLICT", "该操作标识已用于不同会话归属。")
                    return summary
            if self.active_for(session_id) or (self.goals and self.goals.driver(session_id)):
                raise AgentError("RUN_BUSY", "请等待该会话运行结束，再修改归属或分工。")
            await self.worker.call(self.store.append, log, assignment, None)
            return summarize(log)

    async def select_model(
        self, session_id: str, operation_id: str, model_id: ModelId
    ) -> SessionSummary:
        """持久化用户选择；已接纳请求不改动，下一请求读取新值。

        Persist the user choice for the next request, leaving admitted requests unchanged.
        """
        async with self.lock:
            log = await self._load(session_id)
            change = SessionModelChanged(operation_id=operation_id, model_id=model_id)
            prior = next(
                (
                    f.data
                    for f in log.facts
                    if isinstance(f.data, SessionModelChanged)
                    and f.data.operation_id == operation_id
                ),
                None,
            )
            if prior is not None and prior != change:
                raise AgentError("OPERATION_CONFLICT", "该操作标识已经用于另一个模型选择。")
            if prior is None:
                await self.worker.call(self.store.append, log, change, None)
                self.signal_log(log)
            active = self.active_for(session_id)
            return summarize(
                log, active=active is not None, stopping=bool(active and active.cancel.is_set())
            )

    async def shared_context(self, log: SessionLog) -> SharedContext | None:
        """每次请求读取已保存任务版本，不增加模型调用。

        Load a saved task revision before each model request.
        """
        if self.context_loader is None:
            return None
        return await self.worker.call(self.context_loader, log)

    async def view(self, session_id: str, before_seq: int | None = None) -> SessionView:
        """在一致锁边界取得水位与预览，调用方可先订阅再去重。

        Snapshot watermark and preview consistently; callers subscribe first and deduplicate.
        """
        async with self.lock:
            log = await self._load(session_id)
            active = self.active_for(session_id)
            page, cursor = entries(log, before_seq)
            summary = summarize(
                log, active=active is not None, stopping=bool(active and active.cancel.is_set())
            )
            if active and active.fatal_error:
                summary = summary.model_copy(
                    update={"issue": active.fatal_error, "can_continue": False}
                )
            progress = active.progress_snapshot() if active else None
            if active is None:
                # 未结束的新请求不能继承上一请求的首字计时。
                # An interrupted new request must not inherit the previous request's timing.
                for fact in reversed(log.facts):
                    if isinstance(fact.data, (RunAccepted, RequestStarted)):
                        break
                    if isinstance(fact.data, (RunFinished, AssistantCommitted)):
                        progress = fact.data.model_progress
                        break
            return SessionView(
                summary=summary,
                entries=page,
                before_seq=cursor,
                watermark=len(log.facts),
                process_epoch=self.epoch,
                stream_message_id=active.message_id if active else None,
                stream_model_id=active.model_id if active else None,
                stream_text=active.text if active else "",
                stream_reasoning=active.reasoning if active else "",
                delta_index=active.delta_index if active else 0,
                model_progress=progress,
            )

    async def list(self, project_id: str, cursor: str | None, limit: int) -> SessionPage:
        """按稳定目录游标分页，单个损坏会话不阻塞其余会话。

        Page without letting one corrupt log block others.
        """

        def load_page() -> tuple[list[SessionLog], str | None, int]:
            """在业务线程扫描会话目录，不触发文件创建。

            Scan session directories without creating files.
            """
            if not self.store.root.exists():
                return [], None, 0
            candidates = sorted(path.name for path in self.store.root.iterdir() if path.is_dir())
            logs: list[SessionLog] = []
            next_cursor: str | None = None
            unavailable = 0
            page_bytes = 0
            for name in candidates:
                if cursor is not None and name <= cursor:
                    continue
                try:
                    log = self.store.load(name)
                    header = log.facts[0].data if log.facts else None
                    if not isinstance(header, SessionCreated):
                        unavailable += 1
                    if isinstance(header, SessionCreated) and header.project_id == project_id:
                        size = len(summarize(log).model_dump_json().encode("utf-8"))
                        # 分页受传输帧容量约束，不限制可创建的会话数量。
                        # Bound page bytes for transport, never the number of available sessions.
                        if len(logs) >= limit or (logs and page_bytes + size > 350000):
                            next_cursor = logs[-1].session_id
                            break
                        logs.append(log)
                        page_bytes += size
                except AgentError:
                    # 单个不可读记录保留；其余会话仍可列出，已知 ID 可获得明确错误。
                    # Preserve unreadable logs; direct lookup still reports errors.
                    logging.getLogger(__name__).warning("SESSION_LIST_ENTRY_UNAVAILABLE")
                    unavailable += 1
            return logs, next_cursor, unavailable

        async with self.lock:
            logs, next_cursor, unavailable = await self.worker.call(load_page)
            summaries: list[SessionSummary] = []
            for log in logs:
                active = self.active_for(log.session_id)
                summaries.append(
                    summarize(
                        active.log if active else log,
                        active=active is not None,
                        stopping=bool(active and active.cancel.is_set()),
                    )
                )
            return SessionPage(
                unavailable_count=unavailable,
                sessions=summaries,
                next_cursor=next_cursor,
                active_session_ids=[
                    identity
                    for identity, active in self.active_runs.items()
                    if summarize(active.log).project_id == project_id
                ],
            )

    async def start(
        self,
        session_id: str,
        operation_id: str,
        prompt: str,
        requested_limits: RunLimits | None,
        mode: RunMode = "plan",
        plan_document: str | None = None,
        *,
        goal: GoalRunBinding | None = None,
        collaboration_id: str | None = None,
        work_method: WorkMethod | None = None,
    ) -> SessionSummary:
        """先持久接纳再快速确认，同操作标识不重复请求。

        Durably accept then ack, with idempotent starts.
        """
        if not prompt.strip() or len(prompt.encode("utf-8")) > 64000:
            raise AgentError("PROMPT_INVALID", "请输入非空问题（最多 64 KB UTF-8）。")
        if mode == "normal" and plan_document is not None:
            raise AgentError("MODE_INVALID", "计划文档授权仅用于 Plan 模式。")
        if goal is None and collaboration_id is None and mode == "plan" and self.goals is not None:
            async with self.lock:
                existing_log = await self._load(session_id)
                repeated = any(
                    isinstance(fact.data, (RunAccepted, GoalInputQueued))
                    and fact.data.operation_id == operation_id
                    for fact in existing_log.facts
                )
            if not repeated:
                await self.goals.pause_for_plan(session_id)
        async with self.lock:
            if self.closing:
                raise AgentError("APP_CLOSING", "应用正在退出，不接纳新的运行。")
            log = await self._load(session_id)
            if (
                goal is None
                and collaboration_id is None
                and self.goals is not None
                and any(
                    isinstance(fact.data, GoalInputQueued)
                    and fact.data.operation_id == operation_id
                    for fact in log.facts
                )
            ):
                queued = await self.goals.offer_input_locked(
                    log, operation_id, prompt, requested_limits, mode
                )
                if queued is not None:
                    return queued
            for fact in log.facts:
                if isinstance(fact.data, RunAccepted) and fact.data.operation_id == operation_id:
                    if (
                        fact.data.prompt != prompt
                        or fact.data.requested_limits != requested_limits
                        or fact.data.mode != mode
                        or fact.data.plan_document != plan_document
                        or fact.data.goal_id != (goal.goal_id if goal else None)
                        or fact.data.goal_role != (goal.role if goal else None)
                        or fact.data.collaboration_id != collaboration_id
                        or (work_method is not None and fact.data.method != work_method)
                    ):
                        raise AgentError("OPERATION_CONFLICT", "同一操作标识已用于不同输入。")
                    # 返回原运行，而非把重复提交绑定到后来一次运行。
                    # Return the original run rather than a newer run in the same session.
                    end = next(
                        (f.seq for f in log.facts[fact.seq :] if isinstance(f.data, RunAccepted)),
                        len(log.facts) + 1,
                    )
                    original = SessionLog(log.session_id, log.facts[: end - 1], log.issue)
                    active = self.active_for(session_id)
                    is_active = active is not None and active.run_id == fact.run_id
                    return summarize(
                        original,
                        active=is_active,
                        stopping=bool(is_active and active and active.cancel.is_set()),
                    )
            if goal is None and collaboration_id is None and self.goals is not None:
                queued = await self.goals.offer_input_locked(
                    log, operation_id, prompt, requested_limits, mode
                )
                if queued is not None:
                    return queued
            if self.active_for(session_id) is not None:
                raise AgentError("RUN_BUSY", "此会话已有运行，请先停止或等待结束。")
            if collaboration_id is not None:
                if self.collaboration is None:
                    raise AgentError("COLLABORATION_UNAVAILABLE", "协作服务尚未装配。")
                await self.collaboration.admit_locked(log, collaboration_id)
            if goal is None and self.recovery is not None and not log.context()[1]:
                await self.recovery.recover_locked(log, operation_id)
            await self._sync_pending_reports(log)
            summary = summarize(log)
            if not summary.can_continue:
                raise AgentError(
                    "SESSION_READ_ONLY", "会话记录不可接续，请查看具体存储或运行错误。"
                )
            root = await self.validate_project(summary.project_id)
            config = await self.worker.call(load_config, self.store.storage.location)
            limits = requested_limits or config.run
            time_limit = float(limits.max_seconds)
            method_name: WorkMethod = work_method or ("plan" if mode == "plan" else "implement")
            if goal is not None:
                state = states(log.facts).get(goal.goal_id)
                if state is None:
                    raise AgentError("GOAL_NOT_FOUND", "Goal 记录不存在。")
                method_name = (
                    "discuss"
                    if goal.role == "question"
                    else goal.work.method
                    if goal.work
                    else state.definition.method
                )
                consumed = usage(log.facts, goal.goal_id)
                check_budget(state.budget, consumed, requests=1)
                if state.budget.max_active_seconds is not None:
                    time_limit = min(
                        time_limit,
                        state.budget.max_active_seconds
                        - consumed.active_seconds
                        - consumed.reserved_seconds,
                    )
            method = await self.worker.call(load_method, method_name)
            # 重启后确认旧 run 中断；不重放工具，只允许完整历史继续。
            # Mark old unfinished runs interrupted without replaying tools.
            if (
                summary.run
                and summary.run.status == "interrupted"
                and not any(
                    fact.run_id == summary.run.run_id and isinstance(fact.data, RunFinished)
                    for fact in log.facts
                )
            ):
                await self.worker.call(
                    self.store.append,
                    log,
                    RunFinished(
                        status="interrupted",
                        code="PROCESS_INTERRUPTED",
                        message="上次后端退出，未自动重放。",
                    ),
                    summary.run.run_id,
                )
            run_id = str(uuid4())
            await self.worker.call(
                self.store.append,
                log,
                RunAccepted(
                    operation_id=operation_id,
                    prompt=prompt,
                    limits=limits,
                    requested_limits=requested_limits,
                    mode=mode,
                    plan_document=plan_document,
                    goal_id=goal.goal_id if goal else None,
                    goal_role=goal.role if goal else None,
                    active_time_limit_seconds=time_limit if goal else None,
                    work_id=goal.work.work_id if goal and goal.work else None,
                    method=method.name,
                    method_version=method.version,
                    collaboration_id=collaboration_id,
                ),
                run_id,
            )
            active = ActiveRun(log, run_id, limits, mode, plan_document, goal, time_limit, method)
            active.collaboration_id = collaboration_id
            self.active_runs[session_id] = active
            active.task = asyncio.create_task(self._drive(active, root, summary.model_id))
            self._signal(active)
            return summarize(log, active=True)

    async def cancel(self, run_id: str) -> SessionSummary:
        """停止请求不等文件锁，终态等待实际资源清理。

        Signal cancellation without waiting for file locks.
        """
        active = next((run for run in self.active_runs.values() if run.run_id == run_id), None)
        if active is None:
            raise AgentError("RUN_NOT_ACTIVE", "该运行已结束或不属于当前后端。")
        if active.goal is not None and self.goals is not None:
            await self.goals.pause_from_run(active)
        active.stop.set()
        active.cancel.set()
        self._signal(active)
        return summarize(active.log, active=True, stopping=True)

    def remaining_seconds(self, active: ActiveRun) -> float:
        """真实单调耗时约束 Run 与 Goal；已交付服务不延长活跃时间。

        Bound runs and goals by monotonic elapsed time, excluding retained service lifetime.
        """
        elapsed = max(0.0, time.monotonic() - active.started_at)
        remaining = (active.time_limit_seconds or active.limits.max_seconds) - elapsed
        if active.goal is not None:
            state = states(active.log.facts)[active.goal.goal_id]
            consumed = usage(
                active.log.facts, active.goal.goal_id, live_seconds={active.run_id: elapsed}
            )
            if state.budget.max_active_seconds is not None:
                remaining = min(
                    remaining,
                    state.budget.max_active_seconds
                    - consumed.active_seconds
                    - consumed.reserved_seconds,
                )
        return max(0.0, remaining)

    async def _wait_work(
        self, active: ActiveRun, work: asyncio.Task[Literal["finished", "yielded"]]
    ) -> Literal["finished", "yielded"]:
        """预算修改唤醒计时等待，收紧限额立即生效，不轮询或重置时间。

        Budget edits wake the deadline wait; tighter limits apply without polling or resetting time.
        """
        cancel = asyncio.create_task(active.cancel.wait())
        changed: asyncio.Task[bool] | None = None
        try:
            while True:
                active.budget_changed.clear()
                changed = asyncio.create_task(active.budget_changed.wait())
                done, _ = await asyncio.wait(
                    {work, cancel, changed},
                    timeout=self.remaining_seconds(active),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancel in done:
                    raise asyncio.CancelledError
                if work in done:
                    return await work
                if changed not in done:
                    raise AgentError(
                        "BUDGET_GOAL_TIME" if active.goal else "BUDGET_TIME",
                        "已达到本次运行或 Goal 剩余活跃时间预算，请调整后明确继续。",
                    )
                await changed
        finally:
            for task in (cancel, changed):
                if task is not None:
                    task.cancel()
            await asyncio.gather(cancel, *([changed] if changed else []), return_exceptions=True)

    async def _sync_pending_reports(self, log: SessionLog) -> None:
        """调用方持会话锁；只补保存过的工作结果，不重放工具或模型。

        The caller holds the session lock; sync saved results without replaying tools or models.
        """
        synced = {
            fact.data.result_seq for fact in log.facts if isinstance(fact.data, ProgressSynced)
        }
        pending = [
            fact
            for fact in log.facts
            if isinstance(fact.data, RunFinished)
            and fact.data.report is not None
            and fact.seq not in synced
        ]
        for fact in pending:
            if self.sync_report is None:
                raise AgentError(
                    "PROGRESS_SYNC_UNAVAILABLE", "共享进度服务不可用，已保存运行结果。"
                )
            target = await self.sync_report(log.session_id, fact.seq)
            await self.worker.call(
                self.store.append,
                log,
                ProgressSynced(
                    result_seq=fact.seq,
                    task_id=target[0] if target else None,
                    task_revision=target[1] if target else None,
                ),
                None,
            )

    async def _drive(self, active: ActiveRun, root: Path, model_id: ModelId) -> None:
        """协调取消、总时限和终态保存，所有终态只提交一次。

        Coordinate cleanup and one terminal fact.
        """
        sink = ServiceSink(self, active)
        work: asyncio.Task[Literal["finished", "yielded"]] | None = None
        tools: WorkflowTools | None = None
        finished = RunFinished(status="completed", code=None, message=None)
        try:
            context, complete = active.log.context()
            if not complete:
                raise AgentError("SESSION_READ_ONLY", "历史不完整，不能发送给模型。")
            if active.cancel.is_set():
                raise asyncio.CancelledError
            tool_context = ToolContext(
                root=root,
                limits=active.limits,
                stop=active.stop,
                project_id=summarize(active.log).project_id,
                session_id=active.log.session_id,
                run_id=active.run_id,
                mode=active.mode,
                plan_document=active.plan_document,
                request_sink=sink,
                collaboration_id=active.collaboration_id,
            )
            tools = WorkflowTools(
                tool_context, self.tool_factory(tool_context), active.log, self.worker
            )
            model = self.model_factory()
            work = asyncio.create_task(
                run_loop(
                    model=model,
                    tools=tools,
                    sink=sink,
                    model_id=model_id,
                    model_selector=lambda: selected_model(active.log),
                    session_id=active.log.session_id,
                    messages=context,
                    limits=active.limits,
                    stop=active.stop,
                    context_provider=lambda: self.shared_context(active.log),
                    system_prompt=system_prompt(active.mode, active.plan_document)
                    + tools.request_reference()
                    + ("\n\nBundled work method:\n" + active.method.text if active.method else "")
                    + (
                        self.goals.prompt(active.log, active.goal)
                        if self.goals and active.goal
                        else ""
                    ),
                    terminal=tools.finished,
                    yield_requested=lambda: active.yield_requested,
                )
            )
            result = await self._wait_work(active, work)
            if result == "yielded":
                finished = finished.model_copy(
                    update={"checkpoint": True, "message": "已在完整边界让出执行。"}
                )
        except asyncio.CancelledError:
            finished = RunFinished(
                status="interrupted" if self.closing else "cancelled",
                code="APP_CLOSED" if self.closing else "CANCELLED",
                message="应用退出，未自动恢复。" if self.closing else "运行已停止。",
            )
        except AgentError as exc:
            finished = RunFinished(
                status="budget_exceeded" if exc.code.startswith("BUDGET_") else "failed",
                code=exc.code,
                message=exc.message,
            )
        except Exception as exc:
            # 保留异常类别与运行关联，不记录可能含秘密的原始异常消息。
            # Retain exception class and run correlation without potentially secret messages.
            logging.getLogger(__name__).error(
                "RUN_INTERNAL_ERROR type=%s run=%s", type(exc).__name__, active.run_id
            )
            finished = RunFinished(
                status="failed",
                code="RUN_INTERNAL_ERROR",
                message="运行发生内部错误，请查看状态并新建会话。",
            )
        finally:
            active.stop.set()
            if work is not None and not work.done():
                work.cancel()
            if work is not None:
                await asyncio.gather(work, return_exceptions=True)
            if self.finish_run is not None:
                try:
                    await self.finish_run(active.run_id)
                except AgentError as exc:
                    finished = RunFinished(status="failed", code=exc.code, message=exc.message)
            try:
                if tools is not None:
                    finished = finished.model_copy(update={"report": tools.report})
                await sink.commit(finished)
            except AgentError as exc:
                active.log.issue = exc.code
                active.fatal_error = exc.code
            if not active.log.issue:
                try:
                    async with self.lock:
                        await self._sync_pending_reports(active.log)
                except AgentError as exc:
                    active.sync_error = exc.code
                    logging.getLogger(__name__).warning(
                        "PROGRESS_SYNC_PENDING code=%s run=%s", exc.code, active.run_id
                    )
            async with self.lock:
                self.last_log = active.log
                self.active_runs.pop(active.log.session_id)
                self._signal(active)

    async def close(self) -> None:
        """停止并等待活动任务，调用方随后释放写锁。

        Stop and await work before releasing the writer lock.
        """
        try:
            self.closing = True
            if self.collaboration is not None:
                await self.collaboration.close()
            running = tuple(self.active_runs.values())
            for active in running:
                active.stop.set()
                active.cancel.set()
            if self.goals is not None:
                await self.goals.close()
            await asyncio.gather(*(active.task for active in running if active.task is not None))
        finally:
            try:
                if self.close_execution is not None:
                    await self.close_execution()
            finally:
                if self.close_model is not None:
                    await self.close_model()


class ServiceSink:
    """把运行时输出连接到服务持久化与通知。 Connect runtime outputs to persistence and signals."""

    def __init__(self, service: SessionService, active: ActiveRun) -> None:
        """绑定本次运行，不使用全局当前视图。 Bind this run independently of the selected view."""
        self.service = service
        self.active = active

    async def commit(self, data: FactData) -> Fact:
        """存储成功后发布并返回精确事实，取消期间仍等待存储。

        Publish and return the exact persisted fact, awaiting writes even during cancellation.
        """
        async with self.service.lock:
            if (
                isinstance(data, (RequestStarted, AuxiliaryStarted, ToolStarted))
                and self.active.goal is not None
            ):
                if self.service.remaining_seconds(self.active) <= 0:
                    raise AgentError("BUDGET_GOAL_TIME", "Goal 或 Run 的活跃时间预算已用完。")
            if isinstance(data, (AssistantCommitted, RunFinished)):
                data = data.model_copy(update={"model_progress": self.active.model_progress})
            if isinstance(data, RunFinished):
                data = data.model_copy(
                    update={"elapsed_seconds": max(0.0, time.monotonic() - self.active.started_at)}
                )
            fact = await self.service.worker.call(
                self.service.store.append, self.active.log, data, self.active.run_id
            )
            if isinstance(data, RequestStarted):
                self.active.message_id = data.message_id
                self.active.model_id = data.model_id
                self.active.text = ""
                self.active.reasoning = ""
                self.active.delta_index = 0
                self.active.model_progress = None
                self.active.progress_at = None
            elif isinstance(data, AssistantCommitted):
                self.active.message_id = None
                self.active.text = ""
                self.active.reasoning = ""
                self.active.delta_index = 0
            self.service._signal(self.active)
            return fact

    async def text(self, message_id: str, delta: str) -> None:
        """只缓存有界文本；不把实时字符 fsync。 Cache bounded text without per-token fsync."""
        self._display_delta(message_id, delta, "text.delta")

    async def reasoning(self, message_id: str, delta: str) -> None:
        """缓存并发布可见思考，重载快照可接续同一段流。

        Cache reasoning for live snapshot recovery.
        """
        self._display_delta(message_id, delta, "reasoning.delta")

    def _display_delta(
        self, message_id: str, delta: str, kind: Literal["text.delta", "reasoning.delta"]
    ) -> None:
        """两个展示通道共用顺序水位与输出预算。 Share ordering and output budget across channels."""
        if self.active.stop.is_set():
            raise asyncio.CancelledError
        if (
            len((self.active.text + self.active.reasoning + delta).encode("utf-8"))
            > self.active.limits.max_response_bytes
        ):
            raise AgentError("MODEL_OUTPUT_LIMIT", "模型显示文本超过容量。")
        self.active.message_id = message_id
        if kind == "text.delta":
            self.active.text += delta
        else:
            self.active.reasoning += delta
        self.active.delta_index += 1
        self.service._signal(self.active, kind, delta)

    async def progress(self, message_id: str, progress: ModelProgress) -> None:
        """阶段只更新内存，结束时随事实持久化；不阻塞首字。

        Keep phases in memory until a durable end fact, without delaying the first token.
        """
        self.active.message_id = message_id
        self.active.model_progress = progress
        self.active.progress_at = time.monotonic()
        self.service._signal(self.active, "model.progress")
