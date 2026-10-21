"""对显式选中的轨迹建索引并按需读取，不复制另一套日志。

Index explicitly selected traces and read bodies on demand without a second log.
"""

import asyncio
import json
import re
import threading
from dataclasses import dataclass, field
from typing import Protocol

from my_agent.errors import AgentError
from my_agent.evolution.types import (
    EvolutionEpisode,
    EvolutionMaterial,
    EvolutionSelection,
    EvolutionSource,
)
from my_agent.models.types import JsonObject
from my_agent.sessions.projection import summarize
from my_agent.sessions.store import SessionLog
from my_agent.sessions.trace import (
    TraceDetailParams,
    TraceItem,
    trace_detail,
    trace_search_records,
)
from my_agent.sessions.types import RunFinished
from my_agent.worker import BusinessWorker


class InvestigationSessions(Protocol):
    """调查仅依赖已有会话读取和后台工作线程。

    Investigation needs only existing session reads and the business worker.
    """

    worker: BusinessWorker

    async def _load(self, session_id: str) -> SessionLog:
        """读取用户显式引用的会话。 Read an explicitly referenced session."""
        ...


@dataclass
class _EvidenceRow:
    """一个真实轨迹身份及允许读取的冻结日志。

    One actual trace identity and its authorized frozen log.
    """

    item: TraceItem
    log: SessionLog
    project_id: str
    session_title: str
    source: EvolutionSource
    run_status: str = ""
    error_code: str = ""
    searchable: str = ""
    total_chars: int | None = None
    chunks: list[tuple[int, str]] = field(default_factory=list)

    def remember(self, offset: int, text: str) -> None:
        """合并重叠正文，重复读取不夸大覆盖量。

        Merge overlapping body chunks so repeated reads do not inflate coverage.
        """
        if not text:
            return
        merged: list[tuple[int, str]] = []
        for start, content in sorted([*self.chunks, (offset, text)], key=lambda c: c[0]):
            if merged and start <= merged[-1][0] + len(merged[-1][1]):
                previous, body = merged[-1]
                merged[-1] = previous, body + content[max(0, previous + len(body) - start) :]
            else:
                merged.append((start, content))
        self.chunks = merged

    def complete(self) -> bool:
        """仅全部字符已读才标记完整。 Mark complete only after every character was read."""
        return (
            self.total_chars is not None and sum(len(c) for _, c in self.chunks) == self.total_chars
        )


