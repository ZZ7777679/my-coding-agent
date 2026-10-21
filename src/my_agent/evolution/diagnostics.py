"""保留可关联诊断，不保存原始异常文本或局部变量。

Correlated diagnostics without raw exceptions or locals.
"""

import logging
import queue
import re
import threading
import traceback
from pathlib import Path
from uuid import UUID, uuid4

from my_agent.errors import AgentError
from my_agent.evolution.types import DiagnosticEvent, DiagnosticFrame, EvolutionSource
from my_agent.storage import Storage, read_document, utc_now, write_document


class DiagnosticStore:
    """同实例诊断写入与读取；故障仅令诊断降级。

    Instance diagnostics degrade without blocking business work.
    """

    def __init__(self, storage: Storage, max_records: int | None = None) -> None:
        """使用数据根与集中传入的保留量。

        Use the data root and a centrally supplied retention size.
        """
        self.storage = storage
        self.root = storage.root / "logs" / "diagnostics"
        from my_agent.config import DEFAULTS

        settings = DEFAULTS["diagnostics"]
        self.max_records = max_records if max_records is not None else settings["max_records"]
        self.prune_every: int = settings["prune_every"]
        self.queue_size: int = settings["queue_size"]
        self.lock = threading.RLock()
        self.issue: str | None = None
        self.written = 0

    def record(
        self,
        code: str,
        message: str,
        *,
        component: str,
        exception: BaseException | None = None,
        project_id: str | None = None,
        source: EvolutionSource | None = None,
        phase: str | None = None,
        level: str = "error",
    ) -> str | None:
        """记录已公开说明与异常位置，不渲染异常输入。

        Record public text and locations, never exception inputs.
        """
        if not self.storage.writing:
            return None
        causes: list[str] = []
        frames: list[DiagnosticFrame] = []
        seen: set[int] = set()
        current = exception
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            causes.append(type(current).__name__)
            frames.extend(
                DiagnosticFrame(file=item.filename, line=item.lineno or 0, function=item.name)
                for item in traceback.extract_tb(current.__traceback__)
            )
            current = current.__cause__ or (
                None if current.__suppress_context__ else current.__context__
            )
        identity = str(uuid4())
        event = DiagnosticEvent(
            diagnostic_id=identity,
            at=utc_now(),
            code=code,
            message=message,
            component=component,
            level="warning" if level == "warning" else "error",
            cause_code=exception.cause_code if isinstance(exception, AgentError) else None,
            phase=phase or (exception.phase if isinstance(exception, AgentError) else None),
            exception_types=causes,
            frames=frames,
            project_id=project_id,
            source=source or EvolutionSource(),
        )
        try:
            with self.lock:
                self.root.mkdir(parents=True, exist_ok=True)
                write_document(self.root / (identity + ".json"), event)
                self.written += 1
                # 批次清理减少每条日志的目录扫描；保留量不是任务执行预算。
                # Batched pruning avoids scanning per event; retention is not an execution budget.
                if self.written == 1 or self.written % self.prune_every == 0:
                    records = sorted(
                        self.root.glob("*.json"), key=lambda path: path.stat().st_mtime
                    )
                    for path in records[: -self.max_records]:
                        # 仅删除当前诊断目录内的 UUID 文件，不沿链接清理其他目录。
                        # Remove only UUID files here; never follow links for cleanup.
                        if not path.is_symlink() and path.resolve().parent == self.root.resolve():
                            try:
                                UUID(path.stem)
                            except ValueError:
                                continue  # 非诊断文件保留。 Leave unrelated files untouched.
                            path.unlink()
                self.issue = None
            return identity
        except (OSError, AgentError, ValueError) as exc:
            self.issue = "DIAGNOSTIC_WRITE_FAILED: " + type(exc).__name__
            return None

    def page(
        self, project_id: str, limit: int = 30, before: str | None = None
    ) -> tuple[list[DiagnosticEvent], list[str]]:
        """保留全局启动诊断和当前项目记录，局部损坏不隐藏。

        Include startup/project records and expose local corruption.
        """
        result: list[DiagnosticEvent] = []
        issues = [self.issue] if self.issue else []
        try:
            paths = list(self.root.glob("*.json"))
            for path in paths:
                try:
                    event = read_document(path, DiagnosticEvent)
                    if event.project_id in {None, project_id} and (
                        before is None or event.at < before
                    ):
                        result.append(event)
                except AgentError as exc:
                    issues.append(path.name + ": " + exc.code)
        except OSError as exc:
            issues.append("DIAGNOSTIC_READ_FAILED: " + type(exc).__name__)
        return sorted(result, key=lambda item: (item.at, item.diagnostic_id), reverse=True)[
            :limit
        ], issues


class DiagnosticHandler(logging.Handler):
    """接住项目警告的类别与位置；原始日志参数不出进程。

    Capture warning identity/location without raw log arguments.
    """

    def __init__(self, store: DiagnosticStore) -> None:
        """只接 WARNING 以上，不改变其他 handler。

        Capture warnings without replacing other handlers.
        """
        super().__init__(logging.WARNING)
        self.store = store
        self.records: queue.Queue[logging.LogRecord | None] = queue.Queue(maxsize=store.queue_size)
        self.thread = threading.Thread(target=self._consume, name="agent-diagnostics", daemon=True)
        self.thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        """避免保存失败递归记录，不复制可能含秘密的日志参数。

        Avoid recursive logging and secret-bearing arguments.
        """
        if not record.name.startswith("my_agent"):
            return
        # 不格式化日志参数；磁盘慢时不让诊断队列堵住模型与取消。
        # Never interpolate arguments or block model/cancellation work on disk.
        try:
            self.records.put_nowait(record)
        except queue.Full:
            self.store.issue = "DIAGNOSTIC_QUEUE_FULL: 部分诊断未保存"

    def _consume(self) -> None:
        """专用线程写入诊断，退出前排空。

        Persist diagnostics off-loop and drain at shutdown.
        """
        while (record := self.records.get()) is not None:
            template = record.msg if isinstance(record.msg, str) else ""
            match = re.match(r"^([A-Z][A-Z0-9_]{2,63})(?:\s|$)", template)
            code = match.group(1) if match else "PYTHON_" + record.levelname
            self.store.record(
                code,
                f"{record.name} · {Path(record.pathname).name}:{record.lineno}",
                component=record.name,
                level="error" if record.levelno >= logging.ERROR else "warning",
                exception=record.exc_info[1] if record.exc_info else None,
            )

    def close(self) -> None:
        """只关闭本实例监听器，不修改其他日志入口。

        Close this listener, leaving other logging intact.
        """
        if self.thread.is_alive():
            self.records.put(None)
            self.thread.join()
        super().close()
