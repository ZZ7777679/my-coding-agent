"""可重建的历史浏览索引；不作为运行或模型上下文的数据源。

Rebuildable history read index, never a source for execution or model context.
"""

import logging
import os
from pathlib import Path

from pydantic import ValidationError

from my_agent.checkpoints.types import ConversationRestored
from my_agent.errors import AgentError
from my_agent.goals.types import GoalControl, GoalCreated, GoalInputQueued, GoalView
from my_agent.models.types import ModelData, ModelProgress
from my_agent.sessions.projection import (
    HISTORY_PAGE_ENTRIES,
    entries,
    summarize,
    terminal_goal_entries,
)
from my_agent.sessions.recovery_types import SessionRecovered
from my_agent.sessions.store import MAX_FACT_BYTES, SessionLog, SessionStore
from my_agent.sessions.types import (
    AssistantCommitted,
    Fact,
    RequestFailed,
    RequestStarted,
    RunAccepted,
    RunFinished,
    RunInputApplied,
    RunInputQueued,
    SessionCreated,
    SessionSummary,
    SessionView,
    ToolCompleted,
    ToolSkipped,
    ToolStarted,
)
from my_agent.storage import atomic_write


class DisplayIndex(ModelData):
    """仅保存摘要与原日志位置，消息正文仍只在原始日志中。

    Store summaries and log offsets; message bodies remain in the original journal.
    """

    version: int = 1
    stamp: tuple[int, ...]
    summary: SessionSummary
    offsets: list[int]
    display_seqs: list[int]
    support_seqs: list[int]
    tool_sources: dict[int, int]
    terminal_goals: dict[int, GoalView]
    model_progress: ModelProgress | None


def last_progress(log: SessionLog) -> ModelProgress | None:
    """读取最新请求的已保存进度，不继承上一请求时序。

    Read saved progress without inheriting timings from a previous request.
    """
    for fact in reversed(log.facts):
        if isinstance(fact.data, (RunAccepted, RequestStarted)):
            break
        if isinstance(fact.data, (RunFinished, AssistantCommitted)):
            return fact.data.model_progress
    return None


