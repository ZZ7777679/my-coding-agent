"""异步管理项目命令、预览服务和退出清理。

Manage project commands, previews and shutdown asynchronously."""

import asyncio
import codecs
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx

from my_agent.errors import AgentError
from my_agent.execution.commands import command_line, working_directory
from my_agent.execution.environments import EnvironmentStore, execution_environment
from my_agent.execution.listeners import listener_pids, local_endpoint, owns_listener
from my_agent.execution.store import ProgramRecord, ProgramStore, output_view
from my_agent.execution.types import (
    EnvironmentCatalog,
    EnvironmentParams,
    EnvironmentProbe,
    ExecutionSettings,
    GetProgramParams,
    ListProgramsParams,
    OutputChunk,
    ProgramPage,
    ProgramSummary,
    ProgramView,
    RunCommandArgs,
    StartServiceArgs,
)
from my_agent.execution.windows import WindowsProcess
from my_agent.runtime.tools import ToolContext
from my_agent.storage import utc_now
from my_agent.tools.policy import checkpoint
from my_agent.worker import BusinessWorker


async def spawn(
    command: list[str], cwd: Path, env: dict[str, str], settings: ExecutionSettings
) -> WindowsProcess:
    """取消启动也收回已创建句柄，避免线程已启动却无人持有。

    Reap a process created by the worker even if the awaiting coroutine is cancelled.
    """
    pending = asyncio.create_task(
        asyncio.to_thread(WindowsProcess, command, cwd, env, settings.max_output_bytes)
    )
    try:
        return await asyncio.shield(pending)
    except asyncio.CancelledError:
        process = await pending
        try:
            await asyncio.to_thread(process.finish, settings.cleanup_timeout_seconds)
        finally:
            process.close()
        raise


@dataclass
class OwnedProgram:
    """内存中的实际进程所有权；磁盘记录不能重建它。

    Live ownership which cannot be reconstructed from saved records.
    """

    record: ProgramRecord
    process: WindowsProcess
    settings: ExecutionSettings
    deadline: float | None
    task: asyncio.Task[None] | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    failure: AgentError | None = None
    stop_requested: bool = False
    native_dropped: int = 0
    output_bytes: int = 0
    decoders: dict[str, codecs.IncrementalDecoder] = field(default_factory=dict)


