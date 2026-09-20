"""项目路径与发现过滤；忽略规则不是显式访问权限。 Project paths and discovery filters."""

import fnmatch
import ntpath
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from pathspec import GitIgnoreSpec

from my_agent.errors import AgentError
from my_agent.runtime.settings import RunLimits

EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".svn",
        ".hg",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".artifacts",
    }
)


def checkpoint(stop: threading.Event) -> None:
    """同步文件工作点响应取消。 Observe cancellation inside synchronous file work."""
    if stop.is_set():
        raise AgentError("CANCELLED", "运行已停止。")


def relative_path(value: str) -> PurePosixPath:
    """拒绝 Windows 设备、驱动器与越界路径。 Reject device, drive and traversal paths."""
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not value
        or "\x00" in value
        or ":" in value
        or path.is_absolute()
        or PureWindowsPath(value).drive
        or ".." in path.parts
        or any(part.endswith((".", " ")) for part in path.parts if part != ".")
        or ntpath.isreserved(normalized)
    ):
        raise AgentError("PATH_DENIED", "工具只接受项目内的相对路径。")
    return path


@dataclass
class Scan:
    """有界扫描结果及可见限制。 Bounded scan results with visible limitations."""

    files: list[str]
    truncated: bool
    skipped: int


class ReadPolicy:
    """为一次运行绑定真实项目根与受信规则。 Bind real project root and trusted run policy."""

    def __init__(self, root: Path, limits: RunLimits, stop: threading.Event) -> None:
        """不读取项目配置以改变权限。 Do not load project configuration as permissions."""
        self.root = root.resolve(strict=True)
        self.limits = limits
        self.stop = stop
        self.ignore_cache: dict[Path, tuple[tuple[int, int], GitIgnoreSpec]] = {}

    def relative(self, value: str) -> PurePosixPath:
        """将项目内绝对或相对写法统一；不凭路径写法拒绝同一文件。

        Normalize absolute or relative project paths without rejecting equivalent spellings.
        """
        if not value or "\x00" in value or ntpath.isreserved(value):
            raise AgentError("PATH_DENIED", "文件路径无效。")
        selected = Path(value)
        absolute = Path(os.path.abspath(self.root / selected))
        if not absolute.is_relative_to(self.root):
            raise AgentError("PATH_DENIED", "文件工具的目标需要位于当前项目内。")
        return PurePosixPath(absolute.relative_to(self.root).as_posix())

    def _resolve(self, relative: PurePosixPath) -> Path:
        """解析实际目标并核对项目归属。 Resolve the target and check project containment."""
        checkpoint(self.stop)
        try:
            target = self.root.joinpath(*relative.parts).resolve(strict=True)
            if not target.is_relative_to(self.root):
                raise AgentError("PATH_DENIED", "链接目标位于项目之外。")
            return target
        except FileNotFoundError as exc:
            raise AgentError("FILE_NOT_FOUND", "目标不存在，请调整路径或按任务需要创建。") from exc
        except (OSError, RuntimeError) as exc:
            raise AgentError("FILE_UNAVAILABLE", "文件不存在或无法访问。") from exc

    def _rules(self, directory: Path) -> Iterator[tuple[Path, GitIgnoreSpec]]:
        """按根到叶读取嵌套 gitignore。 Read nested gitignore rules from root to leaf."""
        parents = [self.root]
        cursor = self.root
        for part in directory.relative_to(self.root).parts:
            cursor = cursor / part
            parents.append(cursor)
        for parent in parents:
            checkpoint(self.stop)
            ignore = parent / ".gitignore"
            if not ignore.exists():
                continue
            try:
                safe = self._resolve(PurePosixPath(ignore.relative_to(self.root).as_posix()))
                stat = safe.stat()
                version = (stat.st_mtime_ns, stat.st_size)
                cached = self.ignore_cache.get(safe)
                if cached and cached[0] == version:
                    yield parent, cached[1]
                    continue
                raw = safe.read_bytes()
                spec = GitIgnoreSpec.from_lines(raw.decode("utf-8-sig").splitlines())
                self.ignore_cache[safe] = (version, spec)
                yield parent, spec
            except (UnicodeError, ValueError) as exc:
                raise AgentError("IGNORE_INVALID", "无法可靠解析 .gitignore。") from exc

    def _filtered(self, target: Path, relative: PurePosixPath, *, directory: bool = False) -> bool:
        """只用于发现，不阻断指定路径的读写。 Filter discovery, never explicit reads or writes."""
        if any(fnmatch.fnmatchcase(relative.as_posix(), p) for p in self.limits.exclude_globs):
            return True
        if self.limits.include_ignored:
            return False
        if any(part.casefold() in EXCLUDED_DIRS for part in relative.parts):
            return True
        ignored = False
        for base, spec in self._rules(target.parent if target != self.root else self.root):
            rel = target.relative_to(base).as_posix()
            if directory or target.is_dir():
                rel += "/"
            result = spec.check_file(rel)
            if result.include is not None:
                ignored = result.include
        return ignored

    def new_target(self, value: str) -> Path:
        """检查新目标与所有真实祖先，允许创建缺失目录。

        Validate new targets and resolved ancestors."""
        relative = self.relative(value)
        if not relative.parts:
            raise AgentError("PATH_DENIED", "新文件需要明确文件名。")
        try:
            lexical = self.root.joinpath(*relative.parts)
            target = lexical.resolve(strict=False)
            if not target.is_relative_to(self.root):
                raise AgentError("PATH_DENIED", "新文件的父目录位于项目之外。")
            if os.path.lexists(lexical) or os.path.lexists(target):
                raise AgentError("FILE_EXISTS", "目标已存在；请读取后使用精确编辑。")
            return target
        except (OSError, RuntimeError) as exc:
            raise AgentError("FILE_UNAVAILABLE", "无法验证新文件路径。") from exc

    def target(self, value: str, *, directory: bool = False) -> Path:
        """指定文件不受发现过滤影响，仍核对存在性和类型。

        Check explicit target existence and type, independent of discovery filters.
        """
        checkpoint(self.stop)
        if not value or "\x00" in value or ntpath.isreserved(value):
            raise AgentError("PATH_DENIED", "文件路径无效。")
        try:
            target = (self.root / value).resolve(strict=True)
            if target.is_dir() != directory or (not directory and not target.is_file()):
                raise AgentError("FILE_TYPE", "目标类型不符合工具要求。")
            return target
        except FileNotFoundError as exc:
            raise AgentError("FILE_NOT_FOUND", "目标不存在，请调整路径或按任务需要创建。") from exc
        except (OSError, RuntimeError) as exc:
            raise AgentError("FILE_UNAVAILABLE", "无法检查目标文件。") from exc

    def scan(self, directory: str = ".", glob: str = "*") -> Scan:
        """有界遍历候选文件，跳过局部错误且报告截断。 Walk bounded candidates with local errors."""
        start = self.target(directory, directory=True)
        pending = [(start, 0)]
        seen: set[Path] = set()
        files: list[str] = []
        skipped = 0
        truncated = False
        visited = 0
        while pending:
            checkpoint(self.stop)
            parent, depth = pending.pop()
            if parent in seen:
                continue
            seen.add(parent)
            try:
                with os.scandir(parent) as entries:
                    for entry in entries:
                        checkpoint(self.stop)
                        visited += 1
                        if visited > self.limits.max_scan_files:
                            return Scan(sorted(files), True, skipped)
                        candidate = Path(entry.path)
                        rel = (
                            candidate.relative_to(self.root).as_posix()
                            if candidate.is_relative_to(self.root)
                            else candidate.as_posix()
                        )
                        try:
                            is_dir = entry.is_dir()
                            target = self.target(rel, directory=is_dir)
                            if start == self.root and not target.is_relative_to(self.root):
                                skipped += 1
                                continue
                            # 指定子目录意味着定向查看；全项目发现才应用默认忽略。
                            # Explicit subdirectories are targeted views, not workspace discovery.
                            if start == self.root and self._filtered(
                                target, PurePosixPath(rel), directory=is_dir
                            ):
                                skipped += 1
                                continue
                            if is_dir:
                                if depth < self.limits.max_depth:
                                    pending.append((target, depth + 1))
                                else:
                                    truncated = True
                            elif fnmatch.fnmatchcase(rel, glob):
                                files.append(rel)
                        except (AgentError, OSError):
                            checkpoint(self.stop)
                            skipped += 1
            except OSError:
                skipped += 1
        return Scan(sorted(set(files)), truncated, skipped)
