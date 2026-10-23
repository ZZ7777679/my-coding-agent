"""独立复盘、资源候选和恢复，不占用业务 Run。

Independent review, resource candidates and restoration.
"""

import asyncio
from typing import TYPE_CHECKING
from uuid import uuid4
from weakref import WeakValueDictionary

from pydantic import ValidationError

from my_agent.errors import AgentError
from my_agent.evolution.browse import browse_runs
from my_agent.evolution.diagnostics import DiagnosticStore
from my_agent.evolution.resources import EvolutionResources
from my_agent.evolution.store import EvolutionStore
from my_agent.evolution.types import (
    CompareEvolutionCandidate,
    CreateEvolutionCandidate,
    EvolutionCandidate,
    EvolutionCatalog,
    EvolutionCatalogItem,
    EvolutionComparison,
    EvolutionControl,
    EvolutionExperimentParams,
    EvolutionFeedback,
    EvolutionInput,
    EvolutionJob,
    EvolutionJobControl,
    EvolutionPage,
    EvolutionQuery,
    EvolutionRunsPage,
    EvolutionRunsQuery,
    EvolutionTarget,
    GenerateEvolutionCandidate,
    SaveEvolutionCandidate,
    SaveEvolutionFeedback,
)
from my_agent.sessions.projection import summarize
from my_agent.skills.types import SkillParams
from my_agent.storage import utc_now

if TYPE_CHECKING:
    from my_agent.sessions.service import SessionService


