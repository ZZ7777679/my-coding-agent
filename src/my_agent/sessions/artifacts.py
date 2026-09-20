"""核对本会话的当前成果，只读取，不执行或重放项目动作。

Inspect current session artifacts without executing or replaying project actions.
"""

import asyncio
import hashlib
import threading
from pathlib import Path

from my_agent.changes.store import ChangeStore
from my_agent.changes.types import ChangeSummary
from my_agent.errors import AgentError
from my_agent.execution.service import ProgramService
from my_agent.execution.types import GetProgramParams, ProgramSummary
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.pairing import PendingTool
from my_agent.sessions.recovery_types import ToolObservation
from my_agent.tools.read_only import ReadTools
from my_agent.worker import BusinessWorker


class ArtifactInspector:
    """组合已有成果存储和受管程序服务，不通过旧 PID 接管进程。

    Compose existing artifact stores and owned programs without reclaiming historical PIDs.
    """

    def __init__(
        self, changes: ChangeStore, programs: ProgramService, worker: BusinessWorker
    ) -> None:
        """注入同一数据根的服务。 Inject services sharing the same application data root."""
        self.changes, self.programs, self.worker = changes, programs, worker

    def _changes(self, session_id: str) -> tuple[list[ChangeSummary], int]:
        """遍历已有分页，不把第一页缺失当作没有成果。

        Traverse existing pages instead of treating absence from the first page as no artifact.
        """
        cursor = None
        found: list[ChangeSummary] = []
        unavailable = 0
        while True:
            page = self.changes.list(session_id, cursor, 100)
            found.extend(page.changes)
            unavailable += page.unavailable_count
            cursor = page.next_cursor
            if cursor is None:
                return found, unavailable

    async def file(self, root: Path, limits: RunLimits, record: ChangeSummary) -> ToolObservation:
        """按现有文件策略核对当前 hash，历史 applied 与磁盘现状分开表示。

        Check current hashes under file policy; historical apply and disk state stay distinct.
        """
        result = ToolObservation(
            state="observed",
            message="已读取文件修改记录；当前内容不代表原工具响应已经保存。",
            artifact_id=record.change_id,
            artifact_type="file",
            path=record.path,
            recorded_status=record.status,
        )
        reader = ReadTools(root, limits, threading.Event())
        try:
            _, raw, _ = await asyncio.to_thread(reader._read, record.path)
            # 摘要仅用于中断后的状态观察，不参与编辑准入。
            # Digests describe interrupted work; they do not gate file editing.
            digest = hashlib.sha256(raw).hexdigest()
            result.current_sha256 = digest
            result.current_status = (
                "matches_after"
                if digest == record.after_sha256
                else "matches_before"
                if digest == record.before_sha256
                else "changed"
            )
        except AgentError as exc:
            result.current_status, result.code = "unavailable", exc.code
        return result

    async def program(self, summary: ProgramSummary) -> ToolObservation:
        """从现有所有权与保存结果读取最新状态，不启动程序或发送 HTTP 请求。

        Read current owned or saved state without launching programs or issuing HTTP probes.
        """
        view = await self.programs.get(GetProgramParams(program_id=summary.program_id))
        return ToolObservation(
            state="observed",
            message="已核对受管程序的当前记录；退出码与业务是否通过需分别理解。",
            artifact_id=summary.program_id,
            artifact_type="program",
            recorded_status=summary.status,
            current_status=view.summary.status,
            exit_code=view.summary.exit_code,
            code=view.summary.code,
        )

    async def pending(
        self, root: Path, limits: RunLimits, project_id: str, session_id: str, item: PendingTool
    ) -> ToolObservation:
        """按运行 / 工具身份查找成果，缺失 / 损坏保持未知，不猜测命令成功。

        Match run and tool provenance, preserving missing or damaged results as unknown.
        """
        if item.started_seq is None:
            return ToolObservation(state="not_started", message="没有开始事实，此调用未执行。")
        unknown = ToolObservation(
            state="unknown", message="原工具响应未保存，无法确认结果；核对不会重跑此调用。"
        )
        try:
            if item.call.name in {"create_file", "edit_file"}:
                records, unavailable = await self.worker.call(self._changes, session_id)
                matches = [
                    row
                    for row in records
                    if row.run_id == item.run_id
                    and row.tool_call_id == item.call.tool_call_id
                    and row.project_id == project_id
                ]
                if len(matches) == 1 and not unavailable:
                    return await self.file(root, limits, matches[0])
                unknown.code = "CHANGE_UNAVAILABLE" if unavailable else "CHANGE_UNCONFIRMED"
            elif item.call.name in {"run_command", "start_service", "stop_program"}:
                await self.programs.recover()
                programs, unavailable = await self.worker.call(self.programs.store.records)
                program_matches = [
                    record.summary
                    for record in programs
                    if record.summary.session_id == session_id
                    and record.summary.project_id == project_id
                    and (
                        (
                            item.call.name == "stop_program"
                            and record.summary.program_id == item.call.arguments.get("program_id")
                        )
                        or (
                            item.call.name != "stop_program"
                            and record.summary.run_id == item.run_id
                            and record.summary.tool_call_id == item.call.tool_call_id
                        )
                    )
                ]
                if len(program_matches) == 1 and not unavailable:
                    return await self.program(program_matches[0])
                unknown.code = "PROGRAM_UNCONFIRMED"
        except AgentError as exc:
            unknown.code = exc.code
        return unknown
