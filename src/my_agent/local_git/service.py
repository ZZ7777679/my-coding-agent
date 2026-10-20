"""通过受管本机 Git CLI 操作本地版本记录，无远端请求。

Managed local Git CLI, no remote calls.
"""

import asyncio
import codecs
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from my_agent.errors import AgentError
from my_agent.execution.environments import EnvironmentStore, executable, execution_environment
from my_agent.execution.service import spawn
from my_agent.execution.types import EnvironmentView, ExecutionSettings
from my_agent.execution.windows import WindowsProcess
from my_agent.local_git.settings import GitSettingsStore
from my_agent.local_git.types import (
    ConfigureGitParams,
    GitCommit,
    GitCommitParams,
    GitCommitResult,
    GitDiff,
    GitDiffParams,
    GitFileStatus,
    GitHistory,
    GitHistoryParams,
    GitPathsParams,
    GitProjectParams,
    GitSettings,
    GitStatus,
)
from my_agent.worker import BusinessWorker


@dataclass(frozen=True)
class GitExecution:
    """启动时冻结项目环境，后续设置不热切换。

    Freeze project environment for one operation.
    """

    root: Path
    program: str
    env: dict[str, str]
    settings: ExecutionSettings
    view: EnvironmentView


@dataclass(frozen=True)
class GitOutput:
    """真实本地命令退出码及独立输出。

    Actual local exit code and separate output."""

    code: int
    stdout: str
    stderr: str
    truncated: bool


