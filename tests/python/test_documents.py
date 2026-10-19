"""文件工作台的保存、部分成功和选定恢复。

Workbench saves, partial outcomes and selected restores.
"""

import asyncio
import json
import threading
from uuid import uuid4

import pytest

from my_agent.changes.store import ChangeStore
from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.documents.service import DocumentService
from my_agent.documents.types import (
    DocumentChangeParams,
    DocumentOperationParams,
    DocumentParams,
    DocumentSessionParams,
    PatchDocumentsParams,
    SaveDocumentParams,
)
from my_agent.errors import AgentError
from my_agent.models.types import ToolCall
from my_agent.runtime.settings import RunLimits
from my_agent.runtime.tools import ToolContext
from my_agent.storage import Storage
from my_agent.tools.file_types import EditFileArgs
from my_agent.tools.files import FileCoordinator, FileTools
from my_agent.worker import BusinessWorker


@pytest.fixture
def document_stack(tmp_path):
    """临时项目和数据根不影响个人记录。

    Isolate project and data roots from personal records.
    """
    root = tmp_path / "project"
    root.mkdir()
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    worker = BusinessWorker()
    changes = ChangeStore(storage)
    coordinator = FileCoordinator()
    session = str(uuid4())

    async def context(session_id):
        """提供受信会话身份与离线工具环境。

        Supply trusted session identity and offline tools.
        """
        assert session_id == session
        return ToolContext(
            root,
            RunLimits.model_validate(DEFAULTS["run"]),
            threading.Event(),
            "project",
            session,
            str(uuid4()),
            "normal",
            None,
        )

    service = DocumentService(storage, changes, worker, coordinator, context)
    with storage.writer():
        try:
            yield root, changes, service, session, context, coordinator, worker
        finally:
            worker.close()


def test_draft_manual_save_and_agent_conflict(document_stack):
    """草稿恢复、人工保存格式与 Agent 同文件并存。

    Recover drafts and retain formatting alongside Agent edits.
    """
    root, changes, service, session, context, coordinator, worker = document_stack
    original = b"\xef\xbb\xbfvalue = 1\r\n"
    (root / "main.py").write_bytes(original)

    async def scenario():
        """基线冲突保留磁盘和草稿，显式合并后保存。

        Keep both sides on conflict and save after explicit merge.
        """
        params = SaveDocumentParams(
            session_id=session, path="main.py", base_content="value = 1\n", content="value = 2\n"
        )
        await service.draft(params)
        recovered = await service.drafts(DocumentSessionParams(session_id=session))
        assert recovered.drafts[0].content == "value = 2\n"
        assert (root / "main.py").read_bytes() == original
        saved = await service.save(params)
        assert saved.content == "value = 2\r\n"
        assert (root / "main.py").read_bytes() == b"\xef\xbb\xbfvalue = 2\r\n"
        assert changes.load(session, saved.change_id).summary.source == "user"
        dirty = SaveDocumentParams(
            session_id=session, path="main.py", base_content=saved.content, content="value = 3\n"
        )
        await service.draft(dirty)
        tools = FileTools(await context(session), changes, worker, coordinator)
        call_id = str(uuid4())
        result = await tools.execute(
            ToolCall(
                tool_call_id=call_id,
                name="edit_file",
                arguments={"path": "main.py", "old_text": "value = 2", "new_text": "value = 4"},
            )
        )
        assert not result.is_error
        with pytest.raises(AgentError, match="磁盘内容"):
            await service.save(dirty)
        assert (root / "main.py").read_bytes() == b"\xef\xbb\xbfvalue = 4\r\n"
        assert (await service.drafts(DocumentSessionParams(session_id=session))).drafts[
            0
        ].content == dirty.content
        disk = await service.read(DocumentParams(session_id=session, path="main.py"))
        await service.save(
            dirty.model_copy(
                update={"base_content": disk.content, "content": "value = 4\n# human note\n"}
            )
        )
        assert (root / "main.py").read_bytes() == b"\xef\xbb\xbfvalue = 4\r\n# human note\r\n"
        assert not (await service.drafts(DocumentSessionParams(session_id=session))).drafts

    asyncio.run(scenario())


