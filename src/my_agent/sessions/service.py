"""CLI 与桌面共用的会话、运行与订阅服务。 Shared session, run and subscription service."""

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from my_agent.config import load_config
from my_agent.errors import AgentError
from my_agent.models.types import ModelClient, ModelId, ModelProgress
from my_agent.projects import ProjectService
from my_agent.runtime.loop import run_loop
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.projection import entries, summarize
from my_agent.sessions.store import SessionLog, SessionStore
from my_agent.sessions.types import (
    AssistantCommitted,
    FactData,
    RequestStarted,
    RunAccepted,
    RunFinished,
    SessionCreated,
    SessionPage,
    SessionSignal,
    SessionSummary,
    SessionView,
)
from my_agent.tools.read_only import ReadTools
from my_agent.worker import BusinessWorker


@dataclass
class ActiveRun:
    """单个运行的内存状态；文本预览不等于已提交事实。 Live state; preview text is not durable."""

    log: SessionLog
    run_id: str
    limits: RunLimits
    stop: threading.Event = field(default_factory=threading.Event)
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    message_id: str | None = None
    text: str = ""
    delta_index: int = 0
    task: asyncio.Task[None] | None = None
    fatal_error: str | None = None
    model_progress: ModelProgress | None = None


class SessionService:
    """一个后端只有一个活动运行；订阅不触发新模型请求。

    One active run per backend; subscriptions never issue model requests.
    """

    def __init__(
        self,
        store: SessionStore,
        projects: ProjectService,
        worker: BusinessWorker,
        model_factory: Callable[[], ModelClient],
        *,
        close_model: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """显式注入组件，不在运行时创建 provider。

        Inject components without runtime provider construction.
        """
        self.store = store
        self.projects = projects
        self.worker = worker
        self.model_factory = model_factory
        self.close_model = close_model
        self.epoch = str(uuid4())
        self.active: ActiveRun | None = None
        self.lock = asyncio.Lock()
        self.listeners: list[Callable[[SessionSignal], None]] = []
        self.last_log: SessionLog | None = None

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
                "model_progress": active.model_progress,
            }
        )
        for listener in tuple(self.listeners):
            listener(signal)

    async def _load(self, session_id: str) -> SessionLog:
        """活动或刚结束会话复用内存，其余从事实恢复。

        Reuse live state or recover persisted facts.
        """
        if self.active and self.active.log.session_id == session_id:
            return self.active.log
        if self.last_log and self.last_log.session_id == session_id:
            return self.last_log
        return await self.worker.call(self.store.load, session_id)

    async def _project(self, project_id: str) -> Path:
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

    async def create(self, project_id: str, model_id: ModelId) -> SessionSummary:
        """验证项目后保存会话头，不调用模型。 Validate the project and persist a session header."""
        async with self.lock:
            await self._project(project_id)
            log = SessionLog(str(uuid4()), [])
            await self.worker.call(
                self.store.append,
                log,
                SessionCreated(project_id=project_id, model_id=model_id),
                None,
            )
            return summarize(log)

    async def view(self, session_id: str, before_seq: int | None = None) -> SessionView:
        """在一致锁边界取得水位与预览，调用方可先订阅再去重。

        Snapshot watermark and preview consistently; callers subscribe first and deduplicate.
        """
        async with self.lock:
            log = await self._load(session_id)
            active = (
                self.active if self.active and self.active.log.session_id == session_id else None
            )
            page, cursor = entries(log, before_seq)
            summary = summarize(
                log, active=active is not None, stopping=bool(active and active.cancel.is_set())
            )
            if active and active.fatal_error:
                summary = summary.model_copy(
                    update={"issue": active.fatal_error, "can_continue": False}
                )
            progress = active.model_progress if active else None
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
                stream_text=active.text if active else "",
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
            for name in candidates:
                if cursor is not None and name <= cursor:
                    continue
                try:
                    log = self.store.load(name)
                    header = log.facts[0].data if log.facts else None
                    if not isinstance(header, SessionCreated):
                        unavailable += 1
                    if isinstance(header, SessionCreated) and header.project_id == project_id:
                        if len(logs) >= limit:
                            next_cursor = logs[-1].session_id
                            break
                        logs.append(log)
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
                active = (
                    self.active
                    if self.active and self.active.log.session_id == log.session_id
                    else None
                )
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
                active_session_id=self.active.log.session_id if self.active else None,
            )

    async def start(
        self,
        session_id: str,
        operation_id: str,
        prompt: str,
        requested_limits: RunLimits | None,
    ) -> SessionSummary:
        """先持久接纳再快速确认，同操作标识不重复请求。

        Durably accept then ack, with idempotent starts.
        """
        if not prompt.strip() or len(prompt.encode("utf-8")) > 64000:
            raise AgentError("PROMPT_INVALID", "请输入非空问题（最多 64 KB UTF-8）。")
        async with self.lock:
            log = await self._load(session_id)
            for fact in log.facts:
                if isinstance(fact.data, RunAccepted) and fact.data.operation_id == operation_id:
                    if fact.data.prompt != prompt or fact.data.requested_limits != requested_limits:
                        raise AgentError("OPERATION_CONFLICT", "同一操作标识已用于不同输入。")
                    # 返回原运行，而非把重复提交绑定到后来一次运行。
                    # Return the original run rather than a newer run in the same session.
                    end = next(
                        (f.seq for f in log.facts[fact.seq :] if isinstance(f.data, RunAccepted)),
                        len(log.facts) + 1,
                    )
                    original = SessionLog(log.session_id, log.facts[: end - 1], log.issue)
                    is_active = self.active is not None and self.active.run_id == fact.run_id
                    return summarize(
                        original,
                        active=is_active,
                        stopping=bool(is_active and self.active and self.active.cancel.is_set()),
                    )
            if self.active is not None:
                raise AgentError("RUN_BUSY", "已有运行进行中，请先停止或等待结束。")
            summary = summarize(log)
            if not summary.can_continue:
                raise AgentError("SESSION_READ_ONLY", "会话含未配对工具或损坏记录，请新建会话。")
            root = await self._project(summary.project_id)
            config = await self.worker.call(load_config, self.store.storage.location)
            limits = requested_limits or config.run
            # 重启后确认旧 run 中断；不重放工具，只允许完整历史继续。
            # Mark old unfinished runs interrupted without replaying tools.
            if summary.run and summary.run.status == "interrupted":
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
                ),
                run_id,
            )
            active = ActiveRun(log, run_id, limits)
            self.active = active
            active.task = asyncio.create_task(self._drive(active, root, summary.model_id))
            self._signal(active)
            return summarize(log, active=True)

    async def cancel(self, run_id: str) -> SessionSummary:
        """停止请求不等文件锁，终态等待实际资源清理。

        Signal cancellation without waiting for file locks.
        """
        active = self.active
        if active is None or active.run_id != run_id:
            raise AgentError("RUN_NOT_ACTIVE", "该运行已结束或不属于当前后端。")
        active.stop.set()
        active.cancel.set()
        self._signal(active)
        return summarize(active.log, active=True, stopping=True)

    async def _drive(self, active: ActiveRun, root: Path, model_id: ModelId) -> None:
        """协调取消、总时限和终态保存，所有终态只提交一次。

        Coordinate cleanup and one terminal fact.
        """
        sink = ServiceSink(self, active)
        work: asyncio.Task[None] | None = None
        watcher: asyncio.Task[bool] | None = None
        finished = RunFinished(status="completed", code=None, message=None)
        try:
            context, complete = active.log.context()
            if not complete:
                raise AgentError("SESSION_READ_ONLY", "历史不完整，不能发送给模型。")
            if active.cancel.is_set():
                raise asyncio.CancelledError
            tools = ReadTools(root, active.limits, active.stop)
            model = self.model_factory()
            work = asyncio.create_task(
                run_loop(
                    model=model,
                    tools=tools,
                    sink=sink,
                    model_id=model_id,
                    session_id=active.log.session_id,
                    messages=context,
                    limits=active.limits,
                    stop=active.stop,
                )
            )
            watcher = asyncio.create_task(active.cancel.wait())
            done, _ = await asyncio.wait(
                {work, watcher},
                timeout=active.limits.max_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if watcher in done:
                raise asyncio.CancelledError
            if work not in done:
                raise AgentError("BUDGET_TIME", "已达到运行时间预算，可调整后重试。")
            await work
        except asyncio.CancelledError:
            finished = RunFinished(status="cancelled", code="CANCELLED", message="运行已停止。")
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
            for task in (work, watcher):
                if task is not None and not task.done():
                    task.cancel()
            if work is not None:
                await asyncio.gather(work, return_exceptions=True)
            if watcher is not None:
                await asyncio.gather(watcher, return_exceptions=True)
            try:
                await sink.commit(finished)
            except AgentError as exc:
                active.log.issue = exc.code
                active.fatal_error = exc.code
            self.last_log = active.log
            self.active = None
            self._signal(active)

    async def close(self) -> None:
        """停止并等待活动任务，调用方随后释放写锁。

        Stop and await work before releasing the writer lock.
        """
        try:
            if self.active:
                active = self.active
                active.stop.set()
                active.cancel.set()
                if active.task:
                    await active.task
        finally:
            if self.close_model is not None:
                await self.close_model()


class ServiceSink:
    """把运行时输出连接到服务持久化与通知。 Connect runtime outputs to persistence and signals."""

    def __init__(self, service: SessionService, active: ActiveRun) -> None:
        """绑定本次运行，不使用全局当前视图。 Bind this run independently of the selected view."""
        self.service = service
        self.active = active

    async def commit(self, data: FactData) -> None:
        """存储成功后发布事实变更，取消期间仍等待存储。 Publish only after persistence succeeds."""
        async with self.service.lock:
            if isinstance(data, (AssistantCommitted, RunFinished)):
                data = data.model_copy(update={"model_progress": self.active.model_progress})
            await self.service.worker.call(
                self.service.store.append, self.active.log, data, self.active.run_id
            )
            if isinstance(data, RequestStarted):
                self.active.message_id = data.message_id
                self.active.text = ""
                self.active.delta_index = 0
                self.active.model_progress = None
            elif isinstance(data, AssistantCommitted):
                self.active.message_id = None
                self.active.text = ""
                self.active.delta_index = 0
            self.service._signal(self.active)

    async def text(self, message_id: str, delta: str) -> None:
        """只缓存有界文本；不把实时字符 fsync。 Cache bounded text without per-token fsync."""
        if self.active.stop.is_set():
            raise asyncio.CancelledError
        if len((self.active.text + delta).encode("utf-8")) > self.active.limits.max_response_bytes:
            raise AgentError("MODEL_OUTPUT_LIMIT", "模型显示文本超过容量。")
        self.active.message_id = message_id
        self.active.text += delta
        self.active.delta_index += 1
        self.service._signal(self.active, "text.delta", delta)

    async def progress(self, message_id: str, progress: ModelProgress) -> None:
        """阶段只更新内存，结束时随事实持久化；不阻塞首字。

        Keep phases in memory until a durable end fact, without delaying the first token.
        """
        self.active.message_id = message_id
        self.active.model_progress = progress
        self.service._signal(self.active, "model.progress")
