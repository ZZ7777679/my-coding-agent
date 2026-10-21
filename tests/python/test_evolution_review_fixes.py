"""十二项审查缺陷的隔离回归，使用真实服务和离线模型。

Isolated review regressions using real services and offline models.
"""

import asyncio
import json
from uuid import uuid4

from my_agent.evolution.history import search_history
from my_agent.evolution.investigation import InvestigationTools, prepare_investigation
from my_agent.evolution.provenance import candidate_sources
from my_agent.evolution.types import (
    CompareEvolutionCandidate,
    CreateEvolutionCandidate,
    EvolutionBudget,
    EvolutionControl,
    EvolutionFinding,
    EvolutionInput,
    EvolutionJob,
    EvolutionJobControl,
    EvolutionMaterial,
    EvolutionQuery,
    EvolutionScope,
    EvolutionSettings,
    EvolutionSource,
    EvolutionTarget,
    GenerateEvolutionCandidate,
    SaveEvolutionCandidate,
    SaveEvolutionFeedback,
)
from my_agent.memory.types import MemoryFields, MemoryQuery
from my_agent.sessions.trace import TraceDetailParams, trace_detail, trace_items
from my_agent.storage import utc_now
from tests.python.test_evolution import ReviewModel
from tests.python.test_goal_controller import app_at, call, create_session, turn


def proposal(target, *, finding="one", after="New guidance"):
    """构造模型提案，不伪造采用状态。 Build a proposal without adoption state."""
    return {
        "finding_id": finding,
        "title": finding,
        "rationale": "Observed",
        "target": target,
        "after": after,
    }


def test_directed_scope_feedback_and_independent_auto_apply(tmp_path):
    """偏离指定目标可纠正；另一次开放调查的首项冲突不丢后项。

    Correct scope feedback and retain later proposals after an independent conflict.
    """

    class Model(ReviewModel):
        """按阶段模拟范围纠错与外部编辑。 Simulate scope correction and external editing."""

        def __init__(self):
            """初始化离线步骤。 Initialize offline steps."""
            super().__init__()
            self.step = 0
            self.conflict = False

        async def complete(self, **kwargs):
            """返回工具回合并制造真实外部修改。

            Return tool turns and create a real external edit.
            """
            self.step += 1
            rule = {"kind": "project_rule", "identity": "AGENTS.md"}
            guidance = {"kind": "tool_guidance", "identity": "read_file"}
            if not self.conflict:
                if self.step == 1:
                    return turn(
                        call("submit_review", summary="Wrong target", proposals=[proposal(rule)])
                    )
                assert "INVALID_TOOL_ARGUMENTS" in kwargs["messages"][-1]["content"]
                return turn(
                    call("submit_review", summary="Corrected", proposals=[proposal(guidance)])
                )
            if self.step == 1:
                return turn(call("read_review_resource", target=rule))
            (tmp_path / "project" / "AGENTS.md").write_text("External edit", encoding="utf-8")
            return turn(
                call(
                    "submit_review",
                    summary="Independent candidates",
                    proposals=[
                        proposal(rule),
                        proposal(guidance, finding="two", after="Better advice"),
                    ],
                )
            )

    async def scenario():
        """使用隔离存储执行真实服务链。 Exercise real services with isolated storage."""
        model = Model()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            service, pid = app.sessions.evolution, created.task.project_id
            path = tmp_path / "project" / "AGENTS.md"
            path.write_text("Original", encoding="utf-8")
            await app.worker.call(
                service.store.configure,
                EvolutionSettings(project_id=pid, auto_apply=["project_rule", "tool_guidance"]),
            )
            job = await service.generate(
                GenerateEvolutionCandidate(
                    project_id=pid,
                    target=EvolutionTarget(kind="tool_guidance", identity="read_file"),
                )
            )
            await service.jobs[job.job_id][1]
            assert job.status == "completed", job.message
            assert path.read_text(encoding="utf-8") == "Original"
            assert service.store.candidate(pid, job.candidate_id).target.kind == "tool_guidance"
            model.step, model.conflict = 0, True
            second = await service.generate(GenerateEvolutionCandidate(project_id=pid))
            await service.jobs[second.job_id][1]
            assert second.status == "completed", second.message
            assert len(second.candidate_ids) == 2
            first, last = [service.store.candidate(pid, i) for i in second.candidate_ids]
            assert first.status == "draft" and first.pending_action is None and first.message
            assert last.status == "applied"
            assert path.read_text(encoding="utf-8") == "External edit"
            model.step, model.conflict = 0, False
            alias = await service.generate(
                GenerateEvolutionCandidate(
                    project_id=pid, target=EvolutionTarget(kind="code", identity="./AGENTS.md")
                )
            )
            await service.jobs[alias.job_id][1]
            assert alias.status == "completed", alias.message
            canonical = service.store.candidate(pid, alias.candidate_id)
            assert canonical.target.kind == "code" and canonical.status == "draft"
            assert path.read_text(encoding="utf-8") == "External edit"

    asyncio.run(scenario())


