"""单写者保存修改基线与结果。 Single-writer storage for change baselines and outcomes."""

import base64
import binascii
import difflib
import json
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from my_agent.changes.types import ChangePage, ChangeRecord, ChangeSummary, ChangeView
from my_agent.errors import AgentError
from my_agent.storage import Storage, write_document


def identity(value: str) -> str:
    """校验目录键，避免把 RPC 身份当路径。 Validate directory keys rather than accepting paths."""
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except ValueError as exc:
        raise AgentError("CHANGE_ID_INVALID", "修改记录标识无效。") from exc
    return value


class ChangeStore:
    """保存准备与完成状态；进程中断后不自动重放。 Persist intent and outcome without replay."""

    def __init__(self, storage: Storage) -> None:
        """绑定数据根，不在项目中保存应用元数据。 Bind app storage outside project files."""
        self.storage = storage
        self.root = storage.root / "changes"

    def path(self, session_id: str, change_id: str) -> Path:
        """构造受控记录位置。 Construct the validated record location."""
        path = self.root / identity(session_id) / (identity(change_id) + ".json")
        if path.resolve() != path:
            raise AgentError("CHANGE_STORAGE_INVALID", "修改成果存储路径含有不支持的链接。")
        return path

    def save(self, record: ChangeRecord) -> None:
        """持锁原子保存单个完整记录，失败不修改项目。

        Atomically save one record under the writer lock."""
        self.storage.require_writer()
        path = self.path(record.summary.session_id, record.summary.change_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AgentError("CHANGE_SAVE_FAILED", "无法保存修改基线，未继续写入项目。") from exc
        write_document(path, record)

    def load(self, session_id: str, change_id: str) -> ChangeRecord:
        """读取可解码的历史快照；不重新核验摘要或写入项目。

        Read decodable snapshots without rechecking digests or writing to the project."""
        try:
            record = ChangeRecord.model_validate_json(self.path(session_id, change_id).read_bytes())
            if record.summary.session_id != session_id or record.summary.change_id != change_id:
                raise ValueError
            if (record.before_base64 is None) != (record.summary.operation == "create"):
                raise ValueError
            for raw in (record.before_base64, record.after_base64):
                if raw is not None:
                    decoded = base64.b64decode(raw, validate=True)
                    decoded.decode("utf-8-sig")
                    if b"\x00" in decoded:
                        raise ValueError
            return record
        except (ValidationError, ValueError, binascii.Error) as exc:
            raise AgentError("CHANGE_DAMAGED", "修改记录损坏，已保留原文件。") from exc
        except OSError as exc:
            raise AgentError("CHANGE_UNAVAILABLE", "无法读取修改记录。") from exc

    def list(self, session_id: str, cursor: str | None, limit: int) -> ChangePage:
        """读取会话成果分页；损坏文件不隐藏或覆盖。

        Page artifacts without hiding damaged entries."""
        directory = self.root / identity(session_id)
        if directory.resolve() != directory:
            raise AgentError("CHANGE_STORAGE_INVALID", "修改成果目录含有不支持的链接。")
        if not directory.exists():
            return ChangePage(changes=[], next_cursor=None, unavailable_count=0)
        changes: list[ChangeSummary] = []
        unavailable = 0
        size = 0
        for path in sorted(directory.glob("*.json")):
            if cursor and path.stem <= cursor:
                continue
            try:
                summary = self.load(session_id, path.stem).summary
            except AgentError:
                unavailable += 1
                continue
            item_size = len(summary.model_dump_json().encode("utf-8"))
            if changes and (len(changes) >= limit or size + item_size > 200000):
                return ChangePage(
                    changes=changes,
                    next_cursor=changes[-1].change_id,
                    unavailable_count=unavailable,
                )
            changes.append(summary)
            size += item_size
        return ChangePage(changes=changes, next_cursor=None, unavailable_count=unavailable)

    def view(self, session_id: str, change_id: str, offset: int) -> ChangeView:
        """按 JSON 帧字节预算分页差异，超长源码行也可接续。

        Page diffs within JSON frame capacity."""
        record = self.load(session_id, change_id)
        before = base64.b64decode(record.before_base64 or "").decode("utf-8-sig")
        after = base64.b64decode(record.after_base64).decode("utf-8-sig")

        # 保留行结束符的可见标记，避免无末尾换行或 CRLF 被误认为同一内容。
        # Represent line endings explicitly so newline-only edits remain visible.
        def lines(text: str) -> list[str]:
            """为差异保留 LF、CRLF、CR 与无末尾换行区别。 Preserve newline distinctions in diffs."""
            return [
                line.rstrip("\r\n")
                + (
                    " ␍"
                    if line.endswith("\r\n")
                    else " ␍ [CR]"
                    if line.endswith("\r")
                    else ""
                    if line.endswith("\n")
                    else " [no newline]"
                )
                + "\n"
                for line in text.splitlines(keepends=True)
            ]

        diff = "".join(
            difflib.unified_diff(
                lines(before),
                lines(after),
                fromfile="before/" + record.summary.path,
                tofile="after/" + record.summary.path,
            )
        )
        # 游标是字符偏移，按编码后大小保守切片，不丢失长行。
        # Character offsets and conservative encoded sizing preserve even very long lines.
        end = min(len(diff), offset + 24000)
        page = diff[offset:end]
        while len(json.dumps(page, ensure_ascii=False).encode("utf-8")) > 120000:
            end = offset + (end - offset) // 2
            page = diff[offset:end]
        return ChangeView(
            summary=record.summary,
            diff=page,
            next_offset=end if end < len(diff) else None,
        )
