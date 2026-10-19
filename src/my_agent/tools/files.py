"""原目录文件工具与可核对修改成果。

In-place file tools with auditable change artifacts.
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4
from weakref import WeakValueDictionary

from pydantic import ValidationError

from my_agent.changes.store import ChangeStore
from my_agent.changes.types import ChangeRecord, ChangeSummary
from my_agent.errors import AgentError
from my_agent.models.types import JsonObject, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext
from my_agent.storage import utc_now
from my_agent.tools.arguments import argument_message
from my_agent.tools.file_types import (
    CreateFileArgs as CreateFileArgs,
)
from my_agent.tools.file_types import (
    EditFileArgs as EditFileArgs,
)
from my_agent.tools.file_types import (
    FileOperationArgs as FileOperationArgs,
)
from my_agent.tools.file_types import (
    PatchFilesArgs as PatchFilesArgs,
)
from my_agent.tools.file_types import (
    SaveFileArgs as SaveFileArgs,
)
from my_agent.tools.policy import checkpoint
from my_agent.tools.read_only import ReadTools, encode, newline_kind
from my_agent.worker import BusinessWorker


class FileCoordinator:
    """仅协调本应用同一路径写入，不代表系统沙箱。

    Coordinate app writes, not OS isolation.
    """

    def __init__(self) -> None:
        """锁随使用释放，不永久积累项目路径。

        Release unused path locks automatically.
        """
        self.locks: WeakValueDictionary[Path, asyncio.Lock] = WeakValueDictionary()

    def lock(self, path: Path) -> asyncio.Lock:
        """在同一事件循环中取得真实目标锁。

        Obtain a resolved-target lock on the same event loop.
        """
        lock = self.locks.get(path)
        if lock is None:
            lock = asyncio.Lock()
            self.locks[path] = lock
        return lock


def directory_manifest(target: Path) -> dict[str, str]:
    """记录目录内容以避免恢复时覆盖后续工作；不跟随链接。

    Snapshot directory contents without following aliases.
    """
    manifest: dict[str, str] = {}
    for parent, directories, files in os.walk(target, followlinks=False):
        for name in [*directories, *files]:
            entry = Path(parent) / name
            if entry.resolve() != entry:
                raise AgentError("PATH_DENIED", "目录操作包含链接，请先单独处理链接。")
            relative = entry.relative_to(target).as_posix()
            manifest[relative] = (
                "directory" if entry.is_dir() else hashlib.sha256(entry.read_bytes()).hexdigest()
            )
    return manifest


class FileTools:
    """按模式组合读写，先保存基线再执行短原子写入。

    Compose tools and persist baselines before writes."""

    def __init__(
        self,
        context: ToolContext,
        store: ChangeStore,
        worker: BusinessWorker,
        coordinator: FileCoordinator,
    ) -> None:
        """绑定运行身份与独立存储服务。

        Bind run identity and independent storage services.
        """
        self.context = context
        self.read = ReadTools(context.root, context.limits, context.stop)
        self.store = store
        self.worker = worker
        self.coordinator = coordinator

    @staticmethod
    def is_mutating(name: str) -> bool:
        """明确列出产生项目副作用的工具。

        Identify tools with project side effects.
        """
        return name in {
            "create_file",
            "edit_file",
            "save_file",
            "create_directory",
            "move_file",
            "delete_file",
            "patch_files",
        }

    def definitions(self) -> list[JsonObject]:
        """Plan 仅在用户指定文档时暴露写工具，执行时再次校验。

        Gate write schemas and execution.
        """
        definitions = self.read.definitions()
        if self.context.mode == "plan" and not self.context.plan_document:
            return definitions
        for name, model, description in (
            (
                "create_file",
                CreateFileArgs,
                "Create a new UTF-8 project file; never overwrite. Missing parents are created.",
            ),
            (
                "edit_file",
                EditFileArgs,
                "Replace one unique exact snippet in the current project file. "
                "Provide path, old_text and new_text; no hash or repeated read call is required. "
                "Preserves unrelated edits, UTF-8 BOM and newline style. "
                "Returns feedback without overwriting if the snippet is missing/ambiguous or "
                "the file changes during this write; read current content and adjust the edit.",
            ),
            ("create_directory", FileOperationArgs, "Create a project directory; never overwrite."),
            (
                "move_file",
                FileOperationArgs,
                "Move or rename a project file or directory to destination; never overwrite.",
            ),
            (
                "delete_file",
                FileOperationArgs,
                "Delete a selected project file or directory. "
                "Nonempty directories require recursive=true. Each completed file is recorded.",
            ),
            (
                "patch_files",
                PatchFilesArgs,
                "Apply edits containing path, old_text, new_text. Report partial success per edit. "
                "Never replay completed edits.",
            ),
        ):
            if self.context.mode == "plan" and name not in {"create_file", "edit_file"}:
                continue
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

    def _target(self, args: CreateFileArgs | EditFileArgs | SaveFileArgs) -> Path:
        """先检查模式授权再解析目标，不允许链接别名扩大文档授权。

        Check mode before target access."""
        path = self.read.policy.relative(args.path)
        if self.context.mode == "plan":
            allowed = self.context.plan_document
            if not allowed or path != self.read.policy.relative(allowed):
                raise AgentError("PLAN_READ_ONLY", "Plan 模式仅可写入本次明确允许的计划文档。")
        target = (
            self.read.policy.new_target(args.path)
            if isinstance(args, CreateFileArgs)
            else self.read.policy.target(args.path)
        )
        if not target.is_relative_to(self.read.policy.root):
            raise AgentError("PATH_DENIED", "文件写入目标需要位于当前项目内。")
        if self.context.mode == "plan":
            # 文档授权不跟随链接或 junction，避免批准文档却写进源码。
            # A plan-file grant never follows aliases into another project file.
            if target != self.read.policy.root.joinpath(*path.parts):
                raise AgentError(
                    "PLAN_PATH_ALIAS", "计划文档授权不支持链接目标，请指定真实相对路径。"
                )
        return target

    def _prepare(
        self,
        args: CreateFileArgs | EditFileArgs | SaveFileArgs,
        target: Path,
    ) -> tuple[bytes | None, bytes]:
        """从当前文件捕获写入基线，只替换唯一原文并保留无关修改。

        Capture the current file as the write baseline, preserving unrelated edits.
        """
        if self._target(args) != target:
            raise AgentError("FILE_CHANGED", "文件路径在准备期间改变。")
        before: bytes | None = None
        if isinstance(args, (EditFileArgs, SaveFileArgs)):
            text, before, encoding = self.read._read(args.path)
            old, new = (
                (args.old_text, args.new_text)
                if isinstance(args, EditFileArgs)
                else (args.base_content, args.content)
            )
            newline = {"crlf": "\r\n", "cr": "\r", "lf": "\n"}.get(newline_kind(text))
            if newline:
                old = old.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
                new = new.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
            matches = text.count(old) if isinstance(args, EditFileArgs) else int(text == old)
            if matches == 0:
                raise AgentError("EDIT_NOT_FOUND", "当前文件中未找到待替换原文，请核对当前内容。")
            if matches != 1:
                raise AgentError(
                    "EDIT_NOT_UNIQUE", "原文在当前文件中匹配多处，请提供更具体的片段。"
                )
            updated = text.replace(old, new, 1) if isinstance(args, EditFileArgs) else new
            after = (b"\xef\xbb\xbf" if encoding == "utf-8-bom" else b"") + updated.encode("utf-8")
        else:
            after = args.content.encode("utf-8")
        if len(after) > self.context.limits.max_file_bytes:
            raise AgentError("FILE_TOO_LARGE", "新内容超过本次文件预算，可在设置中调整。")
        if b"\x00" in after:
            raise AgentError("FILE_ENCODING", "文件工具仅支持 UTF-8 文本，不写入二进制内容。")
        return before, after

    def _commit(
        self,
        args: CreateFileArgs | EditFileArgs | SaveFileArgs,
        target: Path,
        before: bytes | None,
        after: bytes,
    ) -> None:
        """保存临时文件，内容变化时交回模型调整；新建不覆盖。

        Save via a temporary file, returning concurrent changes for correction without overwrites.
        """
        temporary: Path | None = None
        try:
            checkpoint(self.context.stop)
            if self._target(args) != target:
                raise AgentError("FILE_CHANGED", "目标路径已改变，未写入。")
            if before is None:
                # 逐层确认并创建父目录，每次都重新验证真实路径。
                # Validate before creating each missing parent to reject changed aliases.
                for parent in reversed(target.parents):
                    if parent == self.read.policy.root or not parent.is_relative_to(
                        self.read.policy.root
                    ):
                        continue
                    if self._target(args) != target:
                        raise AgentError("FILE_CHANGED", "父目录已改变，未写入。")
                    parent.mkdir(exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=".agent-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(after)
                stream.flush()
                os.fsync(stream.fileno())
            checkpoint(self.context.stop)
            if self._target(args) != target:
                raise AgentError("FILE_CHANGED", "目标路径已改变，未写入。")
            if before is not None:
                _, current, _ = self.read._read(args.path)
                if current != before:
                    raise AgentError(
                        "FILE_CHANGED",
                        "文件在准备后发生变化，本次未写入；请读取当前内容后调整编辑。",
                    )
                os.chmod(temporary, target.stat().st_mode)
                os.replace(temporary, target)
            elif os.name == "nt":
                # Windows rename 对已存在目标报错，不能用 replace 创建新文件。
                # Windows rename fails on existing targets; replace would overwrite them.
                os.rename(temporary, target)
            else:
                os.link(temporary, target)
                temporary.unlink()
        except OSError as exc:
            raise AgentError(
                "FILE_WRITE_FAILED", "保存文件失败，请检查目标状态后明确继续。"
            ) from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    logging.getLogger(__name__).warning("FILE_TEMP_CLEANUP_FAILED")

    async def _write(
        self, call: ToolCall, source: Literal["agent", "user", "restore"] = "agent"
    ) -> ToolResult:
        """按真实路径锁定，先持久化意图，结果不确定时保留 prepared。

        Persist intent before effects."""
        args = (
            CreateFileArgs.model_validate(call.arguments)
            if call.name == "create_file"
            else SaveFileArgs.model_validate(call.arguments)
            if call.name == "save_file"
            else EditFileArgs.model_validate(call.arguments)
        )
        target = await asyncio.to_thread(self._target, args)
        async with self.coordinator.lock(target):
            before, after = await asyncio.to_thread(self._prepare, args, target)
            return await self._record_write(call, args, target, before, after, source)

    async def _record_write(
        self,
        call: ToolCall,
        args: CreateFileArgs | EditFileArgs | SaveFileArgs,
        target: Path,
        before: bytes | None,
        after: bytes,
        source: Literal["agent", "user", "restore"],
    ) -> ToolResult:
        """在调用方目标锁下保存共用写入意图和实际结果。

        Persist shared write intent and actual outcome under the caller's target lock.
        """
        record = ChangeRecord(
            summary=ChangeSummary(
                change_id=str(uuid4()),
                session_id=self.context.session_id,
                run_id=self.context.run_id,
                project_id=self.context.project_id,
                tool_call_id=call.tool_call_id,
                path=self.read.policy.relative(args.path).as_posix(),
                operation="create" if before is None else "edit",
                source=source,
                status="prepared",
                created_at=utc_now(),
                before_sha256=hashlib.sha256(before).hexdigest() if before is not None else None,
                after_sha256=hashlib.sha256(after).hexdigest(),
            ),
            before_base64=base64.b64encode(before).decode("ascii") if before is not None else None,
            after_base64=base64.b64encode(after).decode("ascii"),
        )
        await self.worker.call(self.store.save, record)
        failure: AgentError | None = None
        try:
            await asyncio.to_thread(self._commit, args, target, before, after)
            summary = record.summary.model_copy(update={"status": "applied"})
        except AgentError as exc:
            failure = exc
            summary = record.summary.model_copy(update={"status": "failed", "error": exc.code})
        try:
            await self.worker.call(self.store.save, record.model_copy(update={"summary": summary}))
        except AgentError as exc:
            raise AgentError(
                "CHANGE_OUTCOME_UNKNOWN",
                "项目写入结果尚未完成记录，请查看修改成果与磁盘；未自动重放。",
            ) from exc
        if failure:
            raise failure
        return ToolResult(
            tool_call_id=call.tool_call_id,
            is_error=False,
            content=encode(
                {
                    "change_id": summary.change_id,
                    "path": summary.path,
                    "status": "applied",
                    "message": "已保存到原项目；差异可在修改成果中查看。",
                }
            ),
        )

    async def create_snapshot(self, path: str, content: bytes) -> ToolResult:
        """恢复保存的原始字节，仍使用共同记录与原子创建路径。

        Restore recorded bytes through shared records and atomic creation.
        """
        args = CreateFileArgs(path=path, content="")
        target = await asyncio.to_thread(self._target, args)
        async with self.coordinator.lock(target):
            call = ToolCall(
                tool_call_id=str(uuid4()),
                name="create_file",
                arguments={"path": path, "content": ""},
            )
            return await self._record_write(call, args, target, None, content, "restore")

    def _operation_target(self, path: str, *, new: bool = False) -> Path:
        """目录操作也限制真实目标，禁止项目根和链接目录。

        Restrict operation targets and reject root/linked directories.
        """
        if self.context.mode == "plan":
            raise AgentError("PLAN_READ_ONLY", "Plan 模式仅允许精确编辑已授权文档。")
        relative = self.read.policy.relative(path)
        target = self.read.policy.new_target(path) if new else self.read.policy._resolve(relative)
        if target == self.read.policy.root or not target.is_relative_to(self.read.policy.root):
            raise AgentError("PATH_DENIED", "操作目标必须位于项目内且不能是项目根。")
        if not new and not target.exists():
            raise AgentError("FILE_NOT_FOUND", "目标不存在，请调整路径。")
        lexical = self.read.policy.root.joinpath(*relative.parts)
        if target.is_dir() and target != lexical:
            raise AgentError("PATH_DENIED", "目录操作请使用真实路径，不通过链接或 junction 操作。")
        return target

    async def _operation_one(
        self,
        name: str,
        args: FileOperationArgs,
        source: Literal["agent", "user", "restore"] = "agent",
        expected_before: bytes | None = None,
        expected_directory: dict[str, str] | None = None,
        tool_call_id: str | None = None,
    ) -> JsonObject:
        """保存操作基线再修改，失败保留结果记录。

        Persist operation intent before effects and retain failure outcomes."""
        target = await asyncio.to_thread(
            self._operation_target, args.path, new=name == "create_directory"
        )
        destination = (
            await asyncio.to_thread(self._operation_target, args.destination, new=True)
            if name == "move_file" and args.destination
            else None
        )
        if name == "move_file" and destination is None:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "移动操作需要 destination。")
        async with self.coordinator.lock(target):
            directory = target.is_dir() or name == "create_directory"
            if (
                directory
                and name == "delete_file"
                and await asyncio.to_thread(lambda: any(target.iterdir()))
            ):
                raise AgentError(
                    "INVALID_TOOL_ARGUMENTS", "目录非空；删除全部内容需要 recursive=true。"
                )
            if (
                directory
                and name == "move_file"
                and destination
                and destination.is_relative_to(target)
            ):
                raise AgentError("PATH_DENIED", "不能将目录移动到自身内部。")
            before = await asyncio.to_thread(target.read_bytes) if not directory else None
            if expected_before is not None and before != expected_before:
                raise AgentError("FILE_CHANGED", "文件在比较后改变，本次恢复未执行。")
            operation: Literal["create_directory", "move", "delete_directory", "delete"] = (
                "create_directory"
                if name == "create_directory"
                else "move"
                if name == "move_file"
                else "delete_directory"
                if directory
                else "delete"
            )
            manifest = (
                await asyncio.to_thread(directory_manifest, target)
                if directory and name == "move_file"
                else None
            )
            if expected_directory is not None and manifest != expected_directory:
                raise AgentError("FILE_CHANGED", "目录在比较后改变，本次恢复未执行。")
            after = before if name == "move_file" else b""
            record = ChangeRecord(
                summary=ChangeSummary(
                    change_id=str(uuid4()),
                    session_id=self.context.session_id,
                    run_id=self.context.run_id,
                    project_id=self.context.project_id,
                    tool_call_id=tool_call_id or str(uuid4()),
                    path=target.relative_to(self.read.policy.root).as_posix(),
                    operation=operation,
                    destination=destination.relative_to(self.read.policy.root).as_posix()
                    if destination
                    else None,
                    source=source,
                    status="prepared",
                    created_at=utc_now(),
                    before_sha256=hashlib.sha256(before).hexdigest()
                    if before is not None
                    else None,
                    after_sha256=hashlib.sha256(after or b"").hexdigest(),
                ),
                before_base64=base64.b64encode(before).decode("ascii")
                if before is not None
                else None,
                after_base64=base64.b64encode(after or b"").decode("ascii"),
                directory_manifest=manifest,
            )
            await self.worker.call(self.store.save, record)

            def commit() -> None:
                """在副作用前再次核对路径和基线；仅删除空目录。

                Recheck targets and baselines before effects; remove only empty directories."""
                checkpoint(self.context.stop)
                if self._operation_target(args.path, new=name == "create_directory") != target:
                    raise AgentError("FILE_CHANGED", "操作目标已改变。")
                if before is not None and target.read_bytes() != before:
                    raise AgentError("FILE_CHANGED", "文件在操作准备后改变，本次未执行。")
                if manifest is not None and directory_manifest(target) != manifest:
                    raise AgentError("FILE_CHANGED", "目录内容在操作准备后改变，本次未移动。")
                if name == "create_directory":
                    target.mkdir(parents=True, exist_ok=False)
                elif name == "move_file" and destination and args.destination:
                    if self._operation_target(args.destination, new=True) != destination:
                        raise AgentError("FILE_CHANGED", "移动目标已改变。")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if os.name == "nt":
                        os.rename(target, destination)
                    else:
                        # POSIX rename can overwrite; the app lock cannot exclude external writers.
                        # POSIX rename 可覆盖目的地；这里明确再次检查，应用锁不代表系统隔离。
                        if destination.exists():
                            raise AgentError("FILE_EXISTS", "移动目标已存在。")
                        target.rename(destination)
                elif directory:
                    target.rmdir()
                else:
                    target.unlink()

            failure: AgentError | None = None
            try:
                await asyncio.to_thread(commit)
            except OSError as exc:
                failure = AgentError(
                    "FILE_WRITE_FAILED", "文件操作失败；已完成的操作保留，请检查磁盘。"
                )
                failure.__cause__ = exc
            except AgentError as exc:
                failure = exc
            summary = record.summary.model_copy(
                update={
                    "status": "failed" if failure else "applied",
                    "error": failure.code if failure else None,
                }
            )
            try:
                await self.worker.call(
                    self.store.save, record.model_copy(update={"summary": summary})
                )
            except AgentError as exc:
                raise AgentError(
                    "CHANGE_OUTCOME_UNKNOWN", "项目操作结果记录未完成，请查看磁盘，未自动重放。"
                ) from exc
            if failure:
                raise failure
            return {"path": args.path, "change_id": summary.change_id, "status": "applied"}

    async def operate(
        self,
        name: str,
        args: FileOperationArgs,
        source: Literal["agent", "user", "restore"] = "agent",
        tool_call_id: str | None = None,
    ) -> list[JsonObject]:
        """递归删除逐项记录成功，不把目录批次包装成事务。

        Record recursive deletion per item without claiming a transaction."""
        target = await asyncio.to_thread(
            self._operation_target, args.path, new=name == "create_directory"
        )
        items: list[JsonObject] = []
        pending = [args.path]
        if name == "delete_file" and target.is_dir() and args.recursive:

            def children() -> list[str]:
                """不跟随链接遍历已核实目录。

                Enumerate verified directories without following aliases.
                """
                paths: list[str] = []
                for parent, directories, files in os.walk(target, topdown=False, followlinks=False):
                    for entry in [*files, *directories]:
                        child = Path(parent) / entry
                        if child.resolve() != child:
                            raise AgentError("PATH_DENIED", "递归操作包含链接，请先单独处理链接。")
                        paths.append(child.relative_to(self.read.policy.root).as_posix())
                return [*paths, args.path]

            pending = await asyncio.to_thread(children)
        for path in pending:
            try:
                items.append(
                    await self._operation_one(
                        name,
                        args.model_copy(update={"path": path}),
                        source,
                        tool_call_id=tool_call_id,
                    )
                )
            except AgentError as exc:
                if exc.code == "CANCELLED":
                    raise
                items.append(
                    {"path": path, "status": "failed", "code": exc.code, "message": exc.message}
                )
                if exc.code in {
                    "FILE_WRITE_FAILED",
                    "CHANGE_OUTCOME_UNKNOWN",
                    "CHANGE_SAVE_FAILED",
                    "FILE_UNAVAILABLE",
                    "DATA_DIR_NOT_WRITABLE",
                    "DATA_WRITE_FAILED",
                }:
                    break
            except FileNotFoundError:
                items.append(
                    {
                        "path": path,
                        "status": "failed",
                        "code": "FILE_NOT_FOUND",
                        "message": "操作准备时目标已不存在，请调整路径。",
                    }
                )
            except OSError:
                items.append(
                    {
                        "path": path,
                        "status": "failed",
                        "code": "FILE_UNAVAILABLE",
                        "message": "无法读取操作基线；已完成的操作保留。",
                    }
                )
                break
        return items

    @staticmethod
    def _batch_result(call: ToolCall, items: list[JsonObject], unattempted: int = 0) -> ToolResult:
        """真实执行/保存故障优先于可修正反馈，同时保留部分成功。

        Prioritize execution/storage faults over correctable feedback, retaining partial success.
        """
        failures = [item for item in items if item.get("status") == "failed"]
        fatal = {
            "FILE_WRITE_FAILED",
            "CHANGE_OUTCOME_UNKNOWN",
            "CHANGE_SAVE_FAILED",
            "FILE_UNAVAILABLE",
            "DATA_DIR_NOT_WRITABLE",
            "DATA_WRITE_FAILED",
        }
        failure = next(
            (item for item in failures if item.get("code") in fatal),
            failures[0] if failures else None,
        )
        return ToolResult(
            tool_call_id=call.tool_call_id,
            is_error=failure is not None,
            content=encode(
                {
                    "items": list(items),
                    "code": failure.get("code") if failure else None,
                    "message": failure.get("message") if failure else None,
                    "partial": bool(failure)
                    and any(item.get("status") == "applied" for item in items),
                    "unattempted": unattempted,
                }
            ),
        )

    async def _execute(self, call: ToolCall) -> ToolResult:
        """返回实际工具结果，运行循环区分局部反馈和执行故障。

        Return tool results so the loop can distinguish local feedback from execution faults."""
        try:
            if call.name == "patch_files":
                args = PatchFilesArgs.model_validate(call.arguments)
                items: list[JsonObject] = []
                for edit in args.edits:
                    result = await self._execute(
                        ToolCall(
                            tool_call_id=call.tool_call_id,
                            name="edit_file",
                            arguments=edit.model_dump(),
                        )
                    )
                    item = json.loads(result.content)
                    items.append(
                        {
                            "path": edit.path,
                            "status": "failed" if result.is_error else "applied",
                            **item,
                        }
                    )
                    if result.is_error and item.get("code") in {
                        "FILE_WRITE_FAILED",
                        "CHANGE_OUTCOME_UNKNOWN",
                        "CHANGE_SAVE_FAILED",
                        "FILE_UNAVAILABLE",
                        "DATA_DIR_NOT_WRITABLE",
                        "DATA_WRITE_FAILED",
                    }:
                        break
                return self._batch_result(call, items, len(args.edits) - len(items))
            if call.name in {"create_directory", "move_file", "delete_file"}:
                items = await self.operate(
                    call.name,
                    FileOperationArgs.model_validate(call.arguments),
                    tool_call_id=call.tool_call_id,
                )
                return self._batch_result(call, items)
            return await self._write(call)
        except ValidationError as exc:
            code, message = "INVALID_TOOL_ARGUMENTS", argument_message(exc)
        except UnicodeError:
            code, message = "FILE_ENCODING", "无法将内容可靠编码为 UTF-8。"
        except FileNotFoundError:
            code, message = "FILE_NOT_FOUND", "操作准备时目标已不存在，请调整路径。"
        except OSError:
            code, message = "FILE_UNAVAILABLE", "无法读取文件操作基线；项目操作未继续。"
        except AgentError as exc:
            if exc.code == "CANCELLED":
                raise
            code, message = exc.code, exc.message
        return ToolResult(
            tool_call_id=call.tool_call_id,
            is_error=True,
            content=encode({"code": code, "message": message}),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """取消仍等待已开始的文件工作与结果落盘，不留下后台写入。

        Reap owned writes on cancellation."""
        if not self.is_mutating(call.name):
            return await self.read.execute(call)
        task = asyncio.create_task(self._execute(call))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            self.context.stop.set()
            try:
                await task
            except AgentError as exc:
                if exc.code != "CANCELLED":
                    raise
            raise
