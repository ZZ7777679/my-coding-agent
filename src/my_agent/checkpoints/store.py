"""请求前后文件快照；Git 工作区、分支和暂存区均不改动。

Before/after file snapshots leave Git worktrees, branches and indexes untouched.
"""

import base64
import difflib
import hashlib
import os
import tempfile
import threading
from pathlib import Path, PurePath
from typing import Literal
from uuid import uuid4

from my_agent.changes.store import ChangeStore, identity
from my_agent.changes.types import ChangeSummary
from my_agent.checkpoints.types import (
    CheckpointPage,
    FileCheckpoint,
    FileCheckpointSummary,
    FileSnapshot,
    RestoreFile,
    RestorePreview,
    RollbackSettings,
)
from my_agent.documents.service import DocumentService
from my_agent.errors import AgentError
from my_agent.runtime.settings import RunLimits
from my_agent.storage import Storage, atomic_write, read_document, utc_now, write_document
from my_agent.tools.policy import ReadPolicy


class CheckpointStore:
    """单写者保存文件内容和覆盖范围，未覆盖文件不假装可恢复。

    Persist content and coverage on the single writer; never claim omitted files are recoverable.
    """

    def __init__(self, storage: Storage) -> None:
        """绑定应用数据根，不创建项目内元数据。 Bind app data without project metadata."""
        self.storage = storage
        self.root = storage.root / "file-checkpoints"

    def path(self, session_id: str, checkpoint_id: str) -> Path:
        """验证身份后定位记录。 Locate records using validated identities."""
        return self.root / identity(session_id) / (identity(checkpoint_id) + ".json")

    def put(self, data: bytes) -> str:
        """去重保存原始字节；地址只在内部使用。 Deduplicate raw bytes using internal addresses."""
        key = hashlib.sha256(data).hexdigest()
        path = self.root / "blobs" / key
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, base64.b64encode(data).decode("ascii"))
        return key

    def get(self, key: str | None) -> bytes | None:
        """读取原始字节，不以摘要再校验制造恢复门槛。 Read original bytes without rehash gates."""
        if key is None:
            return None
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise AgentError("CHECKPOINT_INVALID", "检查点内容地址无效。")
        try:
            return base64.b64decode((self.root / "blobs" / key).read_bytes(), validate=True)
        except (OSError, ValueError) as exc:
            raise AgentError("CHECKPOINT_UNAVAILABLE", "检查点文件内容不可读取。") from exc

    def capture(self, root: Path, limits: RunLimits, settings: RollbackSettings) -> FileSnapshot:
        """遵循文件发现范围，保存字节并记录限额或局部失败。

        Follow discovery scope, preserving bytes and reporting limits or local failures.
        """
        self.storage.require_writer()
        policy = ReadPolicy(root, limits, threading.Event())
        scan = policy.scan()
        snapshot = FileSnapshot(excluded_paths=scan.excluded_paths)
        snapshot.discovery_complete = not (scan.truncated or scan.unavailable)
        total = 0
        if scan.truncated or scan.unavailable:
            snapshot.omitted.append(
                "发现范围已截断或有不可读条目；依赖、Git 元数据等不在代码快照内。"
            )
        for value in scan.files:
            try:
                target = policy.target(value)
                if (
                    not target.is_relative_to(root)
                    or target.stat().st_size > settings.max_file_bytes
                ):
                    snapshot.omitted.append(value)
                    continue
                data = target.read_bytes()
                total += len(data)
                if total > settings.max_total_bytes:
                    snapshot.omitted.append(value)
                    continue
                snapshot.files[value] = self.put(data)
            except (OSError, AgentError):
                snapshot.omitted.append(value)
        return snapshot

    def save(self, record: FileCheckpoint) -> None:
        """保存单份检查点元数据，不称为文件事务。 Save metadata, not a multi-file transaction."""
        self.storage.require_writer()
        path = self.path(record.summary.session_id, record.summary.checkpoint_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_document(path, record)

    def load(self, session_id: str, checkpoint_id: str) -> FileCheckpoint:
        """读取明确的可恢复点。 Read a specific restore point."""
        record = read_document(self.path(session_id, checkpoint_id), FileCheckpoint)
        self.record_coverage(record)
        return record

    @classmethod
    def record_coverage(cls, record: FileCheckpoint) -> None:
        """将起点未覆盖的新发现文件标为遗漏，旧快照同样不猜测文件原先不存在。

        Mark newly discovered files with unknown baselines as omitted, including legacy snapshots.
        """
        if record.summary.kind != "request" or record.after is None:
            return
        before = record.before
        for path in record.after.files.keys() - before.files.keys():
            if (
                not before.discovery_complete
                or before.excluded_paths is None
                or any(
                    PurePath(path) == PurePath(excluded)
                    or (
                        excluded.endswith("/") and PurePath(path).is_relative_to(PurePath(excluded))
                    )
                    for excluded in before.excluded_paths
                )
            ):
                if path not in before.omitted:
                    before.omitted.append(path)
        record.summary.issues = list(
            dict.fromkeys(record.summary.issues + before.omitted + record.after.omitted)
        )
        record.summary.changed_files = len(cls.changes(record))
        if record.summary.status == "ready" and record.summary.issues:
            record.summary.status = "partial"

    def page(self, session_id: str) -> CheckpointPage:
        """损坏记录单独计数，不影响其他可恢复点。 Count unreadable records independently."""
        result = CheckpointPage(checkpoints=[])
        for path in (self.root / identity(session_id)).glob("*.json"):
            try:
                result.checkpoints.append(self.load(session_id, path.stem).summary)
            except AgentError:
                result.unavailable_count += 1
        result.checkpoints.sort(key=lambda s: (s.created_at, s.checkpoint_id), reverse=True)
        return result

    def begin(
        self,
        root: Path,
        session_id: str,
        project_id: str,
        run_id: str,
        before_seq: int,
        title: str,
        limits: RunLimits,
        settings: RollbackSettings,
    ) -> str:
        """接纳请求后、工具运行前捕获起点。 Capture a baseline before any request tools execute."""
        record = FileCheckpoint(
            summary=FileCheckpointSummary(
                checkpoint_id=str(uuid4()),
                session_id=session_id,
                project_id=project_id,
                run_id=run_id,
                before_seq=before_seq,
                title=title[:160],
                status="capturing",
                created_at=utc_now(),
            ),
            before=FileSnapshot(),
        )
        self.save(record)
        try:
            record.before = self.capture(root, limits, settings)
        except (AgentError, OSError) as exc:
            record.summary.status = "failed"
            record.summary.issues = [
                exc.message if isinstance(exc, AgentError) else "请求前文件快照保存失败。"
            ]
        self.save(record)
        return record.summary.checkpoint_id

    def finish(
        self,
        session_id: str,
        checkpoint_id: str,
        root: Path,
        limits: RunLimits,
        settings: RollbackSettings,
    ) -> None:
        """记录请求后的实际文件，包括命令副作用；不猜测其作者。

        Record actual post-request files, including shell effects, without guessing authorship.
        """
        record = self.load(session_id, checkpoint_id)
        if record.summary.status == "failed":
            return
        record.after = self.capture(root, limits, settings)
        # 有限发现未看到不等于文件被删除；有遗漏时不把未知起点当作不存在。
        # Missing from a bounded scan is not deletion; incomplete discovery is not proof of absence.
        for path in record.before.files.keys() - record.after.files.keys():
            if (root / path).exists():
                record.after.omitted.append(path)
        self.record_coverage(record)
        record.summary.finished_at = utc_now()
        record.summary.changed_files = len(self.changes(record))
        record.summary.issues = list(dict.fromkeys(record.before.omitted + record.after.omitted))
        record.summary.status = "partial" if record.summary.issues else "ready"
        self.save(record)

    @staticmethod
    def changes(record: FileCheckpoint) -> list[str]:
        """只比较实际覆盖到的前后文件。 Compare only the files covered by both snapshots."""
        if record.after is None:
            return []
        omitted = set(record.before.omitted + record.after.omitted)
        return sorted(
            path
            for path in record.before.files.keys() | record.after.files.keys()
            if path not in omitted and record.before.files.get(path) != record.after.files.get(path)
        )

    def combine(
        self, session_id: str, checkpoint_id: str, effective_runs: set[str]
    ) -> FileCheckpoint:
        """串联所选起点之后本分支的修改，原始记录不重写。

        Compose current-branch changes after the selected point.
        """
        base = self.load(session_id, checkpoint_id).model_copy(deep=True)
        if base.after is None:
            raise AgentError(
                "CHECKPOINT_INCOMPLETE", "请求的结束文件状态尚未记录，不能猜测恢复范围。"
            )
        if base.summary.kind == "restore":
            return base
        if base.summary.run_id not in effective_runs:
            raise AgentError(
                "CHECKPOINT_OLD_BRANCH", "这是已放弃分支的起点；原记录可查看，不能覆盖当前分支。"
            )
        before: dict[str, str] = {}
        after: dict[str, str] = {}
        seen: set[str] = set()
        records = sorted(self.page(session_id).checkpoints, key=lambda s: s.before_seq)
        for summary in records:
            if (
                summary.kind != "request"
                or summary.before_seq < base.summary.before_seq
                or summary.run_id not in effective_runs
            ):
                continue
            record = self.load(session_id, summary.checkpoint_id)
            if record.after is None:
                raise AgentError(
                    "CHECKPOINT_INCOMPLETE", "后续请求尚无结束快照，先结束运行再恢复。"
                )
            for path in self.changes(record):
                if path not in seen:
                    if path in record.before.files:
                        before[path] = record.before.files[path]
                    seen.add(path)
                if path in record.after.files:
                    after[path] = record.after.files[path]
                else:
                    after.pop(path, None)
            base.summary.issues.extend(record.summary.issues)
            base.summary.finished_at = record.summary.finished_at
        base.before.files, base.after.files = before, after
        return base

    def source(
        self, record: FileCheckpoint, path: str
    ) -> Literal["agent", "observed", "other_session"]:
        """按实际文件工具记录识别已知作者，其余标为观察所得。

        Attribute recorded file-tool effects; all other writes remain observed, not inferred.
        """
        changes = ChangeStore(self.storage)
        own: list[ChangeSummary] = []
        for directory in changes.root.iterdir() if changes.root.exists() else []:
            if not directory.is_dir():
                continue
            cursor = None
            while True:
                page = changes.list_many(
                    [directory.name], cursor, 200, file_path=path, newest_first=True
                )
                for item in page.changes:
                    if (
                        item.project_id != record.summary.project_id
                        or item.created_at < record.summary.created_at
                        or item.status != "applied"
                        or record.summary.finished_at is not None
                        and item.created_at > record.summary.finished_at
                    ):
                        continue
                    if item.session_id != record.summary.session_id:
                        return "other_session"
                    own.append(item)
                cursor = page.next_cursor
                if cursor is None:
                    break
        # 文件工具曾碰过此文件，不代表期间的命令／外部写入也属于它。
        # A file-tool touch cannot attribute intervening shell/external writes to that tool.
        state = self.get(record.before.files.get(path))
        for item in sorted(own, key=lambda item: (item.created_at, item.change_id)):
            try:
                change = changes.load(item.session_id, item.change_id)
            except AgentError:
                return "observed"
            before = (
                base64.b64decode(change.before_base64) if change.before_base64 is not None else None
            )
            after: bytes | None = base64.b64decode(change.after_base64)
            if item.operation == "delete":
                after = None
            elif item.operation == "move":
                if path.replace("\\", "/").casefold() == item.path.replace("\\", "/").casefold():
                    after = None
                else:
                    before = None
            if state != before:
                return "observed"
            state = after
        return (
            "agent"
            if own and record.after and state == self.get(record.after.files.get(path))
            else "observed"
        )

    @staticmethod
    def reverse(before: bytes | None, after: bytes | None, current: bytes | None) -> bytes | None:
        """保留不重叠后续编辑；二进制与新增／删除冲突不强行覆盖。

        Preserve disjoint later edits; never force binary, creation or deletion conflicts.
        """
        if current == after:
            return before
        if current == before:
            return current
        if before is None or after is None or current is None:
            raise AgentError("CHECKPOINT_CONFLICT", "文件新增／删除与后续修改冲突，原文件保持。")
        try:
            return DocumentService.reverse_edit(
                before.decode("utf-8"), after.decode("utf-8"), current.decode("utf-8")
            ).encode("utf-8")
        except UnicodeError as exc:
            raise AgentError(
                "CHECKPOINT_CONFLICT", "二进制或非 UTF-8 文件已有后续改动，原文件保持。"
            ) from exc

    def preview(self, record: FileCheckpoint, root: Path) -> RestorePreview:
        """列出具体冲突和可恢复项，不修改项目。

        List conflicts and restorable files without writes.
        """
        result = RestorePreview(checkpoint=record.summary, files=[], issues=record.summary.issues)
        if record.after is None:
            return result
        for path in self.changes(record):
            item = RestoreFile(
                path=path,
                source="agent" if record.summary.kind == "restore" else self.source(record, path),
                status="ready",
            )
            try:
                target = self.target(root, path)
                current = target.read_bytes() if target.exists() else None
                before, after = (
                    self.get(record.before.files.get(path)),
                    self.get(record.after.files.get(path)),
                )
                desired = self.reverse(before, after, current)
                item.status = "unchanged" if desired == current else "ready"
                try:
                    difference = "".join(
                        difflib.unified_diff(
                            (current or b"").decode("utf-8").splitlines(keepends=True),
                            (desired or b"").decode("utf-8").splitlines(keepends=True),
                            fromfile=path,
                            tofile=path + " (恢复后)",
                        )
                    )
                    item.diff = difference[:8000]
                    if len(difference) > 8000:
                        item.message = "差异预览已截短；恢复操作使用完整文件内容。"
                except UnicodeError:
                    item.message = "原始字节恢复；文本差异不可用。"
            except (AgentError, OSError) as exc:
                item.status, item.message = (
                    "conflict",
                    exc.message if isinstance(exc, AgentError) else "文件不可访问。",
                )
            result.files.append(item)
        return result

    @staticmethod
    def target(root: Path, value: str) -> Path:
        """写入仍使用真实项目边界，链接移出项目时不跟随。

        Retain resolved project write boundaries.
        """
        target = (root / value).resolve()
        if not target.is_relative_to(root) or target == root:
            raise AgentError("CHECKPOINT_PATH_CHANGED", "文件实际目标已移出项目。")
        return target

    @staticmethod
    def write(path: Path, expected: bytes | None, desired: bytes | None) -> None:
        """写前比较真实内容，按字节替换；不要求模型提供版本标识。

        Compare actual bytes before replacement without model-supplied version identifiers.
        """
        if (path.read_bytes() if path.exists() else None) != expected:
            raise AgentError("CHECKPOINT_CONFLICT", "恢复期间文件已改变，请刷新该文件。")
        if desired is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".agent-restore-")
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(desired)
                output.flush()
                os.fsync(output.fileno())
            if (path.read_bytes() if path.exists() else None) != expected:
                raise AgentError("CHECKPOINT_CONFLICT", "恢复期间文件已改变，请刷新该文件。")
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