def test_orphan_continuation_and_job_pagination(tmp_path):
    """旧活动记录在列表、详情、接续一致；相同时间戳仍可翻完历史。

    Orphans behave consistently and equal timestamps do not lose paginated jobs.
    """

    async def scenario():
        """使用隔离存储执行真实服务链。 Exercise real services with isolated storage."""
        async with app_at(tmp_path / "data", ReviewModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service, pid = app.sessions.evolution, created.task.project_id
            origin = EvolutionScope(kind="project", identity=pid)
            prepared = await service.preview(
                GenerateEvolutionCandidate(project_id=pid, origin=origin)
            )
            jobs = [
                EvolutionJob(
                    job_id=str(uuid4()),
                    project_id=pid,
                    status="running",
                    origin=origin,
                    review_input=prepared,
                )
                for _ in range(33)
            ]
            for job in jobs:
                await app.worker.call(service.store.save_job, job)
            first = await service.page(EvolutionQuery(project_id=pid))
            assert len(first.jobs) == 30 and first.jobs_next_cursor
            rest = await service.page(
                EvolutionQuery(project_id=pid, jobs_before=first.jobs_next_cursor)
            )
            assert len(rest.jobs) == 3
            assert len({j.job_id for j in [*first.jobs, *rest.jobs]}) == 33
            detail = await service.job_detail(
                EvolutionJobControl(project_id=pid, job_id=jobs[0].job_id)
            )
            assert detail.status == "interrupted"
            late = await app.sessions.create(pid, "glm-5.3-flash")
            next_job = await service.generate(
                GenerateEvolutionCandidate(
                    project_id=pid, review_job_id=detail.job_id, mode="investigate"
                )
            )
            await service.jobs[next_job.job_id][1]
            assert next_job.status == "completed", next_job.message
            assert late.session_id not in {
                s.source.session_id for s in next_job.review_input.selections
            }

    asyncio.run(scenario())


def test_preparation_is_visible_cancelable_and_budgeted(tmp_path, monkeypatch):
    """材料准备可停止、不占全局锁，并纳入时间预算。

    Preparation is stoppable, outside the global lock and inside the time budget.
    """

    async def scenario():
        """使用隔离存储执行真实服务链。 Exercise real services with isolated storage."""
        model = ReviewModel()
        async with app_at(tmp_path / "data", model) as app:
            first = await create_session(app, tmp_path / "first")
            second = await create_session(app, tmp_path / "second")
            service = app.sessions.evolution
            entered = asyncio.Event()

            async def blocked(*args, **kwargs):
                """只延迟只读准备以观察生命周期。

                Hold read-only preparation to observe lifecycle.
                """
                entered.set()
                await asyncio.Event().wait()

            monkeypatch.setattr("my_agent.evolution.investigation.prepare_investigation", blocked)
            job = await asyncio.wait_for(
                service.generate(GenerateEvolutionCandidate(project_id=first.task.project_id)), 2
            )
            await entered.wait()
            assert job.status == "running" and job.review_input is None
            await app.worker.call(
                service.store.configure,
                EvolutionSettings(
                    project_id=second.task.project_id, budget=EvolutionBudget(max_seconds=1)
                ),
            )
            other = await asyncio.wait_for(
                service.generate(GenerateEvolutionCandidate(project_id=second.task.project_id)), 2
            )
            other_task = service.jobs[other.job_id][1]
            stopped = await service.stop(
                EvolutionJobControl(project_id=job.project_id, job_id=job.job_id)
            )
            assert stopped.status == "cancelled"
            await asyncio.wait_for(other_task, 3)
            assert other.status == "failed" and "预算" in other.message
            assert not model.requests

    asyncio.run(scenario())


def test_feedback_retains_origin_and_frozen_scope(tmp_path):
    """自动反馈与手动接续使用同一已冻结范围。 Feedback reviews share the frozen contextual scope."""

    async def scenario():
        """使用隔离存储执行真实服务链。 Exercise real services with isolated storage."""
        async with app_at(tmp_path / "data", ReviewModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service, pid = app.sessions.evolution, created.task.project_id
            await app.worker.call(
                service.store.configure, EvolutionSettings(project_id=pid, automatic_review=True)
            )
            params = SaveEvolutionFeedback(
                project_id=pid,
                feedback_id=str(uuid4()),
                text="Inspect work",
                origin=EvolutionScope(kind="project", identity=pid),
            )
            saved = await service.feedback(params)
            await service.jobs[saved.review_job_id][1]
            job = service.store.job(pid, saved.review_job_id)
            assert job.origin == params.origin
            assert job.review_input.selections[0].source.session_id == created.session.session_id
            late = await app.sessions.create(pid, "glm-5.3-flash")
            retried = await service.feedback(params)
            assert retried.sources == saved.sources
            prepared = await service.preview(
                GenerateEvolutionCandidate(
                    project_id=pid, origin=params.origin, feedback_ids=[saved.feedback_id]
                )
            )
            assert late.session_id not in {s.source.session_id for s in prepared.selections}

    asyncio.run(scenario())


def test_memory_body_recall_provenance_and_correction(tmp_path):
    """正文命中、实际读取版本与自动派生纠错连通，不依赖模型声明来源。

    Body recall, host-read versions and derived invalidation work without model-authored IDs.
    """

    async def scenario():
        """使用隔离存储执行真实服务链。 Exercise real services with isolated storage."""
        async with app_at(tmp_path / "data", ReviewModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service, pid = app.sessions.evolution, created.task.project_id
            memory = service.resources.memory
            original = await app.worker.call(
                memory.save,
                pid,
                MemoryFields(
                    title="Unrelated title",
                    content="SENTINEL_IN_BODY procedure",
                    tags=["procedure"],
                ),
            )
            prepared, evidence = await prepare_investigation(
                service, GenerateEvolutionCandidate(project_id=pid, instruction="SENTINEL_IN_BODY")
            )
            assert original.memory_id in prepared.model_dump_json()
            job = EvolutionJob(
                job_id=str(uuid4()), project_id=pid, status="running", review_input=prepared
            )
            files = await service.resources.file_tools(pid, job.job_id)
            tools = InvestigationTools(service, job, evidence, files.read)
            result = await tools.execute(call("list_review_resources", query="SENTINEL_IN_BODY"))
            assert not result.is_error and original.memory_id in result.content
            result = await tools.execute(
                call(
                    "read_review_resource",
                    target={"kind": "memory", "identity": original.memory_id},
                )
            )
            assert not result.is_error
            sources, resources = candidate_sources(job.review_input, [], "one", sole_proposal=True)
            assert resources[0].version == str(original.revision)
            candidate = await service.create(
                CreateEvolutionCandidate(
                    project_id=pid,
                    target=EvolutionTarget(kind="memory", identity=""),
                    title="Derived",
                    after=MemoryFields(
                        title="Derived", content="Reusable procedure"
                    ).model_dump_json(),
                )
            )
            candidate.sources, candidate.resource_sources = sources, resources
            await app.worker.call(service.store.save, candidate)
            adopted = await service.control(
                EvolutionControl(
                    project_id=pid, candidate_id=candidate.candidate_id, action="apply"
                ),
                automatic=True,
            )
            assert memory.read(adopted.target.identity, pid).source_ids == [original.memory_id]
            await app.worker.call(
                memory.save,
                pid,
                MemoryFields(title="Corrected", content="Revised"),
                identity=original.memory_id,
            )
            assert memory.read(adopted.target.identity, pid).stale
            assert not any(
                e.memory_id == adopted.target.identity for e in memory.find(pid, MemoryQuery())[0]
            )

    asyncio.run(scenario())


def test_candidate_sources_do_not_inherit_unrelated_trace(tmp_path):
    """分别关联真实读过的事件，不复制整作业来源。 Associate actual reads independently."""
    a = EvolutionSource(session_id=str(uuid4()), seq=1)
    b = EvolutionSource(session_id=str(uuid4()), seq=2)
    prepared = EvolutionInput(
        instruction="Review",
        input_chars=None,
        prepared_at=utc_now(),
        materials=[
            EvolutionMaterial(kind="trace", title="A", source=a, content="a", total_chars=1),
            EvolutionMaterial(kind="trace", title="B", source=b, content="b", total_chars=1),
        ],
    )
    findings = [
        EvolutionFinding(
            finding_id="a", title="A", explanation="A", category="unknown", sources=[a]
        ),
        EvolutionFinding(
            finding_id="b", title="B", explanation="B", category="unknown", sources=[b]
        ),
    ]
    assert candidate_sources(prepared, findings, "a")[0] == [a]
    assert candidate_sources(prepared, findings[:1], "a")[0] == [a]
    assert candidate_sources(prepared, findings, "b")[0] == [b]
    assert candidate_sources(prepared, [], "unknown")[0] == []
    assert (
        candidate_sources(prepared, [], "unknown", sole_proposal=True, inherit_unlinked=False)[0]
        == []
    )

    class ObservationModel(ReviewModel):
        """为真实会话写入最短观察。 Write a minimal observation through real sessions."""

        async def complete(self, **kwargs):
            """不调用外部模型或工具。 Avoid external models and tools."""
            return turn(text="Observed independent result")

    async def scenario():
        """撤回 B 来源只使 B 经验失效。 Invalidating B must leave A's experience usable."""
        async with app_at(tmp_path / "data", ObservationModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service, pid = app.sessions.evolution, created.task.project_id
            other = await app.sessions.create(pid, "glm-5.3-flash")
            materials, findings = [], []
            for index, sid in enumerate([created.session.session_id, other.session_id]):
                await app.sessions.start(sid, str(uuid4()), "Observe", None, "plan")
                await app.sessions.active_for(sid).task
                log = await app.sessions._load(sid)
                row = next(item for item in trace_items(log) if item.kind == "assistant.committed")
                source = EvolutionSource(
                    session_id=sid, seq=row.seq, scope="event", through_seq=log.facts[-1].seq
                )
                detail = trace_detail(log, TraceDetailParams(session_id=sid, seq=row.seq))
                materials.append(
                    EvolutionMaterial(
                        kind="trace",
                        title=str(index),
                        source=source,
                        content=detail.text,
                        total_chars=detail.total_chars,
                    )
                )
                findings.append(
                    EvolutionFinding(
                        finding_id=str(index),
                        title=str(index),
                        explanation="Observed",
                        category="unknown",
                        sources=[source],
                    )
                )
            prepared = EvolutionInput(
                instruction="Review", input_chars=None, prepared_at=utc_now(), materials=materials
            )
            identities = []
            for finding in findings:
                candidate = await service.create(
                    CreateEvolutionCandidate(
                        project_id=pid,
                        target=EvolutionTarget(kind="memory", identity=""),
                        title=finding.title,
                        after=MemoryFields(
                            title=finding.title, content="Independent lesson"
                        ).model_dump_json(),
                    )
                )
                candidate.finding_id = finding.finding_id
                candidate.sources, candidate.resource_sources = candidate_sources(
                    prepared, findings, finding.finding_id
                )
                await app.worker.call(service.store.save, candidate)
                adopted = await service.control(
                    EvolutionControl(
                        project_id=pid, candidate_id=candidate.candidate_id, action="apply"
                    ),
                    automatic=True,
                )
                identities.append(adopted.target.identity)
            source = materials[1].source
            await app.worker.call(
                service.resources.memory.invalidate_source,
                source.session_id,
                source.seq,
                source.seq,
            )
            assert not service.resources.memory.read(identities[0], pid).stale
            assert service.resources.memory.read(identities[1], pid).stale

    asyncio.run(scenario())


def test_history_to_memory_and_stale_comparison(tmp_path):
    """历史按真实效果检索，经验保留版本，修改后不沿用旧改善结论。

    Search actual outcomes and retain experience versions without inheriting stale comparisons.
    """

    class LessonModel(ReviewModel):
        """只使用调查工具读取材料并提出记忆。

        Read through investigation tools and propose memory.
        """

        async def complete(self, **kwargs):
            """查历史、读版本、查记忆、提交候选。

            Search history/memory and propose a versioned lesson.
            """
            self.requests.append(kwargs)
            stage = len(self.requests)
            outputs = [json.loads(m["content"]) for m in kwargs["messages"] if m["role"] == "tool"]
            if stage == 1:
                return turn(call("search_review_history", query="Focused", outcome="improved"))
            if stage == 2:
                identity = outputs[-1]["items"][0]["candidate_id"]
                return turn(
                    call("read_review_history", candidate_id=identity),
                    call("list_review_resources", query="BODY_KEY"),
                )
            if stage == 3:
                return turn(call("read_review_resource", target=outputs[-1]["items"][0]["target"]))
            return turn(
                call(
                    "submit_review",
                    summary="Reusable lesson with recorded provenance",
                    proposals=[
                        proposal(
                            {"kind": "memory", "identity": ""},
                            after=MemoryFields(
                                title="Read lesson",
                                content="Focused read reduced response size in this sample",
                            ).model_dump_json(),
                        )
                    ],
                )
            )

    async def scenario():
        """使用隔离存储执行真实服务链。 Exercise real services with isolated storage."""
        async with app_at(tmp_path / "data", LessonModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service, pid = app.sessions.evolution, created.task.project_id
            candidate = await service.create(
                CreateEvolutionCandidate(
                    project_id=pid,
                    target=EvolutionTarget(kind="tool_guidance", identity="read_file"),
                    title="Focused read",
                    after="Use smaller reads",
                )
            )
            candidate = await service.compare(
                CompareEvolutionCandidate(
                    project_id=pid,
                    candidate_id=candidate.candidate_id,
                    summary="Observed shorter responses",
                    outcome="improved",
                )
            )
            assert (
                search_history(service.store, pid, "Focused", outcome="improved")["matched_count"]
                == 1
            )
            seed = await app.worker.call(
                service.resources.memory.save,
                pid,
                MemoryFields(
                    title="Previous observation", content="BODY_KEY confirms focused reading"
                ),
            )
            await app.worker.call(
                service.store.configure, EvolutionSettings(project_id=pid, auto_apply=["memory"])
            )
            job = await service.generate(
                GenerateEvolutionCandidate(
                    project_id=pid,
                    target=EvolutionTarget(kind="memory", identity=""),
                    candidate_ids=[candidate.candidate_id],
                )
            )
            await service.jobs[job.job_id][1]
            assert job.status == "completed", job.message
            adopted = service.store.candidate(pid, job.candidate_id)
            assert adopted.status == "applied"
            entry = service.resources.memory.read(adopted.target.identity, pid)
            assert entry.evolution_sources[0].content_revision == candidate.content_revision
            assert entry.source_ids == [seed.memory_id]
            assert not entry.stale
            await service.edit(
                SaveEvolutionCandidate(
                    project_id=pid,
                    candidate_id=candidate.candidate_id,
                    revision=candidate.revision,
                    title=candidate.title,
                    rationale=candidate.rationale,
                    after="New untested advice",
                )
            )
            assert search_history(service.store, pid, outcome="improved")["matched_count"] == 0
            assert service.resources.memory.read(adopted.target.identity, pid).stale

    asyncio.run(scenario())
