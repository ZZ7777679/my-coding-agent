"""三个只读工具及有界搜索辅助。 Three read-only tools and bounded search support."""

import asyncio
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Annotated

from pydantic import Field, ValidationError

from my_agent.errors import AgentError
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.processes import probe_environment
from my_agent.runtime.settings import RunLimits
from my_agent.tools.policy import ReadPolicy, checkpoint


class ListFilesArgs(ModelData):
    """目录列举参数。 Directory listing arguments."""

    directory: str = "."
    glob: str = "*"
    limit: Annotated[int, Field(ge=1, le=1000)] = 200


class ReadFileArgs(ModelData):
    """按行读取明确指定的文件。 Read an explicitly selected file by line range."""

    path: Annotated[str, Field(min_length=1, max_length=4096)]
    start_line: Annotated[int, Field(ge=1)] = 1
    lines: Annotated[int, Field(ge=1, le=2000)] = 200


class SearchArgs(ModelData):
    """字面搜索参数，不接受 shell / 正则选项。 Literal search without shell or regex options."""

    query: Annotated[str, Field(min_length=1, max_length=4096)]
    glob: str = "*"
    limit: Annotated[int, Field(ge=1, le=1000)] = 100


def encode(value: JsonObject) -> str:
    """统一工具结果 JSON 表达。 Serialize tool results consistently."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def newline_kind(text: str) -> str:
    """按原内容识别换行，不把无换行或 CR 错记为 LF。 Identify original newline forms accurately."""
    remaining = text.replace("\r\n", "")
    kinds = [
        name
        for name, present in (
            ("crlf", "\r\n" in text),
            ("lf", "\n" in remaining),
            ("cr", "\r" in remaining),
        )
        if present
    ]
    return "mixed" if len(kinds) > 1 else (kinds[0] if kinds else "none")


class ReadTools:
    """一次运行的只读工具集合，取消后等待自有文件工作退出。

    Per-run read-only tools that await owned file work during cancellation.
    """

    def __init__(self, root: Path, limits: RunLimits, stop: threading.Event) -> None:
        """绑定共享策略与预算。 Bind shared policy and limits."""
        self.policy = ReadPolicy(root, limits, stop)
        self.limits = limits
        self.stop = stop

    @staticmethod
    def is_mutating(name: str) -> bool:
        """只读集合不执行副作用。 Read-only tools have no project side effects."""
        return False

    @staticmethod
    def definitions() -> list[JsonObject]:
        """由参数 schema 构造模型工具定义。 Build model tools from validated argument schemas."""
        definitions: list[JsonObject] = []
        for name, model, description in (
            (
                "list_files",
                ListFilesArgs,
                "List files. Accepts paths relative to the project or absolute paths. "
                "Workspace discovery honors ignores; an explicit subdirectory is listed directly.",
            ),
            (
                "read_file",
                ReadFileArgs,
                "Read UTF-8 lines at an explicit path, even if ignored by discovery. "
                "Accepts paths relative to the project or absolute paths; returns line metadata.",
            ),
            (
                "search",
                SearchArgs,
                "Find literal text in readable source files; no shell or regex.",
            ),
        ):
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": model.model_json_schema(),
                    },
                }
            )
        return definitions

    def _read(self, name: str) -> tuple[str, bytes, str]:
        """读取文本、原始字节与编码；原始字节供编辑保留格式和比较当前内容。

        Read text, original bytes and encoding for format-preserving edits and content comparison.
        """
        path = self.policy.target(name)
        try:
            with path.open("rb") as stream:
                before = os.fstat(stream.fileno())
                chunks: list[bytes] = []
                size = 0
                while chunk := stream.read(min(65536, self.limits.max_file_bytes + 1 - size)):
                    checkpoint(self.stop)
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > self.limits.max_file_bytes:
                        raise AgentError("FILE_TOO_LARGE", "文件超过本次读取预算，可在设置中调整。")
                after = os.fstat(stream.fileno())
            if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                raise AgentError("FILE_CHANGED", "文件在读取期间改变，请重新读取。")
            raw = b"".join(chunks)
            if b"\x00" in raw:
                raise AgentError(
                    "FILE_ENCODING", "该文件是二进制或不支持的编码，M1 读取 UTF-8 源码。"
                )
            text = raw.decode("utf-8-sig")
            encoding = "utf-8-bom" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
            return text, raw, encoding
        except UnicodeError as exc:
            raise AgentError("FILE_ENCODING", "无法按 UTF-8 可靠解码文件。") from exc
        except FileNotFoundError as exc:
            raise AgentError("FILE_NOT_FOUND", "读取时目标已不存在，请调整路径。") from exc
        except OSError as exc:
            raise AgentError("FILE_UNAVAILABLE", "读取文件失败。") from exc

    def _read_file(self, args: ReadFileArgs) -> JsonObject:
        """返回有行号的正文与编码信息，明确结果截断。

        Return numbered content and encoding with explicit truncation.
        """
        from my_agent.storage import utc_now

        target = self.policy.target(args.path)
        text, _, encoding = self._read(args.path)
        if self.policy.target(args.path) != target:
            raise AgentError("FILE_CHANGED", "读取期间目标路径改变，请重新读取。")
        lines = text.splitlines()
        selected: list[str] = []
        size = 0
        for number in range(args.start_line, min(len(lines) + 1, args.start_line + args.lines)):
            checkpoint(self.stop)
            line = f"{number}: {lines[number - 1]}"
            if size + len(line.encode("utf-8")) > self.limits.max_tool_bytes // 2:
                break
            selected.append(line)
            size += len(line.encode("utf-8")) + 1
        return {
            "path": args.path.replace("\\", "/"),
            "content": "\n".join(selected),
            "start_line": args.start_line,
            "end_line": args.start_line + len(selected) - 1 if selected else None,
            "total_lines": len(lines),
            "encoding": encoding,
            "newline": newline_kind(text),
            "read_at": utc_now(),
            "truncated": args.start_line + len(selected) <= len(lines),
        }

    def _rg_candidates(self, files: list[str], query: str) -> tuple[list[str], str]:
        """用固定参数筛选候选；环境无密钥，取消时杀死并回收 rg。

        Prefilter using fixed arguments and a key-free environment; reap rg on cancellation.
        """
        executable = shutil.which("rg")
        if not executable or "\n" in query or "\r" in query:
            return files, "python"
        selected: list[str] = []
        for offset in range(0, len(files), 32):
            checkpoint(self.stop)
            batch = files[offset : offset + 32]
            command = [
                executable,
                "--files-with-matches",
                "--null",
                "--fixed-strings",
                "--text",
                "--no-config",
                "--no-ignore",
                "--hidden",
                "--encoding=utf-8",
                "--max-filesize",
                str(self.limits.max_file_bytes),
                "-e",
                query,
                "--",
                *["./" + file for file in batch],
            ]
            try:
                with subprocess.Popen(
                    command,
                    cwd=self.policy.root,
                    env=probe_environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                ) as process:
                    try:
                        while True:
                            checkpoint(self.stop)
                            try:
                                output, _ = process.communicate(timeout=0.1)
                                break
                            except subprocess.TimeoutExpired:
                                continue
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.communicate()
                if process.returncode not in {0, 1}:
                    raise AgentError("SEARCH_FAILED", "rg 搜索失败，请检查项目可读性。")
                # rg 只输出指定文件名，最多一个批次；内容由同一读取策略重新核验。
                # rg returns at most the supplied batch of names; source is revalidated below.
                found = {
                    item.decode("utf-8").replace("\\", "/").removeprefix("./")
                    for item in output.split(b"\x00")
                    if item
                }
                selected.extend(file for file in batch if file in found)
            except FileNotFoundError:
                return files, "python"
            except (OSError, UnicodeError) as exc:
                raise AgentError("SEARCH_FAILED", "无法运行搜索辅助程序。") from exc
        return selected, "rg"

    def _search(self, args: SearchArgs) -> JsonObject:
        """返回可核对匹配，区分无匹配、跳过与截断。 Return verifiable matches and limitations."""
        if "\n" in args.query or "\r" in args.query:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "搜索查询必须是单行字面文本。")
        scan = self.policy.scan(glob=args.glob)
        candidates, backend = self._rg_candidates(scan.files, args.query)
        matches: list[JsonObject] = []
        size = 0
        for file in candidates:
            try:
                text, _, _ = self._read(file)
            except AgentError as exc:
                if exc.code == "CANCELLED":
                    raise
                scan.skipped += 1
                continue
            for number, line in enumerate(text.splitlines(), 1):
                checkpoint(self.stop)
                if args.query not in line:
                    continue
                match: JsonObject = {"path": file, "line": number, "text": line}
                size += len(encode(match).encode("utf-8"))
                if len(matches) >= args.limit or size > self.limits.max_tool_bytes // 2:
                    scan.truncated = True
                    break
                matches.append(match)
            else:
                continue
            break
        return {
            "matches": list(matches),
            "truncated": scan.truncated,
            "skipped": scan.skipped,
            "backend": backend,
        }

    def _execute(self, call: ToolCall) -> ToolResult:
        """校验完整参数后分发，预期错误作为工具结果回传。 Validate and dispatch complete calls."""
        try:
            checkpoint(self.stop)
            if call.name == "read_file":
                result = self._read_file(ReadFileArgs.model_validate(call.arguments))
            elif call.name == "list_files":
                args = ListFilesArgs.model_validate(call.arguments)
                scan = self.policy.scan(args.directory, args.glob)
                visible = scan.files[: args.limit]
                while (
                    len(encode({"files": list(visible)}).encode("utf-8"))
                    > self.limits.max_tool_bytes // 2
                ):
                    visible.pop()
                result = {
                    "files": list(visible),
                    "truncated": scan.truncated or len(visible) < len(scan.files),
                    "skipped": scan.skipped,
                }
            elif call.name == "search":
                result = self._search(SearchArgs.model_validate(call.arguments))
            else:
                raise AgentError("TOOL_NOT_ALLOWED", "当前工具集合不支持此调用。")
            content = encode(result)
            if len(content.encode("utf-8")) > self.limits.max_tool_bytes:
                raise AgentError("TOOL_OUTPUT_LIMIT", "工具结果超过预算，请缩小范围。")
            return ToolResult(tool_call_id=call.tool_call_id, content=content, is_error=False)
        except ValidationError:
            return ToolResult(
                tool_call_id=call.tool_call_id,
                content=encode(
                    {
                        "code": "INVALID_TOOL_ARGUMENTS",
                        "message": "参数不符合工具 schema。",
                    }
                ),
                is_error=True,
            )
        except AgentError as exc:
            if exc.code == "CANCELLED":
                raise
            return ToolResult(
                tool_call_id=call.tool_call_id,
                content=encode(
                    {
                        "code": exc.code,
                        "message": exc.message,
                    }
                ),
                is_error=True,
            )

    async def execute(self, call: ToolCall) -> ToolResult:
        """文件操作离开事件循环，取消时等待清理。

        Offload file work and await cancellation cleanup.
        """
        task = asyncio.create_task(asyncio.to_thread(self._execute, call))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            self.stop.set()
            try:
                await task
            except AgentError as exc:
                if exc.code != "CANCELLED":
                    raise
            raise