class SessionReader:
    """业务线程中的按页读取器；索引缺失或过期时从事实重建。

    Business-thread page reader rebuilding missing or stale indexes from facts.
    """

    def __init__(self, store: SessionStore) -> None:
        """复用既有单写者存储，不创建第二份事件日志。

        Reuse the single-writer store without creating another event journal.
        """
        self.store = store

    def _stamp(self, source: Path) -> tuple[int, ...]:
        """统一以打开的句柄取身份；Windows 的 stat/fstat 创建时间可能不同。

        Use handle identity consistently; Windows stat/fstat creation times may differ.
        """
        with source.open("rb") as stream:
            return self.store._stamp(os.fstat(stream.fileno()))

    def header(self, session_id: str) -> SessionCreated:
        """先读首条元数据过滤项目与 worker，避免加载无关历史。

        Filter projects and workers from the header before loading unrelated history.
        """
        try:
            with self.store.path(session_id).open("rb") as stream:
                fact = Fact.model_validate_json(stream.readline(MAX_FACT_BYTES + 1))
            if isinstance(fact.data, SessionCreated) and fact.session_id == session_id:
                return fact.data
        except (OSError, ValidationError) as exc:
            raise AgentError("SESSION_UNAVAILABLE", "无法读取会话头；原文件保留。") from exc
        raise AgentError("SESSION_DAMAGED", "会话头损坏；原文件保留。")

    def index(self, session_id: str) -> DisplayIndex:
        """按原文件身份刷新派生索引，缓存损坏不阻断原始记录读取。

        Refresh by source identity; invalid derived caches never block reading the journal.
        """
        source = self.store.path(session_id)
        cache = source.with_name("display-index.json")
        try:
            stamp = self._stamp(source)
        except OSError:
            # 原存储负责给出真实读取错误，不将缺文件伪装成空会话。
            # Let the source store report the real error, never fabricate an empty session.
            return self._build(session_id, source, cache)
        try:
            index = DisplayIndex.model_validate_json(cache.read_bytes())
            if (
                index.version == 1
                and index.stamp == stamp
                and index.summary.session_id == session_id
            ):
                return index
        except FileNotFoundError:
            pass  # 派生缓存可缺省。 A derived cache is optional.
        except (OSError, ValidationError):
            logging.getLogger(__name__).warning("SESSION_DISPLAY_INDEX_REBUILD")
        return self._build(session_id, source, cache)

    def _build(self, session_id: str, source: Path, cache: Path) -> DisplayIndex:
        """旧记录首次浏览时建偏移索引；写缓存失败不改变会话结果。

        Index legacy logs on first browse; cache write failures do not change session outcomes.
        """
        # 保存读取前身份；外部同时修改时不将旧快照标为新文件的有效缓存。
        # Capture identity before loading; concurrent edits cannot label an old snapshot as current.
        try:
            stamp = self._stamp(source)
        except OSError:
            self.store.load(session_id)  # 原存储返回具体原因。 Report through the source store.
            stamp = self._stamp(source)
        log = self.store.load(session_id)
        offsets: list[int] = []
        with source.open("rb") as stream:
            for _ in log.facts:
                offsets.append(stream.tell())
                stream.readline(MAX_FACT_BYTES + 1)
        terminal = terminal_goal_entries(log)
        display: list[int] = []
        support: list[int] = []
        tools: dict[tuple[str | None, str], int] = {}
        sources: dict[int, int] = {}
        for fact in log.facts:
            data = fact.data
            if isinstance(data, (ConversationRestored, RunInputApplied)):
                support.append(fact.seq)
            if isinstance(data, ToolStarted):
                tools[fact.run_id, data.call.tool_call_id] = fact.seq
            elif isinstance(data, (ToolCompleted, ToolSkipped)):
                start = tools.get((fact.run_id, data.result.tool_call_id))
                if start is not None:
                    sources[fact.seq] = start
            if (
                isinstance(
                    data,
                    (
                        ConversationRestored,
                        RunAccepted,
                        GoalCreated,
                        RunInputQueued,
                        GoalInputQueued,
                        AssistantCommitted,
                        ToolStarted,
                        ToolCompleted,
                        ToolSkipped,
                        SessionRecovered,
                        RequestFailed,
                        RunFinished,
                    ),
                )
                or (isinstance(data, GoalControl) and data.action == "answer")
                or fact.seq in terminal
            ) and not (isinstance(data, RunAccepted) and data.goal_role == "question"):
                display.append(fact.seq)
        index = DisplayIndex(
            stamp=stamp,
            summary=summarize(log),
            offsets=offsets,
            display_seqs=display,
            support_seqs=support,
            tool_sources=sources,
            terminal_goals=terminal,
            model_progress=last_progress(log),
        )
        # 只允许已有数据根单写者保存缓存；诊断只读实例不写个人数据。
        # Only the data-root writer saves caches; read-only diagnostics never write personal data.
        if self.store.storage.writing and stamp == self._stamp(source):
            try:
                atomic_write(cache, index.model_dump_json() + "\n")
            except AgentError:
                logging.getLogger(__name__).warning("SESSION_DISPLAY_INDEX_SAVE_FAILED")
        return index

    def view(self, session_id: str, before_seq: int | None, epoch: str) -> SessionView:
        """定位最近一页原文，额外读取配对／回退元数据；不加载全文。

        Seek to one recent page plus pairing/rewind metadata without loading all message bodies.
        """
        index = self.index(session_id)
        eligible = [seq for seq in index.display_seqs if before_seq is None or seq < before_seq]
        # 多取一项供既有投影判断是否还有更早内容；字节上限仍由投影统一处理。
        # One lookahead item lets the existing projection decide paging and its byte limit.
        selected = set(eligible[-(HISTORY_PAGE_ENTRIES + 1) :])
        needed = selected | set(index.support_seqs)
        needed.update(index.tool_sources[seq] for seq in selected if seq in index.tool_sources)
        facts: list[Fact] = []
        try:
            with self.store.path(session_id).open("rb") as stream:
                if self.store._stamp(os.fstat(stream.fileno())) != index.stamp:
                    raise ValueError("Source changed after index lookup")
                for seq in sorted(needed):
                    stream.seek(index.offsets[seq - 1])
                    fact = Fact.model_validate_json(stream.readline(MAX_FACT_BYTES + 1))
                    if fact.seq != seq or fact.session_id != session_id:
                        raise ValueError("Derived offset changed")
                    facts.append(fact)
                if self.store._stamp(os.fstat(stream.fileno())) != index.stamp:
                    raise ValueError("Source changed during page read")
            log = SessionLog(session_id, facts)
            page, cursor = entries(
                log, before_seq, selected_seqs=selected, terminal_entries=index.terminal_goals
            )
            if cursor is None and len(eligible) > len(selected) and page:
                cursor = page[0].seq
            summary = index.summary
            watermark = len(index.offsets)
            progress = index.model_progress
        except (OSError, ValueError, IndexError):
            # 缓存竞态只回读原始记录，不标坏会话或限制继续工作。
            # Cache races fall back to the journal, never mark the session damaged or gate work.
            log = self.store.load(session_id)
            page, cursor = entries(log, before_seq)
            summary, watermark, progress = summarize(log), len(log.facts), last_progress(log)
        return SessionView(
            summary=summary,
            entries=page,
            before_seq=cursor,
            watermark=watermark,
            process_epoch=epoch,
            stream_message_id=None,
            stream_text="",
            delta_index=0,
            model_progress=progress,
        )
