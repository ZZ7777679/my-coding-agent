"""M2 文件权限、原内容保护和修改成果检查。 Focused file-safety and artifact checks."""

import asyncio
import hashlib
import json
import os
import threading
from uuid import uuid4

import pytest

from my_agent.changes.store import ChangeStore
from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.errors import AgentError
from my_agent.models.types import ToolCall
from my_agent.runtime.settings import RunLimits
from my_agent.runtime.tools import ToolContext
from my_agent.storage import Storage
from my_agent.tools.files import FileCoordinator, FileTools
from my_agent.worker import BusinessWorker


@pytest.fixture
def file_stack(tmp_path):
    """隔离项目、数据根和业务线程。 Isolate files, app storage and worker."""
    root = tmp_path / "project"
    root.mkdir()
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    worker = BusinessWorker()
    store = ChangeStore(storage)
    coordinator = FileCoordinator()
    session = str(uuid4())

    def make(mode="normal", document=None):
        """为独立运行创建实际文件工具。 Create real file tools for an independent run."""
        return FileTools(
            ToolContext(
                root,
                RunLimits.model_validate(DEFAULTS["run"]),
                threading.Event(),
                "project",
                session,
                str(uuid4()),
                mode,
                document,
            ),
            store,
            worker,
            coordinator,
        )

    with storage.writer():
        try:
            yield root, store, make, session
        finally:
            worker.close()


async def call(tools, name, **arguments):
    """执行实际工具，不经模型网络。 Execute real tools with offline input."""
    result = await tools.execute(
        ToolCall(tool_call_id=str(uuid4()), name=name, arguments=arguments)
    )
    return result, json.loads(result.content)


@pytest.mark.parametrize("limit", ["50", "400", "300", "120"])
def test_read_argument_feedback_names_correct_field(file_stack, limit):
    """复现真实错误字段，具体反馈后同一工具可正确读取。

    Reproduce the saved field mistakes, then read correctly using the same tool instance.
    """
    root, _, make, _ = file_stack
    (root / "main.py").write_text("print(1)\n", encoding="utf-8")

    async def scenario():
        """反馈不泄露输入值，正确参数保持原行为。

        Feedback omits input values while correct arguments retain normal behavior.
        """
        tools = make()
        result, data = await call(tools, "read_file", path="main.py", limit=limit)
        assert result.is_error and data["code"] == "INVALID_TOOL_ARGUMENTS"
        assert "limit: Extra inputs" in data["message"] and '"lines":50' in data["message"]
        result, data = await call(tools, "read_file", path="main.py", lines=1)
        assert not result.is_error and data["content"] == "1: print(1)"
        _, error = await call(tools, "edit_file", path="main.py", new_text="input-sentinel")
        assert "old_text: Field required" in error["message"]
        assert "input-sentinel" not in error["message"]

    asyncio.run(scenario())


def test_create_edit_preserve_and_reopen(file_stack):
    """从空目录创建，保留 BOM / CRLF 并恢复差异。 Create, preserve BOM/CRLF and reopen diffs."""
    root, store, make, session = file_stack

    async def scenario():
        """核对创建、读取、替换和持久化。 Verify creation, reading, replacement and persistence."""
        tools = make()
        result, data = await call(tools, "create_file", path="src/main.py", content="print(1)\n")
        assert not result.is_error and (root / "src/main.py").read_bytes() == b"print(1)\n"
        assert not (root / ".git").exists()
        created = data["change_id"]
        before = b"\xef\xbb\xbfprint(1)\r\n"
        (root / "src/main.py").write_bytes(before)
        _, baseline = await call(tools, "read_file", path="src/main.py")
        assert "sha256" not in baseline
        result, edit = await call(
            tools,
            "edit_file",
            path="src/main.py",
            old_text="print(1)\n",
            new_text="print(2)\n",
        )
        assert not result.is_error
        assert (root / "src/main.py").read_bytes() == b"\xef\xbb\xbfprint(2)\r\n"
        reopened = ChangeStore(store.storage)
        diff = reopened.view(session, edit["change_id"], 0)
        assert "-print(1)" in diff.diff and "+print(2)" in diff.diff
        assert diff.summary.before_sha256 == hashlib.sha256(before).hexdigest()
        # 旧摘要与快照不一致也不拦截历史差异；实际 diff 直接来自保存的正文。
        # Stale digests do not block historical diffs, which come from the saved content.
        saved = reopened.load(session, edit["change_id"])
        reopened.save(
            saved.model_copy(
                update={"summary": saved.summary.model_copy(update={"after_sha256": "legacy"})}
            )
        )
        assert reopened.view(session, edit["change_id"], 0).diff == diff.diff
        assert reopened.load(session, created).summary.operation == "create"
        assert len(reopened.list(session, None, 20).changes) == 2
        # 与随机 UUID 文件名反向安排时间，验证跨页仍按实际记录时间排列。
        # Reverse UUID order with timestamps so pagination proves chronological ordering.
        edited = edit["change_id"]
        chronology = [created, edited] if created > edited else [edited, created]
        for index, change_id in enumerate(chronology):
            saved = reopened.load(session, change_id)
            reopened.save(
                saved.model_copy(
                    update={
                        "summary": saved.summary.model_copy(
                            update={"created_at": f"2026-09-23T00:00:0{index}+00:00"}
                        )
                    }
                )
            )
        first = reopened.list(session, None, 1)
        second = reopened.list(session, first.next_cursor, 1)
        assert [first.changes[0].change_id, second.changes[0].change_id] == chronology
        assert second.next_cursor is None
        with pytest.raises(AgentError):
            reopened.view(str(uuid4()), created, 0)

    asyncio.run(scenario())


