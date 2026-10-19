"""文件浏览、人工保存、草稿与选定修改恢复。

File browsing, human saves, drafts and selected restores.
"""

import asyncio
import base64
import difflib
import json
import threading
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from uuid import uuid4

from my_agent.changes.store import ChangeStore
from my_agent.documents.store import DocumentStore
from my_agent.documents.types import (
    DocumentChangeParams,
    DocumentDiff,
    DocumentDraft,
    DocumentListing,
    DocumentListParams,
    DocumentOperationParams,
    DocumentParams,
    DocumentSearchParams,
    DocumentSearchResult,
    DocumentSessionParams,
    DocumentView,
    DraftPage,
    OperationItem,
    OperationResult,
    PatchDocumentsParams,
    SaveDocumentParams,
)
from my_agent.errors import AgentError
from my_agent.models.types import ToolCall
from my_agent.runtime.tools import ToolContext
from my_agent.storage import Storage, utc_now
from my_agent.tools.files import FileCoordinator, FileOperationArgs, FileTools, directory_manifest
from my_agent.tools.read_only import SearchArgs, newline_kind
from my_agent.worker import BusinessWorker


async def owned_file_work[ResultValue](
    work: Awaitable[ResultValue], tools: FileTools
) -> ResultValue:
    """取消时通知自有文件工作并等待记录和清理。

    Signal owned file work and await its records and cleanup on cancellation.
    """
    task = asyncio.ensure_future(work)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        tools.context.stop.set()
        try:
            await task
        except AgentError as exc:
            if exc.code != "CANCELLED":
                raise
        raise