class ProgramService:
    """事件循环持有进程，文件交给单写者线程；服务不随会话切换停止。

    Own processes on the event loop and persist on the writer; retain services across sessions.
    """

    def __init__(
        self, environments: EnvironmentStore, store: ProgramStore, worker: BusinessWorker
    ) -> None:
        """注入已有存储，不在构造时安装环境或运行命令。

        Inject storage without running commands."""
        self.environments, self.store, self.worker = environments, store, worker
        self.owned: dict[str, OwnedProgram] = {}
        self.recovered = False
        self.recovery_lock = asyncio.Lock()
        self.probes: set[asyncio.Task[EnvironmentCatalog]] = set()
        self.closing = False

    async def recover(self) -> None:
        """持锁后只做一次历史中断标记。

        Mark interrupted history once after acquiring storage ownership."""
        async with self.recovery_lock:
            if not self.recovered:
                await self.worker.call(self.store.recover)
                self.recovered = True

    def _consume(self, owned: OwnedProgram, *, final: bool = False) -> None:
        """消费原生有界队列并保留有界文本尾部；UTF-8 跨块保持解码状态。

        Drain bounded bytes and retain a bounded text tail with incremental UTF-8 decoding.
        """
        chunks, dropped = owned.process.drain()
        lost = dropped - owned.native_dropped
        owned.record.summary.dropped_bytes += lost
        owned.native_dropped = dropped
        if lost:
            # 字节截断可能切开字符；此后明确用替换字符展示，不伪装完整输出。
            # Reset decoders after byte loss; replacement characters make damage visible.
            owned.decoders.clear()
        for channel, data in [*chunks, *(("stdout", b""), ("stderr", b""))] if final else chunks:
            decoder = owned.decoders.setdefault(
                channel, codecs.getincrementaldecoder("utf-8")("replace")
            )
            text = decoder.decode(data, final=final and not data)
            if not text:
                continue
            chunk = OutputChunk(
                seq=owned.record.next_seq,
                stream="stdout" if channel == "stdout" else "stderr",
                text=text,
            )
            owned.record.next_seq += 1
            owned.record.output.append(chunk)
            owned.output_bytes += len(text.encode("utf-8"))
        while owned.output_bytes > owned.settings.max_output_bytes and owned.record.output:
            removed = owned.record.output.pop(0)
            raw = removed.text.encode("utf-8")
            excess = owned.output_bytes - owned.settings.max_output_bytes
            tail = raw[min(excess, len(raw)) :].decode("utf-8", "ignore")
            count = len(raw) - len(tail.encode("utf-8"))
            if tail:
                owned.record.output.insert(0, removed.model_copy(update={"text": tail}))
            owned.output_bytes -= count
            owned.record.summary.dropped_bytes += count

    async def _save(self, owned: OwnedProgram) -> None:
        """在线程读取前冻结快照，避免序列化与输出变化竞争。

        Freeze snapshots before worker serialization."""
        await self.worker.call(self.store.save, owned.record.model_copy(deep=True))

    async def _monitor(self, owned: OwnedProgram) -> None:
        """监视输出与真实退出，任何故障都结束本进程并保存实际结果。

        Monitor real output and exit; faults terminate this owned process and preserve outcomes.
        """
        persisted = 0.0
        try:
            while True:
                self._consume(owned)
                if owned.process.output_failed:
                    raise AgentError("PROGRAM_OUTPUT_FAILED", "程序输出通道中断。")
                code = owned.process.poll()
                if code is not None:
                    owned.record.summary.exit_code = code
                    break
                if owned.deadline and time.monotonic() >= owned.deadline:
                    raise AgentError(
                        "PROGRAM_TIMEOUT", "命令达到执行时限，已停止；可调整时限后明确重试。"
                    )
                if time.monotonic() - persisted >= 0.5:
                    await self._save(owned)
                    persisted = time.monotonic()
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            owned.failure = AgentError(
                "PROGRAM_MONITOR_INTERRUPTED", "程序管理已中断，正在清理自有进程。"
            )
            raise
        except AgentError as exc:
            owned.failure = exc
        except Exception as exc:
            logging.getLogger(__name__).error("PROGRAM_INTERNAL type=%s", type(exc).__name__)
            owned.failure = AgentError("PROGRAM_INTERNAL", "程序管理发生内部错误，已停止本次进程。")
        finally:
            try:
                await asyncio.to_thread(
                    owned.process.finish, owned.settings.cleanup_timeout_seconds
                )
                self._consume(owned, final=True)
            except AgentError as exc:
                owned.failure = exc
            finally:
                owned.process.close()
            state: Literal["failed", "stopped", "exited"] = (
                "failed" if owned.failure else "stopped" if owned.stop_requested else "exited"
            )
            owned.record.summary = owned.record.summary.model_copy(
                update={
                    "status": state,
                    "retained": False,
                    "finished_at": utc_now(),
                    "code": owned.failure.code if owned.failure else None,
                    "message": owned.failure.message if owned.failure else None,
                }
            )
            try:
                await self._save(owned)
                self.owned.pop(owned.record.summary.program_id, None)
            except AgentError as exc:
                # 保留内存结果供本次应用查看；磁盘历史仍为未知，不能谎称保存成功。
                # Keep the live outcome; disk history remains unknown when persistence fails.
                owned.failure = AgentError(
                    "PROGRAM_OUTCOME_UNSAVED", "程序已结束，但结果保存失败；未自动重放。"
                )
                owned.record.summary.code = exc.code
                owned.record.summary.message = owned.failure.message
                owned.record.summary.status = "failed"
            finally:
                owned.done.set()

    async def _launch(
        self,
        context: ToolContext,
        args: RunCommandArgs | StartServiceArgs,
        tool_call_id: str | None = None,
    ) -> OwnedProgram:
        """先保存启动意图，再建立所有权；创建失败不进入假运行状态。

        Persist intent before launch ownership."""
        if self.closing:
            raise AgentError("EXECUTION_CLOSING", "应用正在退出，不能启动程序。")
        if context.mode == "plan":
            raise AgentError("PLAN_READ_ONLY", "Plan 模式不能执行项目程序。")
        checkpoint(context.stop)
        await self.recover()
        view, settings, revision = await self.worker.call(
            self.environments.selected, context.project_id
        )
        root = await self.worker.call(self.environments.project_root, context.project_id)
        cwd = await asyncio.to_thread(working_directory, root, args.cwd)
        argv, env = await asyncio.to_thread(command_line, args.command, view, cwd)
        is_service = isinstance(args, StartServiceArgs)
        if isinstance(args, StartServiceArgs):
            local_endpoint(args.ready_url)
            if await asyncio.to_thread(listener_pids, args.ready_url):
                raise AgentError(
                    "SERVICE_PORT_IN_USE", "预览端口已被占用，未启动新程序；已有程序保持运行。"
                )
        record = ProgramRecord(
            summary=ProgramSummary(
                program_id=str(uuid4()),
                project_id=context.project_id,
                session_id=context.session_id,
                run_id=context.run_id,
                tool_call_id=tool_call_id,
                environment_id=view.record.environment_id,
                environment_name=view.record.name,
                environment_revision=revision,
                kind="service" if is_service else "command",
                command=args.command,
                resolved_command=argv,
                cwd=str(cwd),
                status="starting",
                pid=None,
                exit_code=None,
                retained=False,
                created_at=utc_now(),
                finished_at=None,
                url=args.ready_url if isinstance(args, StartServiceArgs) else None,
                http_status=None,
                code=None,
                message=None,
            ),
            output=[],
            next_seq=1,
        )
        await self.worker.call(self.store.save, record)
        try:
            checkpoint(context.stop)
            process = await spawn(argv, cwd, env, settings)
        except BaseException:
            record.summary.status = "interrupted"
            record.summary.code = "PROGRAM_START_INTERRUPTED"
            record.summary.message = "启动未完成，未自动重试。"
            record.summary.finished_at = utc_now()
            await self.worker.call(self.store.save, record)
            raise
        deadline = (
            time.monotonic() + (args.timeout_seconds or settings.command_timeout_seconds)
            if isinstance(args, RunCommandArgs)
            else None
        )
        record.summary.pid, record.summary.status = process.pid, "running"
        owned = OwnedProgram(record, process, settings, deadline)
        self.owned[record.summary.program_id] = owned
        owned.task = asyncio.create_task(self._monitor(owned))
        return owned

    async def run(
        self, context: ToolContext, args: RunCommandArgs, tool_call_id: str | None = None
    ) -> ProgramView:
        """普通命令等待退出；非零返回仍是实际结果，不自动授权修复。

        Wait for exit; nonzero is a result."""
        owned = await self._launch(context, args, tool_call_id)
        try:
            await owned.done.wait()
        except asyncio.CancelledError:
            await self._stop(owned)
            raise
        if owned.failure:
            raise owned.failure
        return output_view(owned.record, 0)

    async def start_service(
        self, context: ToolContext, args: StartServiceArgs, tool_call_id: str | None = None
    ) -> ProgramView:
        """只对自有监听器做 HTTP 就绪检查，交付前失败则清理。

        Probe HTTP readiness only for an owned listener; clean up before an unsuccessful handoff.
        """
        owned = await self._launch(context, args, tool_call_id)
        ready = False
        timeout = args.ready_timeout_seconds or owned.settings.service_ready_timeout_seconds
        try:
            async with (
                asyncio.timeout(timeout),
                httpx.AsyncClient(trust_env=False, follow_redirects=False) as client,
            ):
                while not owned.done.is_set():
                    if await asyncio.to_thread(owns_listener, owned.process, args.ready_url):
                        try:
                            async with client.stream(
                                "GET", args.ready_url, timeout=min(timeout, 2)
                            ) as response:
                                status = response.status_code
                            if owned.done.is_set() or owned.process.poll() is not None:
                                break
                            owned.record.summary.status = "ready"
                            owned.record.summary.retained = True
                            owned.record.summary.http_status = status
                            owned.record.summary.message = (
                                "本进程 HTTP 已响应；这不代表业务检查通过。"
                            )
                            await self._save(owned)
                            ready = True
                            return output_view(owned.record, 0)
                        except httpx.HTTPError:
                            pass  # 启动中尚未能响应；就绪时限统一控制 / bounded readiness polling.
                    await asyncio.sleep(0.15)
            if owned.failure:
                raise owned.failure
            raise AgentError("SERVICE_EXITED", "服务在就绪前退出，请查看运行卡片的退出码与输出。")
        except TimeoutError as exc:
            owned.failure = AgentError(
                "SERVICE_NOT_READY",
                "服务未在时限内确认自有 HTTP 响应，已停止。端口冲突请查看日志。",
            )
            raise owned.failure from exc
        except AgentError as exc:
            if not owned.done.is_set():
                owned.failure = exc
            raise
        finally:
            if not ready:
                await self._stop(owned)

    async def _stop(self, owned: OwnedProgram) -> None:
        """停止实际持有的 Job 并等待清理；完成记录不再触碰 PID。

        Stop live ownership and await cleanup."""
        if not owned.done.is_set():
            owned.stop_requested = True
            owned.record.summary.status = "stopping"
            owned.process.terminate()
            await owned.done.wait()

    async def get(self, params: GetProgramParams) -> ProgramView:
        """返回实时结果或历史，读取不触发执行。

        Read live or saved results without execution."""
        await self.recover()
        owned = self.owned.get(params.program_id)
        record = (
            owned.record if owned else await self.worker.call(self.store.load, params.program_id)
        )
        return output_view(record, params.after_seq)

    async def list(self, params: ListProgramsParams) -> ProgramPage:
        """卡片优先显示实际持有状态，保存失败不留下虚假的运行中。

        Prefer owned live states so failed persistence does not falsely imply a running process.
        """
        await self.recover()
        page = await self.worker.call(self.store.list, params)
        return page.model_copy(
            update={
                "programs": [
                    self.owned[p.program_id].record.summary if p.program_id in self.owned else p
                    for p in page.programs
                ],
                "active_count": sum(
                    not p.done.is_set() and p.record.summary.project_id == params.project_id
                    for p in self.owned.values()
                ),
            }
        )

    async def stop(self, program_id: str) -> ProgramView:
        """用户显式停止自有程序；重启后的历史只能查看。

        Stop owned programs, never historical PIDs."""
        owned = self.owned.get(program_id)
        if owned:
            await self._stop(owned)
            if owned.failure:
                raise owned.failure
        return await self.get(GetProgramParams(program_id=program_id))

    async def finish_run(self, run_id: str) -> None:
        """结束临时命令，已交付服务保留供用户使用。

        Clean temporary work while retaining handed-off services."""
        for owned in list(self.owned.values()):
            if owned.record.summary.run_id == run_id and not owned.record.summary.retained:
                await self._stop(owned)
                if owned.failure and owned.failure.code == "PROCESS_CLEANUP_FAILED":
                    raise owned.failure

    async def close(self) -> None:
        """真正退出时停止全部自有程序，重启不自动恢复。

        Stop all owned processes on actual app exit."""
        self.closing = True
        for task in list(self.probes):
            task.cancel()
        await asyncio.gather(*self.probes, return_exceptions=True)
        programs = list(self.owned.values())
        results = await asyncio.gather(*(self._stop(p) for p in programs), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise AgentError(
                    "PROCESS_CLEANUP_FAILED", "退出时部分程序尚未确认清理。"
                ) from result
        if any(p.failure and p.failure.code == "PROCESS_CLEANUP_FAILED" for p in programs):
            raise AgentError("PROCESS_CLEANUP_FAILED", "退出时部分程序尚未确认清理。")

    async def probe(self, params: EnvironmentParams) -> EnvironmentCatalog:
        """显式环境探测单独运行并可随退出取消。

        Run explicit environment probes with shutdown cancellation."""
        if self.closing:
            raise AgentError("EXECUTION_CLOSING", "应用正在退出。")
        task = asyncio.create_task(self._probe(params))
        self.probes.add(task)
        try:
            return await task
        finally:
            self.probes.discard(task)

    async def _probe(self, params: EnvironmentParams) -> EnvironmentCatalog:
        """只检查登记的解释器 / 入口，既不安装环境也不导入项目代码。

        Probe references without installation."""
        catalog = await self.worker.call(self.environments.catalog, params.project_id)
        view = next(
            (v for v in catalog.environments if v.record.environment_id == params.environment_id),
            None,
        )
        if view is None:
            raise AgentError("ENVIRONMENT_NOT_FOUND", "环境登记不存在。")
        probe = EnvironmentProbe(
            checked_at=utc_now(),
            project_id=params.project_id,
            code="ENVIRONMENT_READY",
            message="已有环境检查完成。",
            interpreter=None,
            version=None,
            launcher_version=None,
        )
        try:
            if not view.available:
                raise AgentError(view.issue or "ENVIRONMENT_UNAVAILABLE", "环境路径已失效。")
            commands: list[tuple[str, list[str]]] = []
            if view.launcher:
                commands.append(("launcher", [view.launcher, "--version"]))
            if view.interpreter:
                commands.append(
                    (
                        "python",
                        [
                            view.interpreter,
                            "-I",
                            "-B",
                            "-u",
                            "-c",
                            "import json,sys; print(json.dumps({'executable':sys.executable,"
                            "'version':sys.version.split()[0]}))",
                        ],
                    )
                )
            for kind, argv in commands:
                process = await spawn(
                    argv,
                    self.environments.storage.root,
                    execution_environment(view),
                    catalog.settings,
                )
                try:
                    async with asyncio.timeout(catalog.settings.probe_timeout_seconds):
                        while process.poll() is None:
                            await asyncio.sleep(0.05)
                    code = process.poll()
                    await asyncio.to_thread(
                        process.finish, catalog.settings.cleanup_timeout_seconds
                    )
                    chunks, dropped = process.drain()
                    if code or process.output_failed or dropped:
                        raise AgentError("ENVIRONMENT_PROBE_FAILED", "环境检查命令未正常完成。")
                    output = (
                        b"".join(data for channel, data in chunks if channel == "stdout")
                        .decode("utf-8")
                        .strip()
                    )
                    if kind == "python":
                        data = json.loads(output)
                        if (
                            not isinstance(data, dict)
                            or not isinstance(data.get("executable"), str)
                            or not isinstance(data.get("version"), str)
                        ):
                            raise ValueError
                        probe.interpreter, probe.version = data["executable"], data["version"]
                    else:
                        probe.launcher_version = output[:1000]
                finally:
                    try:
                        if process.process:
                            await asyncio.to_thread(
                                process.finish, catalog.settings.cleanup_timeout_seconds
                            )
                    finally:
                        process.close()
            if not commands:
                probe.message = "本机工具环境已登记；具体工具将在执行时解析，未运行版本检查。"
                probe.code = "ENVIRONMENT_REGISTERED"
        except AgentError as exc:
            probe.code, probe.message = exc.code, exc.message
        except (TimeoutError, ValueError, UnicodeError):
            probe.code, probe.message = "ENVIRONMENT_PROBE_FAILED", "环境探测超时或返回格式无效。"
        return await self.worker.call(
            self.environments.save_probe, params.environment_id, view.record.definition, probe
        )