@pytest.mark.parametrize("origin", ["read", "create"])
def test_successive_edits_need_no_model_hash(file_stack, origin):
    """连续编辑无需模型传 hash，无关改动保留，目标原文冲突仍拒绝。

    Edit without model-supplied hashes, preserving unrelated edits and rejecting snippet conflicts.
    """
    root, store, make, session = file_stack

    async def scenario():
        """校验新 schema、连续替换、旧参数兼容与真正冲突，不额外读取。

        Check the schema, successive edits, legacy arguments and conflicts without rereads.
        """
        tools = make()
        edit_schema = next(
            definition["function"]["parameters"]
            for definition in tools.definitions()
            if definition["function"]["name"] == "edit_file"
        )
        assert set(edit_schema["properties"]) == {"path", "old_text", "new_text"}
        assert set(edit_schema["required"]) == {"path", "old_text", "new_text"}
        source = root / "main.py"
        if origin == "read":
            source.write_bytes(b"\xef\xbb\xbfprint(1)\r\n")
            _, version = await call(tools, "read_file", path="main.py")
        else:
            _, version = await call(tools, "create_file", path="main.py", content="print(1)\n")
        assert "sha256" not in version
        initial_changes = len(store.list(session, None, 20).changes)
        for old, new in (("1", "2"), ("2", "3")):
            result, version = await call(
                tools,
                "edit_file",
                path="main.py",
                old_text=f"print({old})\n",
                new_text=f"print({new})\n",
            )
            assert not result.is_error, version
            expected = (
                b"\xef\xbb\xbfprint(" + new.encode() + b")\r\n"
                if origin == "read"
                else f"print({new})\n".encode()
            )
            assert source.read_bytes() == expected
            assert "sha256" not in version
        assert len(store.list(session, None, 20).changes) == initial_changes + 2
        newline = b"\r\n" if origin == "read" else b"\n"
        source.write_bytes(source.read_bytes() + b"# unrelated edit" + newline)
        result, version = await call(
            tools,
            "edit_file",
            path="main.py",
            expected_sha256="legacy value is no longer an editing requirement",
            old_text="print(3)\n",
            new_text="print(4)\n",
        )
        assert not result.is_error, version
        assert source.read_bytes().endswith(b"print(4)" + newline + b"# unrelated edit" + newline)
        _, matches = await call(tools, "search", query="print(4)")
        assert matches["matches"] and all("sha256" not in match for match in matches["matches"])
        source.write_bytes(b"print(9)\n")
        result, error = await call(
            tools,
            "edit_file",
            path="main.py",
            old_text="print(4)\n",
            new_text="print(5)\n",
        )
        assert result.is_error and error["code"] == "EDIT_NOT_FOUND"
        assert source.read_bytes() == b"print(9)\n"
        assert len(store.list(session, None, 20).changes) == initial_changes + 3

    asyncio.run(scenario())


