"""旧历史复用与缓存失效，不改个人数据。 Old-history reuse and invalidation on isolated data."""

from uuid import uuid4

import pytest

from my_agent.config import resolve_data_dir
from my_agent.errors import AgentError
from my_agent.sessions.store import SessionStore
from my_agent.sessions.types import SessionRenamed
from my_agent.storage import Storage
from tests.support.long_session import seed


def test_old_history_reuses_validation_and_observes_changes(tmp_path, monkeypatch):
    """重复读取不重复解析；追加、外部变化、损坏和删除均可见。

    Reuse parsing while preserving appends, external edits, damage and deletion.
    """
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    with storage.writer():
        storage.initialize()
        store = SessionStore(storage)
        identity = seed(store, "project", 180, 19000)
        calls = 0
        original = store._validate_next

        def observe(log, fact):
            """计量真实校验次数，不改变恢复行为。 Count validation without changing recovery."""
            nonlocal calls
            calls += 1
            return original(log, fact)

        monkeypatch.setattr(store, "_validate_next", observe)
        cold = store.load(identity)
        assert cold.issue is None and len(cold.facts) == 721
        assert calls == 721
        for _ in range(12):
            assert len(store.load(identity).facts) == 721
        assert calls == 721
        # 列表快照彼此独立，不允许调用方 append 污染其他读者。
        # List snapshots are independent of caller appends.
        store.load(identity).facts.clear()
        assert len(store.load(identity).facts) == 721
        store.append(cold, SessionRenamed(operation_id=str(uuid4()), title="Renamed"), None)
        assert store.load(identity).facts[-1].data.title == "Renamed"
        target = store.path(identity)
        content = target.read_text(encoding="utf-8")
        target.write_text(content.replace('"Renamed"', '"Changed"'), encoding="utf-8")
        assert store.load(identity).facts[-1].data.title == "Changed"
        with target.open("ab") as stream:
            stream.write(b"broken tail")
        assert store.load(identity).issue == "SESSION_DAMAGED_OR_TOO_LARGE"
        target.unlink()
        with pytest.raises(AgentError) as caught:
            store.load(identity)
        assert caught.value.code == "SESSION_NOT_FOUND"
        target.touch()
        assert store.load(identity).issue == "SESSION_EMPTY"
        assert store.load(identity).issue == "SESSION_EMPTY"


def test_cache_eviction_never_limits_history_access(tmp_path):
    """缓存容量只触发淘汰，大会话仍完整读取。 Cache eviction never truncates histories."""
    store = SessionStore(Storage(resolve_data_dir(str(tmp_path / "data"))))
    first = seed(store, "project", 2, 50)
    second = seed(store, "project", 3, 50)
    store._cache_limit = store.path(second).stat().st_size
    assert len(store.load(first).facts) == 9
    assert len(store.load(second).facts) == 13
    assert first not in store._read_cache
    assert len(store.load(first).facts) == 9
    store._cache_limit = 0
    store._forget_cached(first)
    assert len(store.load(second).facts) == 13
