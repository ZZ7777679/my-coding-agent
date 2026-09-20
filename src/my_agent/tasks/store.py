"""任务日志逐版本保存，复用数据根单写者。

Versioned task journals under the existing single writer.
"""

import logging
from pathlib import Path
from uuid import UUID, uuid5

from pydantic import ValidationError

from my_agent.errors import AgentError
from my_agent.sessions.store import MAX_FACT_BYTES, SESSION_ID, SessionStore
from my_agent.sessions.types import RunFinished, SessionAssigned, SessionCreated
from my_agent.storage import Storage, atomic_write, utc_now
from my_agent.tasks.types import (
    CreateTaskParams,
    TaskFact,
    TaskPage,
    TaskSummary,
    TaskView,
    UpdateTaskParams,
)
from my_agent.workflow.types import EventRef, SourcedWorkItem, TaskWork


class TaskStore:
    """在业务线程读取 / 保存任务；单文件原子替换不代表跨文件事务。

    Read and save tasks on the business worker; atomic files are not cross-file transactions.
    """

    def __init__(self, storage: Storage) -> None:
        """绑定数据根，不创建目录。 Bind the data root without creating directories."""
        self.storage = storage
        self.root = storage.root / "tasks"

    def path(self, task_id: str) -> Path:
        """验证任务 ID 与解析后的路径，拒绝链接逃逸。

        Validate IDs and reject linked storage paths.
        """
        try:
            SESSION_ID.validate_python(task_id, strict=True)
        except ValidationError as exc:
            raise AgentError("TASK_NOT_FOUND", "任务标识不正确。") from exc
        path = self.root / task_id / "events.jsonl"
        if path.resolve() != path:
            raise AgentError("TASK_STORAGE_INVALID", "任务存储路径含有不支持的链接。")
        return path

    def history(self, task_id: str) -> list[TaskFact]:
        """保留损坏或未来版本文件，明确拒绝覆盖。

        Preserve damaged or future journals without overwrite.
        """
        path = self.path(task_id)
        try:
            facts: list[TaskFact] = []
            with path.open("rb") as stream:
                while raw := stream.readline(MAX_FACT_BYTES + 1):
                    if len(raw) > MAX_FACT_BYTES or not raw.endswith(b"\n"):
                        raise ValueError("Invalid task record size")
                    fact = TaskFact.model_validate_json(raw)
                    view = fact.view
                    if (
                        view.task_id != task_id
                        or view.revision != len(facts) + 1
                        or fact.expected_revision != len(facts)
                        or any(item.operation_id == fact.operation_id for item in facts)
                    ):
                        raise ValueError("Invalid task sequence")
                    if facts:
                        first = facts[0].view
                        if (
                            view.project_id,
                            view.created_at,
                            view.initial_session_id,
                            view.initial_model_id,
                        ) != (
                            first.project_id,
                            first.created_at,
                            first.initial_session_id,
                            first.initial_model_id,
                        ):
                            raise ValueError("Task identity changed")
                    facts.append(fact)
            if not facts:
                raise ValueError("Empty task journal")
            return facts
        except FileNotFoundError as exc:
            raise AgentError("TASK_NOT_FOUND", "任务记录不存在。") from exc
        except (ValueError, UnicodeError, AgentError) as exc:
            raise AgentError("TASK_DAMAGED", "任务记录损坏或版本不支持；原文件已保留。") from exc
        except OSError as exc:
            raise AgentError("TASK_UNAVAILABLE", "无法读取任务记录，原文件已保留。") from exc

    def get(self, task_id: str) -> TaskView:
        """读取最新已保存版本。 Read the latest saved version."""
        return self.history(task_id)[-1].view

    def _save(self, facts: list[TaskFact]) -> TaskView:
        """同目录原子替换日志，保存成功后才返回新状态。

        Return new state only after atomic replacement.
        """
        self.storage.require_writer()
        path = self.path(facts[-1].view.task_id)
        lines = [fact.model_dump_json() + "\n" for fact in facts]
        content = "".join(lines)
        if any(len(line.encode("utf-8")) > MAX_FACT_BYTES for line in lines):
            raise AgentError("TASK_CAPACITY", "单条任务记录超过协议容量，未覆盖原记录。")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AgentError("TASK_SAVE_FAILED", "无法创建任务存储目录。") from exc
        atomic_write(path, content)
        return facts[-1].view

    def create(self, params: CreateTaskParams) -> TaskView:
        """操作 ID 确定任务身份，重复请求核对最初输入。

        Derive identity from the operation and compare original input.
        """
        task_id = params.operation_id
        if self.path(task_id).exists():
            facts = self.history(task_id)
            original = facts[0].view
            if (original.project_id, original.initial_model_id, original.fields) != (
                params.project_id,
                params.model_id,
                params.fields,
            ):
                raise AgentError("OPERATION_CONFLICT", "该操作标识已用于不同任务输入。")
            return facts[-1].view
        now = utc_now()
        view = TaskView(
            task_id=task_id,
            project_id=params.project_id,
            revision=1,
            fields=params.fields,
            created_at=now,
            updated_at=now,
            source="user",
            initial_session_id=str(uuid5(UUID(task_id), "first-session")),
            initial_model_id=params.model_id,
        )
        return self._save(
            [TaskFact(operation_id=params.operation_id, expected_revision=0, view=view)]
        )

    def update(self, params: UpdateTaskParams) -> TaskView:
        """保留被替代版本；旧页面保存冲突时不丢失新结论。

        Retain superseded versions and reject stale edits.
        """
        facts = self.history(params.task_id)
        for fact in facts:
            if fact.operation_id == params.operation_id:
                if (
                    fact.expected_revision != params.expected_revision
                    or fact.view.fields != params.fields
                ):
                    raise AgentError("OPERATION_CONFLICT", "该操作标识已用于不同任务修改。")
                return facts[-1].view
        current = facts[-1].view
        if params.expected_revision != current.revision:
            raise AgentError("TASK_VERSION_CONFLICT", "任务信息已变化，请重新载入后合并修改。")
        view = current.model_copy(
            update={
                "revision": current.revision + 1,
                "fields": params.fields,
                "updated_at": utc_now(),
                "source": "user",
            }
        )
        return self._save(
            [
                *facts,
                TaskFact(
                    operation_id=params.operation_id, expected_revision=current.revision, view=view
                ),
            ]
        )

    def record_report(self, session_id: str, result_seq: int) -> TaskView | None:
        """按已保存来源幂等同步报告；不执行原工作，不覆盖用户共同字段。

        Idempotently synchronize a durable report without replaying work or replacing user fields.
        """
        log = SessionStore(self.storage).load(session_id)
        if log.issue:
            raise AgentError("SESSION_READ_ONLY", "来源会话记录不完整，不能同步任务结果。")
        result = next((fact for fact in log.facts if fact.seq == result_seq), None)
        if result is None or not isinstance(result.data, RunFinished) or result.run_id is None:
            raise AgentError("WORK_SOURCE_INVALID", "任务进度来源必须是已保存的运行结果。")
        report = result.data.report
        if report is None:
            return None
        before = log.facts[: result.seq - 1]
        membership = next(
            (
                fact.data
                for fact in reversed(before)
                if isinstance(fact.data, (SessionCreated, SessionAssigned))
            ),
            None,
        )
        if membership is None or membership.task_id is None:
            return None
        facts = self.history(membership.task_id)
        current = facts[-1].view
        header = log.facts[0].data
        if not isinstance(header, SessionCreated) or header.project_id != current.project_id:
            raise AgentError("TASK_PROJECT_MISMATCH", "报告与任务不属于同一项目。")
        source = EventRef(session_id=session_id, run_id=result.run_id, seq=result.seq)
        operation_id = str(uuid5(UUID(session_id), f"work-report:{result.run_id}:{result.seq}"))
        for saved in facts:
            if saved.operation_id == operation_id:
                if saved.view.work.source != source or saved.view.work.last_report != report:
                    raise AgentError("WORK_SOURCE_CHANGED", "同一结果身份对应了不同内容。")
                return current
        merged = {item.item.work_id: item for item in current.work.items}
        for item in report.work_items:
            # 模型进度采用最新报告，完整旧版本仍在日志中；不覆盖用户维护的任务字段。
            # Latest progress wins; journals retain history and user task fields stay intact.
            merged[item.work_id] = SourcedWorkItem(item=item, source=source)
        view = current.model_copy(
            update={
                "revision": current.revision + 1,
                "updated_at": utc_now(),
                "source": "run_report",
                "work": TaskWork(items=list(merged.values()), last_report=report, source=source),
            }
        )
        return self._save(
            [
                *facts,
                TaskFact(operation_id=operation_id, expected_revision=current.revision, view=view),
            ]
        )

    def list(self, project_id: str, cursor: str | None, limit: int) -> TaskPage:
        """只读分页并报告损坏条目，不初始化任务目录。

        Page journals and report damage without initialization.
        """
        if not self.root.exists():
            return TaskPage(tasks=[], next_cursor=None, unavailable_count=0)
        if self.root.resolve() != self.root:
            raise AgentError("TASK_STORAGE_INVALID", "任务存储路径含有不支持的链接。")
        tasks: list[TaskSummary] = []
        unavailable = 0
        try:
            candidates = sorted(path.name for path in self.root.iterdir() if path.is_dir())
            for task_id in candidates:
                if cursor is not None and task_id <= cursor:
                    continue
                try:
                    view = self.get(task_id)
                except AgentError:
                    logging.getLogger(__name__).warning("TASK_LIST_ENTRY_UNAVAILABLE")
                    unavailable += 1
                    continue
                if view.project_id != project_id:
                    continue
                if len(tasks) >= limit:
                    return TaskPage(
                        tasks=tasks, next_cursor=tasks[-1].task_id, unavailable_count=unavailable
                    )
                tasks.append(
                    TaskSummary(
                        task_id=view.task_id,
                        project_id=view.project_id,
                        title=view.fields.title,
                        status=view.fields.status,
                        revision=view.revision,
                    )
                )
        except OSError as exc:
            raise AgentError("TASK_UNAVAILABLE", "无法读取任务目录。") from exc
        return TaskPage(tasks=tasks, next_cursor=None, unavailable_count=unavailable)
