"""共享路径、忽略与凭据文件规则。 Shared path, ignore and credential-file policy."""

import fnmatch
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
SECRET_DIRS = frozenset({".ssh", ".aws", ".azure", ".gnupg", ".kube"})
SECRET_NAMES = frozenset(
    {
        "credentials",
        "credentials.json",
        "secrets.json",
        "secrets.toml",
        "secrets.yaml",
        "secrets.yml",
        "auth.json",
        ".npmrc",
        ".pypirc",
        ".netrc",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "agent.paths.local.json",
    }
)
SECRET_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".jks"})


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
    ):
        raise AgentError("PATH_DENIED", "工具只接受项目内的相对路径。")
    return path


def is_secret(path: PurePosixPath) -> bool:
    """保护常见凭据文件；明确命名的示例文件除外。 Protect credentials, allowing named examples."""
    names = [part.casefold() for part in path.parts]
    if any(part in SECRET_DIRS for part in names):
        return True
    name = path.name.casefold()
    example = name.endswith((".example", ".sample", ".template"))
    return not example and (
        name in SECRET_NAMES
        or name == ".env"
        or name.startswith(".env.")
        or path.suffix.casefold() in SECRET_SUFFIXES
    )


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

    def _resolve(self, relative: PurePosixPath) -> Path:
        """检查链接后的真实路径和硬链接风险。 Check resolved containment and hard-link risk."""
        checkpoint(self.stop)
        try:
            target = self.root.joinpath(*relative.parts).resolve(strict=True)
            if not target.is_relative_to(self.root):
                raise AgentError("PATH_DENIED", "链接目标位于项目之外。")
            real_relative = PurePosixPath(target.relative_to(self.root).as_posix())
            if is_secret(relative) or is_secret(real_relative):
                raise AgentError("SENSITIVE_FILE", "该文件属于受保护的凭据文件。")
            if target.is_file() and target.stat().st_nlink > 1:
                raise AgentError("PATH_DENIED", "不读取具有其他硬链接的文件，请使用普通源码文件。")
            return target
        except (OSError, RuntimeError) as exc:
            raise AgentError("FILE_UNAVAILABLE", "文件不存在或无法访问。") from exc

    def _rules(self, directory: Path) -> Iterator[tuple[Path, GitIgnoreSpec]]:
        """按根到叶读取嵌套 gitignore，限制配置体积。 Read bounded nested gitignore rules."""
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
                with safe.open("rb") as stream:
                    raw = stream.read(65537)
                if len(raw) > 65536:
                    raise AgentError("IGNORE_INVALID", "忽略规则过大，请检查 .gitignore。")
                spec = GitIgnoreSpec.from_lines(raw.decode("utf-8-sig").splitlines())
                self.ignore_cache[safe] = (version, spec)
                yield parent, spec
            except (UnicodeError, ValueError) as exc:
                raise AgentError("IGNORE_INVALID", "无法可靠解析 .gitignore。") from exc

    def _filtered(self, target: Path, relative: PurePosixPath) -> bool:
        """三工具共用过滤；普通忽略可由受信设置覆盖。 Apply shared, trusted file filters."""
        if any(fnmatch.fnmatchcase(relative.as_posix(), p) for p in self.limits.exclude_globs):
            return True
        # .git 永不作为源码上下文，其余普通忽略可显式覆盖。
        # Git metadata is never source context; ordinary ignores have a trusted override.
        if any(part.casefold() in {".git", ".svn", ".hg"} for part in relative.parts):
            return True
        if self.limits.include_ignored:
            return False
        if any(part.casefold() in EXCLUDED_DIRS for part in relative.parts):
            return True
        ignored = False
        for base, spec in self._rules(target.parent if target != self.root else self.root):
            rel = target.relative_to(base).as_posix()
            if target.is_dir():
                rel += "/"
            result = spec.check_file(rel)
            if result.include is not None:
                ignored = result.include
        return ignored

    def target(self, value: str, *, directory: bool = False) -> Path:
        """同时验证别名和真实目标，禁止链接绕过过滤。 Validate alias and real target filters."""
        relative = relative_path(value)
        target = self._resolve(relative)
        real = PurePosixPath(target.relative_to(self.root).as_posix())
        try:
            if target.is_dir() != directory or (not directory and not target.is_file()):
                raise AgentError("FILE_TYPE", "目标类型不符合工具要求。")
            # 检查祖先目录，避免直接 read_file 绕过被忽略目录。
            # Check ancestors so direct reads cannot bypass ignored directories.
            for path in (relative, real):
                for count in range(1, len(path.parts) + 1):
                    part = PurePosixPath(*path.parts[:count])
                    candidate = self.root.joinpath(*part.parts)
                    if self._filtered(candidate, part):
                        raise AgentError("FILE_IGNORED", "文件被项目或应用读取规则忽略。")
            return target
        except OSError as exc:
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
                        rel = Path(entry.path).relative_to(self.root).as_posix()
                        try:
                            is_dir = entry.is_dir()
                            target = self.target(rel, directory=is_dir)
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