class EvolutionService:
    """复用模型工厂和业务线程；维护失败不改原任务结果。

    Reuse the model factory and writer; maintenance failure never changes the source task result.
    """

    def __init__(self, sessions: "SessionService", diagnostics: DiagnosticStore) -> None:
        """绑定既有服务，不启动后台模型。

        Bind existing services without starting background models.
        """
        self.sessions = sessions
        self.store = EvolutionStore(sessions.store.storage)
        self.resources = EvolutionResources(sessions)
        self.diagnostics = diagnostics
        self.jobs: dict[str, tuple[EvolutionJob, asyncio.Task[None]]] = {}
        self.unsaved_jobs: dict[str, EvolutionJob] = {}
        self.locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        self.accept_lock = asyncio.Lock()
        self.active_inputs: dict[str, str] = {}

    async def page(self, query: EvolutionQuery) -> EvolutionPage:
        """读取真实状态；旧进程留下的 running 仅显示为已中断。

        Project actual state, marking orphaned jobs interrupted.
        """
        await self.sessions.validate_project(query.project_id)
        page = await self.sessions.worker.call(self.store.page, query)
        page.diagnostics, issues = await self.sessions.worker.call(
            self.diagnostics.page, query.project_id, query.limit
        )
        page.issues.extend(issues)
        for job in self.unsaved_jobs.values():
            if job.project_id == query.project_id and (
                query.origin is None or job.origin == query.origin
            ):
                page.jobs = [item for item in page.jobs if item.job_id != job.job_id]
                page.jobs.insert(0, job)
                page.issues.append("维护结果尚未落盘：" + job.job_id)
        for job in page.jobs:
            self._normalize_job(job)
        # 列表轮询不反复发送实验输出；详情由用户按需打开。
        # Polling omits experiment output; users open details on demand.
        page.jobs = [
            job.model_copy(
                update={
                    "details_available": bool(
                        job.programs or job.omitted_paths or job.review_input
                    ),
                    "programs": [],
                    "omitted_paths": [],
                    "review_input": None,
                    "response_text": "",
                }
            )
            for job in page.jobs
        ]
        return page

    async def job_detail(self, params: EvolutionJobControl) -> EvolutionJob:
        """按需读取一次维护结果，保留未落盘的真实终态。

        Read maintenance details on demand, including unsaved terminal facts.
        """
        await self.sessions.validate_project(params.project_id)
        live = self.jobs.get(params.job_id)
        item = self.unsaved_jobs.get(params.job_id) or (live[0] if live else None)
        if item is not None and item.project_id == params.project_id:
            return item
        item = await self.sessions.worker.call(self.store.job, params.project_id, params.job_id)
        return self._normalize_job(item)

    def _normalize_job(self, job: EvolutionJob) -> EvolutionJob:
        """列表、详情和接续共用实际活动状态，不重放副作用。

        Normalize live state consistently without replaying side effects.
        """
        if job.status == "running" and job.job_id not in self.jobs:
            job.status = "interrupted"
            job.message = "上次复盘已中断，未自动重放。"
        return job

    async def catalog(self, project_id: str, *, include_memory: bool = True) -> EvolutionCatalog:
        """目录只读资源身份，不全量加载正文。

        List resource identities without loading their bodies.
        """
        await self.sessions.validate_project(project_id)
        worker = self.sessions.worker
        result = EvolutionCatalog(
            items=[
                EvolutionCatalogItem(
                    target=EvolutionTarget(kind="project_rule", identity="AGENTS.md"),
                    label="项目规范 · AGENTS.md",
                )
            ]
        )
        entries, unavailable = (
            await worker.call(self.resources.memory._entries) if include_memory else ([], 0)
        )
        for entry in entries:
            if entry.project_id not in {None, project_id}:
                continue
            result.items.append(
                EvolutionCatalogItem(
                    target=EvolutionTarget(
                        kind="preference" if entry.category == "preference" else "memory",
                        identity=entry.memory_id,
                        scope=entry.scope,
                    ),
                    label=entry.title,
                )
            )
        if unavailable:
            result.issues.append(f"{unavailable} 条记忆不可读，未隐藏已有错误。")
        if self.sessions.skills:
            skills = await worker.call(
                self.sessions.skills.catalog, SkillParams(project_id=project_id)
            )
            result.items.extend(
                EvolutionCatalogItem(
                    target=EvolutionTarget(
                        kind="skill",
                        identity=item.skill_id,
                        scope="project" if item.source == "project" else "user",
                    ),
                    label=f"{item.name} · {item.source}",
                )
                for item in skills.items
            )
            result.issues.extend(skills.issues)
        styles = await worker.call(self.resources.styles.catalog, project_id)
        result.items.extend(
            EvolutionCatalogItem(
                target=EvolutionTarget(kind="workstyle", identity=style.style_id, scope="user"),
                label=style.name,
            )
            for style in styles.styles
        )
        result.issues.extend(styles.issues)
        files = await self.resources.file_tools(project_id, str(uuid4()))
        for definition in self.sessions.tool_factory(files.context).definitions():
            function = definition.get("function")
            if isinstance(function, dict) and isinstance(name := function.get("name"), str):
                result.items.append(
                    EvolutionCatalogItem(
                        target=EvolutionTarget(kind="tool_guidance", identity=name),
                        label=name,
                    )
                )
        return result

    async def feedback(self, params: SaveEvolutionFeedback) -> EvolutionFeedback:
        """保留用户意见及准确来源；自动复盘只依据项目已保存选择。

        Record feedback and respect saved review settings.
        """
        await self.sessions.validate_project(params.project_id)
        for source in [params.source, *params.sources]:
            if source.session_id:
                await self.sessions._load(source.session_id)
        async with self.locks.setdefault(params.feedback_id, asyncio.Lock()):
            existed = await self.sessions.worker.call(
                self.store.path(params.project_id, "feedback", params.feedback_id).exists
            )
            sources = []
            if not existed and params.origin:
                from my_agent.evolution.scopes import scope_sources

                sources = await scope_sources(self.sessions, params.project_id, params.origin)
                for source in sources:
                    if source.session_id:
                        log = await self.sessions._load(source.session_id)
                        source.through_seq = max((f.seq for f in log.facts), default=1)
            result = await self.sessions.worker.call(self.store.feedback, params, sources)
        settings = await self.sessions.worker.call(self.store.settings, params.project_id)
        if not existed and settings.automatic_review:
            try:
                job = await self.generate(
                    GenerateEvolutionCandidate(
                        project_id=params.project_id,
                        origin=params.origin,
                        target=params.target,
                        feedback_ids=[params.feedback_id],
                        instruction=params.text,
                        mode="propose" if params.target else "investigate",
                    )
                )
                result = await self.sessions.worker.call(
                    self.store.link_feedback, result, job.job_id
                )
            except (AgentError, OSError) as exc:
                # 反馈已保存；可选复盘失败单独记录，不能把成功反馈变成失败。
                # Saved feedback remains successful; optional review failure has its own record.
                message = exc.message if isinstance(exc, AgentError) else "自动复盘未能启动。"
                await self.finish_job(
                    EvolutionJob(
                        job_id=str(uuid4()),
                        project_id=params.project_id,
                        status="failed",
                        message=message,
                    )
                )
        return result

    async def preview(self, params: GenerateEvolutionCandidate) -> EvolutionInput:
        """预览待选材料，不调用模型、不保存候选。

        Preview selected input without a model call or candidate write.
        """
        from my_agent.evolution.investigation import prepare_investigation

        return (await prepare_investigation(self, params))[0]

    async def runs(self, params: EvolutionRunsQuery) -> EvolutionRunsPage:
        """按运行分页，避免工具密集的一轮遮住其他轮。

        Page runs so tool-heavy runs cannot hide other turns.
        """
        log = await self.sessions._load(params.session_id)
        if summarize(log).project_id != params.project_id:
            raise AgentError("PROJECT_MISMATCH", "参考会话不属于当前项目。")
        return await self.sessions.worker.call(browse_runs, log, params)

    async def generate(self, params: GenerateEvolutionCandidate) -> EvolutionJob:
        """同一活动输入复用作业；完成后允许明确再次发起。

        Reuse an active identical input, allowing explicit new reviews after completion.
        """
        key = params.model_dump_json()
        async with self.accept_lock:
            identity = self.active_inputs.get(key)
            if identity and identity in self.jobs:
                return self.jobs[identity][0]
            job = await self._accept_generate(params)
            self.active_inputs[key] = job.job_id
            return job

    async def _accept_generate(self, params: GenerateEvolutionCandidate) -> EvolutionJob:
        """接纳调查或指定资源路径，保持共同的可停止作业。

        Accept investigation or directed proposals under the same stoppable job lifecycle.
        """
        from my_agent.evolution.investigation import investigate

        if self.sessions.closing:
            raise AgentError("APP_CLOSING", "应用正在退出。")
        settings = await self.sessions.worker.call(self.store.settings, params.project_id)
        await self.sessions.validate_project(params.project_id)
        origin = params.origin
        if origin is None and params.review_job_id:
            previous = await self.job_detail(
                EvolutionJobControl(project_id=params.project_id, job_id=params.review_job_id)
            )
            origin = previous.origin
        job = EvolutionJob(
            job_id=str(uuid4()),
            project_id=params.project_id,
            status="running",
            origin=origin,
            mode=params.mode,
            review_job_id=params.review_job_id,
            details_available=True,
            message="正在准备范围与筛选线索，可随时停止",
            budget=settings.budget.model_copy(deep=True),
            accepted_at=utc_now(),
            request=params.model_copy(deep=True),
        )
        await self.sessions.worker.call(self.store.save_job, job)
        task = asyncio.create_task(investigate(self, job, params, accepted_settings=settings))
        self.jobs[job.job_id] = job, task
        return job

    async def finish_job(self, job: EvolutionJob) -> None:
        """终态保存失败仍显示内存事实，不留下假运行或未收回任务。

        Retain unsaved terminal facts without orphaned tasks or a misleading running status.
        """
        try:
            await self.sessions.worker.call(self.store.save_job, job)
        except (AgentError, OSError) as exc:
            job.message += " · 终态未能保存，当前仅在内存中可见。"
            self.unsaved_jobs[job.job_id] = job
            error = await self.sessions.worker.call(
                self.diagnostics.capture,
                exc,
                code="EVOLUTION_SAVE_FAILED",
                component="evolution",
                project_id=job.project_id,
                operation="save_job_outcome",
                request_id=job.job_id,
                phase="persistence",
            )
            job.message += " " + error.message
            job.diagnostic_id = job.diagnostic_id or error.diagnostic_id
            job.diagnostic_issue = error.diagnostic_issue or job.diagnostic_issue
        finally:
            self.jobs.pop(job.job_id, None)
            self.active_inputs = {
                key: identity
                for key, identity in self.active_inputs.items()
                if identity != job.job_id
            }

    async def create(self, params: CreateEvolutionCandidate) -> EvolutionCandidate:
        """人工候选也由宿主捕获原版本。

        Capture original content for user-written candidates.
        """
        resource = await self.resources.read(params.project_id, params.target)
        candidate = EvolutionCandidate(
            candidate_id=str(uuid4()),
            project_id=params.project_id,
            target=resource.target,
            before=resource.content,
            after=params.after,
            title=params.title,
            rationale=params.rationale,
            feedback_ids=params.feedback_ids,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        return await self.sessions.worker.call(self.store.save, candidate)

    async def edit(self, params: SaveEvolutionCandidate) -> EvolutionCandidate:
        """只更新草稿正文，不接受前端伪造采用状态或基线。

        Edit draft text without accepting client-authored adoption state or baselines.
        """
        await self.sessions.validate_project(params.project_id)
        lock = self.locks.setdefault(params.candidate_id, asyncio.Lock())
        async with lock:
            candidate = await self.sessions.worker.call(
                self.store.candidate, params.project_id, params.candidate_id
            )
            if candidate.revision != params.revision or candidate.status == "applied":
                raise AgentError(
                    "EVOLUTION_CHANGED", "候选已更新或采用，请重新打开；修改已采用资源可新建候选。"
                )
            candidate.title, candidate.rationale = params.title, params.rationale
            if candidate.after != params.after:
                candidate.content_revision += 1
            candidate.after = params.after
            return await self.sessions.worker.call(self.store.save, candidate)

    async def compare(self, params: CompareEvolutionCandidate) -> EvolutionCandidate:
        """保留用户评价，不冒充自动测试。

        Record user evaluation without claiming automated tests.
        """
        await self.sessions.validate_project(params.project_id)
        lock = self.locks.setdefault(params.candidate_id, asyncio.Lock())
        async with lock:
            candidate = await self.sessions.worker.call(
                self.store.candidate, params.project_id, params.candidate_id
            )
            candidate.comparisons.append(
                EvolutionComparison(
                    at=utc_now(),
                    summary=params.summary,
                    outcome=params.outcome,
                    source=params.source,
                    content_revision=candidate.content_revision,
                )
            )
            return await self.sessions.worker.call(self.store.save, candidate)

    async def control(
        self, params: EvolutionControl, *, automatic: bool = False
    ) -> EvolutionCandidate:
        """串行处理同一候选，采用失败保留实际状态与原任务。

        Serialize each candidate without affecting source tasks.
        """
        await self.sessions.validate_project(params.project_id)
        key = params.candidate_id
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            candidate = await self.sessions.worker.call(
                self.store.candidate, params.project_id, key
            )
            desired_status = "applied" if params.action == "apply" else "reverted"
            if candidate.status == desired_status:
                return candidate
            if params.action == "revert" and candidate.status != "applied":
                raise AgentError("EVOLUTION_NOT_APPLIED", "该候选尚未采用。")
            # 先保存采用意图；崩溃后显示未确认，不自动重放可能已发生的写入。
            # Journal intent before writing; uncertain outcomes are never replayed automatically.
            candidate.pending_action = params.action
            candidate = await self.sessions.worker.call(self.store.save, candidate)
            # 已开始的文件线程不能靠取消协程停止；写入及终态必须一起收回。
            # Cancelling a coroutine cannot stop its file thread; reap writes and terminal records.
            action = asyncio.create_task(self._finish_control(candidate, params, automatic))
            cancelled = False
            while True:
                try:
                    result = await asyncio.shield(action)
                    break
                except asyncio.CancelledError:
                    if action.cancelled():
                        raise
                    cancelled = True
            if cancelled:
                raise asyncio.CancelledError
            return result

    async def _finish_control(
        self, candidate: EvolutionCandidate, params: EvolutionControl, automatic: bool
    ) -> EvolutionCandidate:
        """将已接纳写入和结果保存作为同一受监管的异步动作。

        Supervise an accepted write and its persisted outcome as one asynchronous action.
        """
        try:
            await self.resources.write(
                candidate, revert=params.action == "revert", automatic=automatic
            )
        except (AgentError, OSError, ValidationError) as exc:
            candidate.message = (
                exc.message
                if isinstance(exc, AgentError)
                else "候选格式不符合目标资源。"
                if isinstance(exc, ValidationError)
                else "资源保存失败，写入结果尚未确认。"
            )
            # 已知写入前反馈可以修正；I/O 中断不能冒充完全未写入。
            # Pre-write feedback is repairable; interrupted I/O may have changed the target.
            prewrite = is_prewrite_feedback(exc)
            if prewrite:
                candidate.pending_action = None
            else:
                candidate.message += " 请检查目标实际内容；不会自动重放。"
            await self.sessions.worker.call(self.store.save, candidate)
            raise
        candidate.status = "applied" if params.action == "apply" else "reverted"
        candidate.pending_action = None
        candidate.applied_at = utc_now() if params.action == "apply" else candidate.applied_at
        candidate.message = (
            (
                "代码已保存，重启对应应用后生效。"
                if candidate.target.kind == "code"
                else "下一请求或新任务将按资源加载规则采用。"
            )
            if params.action == "apply"
            else "已恢复原资源；已有运行记录保留。"
        )
        return await self.sessions.worker.call(self.store.save, candidate)

    async def stop(self, params: EvolutionJobControl) -> EvolutionJob:
        """取消并等待当前请求退出，不自动重试。

        Cancel and reap the current request without retrying.
        """
        item = self.jobs.get(params.job_id)
        if item is None or item[0].project_id != params.project_id:
            raise AgentError("EVOLUTION_JOB_NOT_RUNNING", "该复盘已结束或不属于当前项目。")
        job, task = item
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if job.job_id in self.jobs:
            # 尚未进入协程的取消不会执行其 finally；在此保存接纳后的真实终态。
            # Cancellation before entry skips its finally; persist the terminal state here.
            job.status, job.message = "cancelled", "复盘已停止。"
            await self.finish_job(job)
        return job

    async def experiment(self, params: EvolutionExperimentParams) -> EvolutionJob:
        """启动显式代码比较，不修改原项目或创建正式会话。

        Start explicit code comparison without editing the original or creating a formal session.
        """
        from my_agent.evolution.experiments import experiment

        await self.sessions.validate_project(params.project_id)
        if self.sessions.closing:
            raise AgentError("APP_CLOSING", "应用正在退出。")
        candidate = await self.sessions.worker.call(
            self.store.candidate, params.project_id, params.candidate_id
        )
        if candidate.target.kind != "code":
            raise AgentError(
                "EVOLUTION_NOT_CODE", "命令实验用于代码候选；资源效果可通过实际任务评价。"
            )
        job = EvolutionJob(
            job_id=str(uuid4()),
            project_id=params.project_id,
            candidate_id=params.candidate_id,
            status="running",
            message="准备独立副本",
        )
        await self.sessions.worker.call(self.store.save_job, job)
        task = asyncio.create_task(experiment(self, job, candidate, params))
        self.jobs[job.job_id] = job, task
        return job

    async def close(self) -> None:
        """关闭维护后再释放数据锁。

        Finish maintenance before releasing the data lock.
        """
        tasks = [task for _, task in self.jobs.values()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for job, _ in list(self.jobs.values()):
            job.status, job.message = "cancelled", "应用退出，维护已停止。"
            await self.finish_job(job)


def is_prewrite_feedback(exc: Exception) -> bool:
    """识别资源边界已有的写入前可修正反馈。

    Recognize the resource boundary's existing repairable feedback.
    """
    return isinstance(exc, ValidationError) or (
        isinstance(exc, AgentError)
        and exc.code
        in {
            "EVOLUTION_TARGET_CHANGED",
            "EVOLUTION_TARGET_MISSING",
            "INVALID_TOOL_ARGUMENTS",
            "SKILL_NAME_MISMATCH",
            "FILE_NOT_FOUND",
            "FILE_EXISTS",
            "FILE_CHANGED",
        }
    )
