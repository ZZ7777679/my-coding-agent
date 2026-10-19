"""单写者终端快照，重启只保留历史。

Single-writer snapshots without process replay.
"""

from pathlib import Path
from uuid import UUID

from my_agent.errors import AgentError
from my_agent.models.types import ModelData
from my_agent.storage import Storage, read_document, utc_now, write_document
from my_agent.terminals.types import TerminalChunk, TerminalSummary, TerminalView

ACTIVE_STATES = {"starting", "running", "stopping"}


class TerminalRecord(ModelData):
    """单个终端的有界输出快照。 One bounded terminal-output snapshot."""

    summary: TerminalSummary
    output: list[TerminalChunk]
    next_seq: int = 1


def output_view(record: TerminalRecord, after_seq: int = 0) -> TerminalView:
    """分页传输输出而不重复旧内容。

    Page output without retransmitting observed chunks.
    """
    output: list[TerminalChunk] = []
    size = 0
    for chunk in record.output:
        if chunk.seq <= after_seq:
            continue
        count = len(chunk.model_dump_json().encode("utf-8"))
        if output and size + count > 120000:
            break
        output.append(chunk)
        size += count
    return TerminalView(
        summary=record.summary.model_copy(deep=True),
        output=output,
        next_seq=output[-1].seq if output else max(after_seq, record.next_seq - 1),
        truncated=record.summary.dropped_bytes > 0
        or bool(record.output and record.output[0].seq > after_seq + 1),
    )


class TerminalStore:
    """保存来源和终态，不从记录重开旧 PID。

    Persist provenance without reopening saved PIDs.
    """

    def __init__(self, storage: Storage) -> None:
        """记录仅位于应用数据根。 Keep records under application storage."""
        self.storage = storage
        self.root = storage.root / "terminals"

    def path(self, terminal_id: str) -> Path:
        """限制记录身份并核对保存路径。

        Validate identity and the owned storage path.
        """
        try:
            if str(UUID(terminal_id)) != terminal_id:
                raise ValueError
        except ValueError as exc:
            raise AgentError("TERMINAL_ID_INVALID", "终端标识无效。") from exc
        path = self.root / f"{terminal_id}.json"
        if path.resolve() != path:
            raise AgentError("TERMINAL_STORAGE_INVALID", "终端记录目录包含不支持的链接。")
        return path

    def save(self, record: TerminalRecord) -> None:
        """在已有业务写锁下原子保存。

        Save atomically under the existing writer lock.
        """
        self.storage.require_writer()
        path = self.path(record.summary.terminal_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AgentError("TERMINAL_SAVE_FAILED", "无法保存终端记录。") from exc
        write_document(path, record)

    def load(self, terminal_id: str) -> TerminalRecord:
        """读取已有记录，损坏不重置。

        Read existing records without resetting damage.
        """
        record = read_document(self.path(terminal_id), TerminalRecord)
        sequences = [item.seq for item in record.output]
        if record.summary.terminal_id != terminal_id or (
            sequences != sorted(set(sequences))
            or (sequences and (sequences[0] < 1 or sequences[-1] >= record.next_seq))
        ):
            raise AgentError("TERMINAL_RECORD_DAMAGED", "终端记录损坏，原文件已保留。")
        return record

    def records(self) -> tuple[list[TerminalRecord], int]:
        """历史损坏只影响对应条目。 Isolate unreadable history to the affected entry."""
        if self.root.resolve() != self.root:
            raise AgentError("TERMINAL_STORAGE_INVALID", "终端记录目录包含不支持的链接。")
        records: list[TerminalRecord] = []
        unavailable = 0
        for path in self.root.glob("*.json"):
            try:
                records.append(self.load(path.stem))
            except AgentError:
                unavailable += 1
        return records, unavailable

    def recover(self) -> None:
        """未记录终态标为中断，不重启也不杀历史 PID。

        Mark unfinished history without PID actions.
        """
        records, _ = self.records()
        for record in records:
            if record.summary.status in ACTIVE_STATES:
                record.summary.status = "interrupted"
                record.summary.finished_at = utc_now()
                record.summary.code = "TERMINAL_INTERRUPTED"
                record.summary.message = "上次应用未保存终态；未自动重新启动程序。"
                self.save(record)
