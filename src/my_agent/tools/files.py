"""原目录文件工具与可核对修改成果。 In-place file tools with auditable change artifacts."""

import asyncio
import base64
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import uuid4
from weakref import WeakValueDictionary

from pydantic import Field, ValidationError
from pydantic.json_schema import SkipJsonSchema

from my_agent.changes.store import ChangeStore
from my_agent.changes.types import ChangeRecord, ChangeSummary
from my_agent.errors import AgentError
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext
from my_agent.storage import utc_now
from my_agent.tools.policy import checkpoint
from my_agent.tools.read_only import ReadTools, encode, newline_kind
from my_agent.worker import BusinessWorker


class CreateFileArgs(ModelData):
    """只创建不存在的文件，内容采用 UTF-8。 Create an absent file with UTF-8 content."""

    path: Annotated[str, Field(min_length=1, max_length=4096)]
    content: str


class EditFileArgs(ModelData):
    """只要求路径与替换内容；文件变化作为可修正的工具反馈。

    Require a path and replacement text; file changes are correctable tool feedback.
    """

    path: Annotated[str, Field(min_length=1, max_length=4096)]
    old_text: Annotated[str, Field(min_length=1)]
    new_text: str
    # 兼容旧模型调用中的字段，不向新 schema 暴露，也不再用它阻断编辑。
    # Accept legacy calls without exposing this field in new schemas or gating edits on it.
    expected_sha256: SkipJsonSchema[str | None] = None


class FileCoordinator:
    """仅协调本应用同一路径写入，不代表系统沙箱。 Coordinate app writes, not OS isolation."""

    def __init__(self) -> None:
        """锁随使用释放，不永久积累项目路径。 Release unused path locks automatically."""
        self.locks: WeakValueDictionary[Path, asyncio.Lock] = WeakValueDictionary()

    def lock(self, path: Path) -> asyncio.Lock:
        """在同一事件循环中取得真实目标锁。 Obtain a resolved-target lock on the same event loop."""
        lock = self.locks.get(path)
        if lock is None:
            lock = asyncio.Lock()
            self.locks[path] = lock
        return lock


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
        """绑定运行身份与独立存储服务。 Bind run identity and independent storage services."""
        self.context = context
        self.read = ReadTools(context.root, context.limits, context.stop)
        self.store = store
        self.worker = worker
        self.coordinator = coordinator

    @staticmethod
    def is_mutating(name: str) -> bool:
        """明确列出产生项目副作用的工具。 Identify tools with project side effects."""
        return name in {"create_file", "edit_file"}

    def definitions(self) -> list[JsonObject]:
        """Plan 仅在用户指定文档时暴露写工具，执行时再次校验。 Gate write schemas and execution."""
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

    def _target(self, args: CreateFileArgs | EditFileArgs) -> Path:
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
        args: CreateFileArgs | EditFileArgs,
        target: Path,
    ) -> tuple[bytes | None, bytes]:
        """从当前文件捕获写入基线，只替换唯一原文并保留无关修改。

        Capture the current file as the write baseline, preserving unrelated edits.
        """
        if self._target(args) != target:
            raise AgentError("FILE_CHANGED", "文件路径在准备期间改变。")
        before: bytes | None = None
        if isinstance(args, EditFileArgs):
            text, before, encoding = self.read._read(args.path)
            old, new = args.old_text, args.new_text
            newline = {"crlf": "\r\n", "cr": "\r", "lf": "\n"}.get(newline_kind(text))
            if newline:
                old = old.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
                new = new.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
            matches = text.count(old)
            if matches == 0:
                raise AgentError("EDIT_NOT_FOUND", "当前文件中未找到待替换原文，请核对当前内容。")
            if matches != 1:
                raise AgentError(
                    "EDIT_NOT_UNIQUE", "原文在当前文件中匹配多处，请提供更具体的片段。"
                )
            after = (b"\xef\xbb\xbf" if encoding == "utf-8-bom" else b"") + text.replace(
                old, new, 1
            ).encode("utf-8")
        else:
            after = args.content.encode("utf-8")
        if len(after) > self.context.limits.max_file_bytes:
            raise AgentError("FILE_TOO_LARGE", "新内容超过本次文件预算，可在设置中调整。")
        if b"\x00" in after:
            raise AgentError("FILE_ENCODING", "文件工具仅支持 UTF-8 文本，不写入二进制内容。")
        return before, after

    def _commit(
        self,
        args: CreateFileArgs | EditFileArgs,
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

    async def _write(self, call: ToolCall) -> ToolResult:
        """按真实路径锁定，先持久化意图，结果不确定时保留 prepared。

        Persist intent before effects."""
        args = (
            CreateFileArgs.model_validate(call.arguments)
            if call.name == "create_file"
            else EditFileArgs.model_validate(call.arguments)
        )
        target = await asyncio.to_thread(self._target, args)
        async with self.coordinator.lock(target):
            before, after = await asyncio.to_thread(self._prepare, args, target)
            record = ChangeRecord(
                summary=ChangeSummary(
                    change_id=str(uuid4()),
                    session_id=self.context.session_id,
                    run_id=self.context.run_id,
                    project_id=self.context.project_id,
                    tool_call_id=call.tool_call_id,
                    path=self.read.policy.relative(args.path).as_posix(),
                    operation="create" if before is None else "edit",
                    status="prepared",
                    created_at=utc_now(),
                    before_sha256=hashlib.sha256(before).hexdigest()
                    if before is not None
                    else None,
                    after_sha256=hashlib.sha256(after).hexdigest(),
                ),
                before_base64=base64.b64encode(before).decode("ascii")
                if before is not None
                else None,
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
                await self.worker.call(
                    self.store.save, record.model_copy(update={"summary": summary})
                )
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

    async def _execute(self, call: ToolCall) -> ToolResult:
        """返回实际工具结果，运行循环区分局部反馈和执行故障。

        Return tool results so the loop can distinguish local feedback from execution faults."""
        try:
            return await self._write(call)
        except ValidationError:
            code, message = "INVALID_TOOL_ARGUMENTS", "参数不符合文件工具 schema。"
        except UnicodeError:
            code, message = "FILE_ENCODING", "无法将内容可靠编码为 UTF-8。"
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