class LocalGitService:
    """用户操作只访问本地仓库，复用项目环境与进程树清理。

    User operations access local repositories through project environments and process-tree cleanup.
    """

    def __init__(self, environments: EnvironmentStore, worker: BusinessWorker) -> None:
        """不在构造、项目打开或查询时初始化仓库。

        Never initialize repositories on construction/query.
        """
        self.environments, self.worker = environments, worker
        self.processes: set[WindowsProcess] = set()
        self.locks: dict[str, asyncio.Lock] = {}
        self.closing = False
        self.settings_store = GitSettingsStore(environments)

    async def settings(self, params: GitProjectParams) -> GitSettings:
        """读取开关和备份，不要求安装 Git。

        Read switch and backup without requiring Git."""
        return await self.worker.call(self.settings_store.read, params.project_id)

    async def configure(self, params: ConfigureGitParams) -> GitSettings:
        """与本应用该项目 Git 操作串行移动元数据。

        Serialize relocation with this app's project Git work."""
        async with self.locks.setdefault(params.project_id, asyncio.Lock()):
            # 大仓库跨盘复制不占用全应用存储队列；此配置文件只由本项目锁保护写入。
            # Cross-volume copies leave shared storage responsive; this project lock owns writes.
            operation = asyncio.create_task(
                asyncio.to_thread(self.settings_store.configure, params.project_id, params.enabled)
            )
            try:
                return await asyncio.shield(operation)
            except asyncio.CancelledError:
                await operation
                raise

    async def _execution(self, project_id: str) -> GitExecution:
        """选定环境只解析一次，清除可重定向仓库的宿主变量。

        Resolve once and remove repo overrides.
        """
        if self.closing:
            raise AgentError("EXECUTION_CLOSING", "应用正在退出，不能启动 Git 操作。")
        setting = await self.settings(GitProjectParams(project_id=project_id))
        if not setting.enabled:
            raise AgentError("GIT_DISABLED", "本项目 Git 已关闭；可在本地 Git 面板开启并恢复备份。")
        view, settings, _ = await self.worker.call(self.environments.selected, project_id, True)
        root = await self.worker.call(self.environments.project_root, project_id)
        env = execution_environment(view)
        for name in list(env):
            if name.upper() in {
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_COMMON_DIR",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_NAMESPACE",
            }:
                del env[name]
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_OPTIONAL_LOCKS"] = "0"
        program = await asyncio.to_thread(executable, "git.exe", env, root)
        return GitExecution(root, program, env, settings, view)

    async def _run(self, execution: GitExecution, arguments: list[str]) -> GitOutput:
        """持续读取双通道、超时与取消都清理 Job；不启动 remote 命令。

        Drain both channels and reap the job on timeout/cancellation; expose no remote commands.
        """
        command = [
            execution.program,
            "--no-pager",
            "--literal-pathspecs",
            "-c",
            "core.quotepath=false",
            "-c",
            "color.ui=false",
            "-c",
            "status.relativePaths=true",
            *arguments,
        ]
        process = await spawn(
            command,
            execution.root,
            execution.env,
            execution.settings,
            sandbox_directory=self.environments.storage.root / "sandbox-leases"
            if execution.view.execution and execution.view.execution.mode == "sandbox"
            else None,
            root=execution.root,
            view=execution.view,
        )
        self.processes.add(process)
        outputs: dict[str, str] = {"stdout": "", "stderr": ""}
        decoders = {name: codecs.getincrementaldecoder("utf-8")("replace") for name in outputs}
        truncated = False
        count = 0

        def consume() -> None:
            """保留有界输出并标明截断，不截成假成功。

            Bound output and expose truncation.
            """
            nonlocal truncated, count
            chunks, dropped = process.drain()
            truncated = truncated or dropped > 0
            for channel, raw in chunks:
                value = decoders[channel].decode(raw)
                count += len(raw)
                if count > execution.settings.max_output_bytes:
                    truncated = True
                else:
                    outputs[channel] += value

        try:
            async with asyncio.timeout(execution.settings.command_timeout_seconds):
                while True:
                    consume()
                    if process.output_failed:
                        raise AgentError("GIT_OUTPUT_FAILED", "Git 输出通道故障，已停止操作。")
                    code = process.poll()
                    if code is not None:
                        break
                    await asyncio.sleep(0.03)
                await asyncio.to_thread(process.finish, execution.settings.cleanup_timeout_seconds)
                consume()
                for name, decoder in decoders.items():
                    outputs[name] += decoder.decode(b"", final=True)
                return GitOutput(code, outputs["stdout"], outputs["stderr"], truncated)
        except TimeoutError as exc:
            raise AgentError("GIT_TIMEOUT", "Git 操作达到执行时限，未自动重试。") from exc
        finally:
            try:
                await asyncio.to_thread(process.finish, execution.settings.cleanup_timeout_seconds)
            finally:
                process.close()
                self.processes.discard(process)

    @staticmethod
    def _check(output: GitOutput) -> None:
        """非零退出保留必要工具说明，缺失身份不自动配置。

        Report Git errors without configuring identity.
        """
        if output.code:
            detail = (output.stderr or output.stdout).strip()[-2000:]
            raise AgentError(
                "GIT_COMMAND_FAILED", f"本地 Git 操作未完成（exit {output.code}）：{detail}"
            )

    @staticmethod
    def _path(root: Path, value: str) -> str:
        """支持已删除文件，核实最近真实父目录归属，拒绝路径 magic。

        Validate selected project paths.
        """
        selected = Path(value)
        try:
            # Git 操作最后一项目录记录，不能将符号链接名字换成目标名字。
            # Git addresses the final directory entry, not a symlink's target name.
            entry = Path(os.path.abspath(selected if selected.is_absolute() else root / selected))
            if (
                not entry.is_relative_to(root)
                or entry == root
                or not entry.parent.resolve().is_relative_to(root)
            ):
                raise ValueError
            return PurePosixPath(*entry.relative_to(root).parts).as_posix()
        except (OSError, RuntimeError, ValueError) as exc:
            raise AgentError("GIT_PATH_INVALID", "Git 文件路径必须位于所选项目内。") from exc

    async def _status(self, project_id: str, execution: GitExecution) -> GitStatus:
        """查询当前仓库双列状态，不访问 remote。

        Query worktree/index status without remote access.
        """
        exists = await self._run(execution, ["rev-parse", "--is-inside-work-tree"])
        if exists.code:
            # 未初始化仓库是正常空状态；权限/损坏不能冒充未初始化。
            # Absence is normal; access/corruption must not be disguised as no repository.
            if "not a git repository" in exists.stderr.lower():
                return GitStatus(
                    project_id=project_id,
                    available=True,
                    repository=False,
                    branch=None,
                    files=[],
                    message="此项目尚未初始化本地 Git。",
                )
            self._check(exists)
        top = await self._run(execution, ["rev-parse", "--show-toplevel"])
        self._check(top)
        try:
            repository_root = Path(top.stdout.strip()).resolve()
            project_repository = repository_root.samefile(execution.root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise AgentError("GIT_ROOT_UNAVAILABLE", "Git 仓库根目录无法核实。") from exc
        output = await self._run(
            execution, ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "."]
        )
        self._check(output)
        if output.truncated:
            raise AgentError("GIT_OUTPUT_LIMIT", "Git 状态超出当前输出预算，请调整执行设置后刷新。")
        chunks = output.stdout.split("\0")
        files: list[GitFileStatus] = []
        index = 0
        while index < len(chunks):
            entry = chunks[index]
            index += 1
            if not entry:
                continue
            if len(entry) < 4 or entry[2] != " ":
                raise AgentError("GIT_STATUS_INVALID", "Git 返回了无法解析的文件状态。")
            original = None
            if entry[0] in {"R", "C"} or entry[1] in {"R", "C"}:
                if index >= len(chunks) or not chunks[index]:
                    raise AgentError("GIT_STATUS_INVALID", "Git 重命名状态不完整。")
                original, index = chunks[index], index + 1
            files.append(
                GitFileStatus(
                    # porcelain v1 始终以仓库根为基准；公开路径仍按所选项目定位。
                    # Porcelain v1 uses repository-relative paths; public paths use the project.
                    path=PurePosixPath(
                        *Path(os.path.relpath(repository_root / entry[3:], execution.root)).parts
                    ).as_posix(),
                    index_status=entry[0],
                    worktree_status=entry[1],
                    original_path=PurePosixPath(
                        *Path(os.path.relpath(repository_root / original, execution.root)).parts
                    ).as_posix()
                    if original is not None
                    else None,
                )
            )
        branch = await self._run(execution, ["symbolic-ref", "--quiet", "--short", "HEAD"])
        return GitStatus(
            project_id=project_id,
            available=True,
            repository=True,
            repository_root=str(repository_root),
            project_repository=project_repository,
            branch=branch.stdout.strip() if branch.code == 0 else "分离 HEAD",
            files=files,
            message=None
            if project_repository
            else "当前项目位于上层 Git 仓库内；文件操作限当前项目，提交包含该仓库整个暂存区。",
        )

    async def status(self, params: GitProjectParams) -> GitStatus:
        """状态读取与开关操作串行。

        Serialize status reads with switch operations."""
        async with self.locks.setdefault(params.project_id, asyncio.Lock()):
            return await self._status_view(params)

    async def _status_view(self, params: GitProjectParams) -> GitStatus:
        """缺失 Git 只限制工作台，普通编辑与聊天继续。

        Missing Git affects only this workbench.
        """
        try:
            execution = await self._execution(params.project_id)
        except AgentError as exc:
            if exc.code in {"PROGRAM_UNAVAILABLE", "GIT_DISABLED"}:
                return GitStatus(
                    project_id=params.project_id,
                    available=False,
                    repository=False,
                    branch=None,
                    files=[],
                    code=exc.code,
                    message=exc.message
                    if exc.code == "GIT_DISABLED"
                    else "本机未找到 Git，请安装或设置项目工具环境。",
                )
            raise
        return await self._status(params.project_id, execution)

    async def diff(self, params: GitDiffParams) -> GitDiff:
        """差异读取与开关操作串行。

        Serialize diff reads with switch operations."""
        async with self.locks.setdefault(params.project_id, asyncio.Lock()):
            return await self._diff(params)

    async def _diff(self, params: GitDiffParams) -> GitDiff:
        """分别读取工作区或暂存区差异，禁止外部 diff/textconv。

        Read separate local diffs.
        """
        execution = await self._execution(params.project_id)
        path = self._path(execution.root, params.path)
        status = await self._status(params.project_id, execution)
        if not status.repository:
            raise AgentError("GIT_REPOSITORY_REQUIRED", "此操作需要本地 Git 仓库。")
        item = next((f for f in status.files if f.path == path), None)
        if item and item.index_status == "?" and params.area == "worktree":
            # 未跟踪文件用 /dev/null diff，不暂存也不改索引。
            # Read an untracked file against /dev/null without modifying the index.
            output = await self._run(
                execution,
                ["diff", "--no-index", "--no-ext-diff", "--no-textconv", "--", "/dev/null", path],
            )
            if output.code not in {0, 1}:
                self._check(output)
        else:
            arguments = ["diff", "--no-ext-diff", "--no-textconv"]
            if params.area == "index":
                arguments.append("--cached")
            output = await self._run(execution, [*arguments, "--", path])
            self._check(output)
        return GitDiff(
            project_id=params.project_id,
            path=path,
            area=params.area,
            text=output.stdout,
            truncated=output.truncated,
        )

    async def _paths(self, params: GitPathsParams, *, stage: bool) -> GitStatus:
        """单项目索引修改串行，不自动包括未选择文件。

        Serialize explicit index changes per project.
        """
        async with self.locks.setdefault(params.project_id, asyncio.Lock()):
            execution = await self._execution(params.project_id)
            paths = [self._path(execution.root, p) for p in params.paths]
            if stage:
                output = await self._run(execution, ["add", "--", *paths])
            else:
                head = await self._run(execution, ["rev-parse", "--verify", "--quiet", "HEAD"])
                output = await self._run(
                    execution,
                    ["reset", "-q", "HEAD", "--", *paths]
                    if head.code == 0
                    else ["rm", "--cached", "-q", "-f", "--", *paths],
                )
            self._check(output)
            return await self._status(params.project_id, execution)

    async def stage(self, params: GitPathsParams) -> GitStatus:
        """暂存选定文件。

        Stage selected files."""
        return await self._paths(params, stage=True)

    async def unstage(self, params: GitPathsParams) -> GitStatus:
        """取消选定暂存，保留工作区。

        Unstage selected paths without altering worktree content.
        """
        return await self._paths(params, stage=False)

    async def init(self, params: GitProjectParams) -> GitStatus:
        """只响应用户明确初始化操作，不设置 remote/身份。

        Initialize only on explicit user action.
        """
        async with self.locks.setdefault(params.project_id, asyncio.Lock()):
            execution = await self._execution(params.project_id)
            # 显式目录让子项目初始化自己的仓库，不重建发现到的上层仓库。
            # An explicit directory initializes this project, not a discovered parent repository.
            self._check(await self._run(execution, ["init", str(execution.root)]))
            return await self._status(params.project_id, execution)

    async def commit(self, params: GitCommitParams) -> GitCommitResult:
        """仅提交现有暂存区，失败不改身份或自动重试。

        Commit the existing index, no identity edits.
        """
        async with self.locks.setdefault(params.project_id, asyncio.Lock()):
            execution = await self._execution(params.project_id)
            output = await self._run(execution, ["commit", "-m", params.message])
            self._check(output)
            head = await self._run(execution, ["rev-parse", "--verify", "HEAD"])
            self._check(head)
            return GitCommitResult(
                project_id=params.project_id,
                commit_id=head.stdout.strip(),
                output=(output.stdout + output.stderr).strip(),
            )

    async def history(self, params: GitHistoryParams) -> GitHistory:
        """历史读取与开关操作串行。

        Serialize history reads with switch operations."""
        async with self.locks.setdefault(params.project_id, asyncio.Lock()):
            return await self._history(params)

    async def _history(self, params: GitHistoryParams) -> GitHistory:
        """读取本地历史，空仓库正常返回空列表。

        Read local history; unborn HEAD has no commits.
        """
        execution = await self._execution(params.project_id)
        status = await self._status(params.project_id, execution)
        if not status.repository:
            return GitHistory(project_id=params.project_id, commits=[])
        head = await self._run(execution, ["rev-parse", "--verify", "--quiet", "HEAD"])
        if head.code:
            if head.code == 1:
                return GitHistory(project_id=params.project_id, commits=[])
            self._check(head)
        output = await self._run(
            execution, ["log", f"-{params.limit}", "--format=%H%x00%s%x00%an%x00%aI%x00"]
        )
        self._check(output)
        if output.truncated:
            raise AgentError("GIT_OUTPUT_LIMIT", "提交历史超出当前输出预算，请缩小查询条数。")
        fields = output.stdout.split("\0")
        commits: list[GitCommit] = []
        for index in range(0, len(fields) - 1, 4):
            if index + 3 >= len(fields):
                raise AgentError("GIT_HISTORY_INVALID", "本地提交历史不完整。")
            commits.append(
                GitCommit(
                    commit_id=fields[index].strip(),
                    subject=fields[index + 1],
                    author=fields[index + 2],
                    authored_at=fields[index + 3],
                )
            )
        return GitHistory(project_id=params.project_id, commits=commits)

    async def close(self) -> None:
        """应用退出中断自有 Git 命令，操作不自动重放。

        Stop owned Git commands without replay.
        """
        self.closing = True
        for process in list(self.processes):
            process.terminate()
