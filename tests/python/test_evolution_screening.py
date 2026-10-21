"""选择性筛选与现场范围的定向验证。 Target selective screening and contextual scope resolution."""

import asyncio
from dataclasses import replace
from uuid import uuid4

from my_agent.evolution.investigation_evidence import InvestigationEvidence
from my_agent.evolution.scopes import scope_sources
from my_agent.evolution.tools import EvolutionTools
from my_agent.evolution.types import (
    EvolutionQuery,
    EvolutionScope,
    EvolutionSource,
    GenerateEvolutionCandidate,
)
from my_agent.models.types import ToolCall, ToolResult
from my_agent.sessions.types import ToolCompleted
from tests.python.test_evolution import ReviewModel
from tests.python.test_evolution_investigation_evidence import SelectedSessions, make_log
from tests.python.test_goal_controller import app_at, create_session


def test_screening_groups_repeats_and_searches_body_without_marking_it_read():
    """长正文尾部可检索、重复失败归组、选择范围不扩大。

    Search long tails, group repeated failures and retain the exact selected boundary.
    """

    async def scenario():
        first, second = make_log("same-project", long=True), make_log("same-project")
        first.facts[2].data.call.name = "edit_file"
        first.facts[3] = first.facts[3].model_copy(
            update={
                "data": ToolCompleted(
                    result=ToolResult(
                        tool_call_id="first",
                        content="x" * 60000 + "TAIL_BODY_MARKER",
                        is_error=False,
                    )
                )
            }
        )
        sessions = SelectedSessions([first, second])
        try:
            evidence = await InvestigationEvidence.build(
                sessions,
                [
                    EvolutionSource(session_id=first.session_id, scope="session"),
                    EvolutionSource(session_id=second.session_id, scope="session"),
                ],
            )
            await evidence.screen("late failure")
            repeated = next(
                e for e in evidence.episodes if e.count == 2 and e.representative.seq == 5
            )
            assert repeated.representative.session_id in {first.session_id, second.session_id}
            assert len(repeated.related) > 0
            assert evidence.coverage()["read_count"] == 0
            assert evidence.materials == []
            page = await evidence.index("TAIL_BODY_MARKER")
            assert page["matched_count"] == 1
            assert "TAIL_BODY_MARKER" in page["items"][0]["excerpt"]
            assert page["items"][0]["seq"] == 3
            assert evidence.coverage()["read_count"] == 0
            await evidence.screen("TAIL_BODY_MARKER")
            assert evidence.episodes[0].representative.seq == 3
            assert len(evidence.episodes[0].excerpt) < 400
            await evidence.read(first.session_id, 3, offset=60000, limit=2000)
            assert evidence.coverage()["read_count"] == 1
            assert evidence.selected_count == 10
            # 单事件选择不能为了前后文带入未选记录。
            # An event-only selection cannot pull unselected neighboring evidence.
            single = await InvestigationEvidence.build(
                sessions,
                [
                    EvolutionSource(session_id=first.session_id, seq=5, scope="event"),
                ],
            )
            await single.screen()
            assert single.episodes[0].related == []
        finally:
            sessions.worker.close()

    asyncio.run(scenario())


def test_context_scope_and_model_entry_share_frozen_jobs(tmp_path):
    """任务／项目范围正确，模型启动与桌面可见作业同源，接续不引入新记录。

    Resolve scopes and share frozen jobs between model tools and desktop without later scope drift.
    """

    async def scenario():
        async with app_at(tmp_path / "data", ReviewModel()) as app:
            created = await create_session(app, tmp_path / "project")
            other = await create_session(app, tmp_path / "other")
            pid, sid = created.task.project_id, created.session.session_id
            peer = await app.sessions.create(pid, "glm-5.3-flash", task_id=created.task.task_id)
            loose = await app.sessions.create(pid, "glm-5.3-flash")
            original_list = app.sessions.list

            async def small_pages(project_id, cursor, limit):
                """用单项分页验证完整范围，避免只取最近一页。

                Use single-item pages to verify expansion beyond the first page.
                """
                return await original_list(project_id, cursor, 1)

            app.sessions.list = small_pages
            task_scope = EvolutionScope(kind="task", identity=created.task.task_id)
            project_scope = EvolutionScope(kind="project", identity=pid)
            sources = await scope_sources(app.sessions, pid, task_scope)
            assert {s.session_id for s in sources} == {sid, peer.session_id}
            assert {
                s.session_id for s in await scope_sources(app.sessions, pid, project_scope)
            } == {
                sid,
                peer.session_id,
                loose.session_id,
            }
            assert other.session.session_id not in {s.session_id for s in sources}
            service = app.sessions.evolution
            files = await service.resources.file_tools(pid, str(uuid4()))
            tools = EvolutionTools(replace(files.context, session_id=sid), files, service)
            import json

            accepted = await tools.execute(
                ToolCall(
                    tool_call_id="review",
                    name="review_experience",
                    arguments={"scope": "task", "instruction": "Inspect selected work"},
                )
            )
            assert not accepted.is_error, accepted.content
            job_id = json.loads(accepted.content)["job_id"]
            await service.jobs[job_id][1]
            page = await service.page(EvolutionQuery(project_id=pid, origin=task_scope))
            assert [j.job_id for j in page.jobs] == [job_id]
            original = service.store.job(pid, job_id)
            assert original.review_input.coverage.read == 0
            late = await app.sessions.create(pid, "glm-5.3-flash", task_id=created.task.task_id)
            continuation = await service.preview(
                GenerateEvolutionCandidate(
                    project_id=pid,
                    origin=task_scope,
                    review_job_id=job_id,
                    mode="investigate",
                )
            )
            assert late.session_id not in {s.source.session_id for s in continuation.selections}
            assert continuation.selections == original.review_input.selections

    asyncio.run(scenario())