class InvestigationEvidence:
    """冻结选择边界，保存索引与实际已读片段，不预读所有正文。

    Freeze selection boundaries and retain the index and bodies actually read, without eager reads.
    """

    def __init__(self, sessions: InvestigationSessions) -> None:
        """初始化一次调查的临时读取状态。 Initialize transient state for one investigation."""
        self.sessions = sessions
        self.sources: list[EvolutionSource] = []
        self.selections: list[EvolutionSelection] = []
        self.issues: list[str] = []
        self._rows: dict[tuple[str, int], _EvidenceRow] = {}
        self.focus = ""
        self.episodes: list[EvolutionEpisode] = []
        self.stop = threading.Event()

    @classmethod
    async def build(
        cls,
        sessions: InvestigationSessions,
        sources: list[EvolutionSource],
        *,
        accepted_at: str | None = None,
        stop: threading.Event | None = None,
    ) -> "InvestigationEvidence":
        """跨项目展开明确选择，按真实身份去重并冻结配对结果截止点。

        Expand selections across projects, deduplicate identities and freeze result cutoffs.
        """
        result = cls(sessions)
        if stop is not None:
            result.stop = stop
        logs: dict[str, SessionLog] = {}
        snapshots: dict[tuple[str, int], tuple[SessionLog, list[tuple[TraceItem, str]]]] = {}
        seen: set[str] = set()
        for source in sources:
            await asyncio.sleep(0)
            result._check_stopped()
            if source.session_id is None:
                continue
            scope = source.scope or ("event" if source.seq else "run" if source.run_id else None)
            if scope is None:
                result.issues.append("旧会话引用未指定范围，未自动扩大为整个会话。")
                continue
            if (scope == "event" and source.seq is None) or (scope == "run" and not source.run_id):
                raise AgentError("INVALID_SOURCE", "事件需要真实序号，运行需要运行身份。")
            if source.session_id not in logs:
                logs[source.session_id] = await sessions._load(source.session_id)
            original = logs[source.session_id]
            if accepted_at and source.through_seq is None:
                original = SessionLog(
                    original.session_id,
                    [f for f in original.facts if f.at <= accepted_at],
                    original.issue,
                )
                if not original.facts:
                    continue
            summary = await asyncio.to_thread(summarize, original)
            if original.issue and original.issue not in result.issues:
                result.issues.append(original.issue)
            current_end = max((f.seq for f in original.facts), default=0)
            through = min(source.through_seq or current_end, current_end)
            frozen = source.model_copy(update={"scope": scope, "through_seq": through})
            key = frozen.model_dump_json()
            if key in seen:
                continue
            seen.add(key)
            snapshot_key = source.session_id, through
            if snapshot_key not in snapshots:
                log = SessionLog(
                    original.session_id,
                    [f for f in original.facts if f.seq <= through],
                    original.issue,
                )
                snapshots[snapshot_key] = log, await asyncio.to_thread(trace_search_records, log)
            log, records = snapshots[snapshot_key]
            bodies = {item.seq: body for item, body in records}
            selected = [
                item
                for item, _ in records
                if (
                    scope == "session"
                    or scope == "run"
                    and item.run_id == source.run_id
                    or scope == "event"
                    and item.seq == source.seq
                )
                and (scope != "event" or source.run_id is None or item.run_id == source.run_id)
            ]
            if scope != "session" and not selected:
                raise AgentError("TRACE_NOT_FOUND", "所选轨迹不在该范围或截止位置内。")
            result.sources.append(frozen)
            scope_title = {"session": "整个会话", "run": "指定运行", "event": "单条事件"}[scope]
            result.selections.append(
                EvolutionSelection(
                    source=frozen,
                    title=f"{scope_title} · {summary.title}",
                    event_count=len(selected),
                )
            )
            finished = {f.run_id: f.data for f in log.facts if isinstance(f.data, RunFinished)}
            for index, item in enumerate(selected):
                if index % 256 == 0:
                    await asyncio.sleep(0)
                    result._check_stopped()
                identity = source.session_id, item.seq
                existing = result._rows.get(identity)
                # 重叠选择取实际授权的较晚截止点，不能把整会话的范围扩到其他行。
                # Use the later authorized cutoff for this row only, leaving other rows unchanged.
                if existing and (existing.source.through_seq or 0) >= through:
                    continue
                # 单事件索引不能借运行身份带入未选择的终态原因。
                # An event-only index must not import an unselected run's terminal cause.
                terminal = finished.get(item.run_id) if item.kind == "run.finished" else None
                result._rows[identity] = _EvidenceRow(
                    item=item,
                    log=log,
                    project_id=summary.project_id,
                    session_title=summary.title,
                    source=EvolutionSource(
                        session_id=source.session_id,
                        run_id=item.run_id,
                        seq=item.seq,
                        scope="event",
                        through_seq=through,
                    ),
                    run_status=terminal.status if terminal else "",
                    error_code=(terminal.cause_code or terminal.code or "") if terminal else "",
                    searchable=bodies[item.seq],
                )
        return result

    def _check_stopped(self) -> None:
        """停止纯读取计算，不占用业务写入线程。

        Stop read-only computation without occupying the business writer.
        """
        if self.stop.is_set():
            raise asyncio.CancelledError

    @property
    def selected_count(self) -> int:
        return len(self._rows)

    @property
    def materials(self) -> list[EvolutionMaterial]:
        """只返回实际读取的正文片段，索引和未读内容不冒充证据。

        Return only body spans actually read; indexes and unread bodies are not evidence.
        """
        return [
            EvolutionMaterial(
                kind="trace",
                title=f"{row.project_id} · {row.session_title} · #{row.item.seq} "
                f"· [{offset}:{offset + len(text)}] · {row.item.title}",
                source=row.source,
                content=text,
                offset=offset,
                total_chars=row.total_chars or 0,
                truncated=not row.complete(),
            )
            for row in self._rows.values()
            for offset, text in row.chunks
        ]

    def restore(self, materials: list[EvolutionMaterial]) -> None:
        """恢复相同冻结选择中已交付的正文，不读取历史或扩大来源。

        Restore delivered body spans from the same frozen selection without reads or added sources.
        """
        for material in materials:
            source = material.source
            if material.kind != "trace" or source.session_id is None or source.seq is None:
                continue
            row = self._rows.get((source.session_id, source.seq))
            if row is None or source.through_seq != row.source.through_seq:
                continue
            if (
                material.offset < 0
                or material.total_chars < material.offset + len(material.content)
                or row.total_chars is not None
                and row.total_chars != material.total_chars
            ):
                # 历史片段损坏只影响该片段，不能将整个调查变为失败。
                # A malformed historical span affects only that span, never the whole investigation.
                self.issues.append(
                    f"已读片段范围不一致，未恢复：{source.session_id} · #{source.seq}"
                )
                continue
            row.total_chars = material.total_chars
            row.remember(material.offset, material.content)

    def coverage(self) -> JsonObject:
        """报告去重后的阅读覆盖，不推测未读正文的长度。

        Report deduplicated read coverage without guessing unread body sizes.
        """
        read = sum(bool(row.chunks) for row in self._rows.values())
        complete = sum(row.complete() for row in self._rows.values())
        return {
            "selected_count": self.selected_count,
            "read_count": read,
            "fully_read_count": complete,
            "partially_read_count": read - complete,
            "unread_count": self.selected_count - read,
            "omitted_count": self.selected_count - complete,
            "read_chars": sum(len(text) for row in self._rows.values() for _, text in row.chunks),
        }

    async def index(
        self, query: str = "", offset: int = 0, limit: int = 30, *, failed_only: bool = False
    ) -> JsonObject:
        """搜索全部轻量索引并分页；筛选不改变总选择与正文阅读统计。

        Search the entire compact index and page it without changing selection or body coverage.
        """
        _validate_page(offset, limit)
        return await asyncio.to_thread(self._index, query, offset, limit, failed_only)

    def _index(self, query: str, offset: int, limit: int, failed_only: bool) -> JsonObject:
        """在工作线程检索正文，排序不改变原始范围。

        Search locally off-loop without changing scope.
        """
        words = query.casefold().split()
        rows = sorted(
            self._rows.values(),
            key=lambda r: (self._priority(r, self.focus), r.item.at, r.item.seq),
            reverse=True,
        )
        matched = []
        for row in rows:
            self._check_stopped()
            haystack = " ".join(
                (
                    row.project_id,
                    row.session_title,
                    row.item.title,
                    row.item.kind,
                    row.item.tool_name or "",
                    row.item.status,
                    row.run_status,
                    row.error_code,
                    row.searchable,
                )
            ).casefold()
            if all(word in haystack for word in words) and (
                not failed_only
                or row.item.is_error
                or row.item.status in {"failed", "interrupted", "budget_exceeded"}
            ):
                matched.append(row)
        page = matched[offset : offset + limit]
        return {
            "items": [
                {**self._metadata(row), "excerpt": self._excerpt(row, query)} for row in page
            ],
            "matched_count": len(matched),
            "offset": offset,
            "next_offset": offset + len(page) if offset + len(page) < len(matched) else None,
            "search_scope": "selected_public_text",
            "recommendations": [
                episode.model_dump(mode="json")
                for episode in self.episodes[offset : offset + limit]
            ],
            "episode_count": len(self.episodes),
            "next_episode_offset": offset + limit if offset + limit < len(self.episodes) else None,
            "coverage": self.coverage(),
            "issues": list(self.issues),
        }

    async def screen(self, focus: str = "") -> None:
        """按焦点、用户纠正和真实失败归组，保留全部记录可回读。

        Group focus hits, user corrections and actual failures while retaining every source.
        """
        self.focus = focus
        self.episodes = await asyncio.to_thread(self._screen, focus)

    def _screen(self, focus: str) -> list[EvolutionEpisode]:
        """线索按代表事件展示，成功对照与相邻证据仍限于原选择。

        Show representative leads with success contrasts and neighbors within the selection.
        """
        groups: dict[tuple[str, str, str], list[_EvidenceRow]] = {}
        rows = sorted(self._rows.values(), key=lambda r: (r.item.at, r.item.seq))
        for row in rows:
            self._check_stopped()
            # 相同错误码只在同一项目和工具内合并；没有错误码时保留消息差异。
            # Merge error codes only within a project/tool; otherwise preserve message differences.
            signature = row.error_code or self._error_signature(row)
            family = signature if row.item.is_error else row.item.status
            if row.item.tool_name is None:
                # 系统目录／生命周期不单独推荐；仍在完整检索中，可作为前后文回读。
                # Catalog/lifecycle entries stay searchable but are not standalone learning leads.
                if (
                    row.item.kind not in {"run.accepted", "assistant.committed", "run.finished"}
                    and not row.item.is_error
                ):
                    continue
                family = f"{row.log.session_id}:{row.item.run_id}"
            groups.setdefault(
                (row.project_id, row.item.tool_name or "conversation", family), []
            ).append(row)
        ordered = sorted(
            groups.values(),
            key=lambda group: (
                max(self._priority(r, focus) for r in group),
                len(group),
                group[-1].item.at,
            ),
            reverse=True,
        )
        episodes = []
        by_run: dict[tuple[str, str | None], list[_EvidenceRow]] = {}
        for row in rows:
            by_run.setdefault((row.log.session_id, row.item.run_id), []).append(row)
        for group in ordered:
            self._check_stopped()
            row = max(group, key=lambda r: (self._priority(r, focus), r.item.at, r.item.seq))
            reasons = []
            priority = self._priority(row, focus)
            if priority[0]:
                reasons.append("与关注点有文本关联")
            if priority[1]:
                reasons.append("用户纠正／反馈线索，需核实")
            if priority[2]:
                reasons.append("记录包含失败状态，根因待查")
            if len(group) > 1:
                reasons.append(f"同类事件 {len(group)} 次，先读代表记录")
            peers = by_run[(row.log.session_id, row.item.run_id)]
            position = peers.index(row)
            related = [*group[:1], *peers[max(0, position - 1) : position + 2]]
            contrast = next(
                (
                    other
                    for other in reversed(peers)
                    if row.item.tool_name
                    and other.item.tool_name == row.item.tool_name
                    and other.item.is_error != row.item.is_error
                ),
                None,
            )
            if contrast:
                related.append(contrast)
                reasons.append("同轮有不同结果可对照")
            sources = {r.source.model_dump_json(): r.source for r in related if r is not row}
            episodes.append(
                EvolutionEpisode(
                    title=row.item.title,
                    reasons=reasons or ["一般记录，按需查阅"],
                    count=len(group),
                    representative=row.source,
                    related=list(sources.values()),
                    excerpt=self._excerpt(row, focus),
                )
            )
        return episodes

    @staticmethod
    def _error_signature(row: _EvidenceRow) -> str:
        """使用公开错误内容归组，不把所有失败混为一个问题。

        Group by public error content, not one bucket for all failures.
        """
        if not row.item.is_error:
            return ""
        for fact in json.loads(row.searchable):
            result = fact.get("result")
            if isinstance(result, dict):
                content = result.get("content", "")
                try:
                    value = json.loads(content)
                    if isinstance(value, dict):
                        return str(value.get("code") or value.get("message") or content)
                except (ValueError, TypeError):
                    return str(content)
        return row.item.title

    @staticmethod
    def _priority(row: _EvidenceRow, focus: str) -> tuple[int, bool, bool]:
        """启发式仅决定阅读顺序，不丢弃材料或阻断作业。

        Heuristics order reading only, never discard evidence or gate work.
        """
        # 请求材料中复制的工具目录和旧上下文不制造虚假的相关性。
        # Copied catalogs and old context in request manifests must not inflate relevance.
        text = (InvestigationEvidence._content(row) + " " + (row.item.tool_name or "")).casefold()
        terms = re.findall(r"[a-z0-9_./-]+|[\u4e00-\u9fff]+", focus.casefold())
        corrections = row.item.kind == "run.accepted" and any(
            word in text
            for word in ("不对", "错误", "应该", "不要", "希望", "instead", "wrong", "please stop")
        )
        return (
            sum(term in text for term in terms),
            corrections,
            row.item.is_error or row.item.status in {"failed", "interrupted", "budget_exceeded"},
        )

    @staticmethod
    def _content(row: _EvidenceRow) -> str:
        """提取当前事件的公开业务内容，排除复制的请求目录。

        Extract the event's public business content, excluding copied request catalogs.
        """
        parts = []
        for fact in json.loads(row.searchable):
            for key in ("prompt", "text", "message"):
                if isinstance(fact.get(key), str):
                    parts.append(fact[key])
            result = fact.get("result")
            if isinstance(result, dict) and isinstance(result.get("content"), str):
                parts.append(result["content"])
            call = fact.get("call")
            if isinstance(call, dict):
                parts.append(json.dumps(call.get("arguments"), ensure_ascii=False))
        return "\n".join(parts) or row.item.title

    @staticmethod
    def _excerpt(row: _EvidenceRow, query: str) -> str:
        """短摘录仅辅助选材，完整内容使用原回读工具。

        A short excerpt guides selection; the original reader provides complete content.
        """
        terms = re.findall(r"[a-z0-9_./-]+|[\u4e00-\u9fff]+", query.casefold())
        text = InvestigationEvidence._content(row)
        matches = [text.casefold().find(term) for term in terms if term in text.casefold()]
        start = max(0, min(matches) - 80) if matches else 0
        return (
            ("…" if start else "")
            + text[start : start + 320]
            + ("…" if len(text) > start + 320 else "")
        )

    async def read(
        self, session_id: str, seq: int, offset: int = 0, limit: int = 8000
    ) -> JsonObject:
        """沿原 Trace 读取选中行的任意正文页，较大页仍复用既有分段读取。

        Read any body page of an authorized trace row, reusing existing chunks for larger pages.
        """
        _validate_page(offset, limit)
        row = self._rows.get((session_id, seq))
        if row is None:
            raise AgentError("TRACE_NOT_FOUND", "该轨迹未被本次调查选中。")
        cursor, parts = offset, []
        while cursor < offset + limit:
            self._check_stopped()
            detail = await asyncio.to_thread(
                trace_detail,
                row.log,
                TraceDetailParams(session_id=session_id, seq=seq, offset=cursor),
            )
            row.total_chars = detail.total_chars
            text = detail.text[: offset + limit - cursor]
            parts.append(text)
            cursor += len(text)
            if not text or cursor >= detail.total_chars:
                break
        body = "".join(parts)
        row.remember(offset, body)
        return {
            **self._metadata(row),
            "text": body,
            "offset": offset,
            "next_offset": cursor if cursor < (row.total_chars or 0) else None,
            "total_chars": row.total_chars,
            "coverage": self.coverage(),
        }

    def _metadata(self, row: _EvidenceRow) -> JsonObject:
        """显示来源项目与真实身份，不泄露原始 provider 对象。

        Show the source project and actual identity without provider-native state.
        """
        return {
            "project_id": row.project_id,
            "session_id": row.log.session_id,
            "session_title": row.session_title,
            "seq": row.item.seq,
            "run_id": row.item.run_id,
            "kind": row.item.kind,
            "title": row.item.title,
            "status": row.item.status,
            "is_error": row.item.is_error,
            "tool_name": row.item.tool_name,
            "run_status": row.run_status,
            "error_code": row.error_code,
            "through_seq": row.source.through_seq,
            "body_read": bool(row.chunks),
            "fully_read": row.complete(),
        }


def _validate_page(offset: int, limit: int) -> None:
    """只拒绝无效分页参数，不将展示默认大小变为读取硬限额。

    Reject invalid page parameters without turning display defaults into read ceilings.
    """
    if offset < 0 or limit < 1:
        raise AgentError("INVALID_TOOL_ARGUMENTS", "offset 不能为负数，limit 必须为正数。")
