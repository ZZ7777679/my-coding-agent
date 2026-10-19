"""管理持续输入、控制归属、真实退出和应用清理。

Manage terminal control and lifecycle.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from uuid import uuid4

from my_agent.errors import AgentError
from my_agent.execution.commands import command_line, working_directory
from my_agent.execution.environments import EnvironmentStore
from my_agent.execution.types import ExecutionSettings
from my_agent.runtime.tools import ToolContext
from my_agent.sessions.projection import summarize
from my_agent.sessions.store import SessionStore
from my_agent.sessions.types import SessionCreated
from my_agent.spaces.store import SpaceStore
from my_agent.storage import Storage, utc_now
from my_agent.terminals.native import ConPtyProcess, availability
from my_agent.terminals.store import TerminalRecord, TerminalStore, output_view
from my_agent.terminals.types import (
    ListTerminalsParams,
    OpenTerminalParams,
    ReadTerminalParams,
    ResizeTerminalParams,
    TerminalChunk,
    TerminalControlParams,
    TerminalPage,
    TerminalParams,
    TerminalSummary,
    TerminalView,
    WriteTerminalParams,
)
from my_agent.tools.policy import checkpoint
from my_agent.worker import BusinessWorker


@dataclass
class OwnedTerminal:
    """仅内存持有进程，输入和接管串行，监视持续读取。

    Live ownership with serialized control.
    """

    record: TerminalRecord
    process: ConPtyProcess
    settings: ExecutionSettings
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None
    failure: AgentError | None = None
    stopping: bool = False
    output_bytes: int = 0


class TerminalService:
    """按项目保留终端，切换会话不清理；业务快照沿用单写者。

    Retain project terminals across navigation and persist through the existing writer.
    """

    def __init__(
        self, environments: EnvironmentStore, storage: Storage, worker: BusinessWorker
    ) -> None:
        """只注入依赖，缺失可选 PTY 不影响构造。

        Inject dependencies without requiring optional PTY.
        """
        self.environments, self.worker = environments, worker
        self.store = TerminalStore(storage)
        self.sessions = SessionStore(storage)
        self.spaces = SpaceStore(storage)
        self.owned: dict[str, OwnedTerminal] = {}
        self.recovered = False
        self.recovery_lock = asyncio.Lock()
        self.closing = False

    async def recover(self) -> None:
        """历史只标记一次，不自动重启。

        Mark unfinished history once without replay.
        """
        async with self.recovery_lock:
            if not self.recovered:
                await self.worker.call(self.store.recover)
                self.recovered = True

    def _session(self, project_id: str, session_id: str | None) -> str | None:
        """绑定时核实真实会话所属项目。

        Verify project ownership when assigning a session.
        """
        if session_id is None:
            return None
        log = self.sessions.load(session_id)
        creation = next((f.data for f in log.facts if isinstance(f.data, SessionCreated)), None)
        if creation is None or creation.project_id != project_id:
            raise AgentError("TERMINAL_SCOPE_DENIED", "终端只能关联本项目的会话。")
        task_id = summarize(log).task_id
        if task_id is None:
            return None
        try:
            space = self.spaces.get(task_id)
        except AgentError as exc:
            # 可选空间历史不可读不阻断独立会话终端；保持会话来源而非伪造成员。
            # Optional unreadable space history does not block a standalone session terminal.
            logging.getLogger(__name__).warning("TERMINAL_MEMBER_UNKNOWN code=%s", exc.code)
            return None
        if space is None:
            return None
        binding = next((b for b in space.view.bindings if b.session_id == session_id), None)
        return binding.member_id if binding else None

    async def _save(self, owned: OwnedTerminal) -> None:
        """冻结快照后交给存储线程。

        Freeze snapshots before passing them to the writer.
        """
        await self.worker.call(self.store.save, owned.record.model_copy(deep=True))

    def _append(self, owned: OwnedTerminal, text: str) -> None:
        """字符安全分块并按项目输出预算保留尾部。

        Chunk and retain bounded Unicode-safe output.
        """
        # 单个原生读取可能很大；单帧预算按编码后的 JSON 处理。
        # Native reads may be large; small Unicode chunks keep each transport frame bounded.
        for offset in range(0, len(text), 8000):
            part = text[offset : offset + 8000]
            owned.record.output.append(TerminalChunk(seq=owned.record.next_seq, text=part))
            owned.record.next_seq += 1
            owned.output_bytes += len(part.encode("utf-8"))
        while owned.output_bytes > owned.settings.max_output_bytes and owned.record.output:
            removed = owned.record.output.pop(0)
            count = len(removed.text.encode("utf-8"))
            owned.output_bytes -= count
            owned.record.summary.dropped_bytes += count

    async def _monitor(self, owned: OwnedTerminal) -> None:
        """持续消费输出，实际退出后清理子树并保存终态。

        Drain output and persist verified termination.
        """
        persisted = time.monotonic()
        try:
            while True:
                text = await asyncio.to_thread(owned.process.read)
                self._append(owned, text)
                code = await asyncio.to_thread(owned.process.poll)
                if code is not None:
                    owned.record.summary.exit_code = code
                    break
                if time.monotonic() - persisted >= 0.5:
                    await self._save(owned)
                    persisted = time.monotonic()
                # PSReadLine 一次重绘含许多小 VT 片段；逐片段等 40ms 会产生输出背压。
                # PSReadLine emits many small VT chunks; per-chunk sleep causes backpressure.
                await asyncio.sleep(0 if text else 0.04)
        except asyncio.CancelledError:
            owned.failure = AgentError(
                "TERMINAL_MONITOR_INTERRUPTED", "终端管理中断，正在清理进程。"
            )
            raise
        except AgentError as exc:
            owned.failure = exc
        except Exception as exc:
            # 原生 C 扩展可能抛出专用异常；边界仅保存异常类型，不泄露输入。
            # Native extension errors are normalized here without exposing typed input.
            logging.getLogger(__name__).error("TERMINAL_IO_FAILED type=%s", type(exc).__name__)
            owned.failure = AgentError("TERMINAL_IO_FAILED", "终端通道发生故障，已停止进程。")
        finally:
            try:
                await asyncio.to_thread(
                    owned.process.finish, owned.settings.cleanup_timeout_seconds
                )
                # ConPTY 根进程退出后继续异步生成末尾 VT 输出，单次 read 会丢尾行。
                # ConPTY can emit trailing VT output after root exit; one read loses the last line.
                quiet_since = time.monotonic()
                drain_deadline = quiet_since + owned.settings.cleanup_timeout_seconds
                while time.monotonic() < drain_deadline:
                    tail = await asyncio.to_thread(owned.process.read)
                    self._append(owned, tail)
                    if tail:
                        quiet_since = time.monotonic()
                    elif time.monotonic() - quiet_since >= 0.25:
                        break
                    await asyncio.sleep(0 if tail else 0.02)
            except AgentError as exc:
                owned.failure = exc
            except Exception as exc:
                logging.getLogger(__name__).error("TERMINAL_FINAL_IO type=%s", type(exc).__name__)
                owned.failure = AgentError("TERMINAL_IO_FAILED", "终端最终输出未完整读取。")
            finally:
                owned.process.close()
            owned.record.summary.status = (
                "failed" if owned.failure else "stopped" if owned.stopping else "exited"
            )
            owned.record.summary.finished_at = utc_now()
            owned.record.summary.code = owned.failure.code if owned.failure else None
            owned.record.summary.message = owned.failure.message if owned.failure else None
            try:
                await self._save(owned)
                self.owned.pop(owned.record.summary.terminal_id, None)
            except AgentError as exc:
                owned.failure = AgentError(
                    "TERMINAL_OUTCOME_UNSAVED", "终端已结束，但结果保存失败。"
                )
                owned.record.summary.status = "failed"
                owned.record.summary.code = exc.code
                owned.record.summary.message = owned.failure.message
            finally:
                owned.done.set()

    async def open(
        self,
        params: OpenTerminalParams,
        context: ToolContext | None = None,
        tool_call_id: str | None = None,
    ) -> TerminalView:
        """先保存启动意图，再启动真实 ConPTY；人工终端默认用户控制。

        Persist intent before ConPTY spawn; user-created terminals start under user control.
        """
        if self.closing:
            raise AgentError("EXECUTION_CLOSING", "应用正在退出，不能启动终端。")
        if context:
            checkpoint(context.stop)
            if context.mode == "plan":
                raise AgentError("PLAN_READ_ONLY", "Plan 模式不能启动交互程序。")
            if params.project_id != context.project_id:
                raise AgentError("TERMINAL_SCOPE_DENIED", "终端不属于当前项目。")
            params = params.model_copy(update={"session_id": context.session_id})
        available, message = availability()
        if not available:
            raise AgentError("TERMINAL_UNAVAILABLE", message or "交互终端不可用。")
        await self.recover()
        view, settings, _ = await self.worker.call(self.environments.selected, params.project_id)
        root = await self.worker.call(self.environments.project_root, params.project_id)
        member_id = await self.worker.call(self._session, params.project_id, params.session_id)
        if params.member_id is not None and params.member_id != member_id:
            raise AgentError("TERMINAL_SCOPE_DENIED", "成员与终端关联会话不匹配。")
        cwd = await asyncio.to_thread(working_directory, root, params.cwd)
        argv, env = await asyncio.to_thread(command_line, params.command, view, cwd)
        env.pop("NO_COLOR", None)
        env["TERM"] = "xterm-256color"
        record = TerminalRecord(
            summary=TerminalSummary(
                terminal_id=str(uuid4()),
                project_id=params.project_id,
                session_id=params.session_id,
                member_id=member_id,
                run_id=context.run_id if context else None,
                tool_call_id=tool_call_id,
                controller="member" if context else "user",
                command=params.command,
                status="starting",
                pid=None,
                exit_code=None,
                cwd=str(cwd),
                environment_name=view.record.name,
                cols=params.cols,
                rows=params.rows,
                created_at=utc_now(),
                finished_at=None,
            ),
            output=[],
        )
        await self.worker.call(self.store.save, record)
        pending = asyncio.create_task(
            asyncio.to_thread(ConPtyProcess, argv, cwd, env, params.cols, params.rows)
        )
        try:
            process = await asyncio.shield(pending)
        except BaseException:
            # 取消等待不能遗失线程已启动的进程；先收回句柄再传播取消。
            # Cancellation cannot discard a process launched in the worker thread.
            if not pending.cancelled():
                try:
                    launched = await pending
                except Exception:
                    launched = None
                if launched is not None:
                    try:
                        await asyncio.to_thread(launched.finish, settings.cleanup_timeout_seconds)
                    finally:
                        launched.close()
            record.summary.status = "interrupted"
            record.summary.finished_at = utc_now()
            record.summary.code = "TERMINAL_START_INTERRUPTED"
            record.summary.message = "终端未完成启动，未自动重新执行。"
            await self.worker.call(self.store.save, record)
            raise
        record.summary.pid = process.pid
        record.summary.status = "running"
        owned = OwnedTerminal(record, process, settings)
        self.owned[record.summary.terminal_id] = owned
        owned.task = asyncio.create_task(self._monitor(owned))
        return output_view(record)

    async def read(self, params: ReadTerminalParams) -> TerminalView:
        """读取终端不改变控制权或运行生命周期。

        Read without changing control or lifecycle.
        """
        await self.recover()
        owned = self.owned.get(params.terminal_id)
        record = (
            owned.record if owned else await self.worker.call(self.store.load, params.terminal_id)
        )
        return output_view(record, params.after_seq)

    async def list(self, params: ListTerminalsParams) -> TerminalPage:
        """真实内存状态优先于历史，损坏条目明确计数。

        Prefer live state and count unreadable history.
        """
        await self.recover()
        await self.worker.call(self.environments.project_root, params.project_id)
        records, unavailable = await self.worker.call(self.store.records)
        summaries = {r.summary.terminal_id: r.summary for r in records}
        summaries.update({key: owned.record.summary for key, owned in self.owned.items()})
        items = [
            s.model_copy(deep=True) for s in summaries.values() if s.project_id == params.project_id
        ]
        items.sort(key=lambda s: s.created_at, reverse=True)
        available, message = availability()
        return TerminalPage(
            terminals=items,
            active_count=sum(s.status in {"running", "starting", "stopping"} for s in items),
            unavailable_count=unavailable,
            available=available,
            message=message,
        )

    def _live(self, params: TerminalParams) -> OwnedTerminal:
        """只操作内存中的实际所有权。 Operate only on live in-memory ownership."""
        owned = self.owned.get(params.terminal_id)
        if owned is None or owned.done.is_set() or owned.stopping:
            raise AgentError("TERMINAL_NOT_RUNNING", "终端已结束；历史记录不会自动重启。")
        return owned

    @staticmethod
    def _input_owner(owned: OwnedTerminal, context: ToolContext | None) -> None:
        """接管与输入在同一个锁内判断，避免人工与成员交错。

        Check control under the input lock.
        """
        summary = owned.record.summary
        if context is None:
            if summary.controller != "user":
                raise AgentError("TERMINAL_MEMBER_CONTROL", "终端由成员控制，请先接管。")
        else:
            checkpoint(context.stop)
            if context.mode == "plan":
                raise AgentError("PLAN_READ_ONLY", "Plan 模式不能操作终端输入。")
            if summary.project_id != context.project_id or summary.session_id != context.session_id:
                raise AgentError("TERMINAL_SCOPE_DENIED", "终端未关联当前成员会话。")
            if summary.controller != "member":
                raise AgentError("TERMINAL_USER_CONTROL", "用户已接管终端，请等待显式交还。")

    async def write(
        self, params: WriteTerminalParams, context: ToolContext | None = None
    ) -> TerminalView:
        """输入只交给当前控制者，原生失败停止终端。

        Input belongs only to the current controller.
        """
        owned = self._live(params)
        async with owned.lock:
            self._input_owner(owned, context)
            try:
                pending = asyncio.create_task(asyncio.to_thread(owned.process.write, params.text))
                await asyncio.shield(pending)
            except asyncio.CancelledError:
                owned.process.terminate()
                await pending
                raise
            except AgentError:
                raise
            except Exception as exc:
                owned.failure = AgentError("TERMINAL_INPUT_FAILED", "终端输入通道故障，已停止。")
                owned.process.terminate()
                raise owned.failure from exc
        return output_view(owned.record, owned.record.next_seq - 1)

    async def resize(self, params: ResizeTerminalParams) -> TerminalView:
        """尺寸调整不改变输入归属。 Resize without changing input ownership."""
        owned = self._live(params)
        try:
            await asyncio.to_thread(owned.process.resize, params.cols, params.rows)
        except Exception as exc:
            raise AgentError("TERMINAL_RESIZE_FAILED", "终端尺寸调整失败。") from exc
        owned.record.summary.cols, owned.record.summary.rows = params.cols, params.rows
        return output_view(owned.record, owned.record.next_seq - 1)

    async def control(self, params: TerminalControlParams) -> TerminalView:
        """仅用户入口可接管或交还；保存成功后公开新归属。

        Explicit user takeover/return after saving.
        """
        owned = self._live(params)
        async with owned.lock:
            previous = owned.record.summary.model_copy(deep=True)
            if params.controller == "member":
                member_id = await self.worker.call(
                    self._session, previous.project_id, params.session_id
                )
                if params.member_id is not None and params.member_id != member_id:
                    raise AgentError("TERMINAL_SCOPE_DENIED", "成员与终端关联会话不匹配。")
                owned.record.summary.session_id = params.session_id
                owned.record.summary.member_id = member_id
            owned.record.summary.controller = params.controller
            try:
                await self._save(owned)
            except AgentError:
                owned.record.summary = previous
                raise
        return output_view(owned.record, owned.record.next_seq - 1)

    async def interrupt(
        self, params: TerminalParams, context: ToolContext | None = None
    ) -> TerminalView:
        """Ctrl+C 经真实输入通道送给前台程序，终端可继续。

        Send Ctrl+C to the foreground program.
        """
        return await self.write(
            WriteTerminalParams(terminal_id=params.terminal_id, text="\x03"), context
        )

    async def stop(
        self, params: TerminalParams, context: ToolContext | None = None
    ) -> TerminalView:
        """用户关闭可收回整个进程树，成员只能关闭其控制的终端。

        Close the owned process tree.
        """
        owned = self.owned.get(params.terminal_id)
        if owned is not None and not owned.done.is_set():
            if context is not None:
                self._input_owner(owned, context)
            owned.stopping = True
            owned.record.summary.status = "stopping"
            owned.process.terminate()
            await owned.done.wait()
            if owned.failure:
                raise owned.failure
        return await self.read(ReadTerminalParams(terminal_id=params.terminal_id))

    async def close(self) -> None:
        """退出应用清理全部自有终端，不因会话切换调用。

        Clean all owned terminals at app exit.
        """
        self.closing = True
        results = await asyncio.gather(
            *(self.stop(TerminalParams(terminal_id=key)) for key in list(self.owned)),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
