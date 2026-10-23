"""保留可关联的脱敏异常详情，不保存局部变量或整份请求。

Correlated sanitized exception details without locals or complete requests.
"""

import logging
import queue
import re
import threading
import traceback
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from my_agent.errors import AgentError, exception_message, redact_error_data, redact_error_text
from my_agent.evolution.types import (
    DiagnosticCause,
    DiagnosticEvent,
    DiagnosticFrame,
    EvolutionSource,
)
from my_agent.models.types import JsonObject
from my_agent.storage import Storage, read_document, utc_now, write_document


class DiagnosticStore:
    """同实例诊断写入与读取；故障仅令诊断降级。

    Instance diagnostics degrade without blocking business work.
    """

    def __init__(
        self, storage: Storage, max_records: int | None = None, *, secrets: tuple[str, ...] = ()
    ) -> None:
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
        self.secrets = secrets

    def read(self, diagnostic_id: str) -> DiagnosticEvent:
        """读取一条原诊断，旧记录缺少原因层时仍可读。

        Read the original diagnostic, retaining compatibility with old records.
        """
        identity = str(UUID(diagnostic_id))
        return read_document(self.root / (identity + ".json"), DiagnosticEvent)

    def capture(
        self,
        exception: Exception,
        *,
        code: str = "INTERNAL_ERROR",
        component: str,
        project_id: str | None = None,
        source: EvolutionSource | None = None,
        operation: str | None = None,
        request_id: str | None = None,
        tool_call_id: str | None = None,
        phase: str | None = None,
    ) -> AgentError:
        """在异常负责边界生成可读错误并保存一次；诊断失败不替代业务错误。

        Normalize once at the owning boundary; diagnostic failure never replaces the error.
        """
        error = (
            exception
            if isinstance(exception, AgentError)
            else AgentError(
                code,
                f"{type(exception).__name__}: {exception_message(exception, self.secrets)}",
                cause_code=type(exception).__name__,
                phase=phase,
            )
        )
        error.message = redact_error_text(error.message, self.secrets)
        error.remediation = redact_error_text(error.remediation, self.secrets)
        error.tool_call_id = error.tool_call_id or tool_call_id
        error.phase = error.phase or phase
        if (
            not error.diagnostic_id
            and not error.code.startswith("BUDGET_")
            and error.code != "CANCELLED"
        ):
            error.diagnostic_id = self.record(
                error.code,
                error.message,
                component=component,
                exception=exception,
                project_id=project_id,
                source=source,
                phase=error.phase,
                operation=operation,
                request_id=request_id,
                tool_call_id=error.tool_call_id,
            )
            error.diagnostic_issue = self.issue
            if not error.diagnostic_id:
                error.diagnostic_issue = self.issue or "DIAGNOSTIC_UNAVAILABLE: 诊断未持久化"
        return error

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
        operation: str | None = None,
        request_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> str | None:
        """保存逐层脱敏原因和操作身份，不收集局部变量。

        Save sanitized cause layers and operation identities, never locals.
        """
        if not self.storage.writing:
            return None
        causes: list[DiagnosticCause] = []
        seen: set[int] = set()
        pending: list[
            tuple[BaseException, int | None, Literal["error", "cause", "context", "group"]]
        ] = [(exception, None, "error")] if exception is not None else []
        while pending:
            current, parent, relation = pending.pop()
            if id(current) in seen:
                continue
            seen.add(id(current))
            frames = [
                DiagnosticFrame(file=item.filename, line=item.lineno or 0, function=item.name)
                for item in traceback.extract_tb(current.__traceback__)
            ]
            position = len(causes)
            cleaned = redact_error_data(
                current.details if isinstance(current, AgentError) else {}, self.secrets
            )
            details: JsonObject = cleaned if isinstance(cleaned, dict) else {}
            causes.append(
                DiagnosticCause(
                    type=type(current).__name__,
                    message=exception_message(current, self.secrets),
                    relation=relation,
                    parent=parent,
                    frames=frames,
                    details=details,
                    code=current.code if isinstance(current, AgentError) else None,
                )
            )
            linked = current.__cause__ or (
                None if current.__suppress_context__ else current.__context__
            )
            if linked is not None:
                pending.append((linked, position, "cause" if current.__cause__ else "context"))
            if isinstance(current, BaseExceptionGroup):
                pending.extend((child, position, "group") for child in reversed(current.exceptions))
        identity = str(uuid4())
        event = DiagnosticEvent(
            diagnostic_id=identity,
            at=utc_now(),
            code=code,
            message=redact_error_text(message, self.secrets),
            component=component,
            level="warning" if level == "warning" else "error",
            cause_code=exception.cause_code if isinstance(exception, AgentError) else None,
            phase=phase or (exception.phase if isinstance(exception, AgentError) else None),
            exception_types=[cause.type for cause in causes],
            frames=[frame for cause in causes for frame in cause.frames],
            causes=causes,
            details=causes[0].details if causes else {},
            operation=redact_error_text(operation, self.secrets) if operation else None,
            request_id=redact_error_text(request_id, self.secrets) if request_id else None,
            tool_call_id=tool_call_id
            or (exception.tool_call_id if isinstance(exception, AgentError) else None),
            effect_state=exception.effect_state if isinstance(exception, AgentError) else None,
            project_id=project_id,
            source=source or EvolutionSource(),
        )
        saved = False
        try:
            with self.lock:
                self.root.mkdir(parents=True, exist_ok=True)
                write_document(self.root / (identity + ".json"), event)
                saved = True
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
            # 清理旧记录失败不撤销已保存的新证据，也不替换原业务错误。
            # Retention failure neither revokes saved evidence nor replaces the business error.
            issue_code = "DIAGNOSTIC_CLEANUP_FAILED" if saved else "DIAGNOSTIC_WRITE_FAILED"
            self.issue = (
                f"{issue_code}: {type(exc).__name__}: {exception_message(exc, self.secrets)}"
            )
            return identity if saved else None

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
    """记录项目告警的脱敏文字与异常，原始参数不保存。

    Capture sanitized warning messages and exceptions without saving raw arguments.
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
        """非阻塞投递，在消费线程格式化并脱敏后保存。

        Enqueue without blocking; format and sanitize on the consumer thread.
        """
        if not record.name.startswith("my_agent"):
            return
        # 磁盘慢时不让诊断队列堵住模型与取消。
        # Never block model/cancellation work on slow diagnostic storage.
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
                f"{record.name} · {Path(record.pathname).name}:{record.lineno} · "
                + redact_error_text(record.getMessage(), self.store.secrets),
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
