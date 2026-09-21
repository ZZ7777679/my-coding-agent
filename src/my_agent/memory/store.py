"""本地条目与可重算检索；无向量服务。

Local entries and recomputable retrieval without a vector service.
"""

import re
from pathlib import Path
from uuid import UUID, uuid4

from my_agent.context.accounting import record_usage
from my_agent.errors import AgentError
from my_agent.memory.types import MemoryEntry, MemoryFields, MemoryQuery, MemoryState
from my_agent.sessions.store import SessionStore
from my_agent.storage import Storage, atomic_write, read_document, utc_now, write_document


def terms(text: str) -> set[str]:
    """保留英文名称、路径及中文二元片段。

    Retain identifiers, paths and Chinese bigrams.
    """
    result = set(re.findall(r"[a-z0-9_./\\-]+", text.casefold()))
    for word in re.findall(r"[\u4e00-\u9fff]+", text):
        result.update(word[i : i + 2] for i in range(max(1, len(word) - 1)))
    return result


class MemoryStore:
    """所有条目跟随应用数据根；索引由条目即时计算。

    Entries follow the app data root; indices derive from entries.
    """

    def __init__(self, storage: Storage) -> None:
        """复用已有写锁与会话路径解析。

        Reuse the existing writer and session path resolver.
        """
        self.storage = storage
        self.root = storage.root / "memory"
        self.sessions = SessionStore(storage)

    def state(self, session_id: str, current_seq: int) -> MemoryState:
        """首次接入从当前位置开始，不把旧聊天变成积压。

        First use starts now, without historical backlog.
        """
        path = self.sessions.path(session_id).with_name("memory.json")
        if path.exists():
            return read_document(path, MemoryState)
        state = MemoryState(processed_seq=current_seq)
        self.save_state(session_id, state)
        return state

    def save_state(self, session_id: str, state: MemoryState) -> None:
        """原子保存贡献游标与设置。

        Atomically save contribution cursors and settings.
        """
        write_document(self.sessions.path(session_id).with_name("memory.json"), state)
        if state.job:
            record_usage(self.sessions.path(session_id).parent / "memory-usage", state.job)

    def path(self, identity: str) -> Path:
        """ID 只用于定位自己的记录。

        IDs only locate owned records.
        """
        try:
            return self.root / "entries" / f"{UUID(identity)}.json"
        except ValueError as exc:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "记忆 ID 不正确。") from exc

    def read(self, identity: str, project_id: str) -> MemoryEntry:
        """读取当前项目或用户范围的已知条目。

        Read a known project or user-scoped entry.
        """
        path = self.path(identity)
        if not path.exists():
            raise AgentError("MEMORY_NOT_FOUND", "记忆不存在或已忘记。")
        entry = read_document(path, MemoryEntry)
        if entry.project_id not in {None, project_id}:
            raise AgentError("MEMORY_NOT_FOUND", "该记忆不属于当前项目。")
        return entry

    def _entries(self) -> tuple[list[MemoryEntry], int]:
        """读取内部条目供检索和来源传播；损坏条目单独计数。

        Load internal entries for retrieval and invalidation, counting damaged entries.
        """
        directory = self.root / "entries"
        candidates: list[MemoryEntry] = []
        unavailable = 0
        for path in directory.glob("*.json"):
            try:
                entry = read_document(path, MemoryEntry)
            except AgentError:
                unavailable += 1
                continue
            candidates.append(entry)
        return candidates, unavailable

    def find(
        self,
        project_id: str,
        query: MemoryQuery,
        *,
        associations: bool = False,
        include_pinned: bool = False,
    ) -> tuple[list[MemoryEntry], int]:
        """本地词法、结构与可选关系合并召回；局部损坏不拦正常任务。

        Merge local lexical, structured and optional relation retrieval.
        """
        entries, unavailable = self._entries()
        candidates = [entry for entry in entries if entry.project_id in {None, project_id}]
        now = utc_now()

        def active(item: MemoryEntry) -> bool:
            """仅当前有效条目参与召回和替代，不让失效知识隐藏现有知识。

            Only currently active entries participate in recall and supersession.
            """
            return (
                item.enabled
                and not item.stale
                and (item.valid_until is None or item.valid_until >= now[:10])
                and (item.valid_from is None or item.valid_from <= now)
            )

        superseded = {
            identifier for item in candidates if active(item) for identifier in item.supersedes
        }
        eligible = [
            item
            for item in candidates
            if (query.include_disabled or (active(item) and item.memory_id not in superseded))
            and (query.category is None or query.category == item.category)
            and (
                query.subject is None
                or any(query.subject.casefold() in value.casefold() for value in item.subjects)
            )
        ]
        requested = terms(query.query)

        def score(item: MemoryEntry) -> int:
            """排序只影响召回，不成为执行许可。

            Ranking affects retrieval, never execution permission.
            """
            corpus = " ".join([item.title, item.content, *item.tags, *item.subjects])
            return len(requested & terms(corpus))

        # 固定优先属于自动召回偏好，不能令手动关键词搜索返回不相关条目。
        # Pinning belongs to automatic recall, not unrelated keyword search matches.
        found = [
            item
            for item in eligible
            if not query.query or score(item) > 0 or (include_pinned and item.pinned)
        ]
        if associations:
            related = {identifier for item in found for identifier in item.related_ids}
            found.extend(
                item for item in eligible if item.memory_id in related and item not in found
            )
        if query.query or include_pinned:
            found.sort(
                key=lambda item: (
                    include_pinned and item.pinned,
                    score(item),
                    item.updated_at,
                    item.memory_id,
                ),
                reverse=True,
            )
        else:
            found.sort(key=lambda item: item.memory_id)
        if query.cursor:
            index = next(
                (i + 1 for i, item in enumerate(found) if item.memory_id == query.cursor), 0
            )
            found = found[index:]
        return found, unavailable

    def save(
        self,
        project_id: str,
        fields: MemoryFields,
        *,
        identity: str | None = None,
        source: str = "user",
        session_id: str | None = None,
        source_seq: int | None = None,
        expected_revision: int | None = None,
    ) -> MemoryEntry:
        """保存独立知识；后台不覆盖用户编辑，冲突仅跳过该候选。

        Save knowledge; maintenance preserves user edits.
        """
        current = self.read(identity, project_id) if identity else None
        if (
            current
            and source == "maintenance"
            and (
                current.source == "user" or current.pinned or current.revision != expected_revision
            )
        ):
            raise AgentError("MEMORY_EDITED", "记忆已由用户或新工作修改，跳过旧整理候选。")
        identity = identity or str(uuid4())
        path = self.path(identity)
        now = utc_now()
        entry = MemoryEntry.model_validate(
            {
                **fields.model_dump(),
                "memory_id": identity,
                "project_id": project_id if fields.scope == "project" else None,
                "revision": current.revision + 1 if current else 1,
                "source": source,
                "session_id": session_id,
                "source_seq": source_seq,
                "created_at": current.created_at if current else now,
                "updated_at": now,
            }
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        write_document(path, entry)
        if current:
            self.invalidate(identity)
        return entry

    def invalidate(self, identity: str) -> None:
        """来源改变只停用派生注入，不阻塞对话或同步重建。

        Source changes invalidate derived injection without blocking or rebuilding chat.
        """
        # 用户级来源可被多个项目引用；内部传播不能采用召回的项目过滤。
        # User-scoped sources can cross projects; internal propagation must not filter by project.
        entries, _ = self._entries()
        pending = [identity]
        changed = {identity}
        while pending:
            source = pending.pop()
            for entry in entries:
                if source in entry.source_ids and entry.memory_id not in changed:
                    entry.stale = True
                    write_document(self.path(entry.memory_id), entry)
                    pending.append(entry.memory_id)
                    changed.add(entry.memory_id)

    def forget(self, identity: str, project_id: str) -> None:
        """移除正文和派生关系，保留无正文墓碑防止后台旧候选恢复。

        Remove content/relations and leave a content-free tombstone."""
        self.read(identity, project_id)
        tombstone = self.root / "forgotten" / str(UUID(identity))
        tombstone.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(tombstone, utc_now() + "\n")
        self.invalidate(identity)
        try:
            self.path(identity).unlink()
        except OSError as exc:
            raise AgentError("MEMORY_SAVE_FAILED", "未能删除记忆正文。") from exc
        entries, _ = self._entries()
        for entry in entries:
            if identity in entry.source_ids:
                if entry.source == "maintenance":
                    self.path(entry.memory_id).unlink()
                    continue
                entry.stale = True
                write_document(self.path(entry.memory_id), entry)
            if identity in entry.related_ids or identity in entry.supersedes:
                entry.related_ids = [value for value in entry.related_ids if value != identity]
                entry.supersedes = [value for value in entry.supersedes if value != identity]
                write_document(self.path(entry.memory_id), entry)

    def forgotten(self, identity: str) -> bool:
        """只检查删除身份，不保存被忘记的内容。

        Check deletion identity without retaining forgotten text.
        """
        return (self.root / "forgotten" / str(UUID(identity))).exists()
