"""隔离验证自进化的取消、来源失效和比较版本。

Verify evolution cancellation, provenance invalidation and comparison versions in isolation.
"""

import asyncio
import json
import sys
import threading
from uuid import uuid4

import pytest

from my_agent.evolution.types import (
    CreateEvolutionCandidate,
    EvolutionControl,
    EvolutionExperimentParams,
    EvolutionJob,
    EvolutionJobControl,
    EvolutionSettings,
    EvolutionSource,
    EvolutionTarget,
    GenerateEvolutionCandidate,
    SaveEvolutionCandidate,
)
from my_agent.execution.types import ProgramCommand, RunCommandArgs
from my_agent.sessions.types import ToolCompleted
from my_agent.tools.files import FileTools
from tests.python.test_evolution import ReviewModel
from tests.python.test_goal_controller import app_at, call, create_session, turn


def test_stop_reaps_automatic_resource_write(tmp_path, monkeypatch):
    """停止必须等已开始的文件线程和采用终态完成。

    Stopping waits for an entered file thread and its persisted adoption outcome.
    """

    async def scenario():
        """以屏障复现真实文件提交在取消到达时尚未完成。

        Hold a real file commit at a barrier while cancellation arrives.
        """
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        original = FileTools._commit

        def blocked_commit(self, *args):
            """只延迟原提交，不替换文件行为。

            Delay the original commit without replacing file behavior.
            """
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Commit barrier timed out")
            result = original(self, *args)
            finished.set()
            return result

        async with app_at(tmp_path / "data", ReviewModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service, pid = app.sessions.evolution, created.task.project_id
            target = tmp_path / "project" / "AGENTS.md"
            target.write_text("Original rule\n", encoding="utf-8")
            await app.worker.call(
                service.store.configure,
                EvolutionSettings(project_id=pid, auto_apply=["project_rule"]),
            )
            monkeypatch.setattr(FileTools, "_commit", blocked_commit)
            job = await service.generate(
                GenerateEvolutionCandidate(
                    project_id=pid,
                    target=EvolutionTarget(kind="project_rule", identity="AGENTS.md"),
                )
            )
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                stopping = asyncio.create_task(
                    service.stop(EvolutionJobControl(project_id=pid, job_id=job.job_id))
                )
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(stopping), 0.05)
                assert target.read_text(encoding="utf-8") == "Original rule\n"
            finally:
                release.set()
            stopped = await asyncio.wait_for(stopping, 3)
            assert finished.is_set()
            assert stopped.status == "cancelled"
            candidate = service.store.candidate(pid, job.candidate_id)
            assert candidate.status == "applied" and candidate.pending_action is None
            assert target.read_bytes().decode("utf-8") == candidate.after
            assert service.store.job(pid, job.job_id).status == "cancelled"

    asyncio.run(scenario())


