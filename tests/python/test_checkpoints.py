"""M6 回退的有效历史、实际字节与未知来源检查。

M6 checks for rewind history, bytes and provenance.
"""

import asyncio
import json
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from my_agent.checkpoints.service import RollbackService
from my_agent.checkpoints.types import PreviewCheckpointParams, RestoreCheckpointParams
from my_agent.memory.store import MemoryStore
from my_agent.memory.types import MemoryFields, MemorySettings
from tests.python.test_collaboration import pair
from tests.python.test_context_memory import KnowledgeModel, run
from tests.python.test_goal_controller import app_at, call, create_session, turn
from tests.python.test_work_graph import WorkModel


def test_restore_preserves_later_edits_history_memory_and_undo(tmp_path):
    """真实工具改文件后回退，保留外部不重叠编辑及用户记忆，旧分支不再进入请求。

    Restore real tool effects, preserve disjoint edits/user memory, and exclude abandoned messages.
    """

    class Model(KnowledgeModel):
        """只发一次编辑，再给出可辨认的旧分支回答。 Edit once and emit a recognizable old answer."""

        async def complete(self, **kwargs):
            """确定性调用用于覆盖实际请求与文件链路。

            Deterministic calls cover real assembly and files.
            """
            self.requests.append(kwargs)
            if len(self.requests) == 1:
                return turn(call("edit_file", path="main.txt", old_text="old", new_text="new"))
            return turn(text="ABANDONED_ANSWER")

    async def scenario():
        """使用生产快照和恢复服务，检查原始日志仍可读。

        Exercise production snapshots with retained raw logs.
        """
        model = Model()
        async with app_at(tmp_path / "data", model) as app:
            root = tmp_path / "project"
            created = await create_session(app, root)
            sid, pid = created.session.session_id, created.session.project_id
            (root / "main.txt").write_bytes(b"old\r\nuntouched\r\n")
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            assert (await run(app, sid, "CHANGE_REQUEST")).run.status == "completed"
            points = await app.dispatch("checkpoints.list", {"session_id": sid})
            assert len(points.checkpoints) == 1
            point = points.checkpoints[0]
            assert point.changed_files == 1
            (root / "main.txt").write_bytes(b"new\r\nuntouched\r\nexternal\r\n")
            memory = app.sessions.memory.store
            derived = await app.worker.call(
                memory.save,
                pid,
                MemoryFields(title="derived", content="new code"),
                source="maintenance",
                session_id=sid,
                source_seq=point.before_seq,
            )
            user = await app.worker.call(
                memory.save,
                pid,
                MemoryFields(title="preference", content="keep"),
                source="user",
                session_id=sid,
                source_seq=point.before_seq,
            )
            shared = await app.worker.call(
                memory.save,
                pid,
                MemoryFields(title="shared", content="supported", source_ids=[user.memory_id]),
                source="maintenance",
                session_id=sid,
                source_seq=point.before_seq,
            )
            original_entry = memory.path(derived.memory_id).read_bytes()
            service = RollbackService(app.sessions)
            preview = await service.preview(
                PreviewCheckpointParams(session_id=sid, checkpoint_id=point.checkpoint_id)
            )
            assert preview.files[0].status == "ready" and preview.files[0].source == "agent"
            request = RestoreCheckpointParams(
                session_id=sid,
                checkpoint_id=point.checkpoint_id,
                operation_id=str(uuid4()),
                mode="conversation",
            )
            with patch.object(memory, "_entries", side_effect=AssertionError("whole-library scan")):
                restored = await service.restore(request)
            assert restored.rewound and restored.prompt == "CHANGE_REQUEST"
            assert (root / "main.txt").read_bytes() == b"old\r\nuntouched\r\nexternal\r\n"
            log = await app.worker.call(app.sessions.store.load, sid)
            assert "ABANDONED_ANSWER" in str(log.facts)
            assert "ABANDONED_ANSWER" not in str(log.context())
            entries, _ = memory._entries()
            assert next(e for e in entries if e.memory_id == derived.memory_id).stale
            assert not next(e for e in entries if e.memory_id == user.memory_id).stale
            assert not next(e for e in entries if e.memory_id == shared.memory_id).stale
            assert memory.path(derived.memory_id).read_bytes() == original_entry
            reopened = MemoryStore(memory.storage)
            assert reopened.read(derived.memory_id, pid).stale
            corrected = await app.worker.call(
                memory.save,
                pid,
                MemoryFields(title="corrected", content="user verified"),
                identity=derived.memory_id,
                source="user",
            )
            assert not reopened.read(corrected.memory_id, pid).stale
            assert await service.restore(request) == restored
            undo = await service.restore(
                RestoreCheckpointParams(
                    session_id=sid,
                    checkpoint_id=restored.undo_checkpoint_id,
                    operation_id=str(uuid4()),
                )
            )
            assert not undo.rewound and undo.files[0].status == "restored"
            assert (root / "main.txt").read_bytes() == b"new\r\nuntouched\r\nexternal\r\n"

    asyncio.run(scenario())


