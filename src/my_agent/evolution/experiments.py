"""代码候选在独立副本和数据根中验证。

Validate code candidates in separate copies and data roots.
"""

import asyncio
import fnmatch
import os
import shutil
import threading
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from my_agent.config import load_config, resolve_data_dir
from my_agent.errors import AgentError
from my_agent.evolution.types import (
    EvolutionCandidate,
    EvolutionComparison,
    EvolutionExperimentParams,
    EvolutionJob,
)
from my_agent.execution.environments import EnvironmentStore
from my_agent.execution.sandbox import SandboxLease
from my_agent.execution.service import ProgramService
from my_agent.execution.store import ProgramStore
from my_agent.execution.types import EnvironmentView, ExecutionSettings, RunCommandArgs
from my_agent.runtime.tools import ToolContext
from my_agent.storage import Storage, utc_now
from my_agent.worker import BusinessWorker

if TYPE_CHECKING:
    from my_agent.evolution.service import EvolutionService


class ExperimentEnvironment(EnvironmentStore):
    """环境继承启动快照，项目根指向独立副本。

    Reuse the selected environment snapshot while executing inside a separate project copy.
    """

    def __init__(
        self,
        storage: Storage,
        root: Path,
        snapshot: tuple[EnvironmentView, ExecutionSettings, int],
    ) -> None:
        """保存实际环境，不登记到用户项目列表。

        Retain the environment outside the user's project list.
        """
        super().__init__(storage)
        self.root, self.snapshot = root, snapshot

    def selected(
        self, project_id: str, sandbox_supported: bool = False
    ) -> tuple[EnvironmentView, ExecutionSettings, int]:
        """同一实验两次运行保持同一环境配置。

        Keep environment settings identical across both runs.
        """
        return self.snapshot

    def project_root(self, project_id: str | None) -> Path:
        """仅返回实验根，不改原项目。

        Resolve to the experiment root, leaving the original untouched.
        """
        return self.root


def copy_project(
    source: Path,
    destination: Path,
    exclude: list[str],
    stop: threading.Event,
) -> list[str]:
    """复制项目内容，显式记录排除项与链接。

    Copy project contents and report excluded paths/links without following them outside the copy.
    """
    omitted: list[str] = []

    def ignored(directory: str, names: list[str]) -> list[str]:
        """跳过已声明排除项，不把链接复制成原项目写入口。

        Skip declared exclusions and avoid links back into the original project.
        """
        skipped = []
        if stop.is_set():
            raise InterruptedError("Experiment copy cancelled")
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(source).as_posix()
            if (
                path.is_symlink()
                or path.is_junction()
                or any(
                    fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(relative, pattern)
                    for pattern in exclude
                )
            ):
                skipped.append(name)
                omitted.append(relative)
        return skipped

    def copy_file(source_file: str, destination_file: str) -> str:
        """按块检查停止，不让大文件拖住退出。

        Check cancellation between chunks of large files.
        """
        with open(source_file, "rb") as reader, open(destination_file, "wb") as writer:
            while block := reader.read(1024 * 1024):
                if stop.is_set():
                    raise InterruptedError("Experiment copy cancelled")
                writer.write(block)
        shutil.copystat(source_file, destination_file)
        return destination_file

    shutil.copytree(source, destination, ignore=ignored, copy_function=copy_file)
    return omitted


async def copy_snapshot(source: Path, destination: Path, exclude: list[str]) -> list[str]:
    """复制不占用业务单写者，取消后等待线程清理。

    Copy outside the business writer, reaping the copy thread after cancellation.
    """
    stop = threading.Event()
    task = asyncio.create_task(asyncio.to_thread(copy_project, source, destination, exclude, stop))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        stop.set()
        await asyncio.gather(task, return_exceptions=True)
        raise