def test_patch_partial_success_and_selected_restore(document_stack, monkeypatch):
    """缺失原文属于局部反馈，后续补丁继续；恢复保留无关后续编辑。

    Continue after correctable patches and preserve later unrelated edits.
    """
    root, changes, service, session, _, _, _ = document_stack
    (root / "a.py").write_bytes(b"value = 1\n")
    (root / "b.py").write_bytes(b"value = 1\n")

    async def scenario():
        """直接验证逐文件真实状态及恢复冲突。

        Verify actual per-file outcomes and restore conflicts.
        """
        result = await service.patch(
            PatchDocumentsParams(
                session_id=session,
                edits=[
                    EditFileArgs(path="a.py", old_text="1", new_text="2"),
                    EditFileArgs(path="missing.py", old_text="1", new_text="2"),
                    EditFileArgs(path="b.py", old_text="1", new_text="3"),
                ],
            )
        )
        assert result.partial and result.unattempted == 0
        assert [item.status for item in result.items] == ["applied", "failed", "applied"]
        assert result.items[1].code == "FILE_NOT_FOUND"
        first = result.items[0].change_id
        (root / "a.py").write_bytes(b"value = 2\n# later work\n")
        selected = DocumentChangeParams(session_id=session, change_id=first)
        diff = await service.diff(selected)
        assert diff.after == "value = 2\n" and diff.current.endswith("# later work\n")
        await service.restore(selected)
        assert (root / "a.py").read_bytes() == b"value = 1\n# later work\n"
        assert (root / "b.py").read_bytes() == b"value = 3\n"
        (root / "b.py").write_bytes(b"value = 5\n")
        with pytest.raises(AgentError):
            await service.restore(
                DocumentChangeParams(session_id=session, change_id=result.items[2].change_id)
            )
        assert (root / "b.py").read_bytes() == b"value = 5\n"
        with pytest.raises(AgentError):
            service.reverse_edit("value = 1\n", "value = 2\n", "value = 3\n#other=2\n")
        assert any(item.source == "restore" for item in changes.list(session, None, 100).changes)

        original_save = changes.save

        def failing_save(record):
            """真实准备记录写入失败后，不继续未尝试文件。

            Stop unattempted files after a real prepared-record save failure.
            """
            if record.summary.path == "b.py" and record.summary.status == "prepared":
                raise AgentError("DATA_WRITE_FAILED", "Injected isolated storage failure")
            return original_save(record)

        monkeypatch.setattr(changes, "save", failing_save)
        (root / "c.py").write_bytes(b"value = 1\n")
        stopped = await service.patch(
            PatchDocumentsParams(
                session_id=session,
                edits=[
                    EditFileArgs(path="a.py", old_text="1", new_text="4"),
                    EditFileArgs(path="b.py", old_text="5", new_text="6"),
                    EditFileArgs(path="c.py", old_text="1", new_text="7"),
                ],
            )
        )
        assert stopped.partial and stopped.unattempted == 1
        assert stopped.items[-1].code == "DATA_WRITE_FAILED"
        assert (root / "b.py").read_bytes() == b"value = 5\n"
        assert (root / "c.py").read_bytes() == b"value = 1\n"

    asyncio.run(scenario())