def test_plan_and_file_conflicts_preserve_original(file_stack):
    """权限、已有目标、缺失和不唯一原文均不覆盖。 Reject denied or conflicting writes."""
    root, store, make, session = file_stack

    async def scenario():
        """失败后核对磁盘原文。 Verify disk contents after denied calls."""
        plan = make("plan")
        assert {item["function"]["name"] for item in plan.definitions()} == {
            "list_files",
            "read_file",
            "search",
        }
        result, error = await call(plan, "create_file", path="main.py", content="no")
        assert (
            result.is_error
            and error["code"] == "PLAN_READ_ONLY"
            and not (root / "main.py").exists()
        )
        plan = make("plan", "docs/plan.md")
        assert not (await call(plan, "create_file", path="docs/plan.md", content="# Plan\n"))[
            0
        ].is_error
        assert (await call(plan, "create_file", path="docs/code.py", content="no"))[0].is_error
        tools = make()
        source = root / "main.py"
        source.write_bytes(b"same\nsame\n")
        args = dict(path="main.py", old_text="same", new_text="new")
        assert (await call(tools, "edit_file", **args))[1]["code"] == "EDIT_NOT_UNIQUE"
        assert (await call(make(), "edit_file", **args))[1]["code"] == "EDIT_NOT_UNIQUE"
        source.write_bytes(b"external\n")
        assert (await call(tools, "edit_file", **args))[1]["code"] == "EDIT_NOT_FOUND"
        assert (await call(tools, "create_file", path="main.py", content="no"))[1][
            "code"
        ] == "FILE_EXISTS"
        assert source.read_bytes() == b"external\n"
        for path in ("../escape.py", "CON", "new/NUL.txt"):
            assert (await call(tools, "create_file", path=path, content="no"))[0].is_error
        (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
        for path in ("ignored/sub/file.py", ".env", ".git/config", "dist/page.html"):
            assert not (await call(tools, "create_file", path=path, content="sentinel"))[0].is_error
            assert not (
                await call(
                    tools, "edit_file", path=str(root / path), old_text="sentinel", new_text="ok"
                )
            )[0].is_error
            assert (root / path).read_text() == "ok"
        source.write_bytes(b"\xff\xfea\x00")
        assert (await call(tools, "read_file", path="main.py"))[1]["code"] == "FILE_ENCODING"

    asyncio.run(scenario())


def test_links_are_readable_but_writes_keep_project_targets(file_stack):
    """硬链接可读；项目写入与应用存储仍使用各自真实目标。

    Read hard links while keeping project writes and application records in their own roots.
    """
    root, store, make, session = file_stack
    outside = root.parent / "outside"
    outside.mkdir()
    source = root / "source.txt"
    source.write_text("original", encoding="utf-8")
    os.link(source, root / "hardlink.txt")
    if os.name == "nt":
        import subprocess

        subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(root / "alias"), str(outside)],
            check=True,
            capture_output=True,
        )
        store.root.mkdir(parents=True)
        subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(store.root / session), str(outside)],
            check=True,
            capture_output=True,
        )
    else:
        (root / "alias").symlink_to(outside, target_is_directory=True)
        store.root.mkdir(parents=True)
        (store.root / session).symlink_to(outside, target_is_directory=True)

    async def scenario():
        """链接拒绝后不写外部目标。 Denial leaves external targets untouched."""
        tools = make()
        assert not (await call(tools, "read_file", path="hardlink.txt"))[0].is_error
        assert (await call(tools, "create_file", path="alias/file.py", content="no"))[1][
            "code"
        ] == "PATH_DENIED"
        assert (await call(tools, "create_file", path="ordinary.txt", content="no"))[1][
            "code"
        ] == "CHANGE_STORAGE_INVALID"
        assert not (root / "ordinary.txt").exists()
        assert list(outside.iterdir()) == [] and source.read_text() == "original"

    asyncio.run(scenario())


def test_save_failures_and_cancellation_leave_truth(file_stack, monkeypatch):
    """失败保留真实状态，取消等待已启动写入。 Keep truthful outcomes and reap cancelled writes."""
    root, store, make, session = file_stack

    async def scenario():
        """在实际存储边界注入失败与取消。 Inject failure and cancellation at storage boundaries."""
        original = store.save

        def fail(record):
            """模拟数据盘保存失败。 Simulate storage failure."""
            raise AgentError("DATA_DIR_NOT_WRITABLE", "test")

        monkeypatch.setattr(store, "save", fail)
        assert (await call(make(), "create_file", path="blocked.txt", content="x"))[0].is_error
        assert not (root / "blocked.txt").exists()

        def fail_outcome(record):
            """允许准备记录，拒绝结果保存。 Persist intent but reject the outcome."""
            if record.summary.status != "prepared":
                fail(record)
            original(record)

        monkeypatch.setattr(store, "save", fail_outcome)
        assert (await call(make(), "create_file", path="unknown.txt", content="x"))[1][
            "code"
        ] == "CHANGE_OUTCOME_UNKNOWN"
        assert (root / "unknown.txt").read_bytes() == b"x"
        assert store.list(session, None, 20).changes[0].status == "prepared"
        monkeypatch.setattr(store, "save", original)
        source = root / "changed.txt"
        source.write_bytes(b"old\n")
        checking = make()
        await call(checking, "read_file", path="changed.txt")

        def change_before_commit(record):
            """准备记录保存后模拟外部编辑器更新。 Simulate an external edit after preparation."""
            original(record)
            if record.summary.status == "prepared":
                source.write_bytes(b"external\n")

        monkeypatch.setattr(store, "save", change_before_commit)
        assert (
            await call(
                checking,
                "edit_file",
                path="changed.txt",
                old_text="old",
                new_text="new",
            )
        )[1]["code"] == "FILE_CHANGED"
        assert source.read_bytes() == b"external\n"
        monkeypatch.setattr(store, "save", original)
        tools = make()
        entered, release = threading.Event(), threading.Event()
        commit = tools._commit

        def delayed(*args):
            """写入后暂停，覆盖取消窗口。 Pause after writing to exercise cancellation."""
            commit(*args)
            entered.set()
            assert release.wait(5)

        monkeypatch.setattr(tools, "_commit", delayed)
        work = asyncio.create_task(
            call(tools, "create_file", path="cancelled.txt", content="saved")
        )
        assert await asyncio.to_thread(entered.wait, 5)
        work.cancel()
        await asyncio.sleep(0)
        assert not work.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await work
        assert (root / "cancelled.txt").read_bytes() == b"saved"
        final = next(
            change
            for change in store.list(session, None, 20).changes
            if change.path == "cancelled.txt"
        )
        assert final.status == "applied"

    asyncio.run(scenario())
