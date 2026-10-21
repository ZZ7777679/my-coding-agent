"""反馈、候选及采用记录的单写者存储。

Single-writer feedback, candidate and adoption storage.
"""

from pathlib import Path
from uuid import UUID

from my_agent.errors import AgentError
from my_agent.evolution.types import (
    EvolutionCandidate,
    EvolutionCandidateSummary,
    EvolutionFeedback,
    EvolutionJob,
    EvolutionPage,
    EvolutionQuery,
    EvolutionRecoveryResult,
    EvolutionSettings,
    SaveEvolutionFeedback,
)
from my_agent.storage import Storage, read_document, utc_now, write_document


class EvolutionStore:
    """持久化改进记录，不覆写原任务事实。

    Persist improvements without rewriting original task facts.
    """

    def __init__(self, storage: Storage) -> None:
        """仅定位应用目录；不创建项目文件。

        Locate app data without creating project files.
        """
        self.storage = storage
        self.root = storage.root / "evolution"

    def path(self, project_id: str, collection: str, identity: str) -> Path:
        """由宿主指定集合、UUID 指定记录。

        Locate host-selected collections and UUID records.
        """
        return self.root / str(UUID(project_id)) / collection / (str(UUID(identity)) + ".json")

    def settings(self, project_id: str) -> EvolutionSettings:
        """旧项目使用显式默认值，不自动启动模型。

        Default old projects without starting models.
        """
        path = self.path(project_id, "settings", project_id)
        return (
            read_document(path, EvolutionSettings)
            if path.exists()
            else EvolutionSettings(project_id=project_id)
        )

    def configure(self, settings: EvolutionSettings) -> EvolutionSettings:
        """保存下一次维护的项目选择。

        Save project choices for subsequent maintenance.
        """
        self.storage.require_writer()
        path = self.path(settings.project_id, "settings", settings.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_document(path, settings)
        return settings

    def feedback(self, params: SaveEvolutionFeedback) -> EvolutionFeedback:
        """同一 ID 重试不复制反馈，也不静默覆盖不同文字。

        Idempotent feedback preserves original content.
        """
        self.storage.require_writer()
        path = self.path(params.project_id, "feedback", params.feedback_id)
        if path.exists():
            current = read_document(path, EvolutionFeedback)
            if current.model_dump(exclude={"created_at", "review_job_id"}) != params.model_dump():
                raise AgentError("OPERATION_CONFLICT", "该反馈身份已用于不同内容。")
            return current
        result = EvolutionFeedback(**params.model_dump(), created_at=utc_now())
        path.parent.mkdir(parents=True, exist_ok=True)
        write_document(path, result)
        return result

    def read_feedback(self, project_id: str, identity: str) -> EvolutionFeedback:
        """读取用户明确选择的反馈。

        Read explicitly selected feedback.
        """
        return read_document(self.path(project_id, "feedback", identity), EvolutionFeedback)

    def link_feedback(self, feedback: EvolutionFeedback, job_id: str) -> EvolutionFeedback:
        """保存反馈关联的复盘，重试时返回同一个身份。

        Persist the associated review so repeated feedback returns the same identity.
        """
        self.storage.require_writer()
        feedback.review_job_id = job_id
        write_document(self.path(feedback.project_id, "feedback", feedback.feedback_id), feedback)
        return feedback

    def candidate(self, project_id: str, identity: str) -> EvolutionCandidate:
        """损坏记录保留原样，错误只影响该候选。

        Preserve corrupt records and scope errors to this candidate.
        """
        item = read_document(self.path(project_id, "candidates", identity), EvolutionCandidate)
        if item.recovery_directory:
            path = Path(item.recovery_directory) / "result.json"
            if path.exists():
                try:
                    result = read_document(path, EvolutionRecoveryResult)
                    if result.candidate_id == item.candidate_id and result.status == "reverted":
                        item.status, item.pending_action = "reverted", None
                        item.message = "独立恢复入口已恢复代码；" + result.at
                except AgentError as exc:
                    item.message += " · 独立恢复结果不可读：" + exc.code
        return item

    def save(self, candidate: EvolutionCandidate) -> EvolutionCandidate:
        """先保存旧候选版本，再发布当前值；不声称跨文件事务。

        Archive prior revisions before publishing, not a transaction.
        """
        self.storage.require_writer()
        path = self.path(candidate.project_id, "candidates", candidate.candidate_id)
        if path.exists():
            previous = read_document(path, EvolutionCandidate)
            history = path.parent / "history" / candidate.candidate_id / f"{previous.revision}.json"
            history.parent.mkdir(parents=True, exist_ok=True)
            if not history.exists():
                write_document(history, previous)
            candidate = candidate.model_copy(update={"revision": previous.revision + 1})
        candidate = candidate.model_copy(update={"updated_at": utc_now()})
        path.parent.mkdir(parents=True, exist_ok=True)
        write_document(path, candidate)
        return candidate

    def save_job(self, job: EvolutionJob) -> EvolutionJob:
        """维护成本与状态独立落盘。

        Persist maintenance cost and state independently.
        """
        self.storage.require_writer()
        job.updated_at = utc_now()
        path = self.path(job.project_id, "jobs", job.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_document(path, job)
        return job

    def job(self, project_id: str, identity: str) -> EvolutionJob:
        """读取明确作业的完整结果。

        Read the complete result for one explicit job.
        """
        return read_document(self.path(project_id, "jobs", identity), EvolutionJob)

    def page(self, query: EvolutionQuery) -> EvolutionPage:
        """统一时间游标跨反馈／候选分页，避免每轮发送补丁正文。

        Page a combined timeline without full patches.
        """
        page = EvolutionPage(settings=self.settings(query.project_id))
        rows: list[tuple[str, str, EvolutionFeedback | EvolutionCandidate]] = []
        root = self.root / str(UUID(query.project_id))
        for collection in ("feedback", "candidates"):
            for path in (root / collection).glob("*.json"):
                try:
                    item: EvolutionFeedback | EvolutionCandidate = (
                        read_document(path, EvolutionFeedback)
                        if collection == "feedback"
                        else self.candidate(query.project_id, path.stem)
                    )
                    at = item.created_at if isinstance(item, EvolutionFeedback) else item.updated_at
                    identity = (
                        item.feedback_id
                        if isinstance(item, EvolutionFeedback)
                        else item.candidate_id
                    )
                    cursor = at + "|" + identity
                    if query.before is None or cursor < query.before:
                        rows.append((cursor, collection, item))
                except AgentError as exc:
                    page.issues.append(path.name + ": " + exc.code)
        rows.sort(key=lambda row: row[0], reverse=True)
        if len(rows) > query.limit:
            page.next_cursor = rows[query.limit - 1][0]
        for _, _, item in rows[: query.limit]:
            if isinstance(item, EvolutionFeedback):
                page.feedback.append(item)
            else:
                page.candidates.append(
                    EvolutionCandidateSummary(
                        candidate_id=item.candidate_id,
                        title=item.title,
                        target=item.target,
                        status=item.status,
                        updated_at=item.updated_at,
                        message=item.message,
                        content_revision=item.content_revision,
                        comparison=item.comparisons[-1] if item.comparisons else None,
                    )
                )
        for path in (root / "jobs").glob("*.json"):
            try:
                job = read_document(path, EvolutionJob)
                if query.origin is None or job.origin == query.origin:
                    page.jobs.append(job)
            except AgentError as exc:
                page.issues.append(path.name + ": " + exc.code)
        page.jobs = sorted(page.jobs, key=lambda job: job.updated_at, reverse=True)[: query.limit]
        return page