def test_directory_move_delete_and_creation_restores(document_stack):
    """目录移动、删除与恢复不覆盖之后的内容。

    Directory operations and restores do not overwrite later content.
    """
    root, _, service, session, _, _, _ = document_stack

    async def scenario():
        """新建恢复需要空目录；目录移动恢复检查真实后续改动。

        Restore creations only when empty and detect later changes after moves.
        """
        created = await service.operate(
            DocumentOperationParams(session_id=session, path="folder", operation="create_directory")
        )
        await service.operate(
            DocumentOperationParams(
                session_id=session,
                path="folder/main.py",
                operation="create_file",
                content="initial\n",
            )
        )
        with pytest.raises(AgentError):
            await service.restore(
                DocumentChangeParams(session_id=session, change_id=created.items[0].change_id)
            )
        moved = await service.operate(
            DocumentOperationParams(
                session_id=session, path="folder", destination="renamed", operation="move"
            )
        )
        (root / "renamed/main.py").write_bytes(b"later\n")
        selected = DocumentChangeParams(session_id=session, change_id=moved.items[0].change_id)
        assert not (await service.diff(selected)).restorable
        with pytest.raises(AgentError):
            await service.restore(selected)
        assert not (root / "folder").exists()
        (root / "renamed/main.py").write_bytes(b"initial\n")
        await service.restore(selected)
        assert (root / "folder/main.py").read_bytes() == b"initial\n"
        removed = await service.operate(
            DocumentOperationParams(
                session_id=session, path="folder", operation="delete", recursive=True
            )
        )
        assert all(item.status == "applied" for item in removed.items)
        assert not (root / "folder").exists()
        for item in reversed(removed.items):
            await service.restore(
                DocumentChangeParams(session_id=session, change_id=item.change_id)
            )
        assert (root / "folder/main.py").read_bytes() == b"initial\n"
        assert not (root / ".git").exists()
        binary = b"\x89PNG\x00\xff\r\n"
        (root / "image.bin").write_bytes(binary)
        moved_binary = await service.operate(
            DocumentOperationParams(
                session_id=session, path="image.bin", destination="moved.bin", operation="move"
            )
        )
        selected_binary = DocumentChangeParams(
            session_id=session, change_id=moved_binary.items[0].change_id
        )
        assert (await service.diff(selected_binary)).restorable
        await service.restore(selected_binary)
        assert (root / "image.bin").read_bytes() == binary
        deleted_binary = await service.operate(
            DocumentOperationParams(session_id=session, path="image.bin", operation="delete")
        )
        binary_diff = await service.diff(
            DocumentChangeParams(session_id=session, change_id=deleted_binary.items[0].change_id)
        )
        assert binary_diff.restorable and binary_diff.message
        await service.restore(
            DocumentChangeParams(session_id=session, change_id=deleted_binary.items[0].change_id)
        )
        assert (root / "image.bin").read_bytes() == binary

    asyncio.run(scenario())


def test_new_tool_batch_feedback_no_hash(document_stack):
    """模型批量工具使用原文，失败结果带部分成功事实。

    Model batches use text and expose partial success facts.
    """
    root, changes, _, session, context, coordinator, worker = document_stack
    (root / "main.py").write_bytes(b"value = 1\n")

    async def scenario():
        """执行公开 Agent 工具而不是服务替身。

        Execute actual public Agent tools rather than service mocks.
        """
        tools = FileTools(await context(session), changes, worker, coordinator)
        call_id = str(uuid4())
        result = await tools.execute(
            ToolCall(
                tool_call_id=call_id,
                name="patch_files",
                arguments={
                    "edits": [
                        {"path": "main.py", "old_text": "1", "new_text": "2"},
                        {"path": "missing.py", "old_text": "1", "new_text": "2"},
                    ]
                },
            )
        )
        data = json.loads(result.content)
        assert result.is_error and data["partial"] and data["code"] == "FILE_NOT_FOUND"
        assert (root / "main.py").read_bytes() == b"value = 2\n"
        assert "sha256" not in result.content
        assert changes.list(session, None, 100).changes[0].tool_call_id == call_id
        (root / "nonempty").mkdir()
        (root / "nonempty/file.py").write_bytes(b"preserved")
        feedback = await tools.execute(
            ToolCall(tool_call_id=str(uuid4()), name="delete_file", arguments={"path": "nonempty"})
        )
        assert json.loads(feedback.content)["code"] == "INVALID_TOOL_ARGUMENTS"
        assert (root / "nonempty/file.py").read_bytes() == b"preserved"

    asyncio.run(scenario())
