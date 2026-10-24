"""浏览索引、配对和分页的隔离验证。 Isolated read-index, pairing and paging checks."""

from uuid import uuid4

import pytest

from my_agent.checkpoints.types import ConversationRestored
from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.errors import AgentError
from my_agent.models.types import ModelTurn, TokenUsage, ToolCall, ToolResult
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.projection import entries, summarize
from my_agent.sessions.reading import SessionReader
from my_agent.sessions.store import SessionLog, SessionStore
from my_agent.sessions.types import (
    AssistantCommitted,
    RequestStarted,
    RunAccepted,
    RunFinished,
    SessionRenamed,
    ToolCompleted,
    ToolStarted,
)
from my_agent.storage import Storage
from tests.support.long_session import seed


def test_paged_reads_survive_restart_without_replaying_history(tmp_path, monkeypatch):
    """重启后摘要和旧页只定位原文，全部分页与原投影一致。

    Reopened summaries/pages seek source bytes and match the original full projection.
    """
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    with storage.writer():
        storage.initialize()
        store = SessionStore(storage)
        identity = seed(store, "project", 65, 9000)
        original = store.path(identity).read_bytes()
        full = store.load(identity)
        first = SessionReader(store).view(identity, None, str(uuid4()))
        assert first.before_seq and len(first.entries) <= 40
        assert first.summary == summarize(full)
        restarted = SessionStore(storage)

        def no_full_read(*args):
            """浏览命中索引时禁止回放。 Fail if indexed browsing replays the full journal."""
            pytest.fail("Indexed browsing replayed the entire log")

        monkeypatch.setattr(restarted, "load", no_full_read)
        reader = SessionReader(restarted)
        assert reader.header(identity).project_id == "project"
        cursor = None
        found = []
        while True:
            view = reader.view(identity, cursor, first.process_epoch)
            expected, boundary = entries(full, cursor)
            assert view.entries == expected
            assert view.before_seq == boundary
            found.extend(item.seq for item in view.entries)
            cursor = boundary
            if cursor is None:
                break
        assert len(found) == len(set(found)) == 65 * 3
        assert store.path(identity).read_bytes() == original


def test_index_refreshes_and_cache_failure_never_blocks_history(tmp_path, monkeypatch):
    """追加、外部变化与缓存损坏可重建；缓存写失败不阻断查看。

    Rebuild on appends/external changes/corrupt cache; cache writes cannot gate history.
    """
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    with storage.writer():
        storage.initialize()
        store = SessionStore(storage)
        identity = seed(store, "project", 2, 200)
        reader = SessionReader(store)
        assert reader.index(identity).summary.title == "Archived question 0"
        log = store.load(identity)
        store.append(log, SessionRenamed(operation_id=str(uuid4()), title="Renamed"), None)
        assert reader.index(identity).summary.title == "Renamed"
        cache = store.path(identity).with_name("display-index.json")
        cache.write_text("broken cache", encoding="utf-8")
        assert reader.view(identity, None, str(uuid4())).summary.title == "Renamed"
        with store.path(identity).open("ab") as stream:
            stream.write(b"broken source tail")

        def unwritable(*args):
            """只模拟派生缓存写失败。 Simulate a derived-cache write failure only."""
            raise AgentError("DATA_DIR_NOT_WRITABLE", "Fixture")

        monkeypatch.setattr("my_agent.sessions.reading.atomic_write", unwritable)
        view = reader.view(identity, None, str(uuid4()))
        assert view.summary.issue == "SESSION_DAMAGED_OR_TOO_LARGE"
        assert len(view.entries) == 6


def test_tool_pairing_and_rewind_remain_identical_in_pages(tmp_path):
    """工具配对跨页、回退标记和完整性检查保持原有语义。

    Preserve cross-page tool pairing, rewind markers and completeness semantics.
    """
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    with storage.writer():
        storage.initialize()
        store = SessionStore(storage)
        identity = seed(store, "project", 0, 0)
        log = store.load(identity)
        for index in range(23):
            run, message = str(uuid4()), str(uuid4())
            store.append(
                log,
                RunAccepted(
                    operation_id=str(uuid4()),
                    prompt=f"Question {index}",
                    limits=RunLimits.model_validate(DEFAULTS["run"]),
                    requested_limits=None,
                    mode="normal",
                ),
                run,
            )
            store.append(log, RequestStarted(message_id=message), run)
            call = ToolCall(
                tool_call_id=f"call-{index}", name="read_file", arguments={"path": "a.py"}
            )
            store.append(
                log,
                AssistantCommitted(
                    message_id=message,
                    turn=ModelTurn(
                        text="",
                        tool_calls=[call],
                        native={"role": "assistant"},
                        usage=TokenUsage(input_tokens=10, output_tokens=2),
                    ),
                ),
                run,
            )
            assert log.context_complete() == log.context()[1] is False
            store.append(log, ToolStarted(call=call), run)
            store.append(
                log,
                ToolCompleted(
                    result=ToolResult(
                        tool_call_id=call.tool_call_id,
                        content="observed",
                        is_error=False,
                    )
                ),
                run,
            )
            store.append(
                log,
                RunFinished(status="completed", code=None, message=None, elapsed_seconds=1),
                run,
            )
            assert log.context_complete() == log.context()[1] is True
        store.append(
            log,
            ConversationRestored(
                operation_id=str(uuid4()),
                checkpoint_id=str(uuid4()),
                before_seq=8,
                message="Rewound conversation; source retained",
            ),
            None,
        )
        assert log.context_complete() == log.context()[1] is True
        reader = SessionReader(store)
        cursor = None
        while True:
            view = reader.view(identity, cursor, str(uuid4()))
            expected, boundary = entries(log, cursor)
            assert view.entries == expected
            assert view.before_seq == boundary
            cursor = boundary
            if cursor is None:
                break


def test_pair_checks_do_not_construct_context_and_read_only_does_not_save(tmp_path, monkeypatch):
    """冷读不组装模型上下文；只读计时也不会写入展示索引。

    Cold reads do not construct model context; read-only profiling never saves indexes.
    """
    store = SessionStore(Storage(resolve_data_dir(str(tmp_path / "data"))))
    identity = seed(store, "project", 30, 1000)

    def no_context(*args, **kwargs):
        """禁止仅为浏览构造模型消息。 Fail if browsing builds model messages."""
        pytest.fail("Browsing constructed model context")

    monkeypatch.setattr(SessionLog, "context", no_context)
    assert SessionReader(store).view(identity, None, str(uuid4())).summary.can_continue
    assert not store.path(identity).with_name("display-index.json").exists()
