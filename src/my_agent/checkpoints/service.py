"""代码恢复、有效历史与派生记忆共用一个接续入口。

One restoration entry coordinates code, effective history and derived memory provenance.
"""

from typing import TYPE_CHECKING
from uuid import uuid4

from my_agent.checkpoints.types import (
    ConversationRestored,
    FileCheckpoint,
    FileCheckpointSummary,
    FileSnapshot,
    PreviewCheckpointParams,
    RestoreCheckpointParams,
    RestorePreview,
    RestoreReceipt,
    RestoreResult,
)
from my_agent.errors import AgentError
from my_agent.sessions.projection import summarize
from my_agent.sessions.types import RunAccepted
from my_agent.storage import read_document, utc_now, write_document

if TYPE_CHECKING:
    from my_agent.sessions.service import SessionService
    from my_agent.sessions.store import SessionLog


class RollbackService:
    """恢复是显式操作；逐文件保留结果，不改写原事件或 Git。

    Restoration is explicit and records per-file outcomes without rewriting events or Git.
    """

    def __init__(self, sessions: "SessionService") -> None:
        """复用当前会话锁、单写者及代码检查点。 Reuse session locks, writer and code snapshots."""
        self.sessions = sessions
        self.store = sessions.checkpoints

    def _record(
        self, log: "SessionLog", checkpoint_id: str, current_run: str | None = None
    ) -> FileCheckpoint:
        """只串联当前有效分支，并核实项目归属。

        Compose only the effective branch within its project.
        """
        runs = {
            fact.run_id
            for fact in log.effective_facts()
            if isinstance(fact.data, RunAccepted) and fact.run_id
        }
        runs.discard(current_run or "")
        record = self.store.combine(log.session_id, checkpoint_id, runs)
        if record.summary.project_id != summarize(log).project_id:
            raise AgentError("CHECKPOINT_PROJECT", "检查点不属于此会话项目。")
        return record

    async def preview(
        self, params: PreviewCheckpointParams, current_run: str | None = None
    ) -> RestorePreview:
        """读取实际文件进行预览，不更改运行或会话。 Preview current files without state changes."""
        log = await self.sessions.worker.call(self.sessions.store.load, params.session_id)
        record = await self.sessions.worker.call(
            self._record, log, params.checkpoint_id, current_run
        )
        root = await self.sessions.validate_project(record.summary.project_id)
        return await self.sessions.worker.call(self.store.preview, record, root)

    async def restore(
        self, params: RestoreCheckpointParams, current_run: str | None = None
    ) -> RestoreResult:
        """停止独立维护后恢复选定代码；只有结果完整才切换有效对话。

        Stop independent maintenance, restore selected code, then rewind only a complete result.
        """
        sessions = self.sessions
        receipt = self.store.path(params.session_id, params.operation_id).with_suffix(".receipt")
        if receipt.exists():
            previous: RestoreReceipt = await sessions.worker.call(
                read_document, receipt, RestoreReceipt
            )
            if previous.params != params:
                raise AgentError("OPERATION_CONFLICT", "恢复操作身份对应不同参数，请刷新后重试。")
            if previous.completed:
                return previous.result
            log = await sessions.worker.call(sessions.store.load, params.session_id)
            fact = next(
                (
                    f.data
                    for f in log.facts
                    if isinstance(f.data, ConversationRestored)
                    and f.data.operation_id == params.operation_id
                ),
                None,
            )
            if fact:
                # 事实已写入但回执尚未落盘时只补回执，绝不重复文件副作用。
                # Reconcile a committed fact after a lost receipt, never replay file effects.
                previous.result.rewound = fact.before_seq is not None
                previous.result.message = fact.message
                previous.result.prompt = next(
                    (
                        f.data.prompt
                        for f in log.facts
                        if f.seq == fact.before_seq and isinstance(f.data, RunAccepted)
                    ),
                    "",
                )
                previous.completed = True
                await sessions.worker.call(write_document, receipt, previous)
            return previous.result
        active = sessions.active_for(params.session_id)
        if active and (active.run_id != current_run or params.mode != "code"):
            raise AgentError("CHECKPOINT_RUNNING", "请先停止当前运行再恢复；其他会话的工作保持。")
        if sessions.goals and not current_run:
            await sessions.goals.pause_for_plan(params.session_id)
        if sessions.contexts:
            await sessions.contexts.stop_job(params.session_id)
        if sessions.memory:
            await sessions.memory.stop_job(params.session_id)
        async with sessions.lock:
            active = sessions.active_for(params.session_id)
            if active and active.run_id != current_run:
                raise AgentError("CHECKPOINT_RUNNING", "会话已开始新运行，请停止后恢复。")
            log = await sessions._load(params.session_id)
            record = await sessions.worker.call(
                self._record, log, params.checkpoint_id, current_run
            )
            root = await sessions.validate_project(record.summary.project_id)
            preview = await sessions.worker.call(self.store.preview, record, root)
            undo = FileCheckpoint(
                summary=FileCheckpointSummary(
                    checkpoint_id=str(uuid4()),
                    session_id=params.session_id,
                    project_id=record.summary.project_id,
                    run_id=None,
                    before_seq=len(log.facts) + 1,
                    title="撤销恢复：" + record.summary.title,
                    kind="restore",
                    status="capturing",
                    created_at=utc_now(),
                ),
                before=FileSnapshot(),
                after=FileSnapshot(),
            )
            result = RestoreResult(
                files=preview.files,
                undo_checkpoint_id=undo.summary.checkpoint_id,
                rewound=False,
                message="恢复操作尚未全部完成；按文件结果核对，可使用撤销恢复检查点。",
            )
            journal = RestoreReceipt(params=params, result=result)

            def apply() -> None:
                """保存每个文件的反向起点再写入；冲突不影响其他文件。

                Persist undo bytes before writing; local conflicts do not block other files.
                """
                assert record.after is not None and undo.after is not None
                self.store.save(undo)
                write_document(receipt, journal)
                for item in preview.files:
                    if params.paths is not None and item.path not in params.paths:
                        item.status, item.message = "skipped", "未选择此文件。"
                        continue
                    if item.source == "other_session":
                        item.status, item.message = (
                            "skipped",
                            "包含其他会话的已记录修改，保持原文件。",
                        )
                        continue
                    if item.source == "observed" and not params.include_observed:
                        item.status, item.message = (
                            "skipped",
                            "请求期间观察到变化，作者未知；可在预览中明确选择恢复。",
                        )
                        continue
                    if item.status not in {"ready", "unchanged"}:
                        continue
                    try:
                        target = self.store.target(root, item.path)
                        current = target.read_bytes() if target.exists() else None
                        desired = self.store.reverse(
                            self.store.get(record.before.files.get(item.path)),
                            self.store.get(record.after.files.get(item.path)),
                            current,
                        )
                        if current == desired:
                            item.status = "unchanged"
                            continue
                        if current is not None:
                            undo.before.files[item.path] = self.store.put(current)
                        if desired is not None:
                            undo.after.files[item.path] = self.store.put(desired)
                        self.store.save(undo)
                        self.store.write(target, current, desired)
                        item.status = "restored"
                    except (AgentError, OSError) as exc:
                        item.status = (
                            "conflict"
                            if isinstance(exc, AgentError) and "CONFLICT" in exc.code
                            else "failed"
                        )
                        item.message = (
                            exc.message if isinstance(exc, AgentError) else "文件保存失败。"
                        )
                        # 只记录已完成恢复的反向变更，失败项不能变成新的可撤销修改。
                        # Failed writes must not masquerade as completed undo changes.
                        undo.before.files.pop(item.path, None)
                        undo.after.files.pop(item.path, None)
                    write_document(receipt, journal)
                undo.summary.changed_files = len(self.store.changes(undo))
                undo.summary.status = (
                    "partial"
                    if any(f.status in {"conflict", "failed"} for f in preview.files)
                    else "ready"
                )
                self.store.save(undo)

            await sessions.worker.call(apply)
            restored = [item.path for item in preview.files if item.status == "restored"]
            complete = all(item.status in {"restored", "unchanged"} for item in preview.files)
            rewound = (
                params.mode == "conversation" and complete and record.summary.kind == "request"
            )
            prompt = next(
                (
                    f.data.prompt
                    for f in log.facts
                    if f.seq == record.summary.before_seq and isinstance(f.data, RunAccepted)
                ),
                "",
            )
            message = (
                "已覆盖代码按检查点恢复；从所选消息之前重新开始，旧分支仅供历史查阅。"
                if rewound
                else "已处理所选代码恢复，对话保留。请按文件结果查看未恢复项；"
                "后续执行先读取当前代码。"
            )
            if preview.issues:
                message += " 检查点存在未覆盖内容，详情见覆盖范围说明。"
            contexts = sessions.contexts
            if contexts:

                def reset_context() -> None:
                    """存档旧摘要，当前窗口不再采用它们。

                    Archive obsolete summaries before excluding them.
                    """
                    state = contexts.store.read(params.session_id)
                    if rewound:
                        write_document(receipt.with_suffix(".context"), state)
                        state.checkpoints = []
                        state.previews = []
                    state.job = None
                    contexts.store.save(params.session_id, state)

                await sessions.worker.call(reset_context)
            if sessions.memory and (restored or rewound):
                await sessions.worker.call(self._memory, log, record.summary.before_seq)
            await sessions.worker.call(
                sessions.store.append,
                log,
                ConversationRestored(
                    operation_id=params.operation_id,
                    checkpoint_id=params.checkpoint_id,
                    before_seq=record.summary.before_seq if rewound else None,
                    paths=restored,
                    message=message + (" 恢复文件：" + ", ".join(restored) if restored else ""),
                ),
                None,
            )
            sessions.last_log = log
            result.rewound, result.prompt, result.message = (
                rewound,
                prompt if rewound else "",
                message,
            )
            journal.completed = True
            await sessions.worker.call(write_document, receipt, journal)
            sessions.signal_log(log)
            return result

    def _memory(self, log: "SessionLog", before_seq: int) -> None:
        """只处理该来源的自动结论；用户条目和独立多来源知识保留。

        Invalidate derived conclusions, retaining user and independent sources.
        """
        memory = self.sessions.memory
        if memory is None:
            return
        memory.store.invalidate_source(log.session_id, before_seq, len(log.facts))
        state = memory.store.state(log.session_id, len(log.facts))
        state.pending_seq, state.pending_offset, state.job = None, 0, None
        # 已放弃的旧区段不重新排队；新事件序号仍单调增长。
        # Abandoned ranges are not requeued; new fact sequences remain monotonic.
        state.processed_seq = len(log.facts)
        memory.store.save_state(log.session_id, state)