class DocumentService:
    """共用 Agent 文件后端；入口提供已核实项目和身份。

    Reuse Agent file backend with trusted project context.
    """

    def __init__(
        self,
        storage: Storage,
        changes: ChangeStore,
        worker: BusinessWorker,
        coordinator: FileCoordinator,
        resolve_context: Callable[[str], Awaitable[ToolContext]],
    ) -> None:
        """绑定共享协调器和会话解析器，不创建另一套写入器。

        Bind shared coordination and session resolution without another writer."""
        self.store = DocumentStore(storage)
        self.changes = changes
        self.worker = worker
        self.coordinator = coordinator
        self.resolve_context = resolve_context
        self.searches: dict[str, threading.Event] = {}

    async def tools(self, session_id: str) -> FileTools:
        """读取实际会话归属，为人工操作使用共享文件服务。

        Resolve actual ownership and reuse file tools for human actions."""
        return FileTools(
            await self.resolve_context(session_id), self.changes, self.worker, self.coordinator
        )

    async def list(self, params: DocumentListParams) -> DocumentListing:
        """发现遵循项目忽略设置，快速打开按路径过滤。

        Honor discovery ignores and filter quick-open paths.
        """
        tools = await self.tools(params.session_id)

        def listing() -> DocumentListing:
            """从已有发现结果生成文件树及空目录。

            Build a file tree including empty directories from shared discovery."""
            scan = tools.read.policy.scan(params.directory)
            files = [name for name in scan.files if params.query.casefold() in name.casefold()]
            directories: set[str] = set()
            for name in files:
                directories.update(
                    parent.as_posix() for parent in PurePosixPath(name).parents if parent.parts
                )
            root = tools.read.policy.target(params.directory, directory=True)
            # 仅直接子目录补足空目录；递归文件树来自现有有界扫描。
            # Include immediate empty directories; recursive files use bounded shared scanning.
            for child in root.iterdir():
                if child.is_dir() and child.resolve().is_relative_to(tools.read.policy.root):
                    relative = PurePosixPath(child.relative_to(tools.read.policy.root).as_posix())
                    if not tools.read.policy._filtered(child, relative, directory=True):
                        directories.add(relative.as_posix())
            return DocumentListing(
                files=files[: params.limit],
                directories=sorted(directories),
                truncated=scan.truncated or len(files) > params.limit,
                skipped=scan.skipped,
            )

        return await asyncio.to_thread(listing)

    async def read(self, params: DocumentParams) -> DocumentView:
        """读取完整编辑文本，保持换行事实。

        Read complete editor text with its actual newline metadata.
        """
        tools = await self.tools(params.session_id)
        content, _, encoding = await asyncio.to_thread(tools.read._read, params.path)
        return DocumentView(
            path=params.path,
            content=content,
            encoding=encoding,
            newline=newline_kind(content),
            read_at=utc_now(),
        )

    async def search(self, params: DocumentSearchParams) -> DocumentSearchResult:
        """复用共享搜索；同会话新查询停止旧查询，取消时回收进程。

        Share model search; supersede prior session queries and reap processes on cancellation.
        """
        tools = await self.tools(params.session_id)
        previous = self.searches.get(params.session_id)
        if previous is not None:
            previous.set()
        self.searches[params.session_id] = tools.context.stop
        try:
            result = await owned_file_work(
                asyncio.to_thread(
                    tools.read._search,
                    SearchArgs.model_validate(params.model_dump(exclude={"session_id"})),
                ),
                tools,
            )
            return DocumentSearchResult.model_validate(result)
        finally:
            if self.searches.get(params.session_id) is tools.context.stop:
                self.searches.pop(params.session_id)

    async def drafts(self, params: DocumentSessionParams) -> DraftPage:
        """验证会话后读取数据根草稿。

        Validate the session then load data-root drafts.
        """
        await self.resolve_context(params.session_id)
        return await self.worker.call(self.store.load, params.session_id)

    async def draft(self, params: SaveDocumentParams) -> DraftPage:
        """持久化缓冲，不写入项目。

        Persist buffers without writing project files.
        """
        tools = await self.tools(params.session_id)
        path = tools.read.policy.relative(params.path).as_posix()
        return await self.worker.call(
            self.store.save, DocumentDraft(**params.model_dump(exclude={"path"}), path=path)
        )

    async def save(self, params: SaveDocumentParams) -> DocumentView:
        """人工保存经过相同记录/基线/原子写入路径。

        Human saves use the same records, baselines and atomic writes.
        """
        tools = await self.tools(params.session_id)
        call = ToolCall(
            tool_call_id=str(uuid4()),
            name="save_file",
            arguments=params.model_dump(exclude={"session_id"}),
        )
        try:
            result = await owned_file_work(tools._write(call, source="user"), tools)
        except AgentError as exc:
            if exc.code in {"EDIT_NOT_FOUND", "EDIT_NOT_UNIQUE"}:
                raise AgentError(
                    "DOCUMENT_CONFLICT", "磁盘内容已改变，草稿已保留，请比较并合并后保存。"
                ) from exc
            raise
        await self.draft(params.model_copy(update={"base_content": params.content}))
        view = await self.read(DocumentParams(session_id=params.session_id, path=params.path))
        return view.model_copy(update={"change_id": json.loads(result.content)["change_id"]})

    async def operate(self, params: DocumentOperationParams) -> OperationResult:
        """按用户选择操作，报告每个真实文件结果。

        Perform selected operations with truthful per-file outcomes.
        """
        tools = await self.tools(params.session_id)
        if params.operation == "create_file":
            result = await owned_file_work(
                tools._write(
                    ToolCall(
                        tool_call_id=str(uuid4()),
                        name="create_file",
                        arguments={"path": params.path, "content": params.content},
                    ),
                    source="user",
                ),
                tools,
            )
            return OperationResult(
                items=[
                    OperationItem(
                        path=params.path,
                        status="applied",
                        change_id=json.loads(result.content)["change_id"],
                    )
                ],
                partial=False,
            )
        name = {
            "create_directory": "create_directory",
            "move": "move_file",
            "delete": "delete_file",
        }[params.operation]
        items = [
            OperationItem.model_validate(item)
            for item in await owned_file_work(
                tools.operate(
                    name,
                    FileOperationArgs(
                        path=params.path, destination=params.destination, recursive=params.recursive
                    ),
                    source="user",
                ),
                tools,
            )
        ]
        return OperationResult(
            items=items,
            partial=any(item.status == "applied" for item in items)
            and any(item.status == "failed" for item in items),
        )

    async def patch(self, params: PatchDocumentsParams) -> OperationResult:
        """顺序补丁不回滚或重放已成功文件。

        Apply sequential patches without rolling back or replaying successful files."""
        tools = await self.tools(params.session_id)
        items: list[OperationItem] = []
        for edit in params.edits:
            result = await owned_file_work(
                tools._execute(
                    ToolCall(
                        tool_call_id=str(uuid4()), name="edit_file", arguments=edit.model_dump()
                    )
                ),
                tools,
            )
            data = json.loads(result.content)
            items.append(
                OperationItem(
                    path=edit.path,
                    status="failed" if result.is_error else "applied",
                    change_id=data.get("change_id"),
                    code=data.get("code"),
                    message=data.get("message"),
                )
            )
            if data.get("code") in {
                "FILE_WRITE_FAILED",
                "FILE_UNAVAILABLE",
                "CHANGE_OUTCOME_UNKNOWN",
                "CHANGE_SAVE_FAILED",
                "DATA_DIR_NOT_WRITABLE",
                "DATA_WRITE_FAILED",
            }:
                break
        return OperationResult(
            items=items,
            partial=any(item.status == "applied" for item in items)
            and any(item.status == "failed" for item in items),
            unattempted=len(params.edits) - len(items),
        )

    async def diff(self, params: DocumentChangeParams) -> DocumentDiff:
        """读取历史快照和独立当前磁盘内容；历史错误不阻断其他文件。

        Read historical snapshots and independent live disk contents."""
        tools = await self.tools(params.session_id)
        record = await self.worker.call(self.changes.load, params.session_id, params.change_id)
        path = (
            record.summary.destination
            if record.summary.operation == "move"
            else record.summary.path
        )
        if not path:
            raise AgentError("CHANGE_DAMAGED", "移动记录缺少目标路径。")
        target = tools.read.policy.root / tools.read.policy.relative(path)
        exists = await asyncio.to_thread(target.exists)
        directory = await asyncio.to_thread(target.is_dir)
        before_bytes = base64.b64decode(record.before_base64 or "")
        after_bytes = base64.b64decode(record.after_base64)
        current_bytes = b""
        if exists and not directory:
            current_target = await asyncio.to_thread(tools._operation_target, path)
            current_bytes = await asyncio.to_thread(current_target.read_bytes)
        binary = False
        try:
            before, after, current = [
                raw.decode("utf-8-sig") for raw in (before_bytes, after_bytes, current_bytes)
            ]
            if any(b"\x00" in raw for raw in (before_bytes, after_bytes, current_bytes)):
                binary = True
                before = after = current = ""
        except UnicodeError:
            binary = True
            before = after = current = ""
        restorable = record.summary.status == "applied"
        message = "二进制文件不展示文本差异；恢复仍保留实际字节并检查后续改动。" if binary else None
        if record.summary.operation == "move" and directory:
            restorable = (
                restorable
                and record.directory_manifest is not None
                and await asyncio.to_thread(directory_manifest, target) == record.directory_manifest
            )
        elif record.summary.operation in {"create", "move"}:
            restorable = restorable and exists and current_bytes == after_bytes
        elif record.summary.operation in {"delete", "delete_directory"}:
            restorable = restorable and not exists
        elif record.summary.operation == "create_directory":
            restorable = (
                restorable
                and directory
                and not await asyncio.to_thread(lambda: any(target.iterdir()))
            )
        elif record.summary.operation == "edit":
            try:
                self.reverse_edit(before, after, current)
                restorable = restorable and exists and not binary
            except AgentError:
                restorable = False
        if not restorable:
            message = "存在后续修改或记录未完成，请比较后手动合并；没有覆盖当前文件。"
        return DocumentDiff(
            summary=record.summary,
            before=before,
            after=after,
            current=current,
            current_exists=exists,
            restorable=restorable,
            message=message,
        )

    async def restore(self, params: DocumentChangeParams) -> OperationResult:
        """只反转选定修改；重叠后续修改交给比较，不覆盖。

        Reverse only the selected change and refuse overlapping later edits."""
        tools = await self.tools(params.session_id)
        view = await self.diff(params)
        if not view.restorable:
            raise AgentError("DOCUMENT_CONFLICT", view.message or "该修改不可恢复。")
        summary = view.summary
        if summary.operation == "edit":
            merged = self.reverse_edit(view.before, view.after, view.current)
            result = await owned_file_work(
                tools._write(
                    ToolCall(
                        tool_call_id=str(uuid4()),
                        name="save_file",
                        arguments={
                            "path": summary.path,
                            "base_content": view.current,
                            "content": merged,
                        },
                    ),
                    source="restore",
                ),
                tools,
            )
            return OperationResult(
                items=[
                    OperationItem(
                        path=summary.path,
                        status="applied",
                        change_id=json.loads(result.content)["change_id"],
                    )
                ],
                partial=False,
            )
        if summary.operation == "delete":
            record = await self.worker.call(self.changes.load, params.session_id, params.change_id)
            raw = base64.b64decode(record.before_base64 or "")
            result = await owned_file_work(tools.create_snapshot(summary.path, raw), tools)
            return OperationResult(
                items=[
                    OperationItem(
                        path=summary.path,
                        status="applied",
                        change_id=json.loads(result.content)["change_id"],
                    )
                ],
                partial=False,
            )
        name = (
            "create_directory"
            if summary.operation == "delete_directory"
            else "move_file"
            if summary.operation == "move"
            else "delete_file"
        )
        args = FileOperationArgs(
            path=summary.destination or summary.path
            if summary.operation == "move"
            else summary.path,
            destination=summary.path if summary.operation == "move" else None,
        )
        # 当前内容与历史末端一致才允许反转创建/移动；重复读取不向模型增加门槛。
        # Reverse creates/moves only against matching endpoints; no model hash requirement is added.
        target = await asyncio.to_thread(
            tools._operation_target, args.path, new=name == "create_directory"
        )
        record = await self.worker.call(self.changes.load, params.session_id, params.change_id)
        expected_before = (
            base64.b64decode(record.after_base64)
            if summary.operation in {"create", "move"} and not target.is_dir()
            else None
        )
        item = await owned_file_work(
            tools._operation_one(
                name,
                args,
                source="restore",
                expected_before=expected_before,
                expected_directory=record.directory_manifest
                if summary.operation == "move" and target.is_dir()
                else None,
            ),
            tools,
        )
        items = [OperationItem.model_validate(item)]
        return OperationResult(items=items, partial=False)

    @staticmethod
    def reverse_edit(before: str, after: str, current: str) -> str:
        """比较选定修改与后续修改区间，保留不重叠的内容。

        Compare selected and later edit ranges while retaining disjoint changes."""
        if current == after:
            return before
        selected = [
            op
            for op in difflib.SequenceMatcher(a=after, b=before, autojunk=False).get_opcodes()
            if op[0] != "equal"
        ]
        later = [
            op
            for op in difflib.SequenceMatcher(a=after, b=current, autojunk=False).get_opcodes()
            if op[0] != "equal"
        ]
        edits: list[tuple[int, int, str]] = []
        for _, start, end, restored_start, restored_end in selected:
            shift = 0
            for _, changed_start, changed_end, current_start, current_end in later:
                overlap = max(start, changed_start) < min(end, changed_end)
                if start == end:
                    overlap = overlap or changed_start <= start < changed_end
                if changed_start == changed_end:
                    overlap = overlap or start < changed_start < end
                if start == end == changed_start == changed_end:
                    overlap = True
                if overlap:
                    raise AgentError("DOCUMENT_CONFLICT", "选定修改与后续内容重叠，请比较后合并。")
                if changed_end <= start:
                    shift += (current_end - current_start) - (changed_end - changed_start)
            first, last = start + shift, end + shift
            if current[first:last] != after[start:end]:
                raise AgentError("DOCUMENT_CONFLICT", "恢复片段无法可靠定位，请比较后合并。")
            # 匹配算法可能把重复片段对齐到另一行；核对同一行上下文防止恢复错位置。
            # Matching can align repeated tokens to another line; verify local line context.
            context_start = max(after.rfind("\n", 0, start) + 1, start - 80)
            newline = after.find("\n", end)
            context_end = min(len(after) if newline < 0 else newline, end + 80)
            left, right = after[context_start:start], after[end:context_end]
            if (left and current[max(0, first - len(left)) : first] != left) or (
                right and current[last : last + len(right)] != right
            ):
                raise AgentError("DOCUMENT_CONFLICT", "修改片段的行上下文已改变，请比较后合并。")
            edits.append((first, last, before[restored_start:restored_end]))
        # 从后到前反转坐标，已接受的无关后续改动不变。
        # Reverse coordinates from the end, preserving accepted unrelated later edits.
        for first, last, restored in reversed(edits):
            current = current[:first] + restored + current[last:]
        return current
