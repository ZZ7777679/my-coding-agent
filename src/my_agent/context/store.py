"""派生摘要存储与公开历史分页。

Derived checkpoint storage and public history paging.
"""

import json
import re
from uuid import UUID, uuid4

from my_agent.context.accounting import record_usage
from my_agent.context.types import ContextState, HistoryItem, HistoryPage, HistoryParams
from my_agent.errors import AgentError
from my_agent.sessions.projection import entries
from my_agent.sessions.store import SessionLog, SessionStore
from my_agent.sessions.types import ToolCompleted, ToolSkipped, ToolStarted
from my_agent.storage import atomic_write, read_document, write_document


class ContextStore:
    """复用会话身份和写入线程，不改写原始事件。

    Reuse session identity and writer, never rewrite events.
    """

    def __init__(self, sessions: SessionStore) -> None:
        """绑定现有会话存储。

        Bind the existing session store.
        """
        self.sessions = sessions

    def read(self, session_id: str) -> ContextState:
        """旧会话没有摘要文件时正常返回空状态。

        Old sessions naturally start without checkpoints.
        """
        path = self.sessions.path(session_id).with_name("context.json")
        return read_document(path, ContextState) if path.exists() else ContextState()

    def save(self, session_id: str, state: ContextState) -> None:
        """原子保存完整派生状态。

        Atomically save complete derived state.
        """
        path = self.sessions.path(session_id).with_name("context.json")
        write_document(path, state)
        if state.job:
            record_usage(path.parent / "context-usage", state.job)

    def history(self, log: SessionLog, params: HistoryParams) -> HistoryPage:
        """搜索公开记录并分段返回原文，不暴露 provider 原生字段。

        Search public entries, not provider internals.
        """
        if params.artifact_id:
            path = (
                self.sessions.path(log.session_id).parent
                / "artifacts"
                / f"{UUID(params.artifact_id)}.txt"
            )
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise AgentError(
                    "HISTORY_UNAVAILABLE", "这项归档材料不可读取，其他工作可继续。"
                ) from exc
            matches_at = (
                [
                    match.start()
                    for match in re.finditer(re.escape(params.query), text, re.IGNORECASE)
                ]
                if params.query
                else []
            )
            start = (
                next((position for position in matches_at if position >= params.offset), len(text))
                if params.query
                else params.offset
            )
            end = min(len(text), start + params.max_chars)
            return HistoryPage(
                items=[
                    HistoryItem(
                        seq=0,
                        kind="artifact",
                        text=text[start:end],
                        offset=start,
                        next_offset=end if end < len(text) else None,
                        total_chars=len(text),
                    )
                ]
                if start < len(text)
                else [],
                next_after_seq=None,
                matches=len(matches_at) if params.query else 1,
                match_unit="occurrences" if params.query else "records",
                through_seq=len(log.facts),
                complete=True,
            )
        through = min(params.through_seq or len(log.facts), len(log.facts))
        # 调用 ID 只在一次运行内关联；未完成的调用没有结果序号。
        # Scope call IDs to their run; unfinished calls have no result sequence.
        calls: dict[tuple[str | None, str], tuple[int, str]] = {}
        results: dict[tuple[str | None, str], int] = {}
        identities: dict[int, tuple[str | None, str]] = {}
        for fact in log.facts[:through]:
            data = fact.data
            if isinstance(data, ToolStarted):
                identity = (fact.run_id, data.call.tool_call_id)
                calls[identity] = (fact.seq, data.call.name)
                identities[fact.seq] = identity
            elif isinstance(data, (ToolCompleted, ToolSkipped)):
                identity = (fact.run_id, data.result.tool_call_id)
                results[identity] = fact.seq
                identities[fact.seq] = identity
        lookup_sequences: set[int] = set()
        if params.query and params.entry_seq is None and not params.include_lookup_results:
            # 关键词命中源材料，而不是把先前查找结果再当一份独立证据。
            # Search source material instead of counting prior lookup output as new evidence.
            lookups = {
                (fact.run_id, fact.data.call.tool_call_id)
                for fact in log.facts
                if isinstance(fact.data, ToolStarted)
                and fact.data.call.name
                in {"read_history", "read_work_status", "get_context_status"}
            }
            for fact in log.facts:
                data = fact.data
                lookup_id = (
                    data.call.tool_call_id
                    if isinstance(data, ToolStarted)
                    else data.result.tool_call_id
                    if isinstance(data, (ToolCompleted, ToolSkipped))
                    else None
                )
                if (fact.run_id, lookup_id) in lookups:
                    lookup_sequences.add(fact.seq)
        matches: list[tuple[int, str, str, int]] = []
        pattern = re.compile(re.escape(params.query), re.IGNORECASE) if params.query else None
        public = []
        cursor = None
        while True:
            page, cursor = entries(log, cursor)
            public.extend(page)
            if cursor is None:
                break
        for item in sorted(public, key=lambda value: value.seq):
            if item.seq in lookup_sequences:
                continue
            if not params.after_seq < item.seq <= through:
                continue
            if params.entry_seq is not None and item.seq != params.entry_seq:
                continue
            text = item.text
            # 运行卡片附带调用仅用于展示；历史结果不能被参数覆盖。
            # Program cards carry the call for display; preserve the actual result for history.
            if item.result:
                text = item.result.content
            elif item.call:
                text = json.dumps(item.call.model_dump(mode="json"), ensure_ascii=False)
            offset = params.offset if params.entry_seq is not None else 0
            if pattern:
                hit = pattern.search(text, offset)
                if hit is None:
                    continue
                offset = hit.start()
            matches.append((item.seq, item.kind, text, offset))
        result: list[HistoryItem] = []
        remaining = params.max_chars
        for seq, kind, text, offset in matches[: params.limit]:
            end = min(len(text), offset + remaining)
            link_identity = identities.get(seq)
            call = calls.get(link_identity) if link_identity else None
            result.append(
                HistoryItem(
                    seq=seq,
                    kind=kind,
                    text=text[offset:end],
                    offset=offset,
                    next_offset=end if end < len(text) else None,
                    total_chars=len(text),
                    tool_name=call[1] if call else None,
                    tool_call_id=link_identity[1] if link_identity else None,
                    call_seq=call[0] if call else None,
                    result_seq=results.get(link_identity) if link_identity else None,
                )
            )
            remaining -= max(0, end - offset)
            if remaining <= 0:
                break
        return HistoryPage(
            items=result,
            matches=len(matches),
            through_seq=through,
            next_after_seq=result[-1].seq if len(result) < len(matches) else None,
            complete=log.issue is None,
        )

    def archive(self, session_id: str, text: str) -> str:
        """保存实际工具材料，模型预览缩短不删除此副本。

        Persist received tool material independently of bounded model previews.
        """
        identity = str(uuid4())
        path = self.sessions.path(session_id).parent / "artifacts" / f"{identity}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, text)
        return identity