async def run_copy(
    owner: "EvolutionService",
    job: EvolutionJob,
    root: Path,
    data: Path,
    command: RunCommandArgs,
    snapshot: tuple[EnvironmentView, ExecutionSettings, int],
) -> None:
    """复用程序监管与取消，独立数据不进入日常会话。

    Reuse process ownership/cancellation with isolated program records.
    """
    worker, stack = BusinessWorker(), ExitStack()
    # 实验嵌套目录可能超过 Win32 旧路径长度；使用扩展路径而不改系统策略。
    # Nested experiments can exceed legacy Win32 paths; use extended paths, not system policy.
    data_path = str(data.resolve())
    if os.name == "nt" and not data_path.startswith("\\\\?\\"):
        data_path = (
            "\\\\?\\UNC\\" + data_path[2:]
            if data_path.startswith("\\\\")
            else "\\\\?\\" + data_path
        )
    storage = Storage(resolve_data_dir(data_path))
    programs = ProgramService(
        ExperimentEnvironment(storage, root, snapshot),
        ProgramStore(storage),
        worker,
    )
    try:
        await worker.call(stack.enter_context, storage.writer())
        await worker.call(storage.initialize)
        config = await owner.sessions.worker.call(
            load_config, owner.sessions.store.storage.location
        )
        context = ToolContext(
            root=root,
            limits=config.run,
            stop=threading.Event(),
            project_id=job.project_id,
            session_id=job.job_id,
            run_id=str(uuid4()),
            mode="normal",
            plan_document=None,
        )
        result = await programs.run(context, command)
        job.programs.append(result)
        await owner.sessions.worker.call(owner.store.save_job, job)
    finally:
        try:
            await programs.close()
            await asyncio.to_thread(SandboxLease.close_all, storage.root / "sandbox-leases")
        finally:
            await worker.call(stack.close)
            worker.close()


async def experiment(
    owner: "EvolutionService",
    job: EvolutionJob,
    candidate: EvolutionCandidate,
    params: EvolutionExperimentParams,
) -> None:
    """对比同一命令的真实结果，不自动采用或修复失败。

    Compare observed command results without automatically applying or repairing failures.
    """
    worker = owner.sessions.worker
    try:
        root = await owner.sessions.validate_project(job.project_id)
        snapshot = await worker.call(
            EnvironmentStore(owner.sessions.store.storage).selected,
            job.project_id,
            True,
        )
        directory = owner.sessions.store.storage.root / "evolution" / "experiments" / job.job_id
        await worker.call(directory.mkdir, parents=True, exist_ok=True)
        job.experiment_directory = str(directory)
        # 两个副本从同一个快照生成，基线命令的副作用不会污染候选。
        # Clone both variants before running so baseline side effects cannot pollute the candidate.
        baseline, proposed = directory / "baseline", directory / "candidate"
        job.omitted_paths = await copy_snapshot(root, baseline, params.exclude)
        await copy_snapshot(baseline, proposed, [])
        relative = Path(candidate.target.identity)
        if relative.is_absolute():
            relative = relative.relative_to(root)
        if not (baseline / relative).resolve().is_relative_to(baseline.resolve()):
            raise AgentError("PATH_DENIED", "代码目标不在实验副本内。")
        for stage, content in ((baseline, candidate.before), (proposed, candidate.after)):
            path = stage / relative
            if content is None:
                await worker.call(path.unlink, missing_ok=True)
            else:
                await worker.call(path.parent.mkdir, parents=True, exist_ok=True)
                await worker.call(path.write_text, content, encoding="utf-8", newline="")
        for label, stage in (("baseline", baseline), ("candidate", proposed)):
            job.message = "正在执行" + ("原版本" if label == "baseline" else "候选版本") + "检查"
            await worker.call(owner.store.save_job, job)
            await run_copy(
                owner, job, stage, directory / (label + "-data"), params.command, snapshot
            )
        before, after = (program.summary.exit_code for program in job.programs)
        outcome: Literal["improved", "regressed", "unchanged", "inconclusive"] = (
            "improved"
            if before != 0 and after == 0
            else "regressed"
            if before == 0 and after != 0
            else "unchanged"
            if before == after == 0
            else "inconclusive"
        )
        async with owner.locks.setdefault(candidate.candidate_id, asyncio.Lock()):
            current = await worker.call(
                owner.store.candidate, job.project_id, candidate.candidate_id
            )
            changed = current.content_revision != candidate.content_revision
            summary = (
                f"同命令：原版 exit={before}，候选 exit={after}。"
                f"实验目录 {directory}；只代表本次检查。"
                + ("候选已更新，此结果属于之前版本。" if changed else "")
            )
            current.comparisons.append(
                EvolutionComparison(
                    at=utc_now(),
                    summary=summary,
                    outcome="inconclusive" if changed else outcome,
                    method="execution",
                    content_revision=candidate.content_revision,
                )
            )
            await worker.call(owner.store.save, current)
        job.status, job.message = "completed", summary
    except asyncio.CancelledError:
        job.status, job.message = "cancelled", "实验已停止，原项目未被采用。"
    except Exception as exc:
        job.status = "failed"
        job.message = exc.message if isinstance(exc, AgentError) else "实验未完成，请查看诊断。"
        await worker.call(
            owner.diagnostics.record,
            "EVOLUTION_EXPERIMENT_FAILED",
            job.message,
            component="evolution.experiment",
            exception=exc,
            project_id=job.project_id,
        )
    finally:
        await owner.finish_job(job)