def test_peer_changes_are_preserved_and_model_can_restore_disjoint_code(tmp_path):
    """模型调用回退工具保留同项目另一会话的修改，重叠项返回冲突。

    Model restore preserves peer edits and reports overlapping changes per file.
    """

    async def scenario():
        """真实两会话文件工具和模型恢复入口共用同一实现。

        Exercise two real session tool chains and the model restoration entry.
        """
        model = WorkModel()
        async with app_at(tmp_path / "data", model) as app:
            root = tmp_path / "project"
            source, peer = await pair(app, root)
            await app.sessions.memory.configure(source, MemorySettings(automatic=False))
            for name in ("a.txt", "b.txt"):
                (root / name).write_bytes(b"old\nend\n")
            model.steps = [
                turn(
                    *(
                        call("edit_file", path=name, old_text="old", new_text="new")
                        for name in ("a.txt", "b.txt")
                    )
                ),
                turn(text="edited"),
            ]
            assert (await run(app, source, "edit")).run.status == "completed"
            page = await app.dispatch("checkpoints.list", {"session_id": source})
            identity = page.checkpoints[0].checkpoint_id
            model.steps = [
                turn(
                    call("edit_file", path="a.txt", old_text="end", new_text="peer"),
                    call("edit_file", path="b.txt", old_text="new", new_text="peer"),
                ),
                turn(text="peer edited"),
            ]
            assert (await run(app, peer, "peer edit")).run.status == "completed"
            model.steps = [
                turn(
                    call(
                        "discover_tools",
                        names=["list_checkpoints", "preview_restore", "restore_checkpoint"],
                    )
                ),
                turn(call("preview_restore", checkpoint_id=identity)),
                turn(call("restore_checkpoint", checkpoint_id=identity)),
                turn(text="restored nonconflicting file"),
            ]
            result = await run(app, source, "Restore my earlier edit, keep peer changes")
            assert result.run.status == "completed"
            assert (root / "a.txt").read_bytes() == b"old\npeer\n"
            assert (root / "b.txt").read_bytes() == b"peer\nend\n"
            output = json.loads(
                next(
                    message["content"]
                    for message in reversed(model.requests[-1]["messages"])
                    if message["role"] == "tool"
                )
            )
            assert {item["path"]: item["status"] for item in output["files"]} == {
                "a.txt": "restored",
                "b.txt": "conflict",
            }
            assert not output["rewound"]

    asyncio.run(scenario())