def test_automatic_memory_retains_selected_trace_provenance(tmp_path):
    """自动记忆跟随多个会话和配对结果失效，人工确认保留原语义。

    Automatic memory follows multiple sessions and paired results; user confirmation stays valid.
    """

    class ReadingModel(ReviewModel):
        """源会话使用真实读取工具，不访问外网。

        Source sessions use a real read tool without networking.
        """

        async def complete(self, **kwargs):
            """先读取，再提交简短回答。

            Read first, then commit a short response.
            """
            if kwargs["messages"][-1]["role"] == "tool":
                return turn(text="Observed source fact")
            return turn(call("read_file", path="fact.txt"))

    async def scenario():
        """复用真实选材快照和自动采用入口。

        Exercise real evidence snapshots and the automatic adoption path.
        """
        async with app_at(tmp_path / "data", ReadingModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service, pid = app.sessions.evolution, created.task.project_id
            other = await app.sessions.create(pid, "glm-5.3-flash")
            (tmp_path / "project" / "fact.txt").write_text("Source fact", encoding="utf-8")
            sources = []
            result_seq = None
            for sid in (created.session.session_id, other.session_id):
                accepted = await app.sessions.start(sid, str(uuid4()), "Read fact", None, "plan")
                await app.sessions.active_for(sid).task
                log = await app.sessions._load(sid)
                sources.append(
                    EvolutionSource(
                        session_id=sid,
                        run_id=accepted.run.run_id,
                        scope="run",
                        through_seq=log.facts[-1].seq,
                    )
                )
                result_seq = next(
                    fact.seq for fact in log.facts if isinstance(fact.data, ToolCompleted)
                )
            target = EvolutionTarget(kind="memory", identity="")
            prepared = await service.preview(
                GenerateEvolutionCandidate(project_id=pid, target=target, sources=sources)
            )
            job = EvolutionJob(
                job_id=str(uuid4()), project_id=pid, status="completed", review_input=prepared
            )
            await app.worker.call(service.store.save_job, job)
            fields = json.dumps({"title": "Source fact", "content": "Observed source fact"})
            candidate = await service.create(
                CreateEvolutionCandidate(
                    project_id=pid, target=target, title="Derived fact", after=fields
                )
            )
            candidate.review_job_id, candidate.sources = job.job_id, sources
            candidate = await app.worker.call(service.store.save, candidate)
            automatic = await service.control(
                EvolutionControl(
                    project_id=pid, candidate_id=candidate.candidate_id, action="apply"
                ),
                automatic=True,
            )
            entry = service.resources.memory.read(automatic.target.identity, pid)
            assert {source.session_id for source in entry.trace_sources} == {
                source.session_id for source in sources
            }
            assert any(
                source.session_id == other.session_id and source.seq == result_seq
                for source in entry.trace_sources
            )
            manual = await service.create(
                CreateEvolutionCandidate(
                    project_id=pid, target=target, title="Confirmed fact", after=fields
                )
            )
            manual = await service.control(
                EvolutionControl(project_id=pid, candidate_id=manual.candidate_id, action="apply")
            )
            await app.worker.call(
                service.resources.memory.invalidate_source,
                other.session_id,
                result_seq,
                result_seq,
            )
            assert service.resources.memory.read(automatic.target.identity, pid).stale
            assert not service.resources.memory.read(manual.target.identity, pid).stale

    asyncio.run(scenario())


def test_experiment_comparison_retains_tested_content_revision(tmp_path):
    """实验记录绑定被测正文，后续编辑不会冒用旧通过结论。

    Bind experiments to tested content so later edits cannot inherit an old passing result.
    """

    async def scenario():
        """执行一条真实 Python 检查后修改草稿。

        Edit a draft after executing one actual Python check.
        """
        async with app_at(tmp_path / "data", ReviewModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service, pid = app.sessions.evolution, created.task.project_id
            (tmp_path / "project" / "answer.py").write_text("value = 1\n", encoding="utf-8")
            candidate = await service.create(
                CreateEvolutionCandidate(
                    project_id=pid,
                    target=EvolutionTarget(kind="code", identity="answer.py"),
                    title="Correct answer",
                    after="value = 2\n",
                )
            )
            job = await service.experiment(
                EvolutionExperimentParams(
                    project_id=pid,
                    candidate_id=candidate.candidate_id,
                    command=RunCommandArgs(
                        command=ProgramCommand(
                            kind="program",
                            program=sys.executable,
                            arguments=["-c", "import answer; assert answer.value == 2"],
                        )
                    ),
                )
            )
            await service.jobs[job.job_id][1]
            assert [program.summary.exit_code for program in job.programs] == [1, 0]
            tested = service.store.candidate(pid, candidate.candidate_id)
            edited = await service.edit(
                SaveEvolutionCandidate(
                    project_id=pid,
                    candidate_id=tested.candidate_id,
                    title=tested.title,
                    rationale=tested.rationale,
                    after="value = 3\n",
                    revision=tested.revision,
                )
            )
            assert edited.comparisons[-1].outcome == "improved"
            assert edited.comparisons[-1].content_revision == tested.content_revision
            assert edited.content_revision == tested.content_revision + 1

    asyncio.run(scenario())
