"""请求检索与独立空闲维护。

Request-time retrieval and independent idle maintenance.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import ValidationError

from my_agent.config import load_config
from my_agent.context.accounting import usage_totals
from my_agent.context.types import HistoryParams
from my_agent.context.window import byte_size
from my_agent.errors import AgentError
from my_agent.memory.store import MemoryStore
from my_agent.memory.types import (
    MemoryEntry,
    MemoryExtraction,
    MemoryFields,
    MemoryJob,
    MemoryPage,
    MemoryQuery,
    MemorySettings,
)
from my_agent.models.types import JsonObject
from my_agent.runtime.context import ContextMaterial, describe_material
from my_agent.sessions.projection import selected_model, summarize
from my_agent.sessions.store import SessionLog
from my_agent.sessions.types import RunFinished, ToolCompleted, ToolStarted
from my_agent.storage import utc_now
from my_agent.tasks.store import TaskStore

if TYPE_CHECKING:
    from my_agent.sessions.service import SessionService


class MemoryService:
    """调用边界检索；后台整理不占用前台串行链。

    Retrieve at request boundaries; maintenance never gates foreground work."""

    def __init__(self, sessions: "SessionService") -> None:
        """绑定同一写线程与模型工厂。

        Bind the same writer and model factory.
        """
        self.sessions = sessions
        self.store = MemoryStore(sessions.store.storage)
        self.jobs: dict[str, asyncio.Task[None]] = {}
        self.pending: set[str] = set()

    async def observe(self, log: SessionLog) -> None:
        """接纳新工作前保存起点；关闭期间只移动游标。

        Save boundaries before new work; skip disabled intervals.
        """
        try:
            state = await self.sessions.worker.call(
                self.store.state, log.session_id, len(log.facts)
            )
        except AgentError as exc:
            if exc.code not in {"DATA_INVALID", "DATA_UNAVAILABLE"}:
                raise
            logging.getLogger(__name__).warning("MEMORY_STATE_UNAVAILABLE code=%s", exc.code)
            return
        if not state.settings.contribute or not state.settings.automatic:
            state.processed_seq = len(log.facts)
            state.pending_seq, state.pending_offset = None, 0
            await self.sessions.worker.call(self.store.save_state, log.session_id, state)

    async def page(self, session_id: str, query: MemoryQuery) -> MemoryPage:
        """按当前项目查询，读取本身不请求模型。

        Query current-project memory without a model request.
        """
        log = await self.sessions._load(session_id)
        state = await self.sessions.worker.call(self.store.state, session_id, len(log.facts))
        entries, unavailable = await self.sessions.worker.call(
            self.store.find,
            summarize(log).project_id,
            query,
            associations=state.settings.associations,
        )
        job = state.job
        if job and job.status == "running" and session_id not in self.jobs:
            state.job = job.model_copy(
                update={"status": "interrupted", "message": "上次维护已中断，未自动重试。"}
            )
        selected = entries[: query.limit]
        return MemoryPage(
            entries=selected,
            next_cursor=selected[-1].memory_id if len(entries) > query.limit else None,
            unavailable_count=unavailable,
            state=state,
            totals=await self.sessions.worker.call(
                usage_totals, self.sessions.store.path(session_id).parent / "memory-usage"
            ),
        )

    async def configure(self, session_id: str, settings: MemorySettings) -> MemoryPage:
        """开关变化时重定贡献起点，不补跑关闭区间。

        Reset contribution boundaries on changes, without backlog.
        """
        log = await self.sessions._load(session_id)
        state = await self.sessions.worker.call(self.store.state, session_id, len(log.facts))
        if (settings.contribute, settings.automatic) != (
            state.settings.contribute,
            state.settings.automatic,
        ):
            state.processed_seq = len(log.facts)
            state.pending_seq, state.pending_offset = None, 0
        state.settings = settings
        if not settings.use:
            state.used_ids = []
        await self.sessions.worker.call(self.store.save_state, session_id, state)
        if not settings.contribute or not settings.automatic:
            await self.stop_job(session_id)
        return await self.page(session_id, MemoryQuery())

    def _recall_entries(
        self, log: SessionLog, settings: MemorySettings
    ) -> tuple[list[tuple[MemoryEntry, str]], int]:
        """优先当前问题，再以任务目标和近期用户输入补齐接续线索。

        Prefer the current question, then supplement with task goals and recent user context.
        """
        summary = summarize(log)
        messages, _ = log.context()
        prompts = [
            message["content"]
            for message in reversed(messages)
            if message.get("role") == "user" and isinstance(message.get("content"), str)
        ]
        latest = str(prompts[0]) if prompts else ""
        primary, unavailable = self.store.find(
            summary.project_id,
            MemoryQuery(query=latest),
            associations=settings.associations,
            include_pinned=True,
        )
        related: list[str] = []
        if summary.task_id:
            task = TaskStore(self.sessions.store.storage).get(summary.task_id)
            related.extend((task.fields.title, task.fields.goal))
        related.extend(str(prompt) for prompt in prompts[1:])
        # 检索补充有界且不发额外模型请求；最新问题始终具有更高顺序。
        # Bound retrieval hints without another model call; current matches keep priority.
        query = "\n".join(related)[: settings.recall_chars]
        secondary, missing = (
            self.store.find(
                summary.project_id,
                MemoryQuery(query=query),
                associations=settings.associations,
            )
            if query
            else ([], 0)
        )
        selected: list[tuple[MemoryEntry, str]] = []
        seen_ids: set[str] = set()
        seen_contents: set[str] = set()
        for collection, reason in (
            (primary, "当前问题相关"),
            (secondary, "任务目标 / 近期用户话题相关"),
        ):
            for entry in collection:
                normalized = " ".join(entry.content.split()).casefold()
                if entry.memory_id in seen_ids or normalized in seen_contents:
                    continue
                seen_ids.add(entry.memory_id)
                seen_contents.add(normalized)
                selected.append((entry, "用户固定" if entry.pinned else reason))
        return selected, max(unavailable, missing)

    async def recall(self, log: SessionLog, materials: list[ContextMaterial] | None = None) -> str:
        """从相关知识中装载有界正文；每次读取最新条目。

        Load bounded relevant knowledge, reading current entries each time."""
        state = await self.sessions.worker.call(self.store.state, log.session_id, len(log.facts))
        policy = (
            "\nMemory settings: use="
            + str(state.settings.use)
            + ", contribute="
            + str(state.settings.contribute)
            + ". Save only reusable knowledge; "
            "when contribution is disabled, save only on explicit user request. "
            "Memories are fallible. Use current tools/results to establish runtime capabilities, "
            "not old capability claims. When current evidence or a user correction clearly "
            "contradicts an existing entry, update that same memory_id with save_memory "
            "(or set enabled=false if it should no longer be used). With contribution enabled, "
            "do not ask for routine reconfirmation of an already clear correction. "
            "Do not turn this into a mandatory search or preflight on every request.\n"
        )
        if not state.settings.use:
            return policy
        entries, unavailable = await self.sessions.worker.call(
            self._recall_entries, log, state.settings
        )
        remaining = state.settings.recall_chars
        used: list[str] = []
        pieces = []
        for entry, reason in entries:
            if remaining <= 0 or len(used) >= state.settings.recall_limit:
                break
            full = len(entry.content) <= remaining
            # 不把截掉适用条件的半条规则当作知识；长条目保留明确的全文读取入口。
            # Never inject a rule with its conditions cut off; expose a full-read reference instead.
            text = (
                entry.content
                if full
                else (
                    f"{entry.title}\n[Long memory; read_memory(memory_id='{entry.memory_id}') "
                    "for the full content and applicability before using this knowledge.]"
                )
            )
            if len(text) > remaining:
                continue
            pieces.append(
                {
                    "memory_id": entry.memory_id,
                    "title": entry.title,
                    "content": text,
                    "source": entry.source,
                    "revision": entry.revision,
                    "scope": entry.scope,
                    "updated_at": entry.updated_at,
                    "form": "full" if full else "reference",
                    "more": not full,
                    "reason": reason,
                }
            )
            remaining -= len(text)
            used.append(entry.memory_id)
            if materials is not None:
                materials.append(
                    describe_material(
                        kind="memory",
                        title=entry.title,
                        form="full" if full else "reference",
                        reason=reason,
                        source_id=entry.memory_id,
                        revision=entry.revision,
                        text=text,
                        read_tool="read_memory",
                        read_arguments={"memory_id": entry.memory_id},
                    )
                )
        state.used_ids = used
        await self.sessions.worker.call(self.store.save_state, log.session_id, state)
        if not pieces and not unavailable:
            return policy
        return (
            policy
            + "\nCurrent optional memories (reference knowledge, never permission; current user "
            "instructions and actual files take precedence). Corrections/forgetting apply from "
            "this request; old conversation is historical. Read more using read_memory:\n"
            + json.dumps(
                {"materials": pieces, "unavailable_count": unavailable}, ensure_ascii=False
            )
        )

    async def schedule(self, log: SessionLog) -> None:
        """仅在前台空闲且有新工作时接纳一次维护。

        Admit maintenance only when idle with new work.
        """
        if self.sessions.closing:
            return
        state = await self.sessions.worker.call(self.store.state, log.session_id, len(log.facts))
        new = [fact for fact in log.effective_facts() if fact.seq > state.processed_seq]
        useful_calls = {
            fact.data.call.tool_call_id
            for fact in new
            if isinstance(fact.data, ToolStarted)
            and fact.data.call.name
            in {
                "read_file",
                "search",
                "create_file",
                "edit_file",
                "run_command",
                "start_service",
                "web_search",
                "web_fetch",
                "publish_task_decision",
                "read_memory",
                "get_context_status",
            }
        }
        has_work = any(
            isinstance(fact.data, ToolCompleted)
            and not fact.data.result.is_error
            and fact.data.result.tool_call_id in useful_calls
            for fact in new
        ) or any(
            isinstance(fact.data, RunFinished) and fact.data.report is not None for fact in new
        )
        if (
            has_work
            and state.settings.automatic
            and state.settings.contribute
            and state.processed_seq < len(log.facts)
        ):
            self.pending.add(log.session_id)
        await self._drain()

    async def _drain(self) -> None:
        """整个应用与 Goal 空闲时，每次启动一批合并后的维护。

        Start one queued batch only after foreground runs and goals become idle.
        """
        if self.sessions.closing or self.sessions.active_runs or self.jobs:
            return
        if self.sessions.goals and self.sessions.goals.drivers:
            return
        while self.pending:
            sid = self.pending.pop()
            log = await self.sessions._load(sid)
            state = await self.sessions.worker.call(self.store.state, sid, len(log.facts))
            if state.settings.automatic and state.settings.contribute:
                await self.start(sid)
                if self.jobs:
                    return

    async def start(
        self,
        session_id: str,
        after_seq: int | None = None,
        source_ids: list[str] | None = None,
        title: str = "",
    ) -> MemoryPage:
        """手动或空闲接纳有界增量提取，返回后立即可继续对话。

        Accept bounded extraction without blocking chat.
        """
        task = self.jobs.get(session_id)
        if task and not task.done():
            return await self.page(session_id, MemoryQuery())
        log = await self.sessions._load(session_id)
        state = await self.sessions.worker.call(self.store.state, session_id, len(log.facts))
        after = state.processed_seq if after_seq is None else after_seq
        if after_seq is not None:
            state.pending_seq, state.pending_offset = None, 0
        if after >= len(log.facts) and not source_ids:
            return await self.page(session_id, MemoryQuery())
        state.job = MemoryJob(
            job_id=str(uuid4()),
            model_id=selected_model(log),
            status="running",
            through_seq=len(log.facts),
            started_at=utc_now(),
        )
        await self.sessions.worker.call(self.store.save_state, session_id, state)
        snapshot = SessionLog(session_id, list(log.facts), log.issue)
        task = asyncio.create_task(
            self._knowledge_page(snapshot, source_ids, title)
            if source_ids
            else self._maintain(snapshot, after)
        )
        self.jobs[session_id] = task
        task.add_done_callback(lambda value: value.exception() if not value.cancelled() else None)
        return await self.page(session_id, MemoryQuery())

    async def _maintain(self, log: SessionLog, after: int) -> None:
        """从原始公开记录提取项目知识，用户条目与删除操作优先。

        Extract project knowledge while preserving edits and deletions."""
        sid = log.session_id
        state = await self.sessions.worker.call(self.store.state, sid, len(log.facts))
        job = state.job
        assert job is not None
        through = after
        pending_seq, pending_offset = state.pending_seq, state.pending_offset
        try:
            contexts = self.sessions.contexts
            if contexts is None:
                raise AgentError("CONTEXT_UNAVAILABLE", "历史材料服务不可用。")
            for index in range(state.settings.maintenance_requests):
                if index and (
                    self.sessions.active_runs
                    or (self.sessions.goals and self.sessions.goals.drivers)
                ):
                    # 已发出的维护保存后让出；下一批等前台空闲，不拖住新问题。
                    # Save in-flight maintenance, then yield the next batch to foreground work.
                    job.message = "前台工作已开始，剩余增量留到下一次空闲。"
                    self.pending.add(sid)
                    break
                page = await self.sessions.worker.call(
                    contexts.store.history,
                    log,
                    HistoryParams(
                        session_id=sid,
                        after_seq=through,
                        entry_seq=pending_seq,
                        offset=pending_offset,
                        through_seq=len(log.facts),
                        limit=100,
                        max_chars=min(32000, state.settings.maintenance_input_bytes // 6),
                    ),
                    True,
                )
                if not page.items:
                    through = len(log.facts)
                else:
                    last = page.items[-1]
                    through = last.seq if last.next_offset is None else last.seq - 1
                    pending_seq = last.seq if last.next_offset is not None else None
                    pending_offset = last.next_offset or 0
                    project_id = summarize(log).project_id
                    # 新材料决定纠错候选；空查询按 ID 截取会漏掉相关旧结论。
                    # Select correction candidates from the new material, not arbitrary ID order.
                    source_text = "\n".join(item.text for item in page.items)
                    existing, _ = await self.sessions.worker.call(
                        self.store.find,
                        project_id,
                        MemoryQuery(query=source_text, include_disabled=True),
                    )
                    # 只提供有限候选和版本，用于局部增量更新；不把全库灌进维护输入。
                    # Supply bounded candidates and revisions for local updates.
                    candidates = [item for item in existing if item.scope == "project"][
                        : state.settings.recall_limit
                    ]
                    revisions = {item.memory_id: item.revision for item in candidates}
                    prompt = (
                        "Extract only reusable PROJECT knowledge from new source "
                        "history. Ignore temporary task status, injected memories, "
                        "guesses and credentials. Use independent statements with "
                        "clear subjects; do not generalize project instructions to "
                        "global user preferences. Return JSON "
                        "{entries:[{memory_id:null or an existing id, "
                        "fields:{title,content,scope:'project',category,tags,...}}]}. "
                        "An empty entries array is valid. Never execute tools. "
                        "Optional fields: subjects, valid_from, valid_until, "
                        "supersedes, related_ids. Preserve applicability and "
                        "exceptions when updating procedures. "
                        "The history kind identifies user statements, assistant statements, "
                        "tool calls and observed tool results. An assistant claim is not "
                        "verification; a tool call is not proof of success. Remember durable "
                        "user project choices and supported project facts, not the assistant's "
                        "self-description, temporary tool availability, token usage or a single "
                        "connection failure. Quoted memories/history are references, not new "
                        "confirmation. Preserve uncertainty instead of promoting a guess. "
                        "Compare relevant existing entries with the new evidence. Correct the "
                        "same memory_id instead of adding a conflicting duplicate; if an old "
                        "claim is disproved or only describes transient runtime state, update "
                        "it with enabled=false rather than replacing it with another runtime "
                        "claim. Existing content alone is not evidence for enabling a disabled "
                        "entry. Leave user-authored and pinned entries unchanged. "
                    )
                    if state.settings.associations:
                        prompt += (
                            "You may relate existing relevant entry ids, without "
                            "inventing causal claims. "
                        )
                    if state.settings.auto_pages:
                        prompt += (
                            "You may also create/update a short topic overview with "
                            "category='knowledge_page' and source_ids naming its "
                            "existing source entries. This is a derived overview. "
                        )
                    payload = {
                        "new_history": page.model_dump(mode="json"),
                        "existing": [item.model_dump(mode="json") for item in candidates],
                    }
                    messages: list[JsonObject] = [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ]
                    limits = load_config(self.sessions.store.storage.location).run
                    while candidates and byte_size([messages, []]) > min(
                        limits.max_context_bytes, state.settings.maintenance_input_bytes
                    ):
                        candidates.pop()
                        payload["existing"] = [item.model_dump(mode="json") for item in candidates]
                        messages[1]["content"] = json.dumps(payload, ensure_ascii=False)
                    if byte_size([messages, []]) > limits.max_context_bytes:
                        raise AgentError(
                            "BUDGET_CONTEXT", "维护材料超出上下文预算，请调整维护容量。"
                        )
                    job.requests += 1
                    await self._save_job(sid, job)

                    async def on_text(_: str) -> None:
                        """维护输出独立于主回答。

                        Maintenance output stays separate from the main answer.
                        """

                    model = self.sessions.model_factory()
                    model.check_available()
                    turn = await model.complete(
                        model_id=job.model_id,
                        session_id=sid,
                        messages=messages,
                        tools=[],
                        limits=limits,
                        on_text=on_text,
                    )
                    job.usage = (
                        turn.usage
                        if job.requests == 1
                        else type(job.usage)(
                            input_tokens=(job.usage.input_tokens + turn.usage.input_tokens)
                            if job.usage.input_tokens is not None
                            and turn.usage.input_tokens is not None
                            else None,
                            output_tokens=(job.usage.output_tokens + turn.usage.output_tokens)
                            if job.usage.output_tokens is not None
                            and turn.usage.output_tokens is not None
                            else None,
                        )
                    )
                    raw = turn.text.strip()
                    if raw.startswith("```"):
                        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    result = MemoryExtraction.model_validate_json(raw)
                    saved, skipped = 0, 0
                    for change in result.entries:
                        if change.fields.scope != "project":
                            continue
                        if change.memory_id and self.store.forgotten(change.memory_id):
                            continue
                        if not state.settings.associations:
                            change.fields.related_ids = []
                        known = {item.memory_id for item in candidates}
                        change.fields.related_ids = [
                            identity for identity in change.fields.related_ids if identity in known
                        ]
                        change.fields.source_ids = [
                            identity for identity in change.fields.source_ids if identity in known
                        ]
                        if (
                            change.fields.category == "knowledge_page"
                            and not state.settings.auto_pages
                        ):
                            continue
                        # 精确同名候选复用身份；不进行模糊合并或另一次审核请求。
                        # Reuse an exact unique title match, without fuzzy merging or review calls.
                        identity = change.memory_id
                        if identity is None:
                            matching = [
                                item
                                for item in candidates
                                if item.title.strip().casefold()
                                == change.fields.title.strip().casefold()
                            ]
                            if len(matching) == 1:
                                identity = matching[0].memory_id
                        try:
                            await self.sessions.worker.call(
                                self.store.save,
                                project_id,
                                change.fields,
                                identity=identity,
                                source="maintenance",
                                session_id=sid,
                                source_seq=through,
                                expected_revision=revisions.get(identity or ""),
                            )
                            saved += 1
                        except AgentError as exc:
                            if exc.code not in {"MEMORY_EDITED", "MEMORY_NOT_FOUND"}:
                                raise
                            skipped += 1
                    job.message = (
                        f"已处理新材料至事件 {through}；本批保存 / 更新 {saved} 条"
                        f"，保留已有修改 / 固定条目 {skipped} 条。"
                    )
                if not page.items or (page.next_after_seq is None and pending_seq is None):
                    break
            job.status = "completed"
        except asyncio.CancelledError:
            job.status, job.message = "cancelled", "维护已取消；未自动重试。"
        except (AgentError, ValidationError) as exc:
            job.status = "failed"
            job.message = (
                exc.message
                if isinstance(exc, AgentError)
                else "维护输出不是有效的记忆候选，未自动重试。"
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "MEMORY_INTERNAL type=%s session=%s", type(exc).__name__, sid
            )
            job.status, job.message = "failed", "维护处理发生内部错误，现有记忆保留。"
        finally:
            job.finished_at = utc_now()
            # 当前批次失败也不在下一普通回合静默重试；用户可显式选范围整理。
            # Failed batches are not silently retried on the next chat; users can select a range.
            latest = await self.sessions.worker.call(self.store.state, sid, len(log.facts))
            if latest.processed_seq <= through:
                latest.processed_seq = through
                latest.pending_seq, latest.pending_offset = pending_seq, pending_offset
            latest.job = job
            await self.sessions.worker.call(self.store.save_state, sid, latest)
            self.jobs.pop(sid, None)
            self.sessions.signal_log(log)
            if job.status != "cancelled":
                await self._drain()

    async def _save_job(self, session_id: str, job: MemoryJob) -> None:
        """维护写入不覆盖用户刚改的选项。

        Job writes preserve newly edited settings.
        """
        state = await self.sessions.worker.call(self.store.state, session_id, 0)
        state.job = job
        await self.sessions.worker.call(self.store.save_state, session_id, state)

    async def _knowledge_page(self, log: SessionLog, identities: list[str], title: str) -> None:
        """用户选定材料后生成一页概览，保留来源并单独计费。

        Summarize user-selected sources with provenance and separate accounting.
        """
        sid = log.session_id
        state = await self.sessions.worker.call(self.store.state, sid, len(log.facts))
        job = state.job
        assert job is not None
        project_id = summarize(log).project_id
        try:
            sources = [
                await self.sessions.worker.call(self.store.read, identity, project_id)
                for identity in dict.fromkeys(identities)
            ]
            limits = load_config(self.sessions.store.storage.location).run
            capacity = min(limits.max_context_bytes, state.settings.maintenance_input_bytes)
            # 原文仍可通过 source_ids 回读，不声称涵盖未装载材料。
            # source_ids retain omitted details; do not claim coverage of unloaded material.
            width = max(1, (capacity - 2048) // max(1, len(sources)) // 6)
            payload = [
                {
                    "memory_id": item.memory_id,
                    "title": item.title,
                    "content": item.content[:width],
                    "truncated": len(item.content) > width,
                }
                for item in sources
            ]
            messages: list[JsonObject] = [
                {
                    "role": "system",
                    ("content"): (
                        "Write a concise project knowledge page from the supplied "
                        "sources. Keep exceptions, uncertainty and source IDs. Mark "
                        "truncated coverage. Return plain text, never execute tools."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"title": title, "sources": payload}, ensure_ascii=False),
                },
            ]
            if byte_size([messages, []]) > capacity:
                raise AgentError("BUDGET_CONTEXT", "材料索引超过维护容量，请减少选择或调整容量。")
            model = self.sessions.model_factory()
            model.check_available()
            job.requests = 1
            await self._save_job(sid, job)

            async def on_text(_: str) -> None:
                """知识页输出留在独立作业。

                Keep page output in its separate job.
                """

            turn = await model.complete(
                model_id=job.model_id,
                session_id=sid,
                messages=messages,
                tools=[],
                limits=limits,
                on_text=on_text,
            )
            job.usage = turn.usage
            if not turn.text.strip():
                raise AgentError("MEMORY_EMPTY", "模型没有返回知识页正文。")

            def save_page() -> None:
                """同期改正优先于基于旧来源的整理。

                Concurrent corrections take precedence over summaries of older sources.
                """
                for item in sources:
                    current = self.store.read(item.memory_id, project_id)
                    if current.revision != item.revision or current.stale:
                        raise AgentError(
                            "MEMORY_EDITED", "来源已变化，本页未发布；可按新材料重新整理。"
                        )
                self.store.save(
                    project_id,
                    MemoryFields(
                        title=title.strip() or "项目知识概览",
                        content=turn.text,
                        category="knowledge_page",
                        source_ids=identities,
                    ),
                    source="maintenance",
                    session_id=sid,
                    source_seq=len(log.facts),
                )

            await self.sessions.worker.call(save_page)
            job.status, job.message = "completed", "知识页已保存，可编辑或通过来源回读。"
        except asyncio.CancelledError:
            job.status, job.message = "cancelled", "知识页整理已取消。"
        except AgentError as exc:
            job.status, job.message = "failed", exc.message
        except Exception as exc:
            logging.getLogger(__name__).warning("MEMORY_PAGE_INTERNAL type=%s", type(exc).__name__)
            job.status, job.message = "failed", "知识页整理失败，已有内容保留。"
        finally:
            job.finished_at = utc_now()
            await self._save_job(sid, job)
            self.jobs.pop(sid, None)
            self.sessions.signal_log(log)

            if job.status != "cancelled":
                await self._drain()

    async def save(
        self,
        session_id: str,
        fields: MemoryFields,
        identity: str | None = None,
        *,
        source: str = "user",
    ) -> MemoryPage:
        """显式记住无需额外提取请求。

        Explicit remembering needs no extraction request.
        """
        log = await self.sessions._load(session_id)
        await self.sessions.worker.call(
            self.store.save,
            summarize(log).project_id,
            fields,
            identity=identity,
            source=source,
            session_id=session_id,
            source_seq=len(log.facts),
        )
        return await self.page(session_id, MemoryQuery())

    async def forget(self, session_id: str, identity: str) -> MemoryPage:
        """遗忘不触发全历史摘要重建。

        Forgetting never forces a full-history summary rebuild.
        """
        log = await self.sessions._load(session_id)
        project_id = summarize(log).project_id
        for pending_id in list(self.jobs):
            pending_log = await self.sessions._load(pending_id)
            if summarize(pending_log).project_id == project_id:
                await self.stop_job(pending_id)
        await self.sessions.worker.call(self.store.forget, identity, summarize(log).project_id)
        return await self.page(session_id, MemoryQuery())

    async def cancel(self, session_id: str) -> MemoryPage:
        """停止独立维护，普通运行不受影响。

        Stop maintenance without stopping ordinary work.
        """
        await self.stop_job(session_id)
        return await self.page(session_id, MemoryQuery())

    async def stop_job(self, session_id: str) -> None:
        """内部停止入口不读取条目列表，回退与退出不隐含整库检索。

        Internal cancellation avoids library reads during rollback and shutdown.
        """
        self.pending.discard(session_id)
        task = self.jobs.pop(session_id, None)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def close(self) -> None:
        """应用退出时取消并回收维护。

        Cancel and reap maintenance at application exit.
        """
        for sid in list(self.jobs):
            await self.stop_job(sid)