def test_observed_binary_creation_is_explicit_and_restorable(tmp_path):
    """快照捕获模型调用期间的非文件工具写入，预览明确作者未知，回退不要求 Git。

    Capture non-tool writes during a request with honest provenance and Git-independent rollback.
    """

    class Model(KnowledgeModel):
        """模拟命令写入原始二进制。 Simulate command-produced raw binary bytes."""

        async def complete(self, **kwargs):
            """仅产生一次受控项目文件。 Produce one controlled project file."""
            if kwargs["messages"][-1]["role"] != "tool":
                return turn(call("create_file", path="mixed.txt", content="tool wrote this\n"))
            (tmp_path / "project/data.bin").write_bytes(b"\x00\xff\x81")
            (tmp_path / "project/mixed.txt").write_bytes(b"tool wrote this\nexternal addition\n")
            return turn(text="done")

    async def scenario():
        """先核实默认保留，再明确恢复观察到的文件。

        Verify default preservation then explicit restoration.
        """
        async with app_at(tmp_path / "data", Model()) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            await run(app, sid, "generate")
            points = await app.dispatch("checkpoints.list", {"session_id": sid})
            service = RollbackService(app.sessions)
            args = {"session_id": sid, "checkpoint_id": points.checkpoints[0].checkpoint_id}
            preview = await service.preview(PreviewCheckpointParams(**args))
            assert len(preview.files) == 2
            assert all(item.source == "observed" for item in preview.files)
            kept = await service.restore(RestoreCheckpointParams(**args, operation_id=str(uuid4())))
            assert all(item.status == "skipped" for item in kept.files)
            result = await service.restore(
                RestoreCheckpointParams(**args, operation_id=str(uuid4()), include_observed=True)
            )
            assert all(item.status == "restored" for item in result.files)
            assert not (tmp_path / "project/data.bin").exists()
            assert not (tmp_path / "project/mixed.txt").exists()
            assert not (tmp_path / "project/.git").exists()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "scope",
    [
        "file",
        "directory",
        "legacy",
        pytest.param("directory_case", marks=pytest.mark.skipif(os.name != "nt", reason="Windows")),
    ],
)
def test_unignored_existing_files_are_not_deleted_by_restore(tmp_path, scope):
    """真实恢复保留起点忽略的文件，同时仍能删除已知范围内新建文件。

    Real restoration preserves ignored baseline files while undoing covered new files.
    """

    async def scenario():
        """覆盖单文件、忽略目录和旧快照，未知覆盖只影响相关恢复文件。

        Cover excluded files/directories and legacy snapshots without blocking other restores.
        """

        class Model(WorkModel):
            """模拟请求内的 Windows 目录大小写改名。 Simulate an in-request Windows case rename."""

            async def complete(self, **kwargs):
                """保留目录大小写改名中的内容。 Preserve contents during case rename."""
                result = await super().complete(**kwargs)
                if scope == "directory_case" and not result.tool_calls:
                    (tmp_path / "project/hidden").rename(tmp_path / "project/Hidden")
                return result

        model = Model()
        async with app_at(tmp_path / "data", model) as app:
            root = tmp_path / "project"
            created = await create_session(app, root)
            sid = created.session.session_id
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            path = "hidden/existing.txt" if scope.startswith("directory") else "existing.txt"
            ignored = "hidden/" if scope.startswith("directory") else path
            original = root / path
            original.parent.mkdir(exist_ok=True)
            original.write_bytes(b"pre-existing user content\r\n")
            (root / ".gitignore").write_text(ignored + "\n", encoding="utf-8")
            model.steps = [
                turn(
                    call("edit_file", path=".gitignore", old_text=ignored, new_text="# visible"),
                    call("create_file", path="created.txt", content="new file"),
                ),
                turn(text="done"),
            ]
            assert (await run(app, sid, "unignore and create")).run.status == "completed"
            if scope == "directory_case":
                path = "Hidden/existing.txt"
            service = RollbackService(app.sessions)
            points = await app.dispatch("checkpoints.list", {"session_id": sid})
            point = points.checkpoints[0]
            if scope == "legacy":
                # 模拟修复前快照的缺字段格式，不重写任何个人记录。
                # Simulate the earlier stored format without touching personal records.
                stored = service.store.path(sid, point.checkpoint_id)
                data = json.loads(stored.read_text(encoding="utf-8"))
                data["before"].pop("excluded_paths")
                data["before"]["omitted"] = []
                data["summary"].update(status="ready", issues=[])
                stored.write_text(json.dumps(data), encoding="utf-8")
            args = {"session_id": sid, "checkpoint_id": point.checkpoint_id}
            preview = await service.preview(PreviewCheckpointParams(**args))
            assert path not in {item.path for item in preview.files}
            assert path in preview.issues
            restored = await service.restore(
                RestoreCheckpointParams(**args, operation_id=str(uuid4()), include_observed=True)
            )
            assert all(item.status == "restored" for item in restored.files)
            assert original.read_bytes() == b"pre-existing user content\r\n"
            assert (root / ".gitignore").read_text(encoding="utf-8") == ignored + "\n"
            assert (root / "created.txt").exists() is (scope == "legacy")

    asyncio.run(scenario())
