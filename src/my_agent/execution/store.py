"""受管程序历史与有界输出，不按历史 PID 重放。

Managed process history without PID-based replay."""

from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from my_agent.errors import AgentError
from my_agent.execution.types import (
    ListProgramsParams,
    OutputChunk,
    ProgramPage,
    ProgramSummary,
    ProgramView,
)
from my_agent.models.types import ModelData
from my_agent.storage import Storage, utc_now, write_document

ACTIVE_STATES = {"starting", "running", "ready", "stopping"}


class ProgramRecord(ModelData):
    """一个程序的原子快照，输出是保留尾部而非完整日志。

    Atomic snapshot containing a bounded log tail."""

    summary: ProgramSummary
    output: list[OutputChunk]
    next_seq: int


def output_view(record: ProgramRecord, after_seq: int) -> ProgramView:
    """按传输容量分页，不把配置的日志容量误当单帧大小。

    Page logs independently of retained capacity."""
    output: list[OutputChunk] = []
    size = 0
    for item in record.output:
        if item.seq <= after_seq:
            continue
        item_size = len(item.model_dump_json().encode("utf-8"))
        if output and size + item_size > 120000:
            break
        output.append(item)
        size += item_size
    return ProgramView(
        summary=record.summary,
        output=output,
        next_seq=output[-1].seq if output else max(after_seq, record.next_seq - 1),
        truncated=record.summary.dropped_bytes > 0
        or bool(record.output and after_seq < record.output[0].seq - 1),
    )


class ProgramStore:
    """按应用写锁保存进程来源和实际结果，不修改项目。

    Persist provenance and outcomes under the app lock."""

    def __init__(self, storage: Storage) -> None:
        """程序记录归应用数据根。

        Keep process records in application data."""
        self.storage = storage
        self.root = storage.root / "programs"

    def path(self, program_id: str) -> Path:
        """仅接受 UUID，并拒绝记录目录链接。

        Accept identities only and reject linked record storage."""
        try:
            if str(UUID(program_id)) != program_id:
                raise ValueError
        except ValueError as exc:
            raise AgentError("PROGRAM_ID_INVALID", "程序标识无效。") from exc
        path = self.root / (program_id + ".json")
        if path.resolve() != path:
            raise AgentError("PROGRAM_STORAGE_INVALID", "程序记录目录含有不支持的链接。")
        return path

    def save(self, record: ProgramRecord) -> None:
        """单个快照原子写入，失败明确返回。

        Atomically save one snapshot and surface write failures."""
        self.storage.require_writer()
        path = self.path(record.summary.program_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AgentError("PROGRAM_SAVE_FAILED", "无法保存程序记录。") from exc
        write_document(path, record)

    def load(self, program_id: str) -> ProgramRecord:
        """读取记录，损坏时保留原文而非重置。

        Preserve damaged history instead of resetting it."""
        try:
            record = ProgramRecord.model_validate_json(self.path(program_id).read_bytes())
            if record.summary.program_id != program_id:
                raise ValueError
            seqs = [chunk.seq for chunk in record.output]
            if seqs != sorted(set(seqs)) or (seqs and (seqs[0] < 1 or seqs[-1] >= record.next_seq)):
                raise ValueError
            return record
        except (ValidationError, ValueError) as exc:
            raise AgentError("PROGRAM_RECORD_DAMAGED", "程序记录损坏，已保留文件。") from exc
        except OSError as exc:
            raise AgentError("PROGRAM_RECORD_UNAVAILABLE", "无法读取程序记录。") from exc

    def records(self) -> tuple[list[ProgramRecord], int]:
        """扫描自有记录，明确计数不可读条目。

        Scan owned records with explicit unavailable counts."""
        if self.root.resolve() != self.root:
            raise AgentError("PROGRAM_STORAGE_INVALID", "程序记录目录含有不支持的链接。")
        records: list[ProgramRecord] = []
        unavailable = 0
        for path in self.root.glob("*.json"):
            try:
                records.append(self.load(path.stem))
            except AgentError:
                unavailable += 1
        return records, unavailable

    def recover(self) -> None:
        """启动时标记未结束历史；绝不重启或按旧 PID 杀进程。

        Mark interruption without replay or PID kills."""
        records, _ = self.records()
        for record in records:
            if record.summary.status in ACTIVE_STATES:
                record.summary = record.summary.model_copy(
                    update={
                        "status": "interrupted",
                        "retained": False,
                        "finished_at": utc_now(),
                        "code": "PROGRAM_INTERRUPTED",
                        "message": "上次应用未记录最终结果；未自动重新启动。",
                    }
                )
                self.save(record)

    def list(self, params: ListProgramsParams) -> ProgramPage:
        """项目 / 会话分页查询，活动数覆盖整个项目。

        Page cards and count live records across the project."""
        records, unavailable = self.records()
        items = [r.summary for r in records if r.summary.project_id == params.project_id]
        active_count = sum(item.status in ACTIVE_STATES for item in items)
        items = sorted(
            (
                item
                for item in items
                if not params.session_id or item.session_id == params.session_id
            ),
            key=lambda item: (item.created_at, item.program_id),
            reverse=True,
        )
        if params.cursor:
            boundary = self.load(params.cursor).summary
            if boundary.project_id != params.project_id or (
                params.session_id and boundary.session_id != params.session_id
            ):
                raise AgentError("PROGRAM_CURSOR_INVALID", "程序分页游标不属于当前范围。")
            items = [
                item
                for item in items
                if (item.created_at, item.program_id) < (boundary.created_at, boundary.program_id)
            ]
        page: list[ProgramSummary] = []
        size = 0
        for item in items:
            item_size = len(item.model_dump_json().encode("utf-8"))
            if page and (len(page) >= params.limit or size + item_size > 160000):
                break
            page.append(item)
            size += item_size
        return ProgramPage(
            programs=page,
            next_cursor=page[-1].program_id if len(page) < len(items) else None,
            unavailable_count=unavailable,
            active_count=active_count,
        )
