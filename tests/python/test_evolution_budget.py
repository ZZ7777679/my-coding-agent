"""改进预算经真实服务保存并进入模型调用，不使用个人数据或网络。

Verify persisted improvement budgets through real services without personal data or network.
"""

import asyncio
import json
from uuid import uuid4

import pytest

from my_agent.evolution.types import (
    EvolutionBudget,
    EvolutionJob,
    EvolutionJobControl,
    EvolutionSettings,
    EvolutionTarget,
    GenerateEvolutionCandidate,
    SaveEvolutionFeedback,
)
from tests.python.test_evolution import ReviewModel
from tests.python.test_goal_controller import app_at, call, create_session, turn


class BudgetModel(ReviewModel):
    """暂停首请求并要求继续读取，观察预算快照和实际循环限额。

    Pause the first request and read again to observe snapshots and enforced loop limits.
    """

    def __init__(self):
        """记录调用与手动释放信号。 Record calls and an explicit release signal."""
        super().__init__()
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.steps = {}

    async def complete(self, **kwargs):
        """调查执行两次文件读取；定向生成返回一个合法候选。

        Investigations read twice; directed generation returns one valid candidate.
        """
        self.requests.append(kwargs)
        self.started.set()
        await self.release.wait()
        if kwargs["messages"][0]["content"].startswith("Investigate selected"):
            sid = kwargs["session_id"]
            step = self.steps.get(sid, 0)
            self.steps[sid] = step + 1
            if step < 2:
                return turn(call("read_file", path="AGENTS.md"))
            return turn(text=json.dumps({"summary": "Read only; no changes needed."}))
        return turn(text=json.dumps({"title": "Focused", "rationale": "Feedback", "after": "New"}))


@pytest.mark.parametrize("mode", ["investigate", "propose", "directed"])
@pytest.mark.parametrize("unlimited", [False, True])
def test_evolution_budget_is_independent_persisted_and_snapshotted(tmp_path, mode, unlimited):
    """调查／接续／定向生成独立于全局设置，在途不变，新作业采用新值。

    Investigation, proposal and directed jobs ignore global budgets and snapshot each start.
    """

    async def scenario():
        model = BudgetModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            pid = created.task.project_id
            (tmp_path / "project" / "AGENTS.md").write_text("Original", encoding="utf-8")
            config = await app.dispatch("config.get", {})
            global_run = config.run.model_copy(
                update={
                    "max_requests": 1,
                    "max_tools": 1,
                    "max_context_bytes": 4096,
                    "max_response_bytes": 1024,
                }
            )
            await app.dispatch(
                "config.update", {"model_id": config.model_id, "run": global_run.model_dump()}
            )
            budget = EvolutionBudget(
                max_requests=4,
                max_tools=3,
                max_seconds=40,
                request_timeout_seconds=21,
                max_output_tokens=2048,
            )
            settings = EvolutionSettings(project_id=pid, budget=budget, input_chars=30000)
            if unlimited:
                budget = EvolutionBudget.model_validate(
                    {key: None for key in EvolutionBudget.model_fields}
                )
                settings.budget = budget
            saved = await app.dispatch("evolution.configure", settings.model_dump())
            service = app.sessions.evolution
            assert saved.budget == budget
            assert service.store.settings(pid) == saved
            params = GenerateEvolutionCandidate(
                project_id=pid,
                mode="propose" if mode == "directed" else mode,
                target=EvolutionTarget(kind="project_rule", identity="AGENTS.md")
                if mode == "directed"
                else None,
                instruction="Review the rules",
            )
            job = await service.generate(params)
            task = service.jobs[job.job_id][1]
            await asyncio.wait_for(model.started.wait(), 5)
            updated = saved.model_copy(
                update={"budget": budget.model_copy(update={"max_requests": 1})}
            )
            await app.dispatch("evolution.configure", updated.model_dump())
            model.release.set()
            await task
            assert job.status == "completed", job.message
            assert job.budget == budget
            assert job.requests == 3
            for request in model.requests:
                assert all(
                    getattr(request["limits"], key) == value
                    for key, value in budget.model_dump().items()
                )
            assert service.store.job(pid, job.job_id).budget == budget
            assert (await app.dispatch("config.get", {})).run == global_run
            assert service.store.settings(pid).budget == updated.budget
            next_job = await service.generate(params)
            await service.jobs[next_job.job_id][1]
            assert next_job.budget == updated.budget
            assert next_job.status == "failed"
            assert next_job.requests == 1
            assert "请求预算" in next_job.message
            assert EvolutionJob.model_validate(job.model_dump(exclude={"budget"})).budget is None
            assert EvolutionSettings.model_validate({"project_id": pid}).budget == EvolutionBudget()

    asyncio.run(scenario())


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("deadline", [1, None])
def test_evolution_total_timeout_uses_module_budget(tmp_path, directed, deadline):
    """两条入口都在模块总时限停止，保留明确调整入口。

    Both entry paths stop at their module deadline and identify the adjustment location.
    """

    async def scenario():
        model = BudgetModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            pid = created.task.project_id
            (tmp_path / "project" / "AGENTS.md").write_text("Original", encoding="utf-8")
            await app.dispatch(
                "evolution.configure",
                {
                    "project_id": pid,
                    "budget": {"max_seconds": deadline, "request_timeout_seconds": None},
                },
            )
            service = app.sessions.evolution
            job = await service.generate(
                GenerateEvolutionCandidate(
                    project_id=pid,
                    mode="propose" if directed else "investigate",
                    target=EvolutionTarget(kind="project_rule", identity="AGENTS.md")
                    if directed
                    else None,
                    instruction="Review the rules",
                )
            )
            task = service.jobs[job.job_id][1]
            if deadline is None:
                await asyncio.wait_for(model.started.wait(), 5)
                await service.stop(EvolutionJobControl(project_id=pid, job_id=job.job_id))
                assert job.status == "cancelled"
            else:
                await asyncio.wait_for(task, 5)
                assert job.status == "failed"
                assert "改进预算" in job.message
            assert job.requests == 1
            assert job.job_id not in service.jobs
            assert service.store.job(pid, job.job_id).status == job.status

    asyncio.run(scenario())


@pytest.mark.parametrize("directed", [False, True])
def test_evolution_unlimited_materials_keep_full_feedback(tmp_path, directed):
    """有限选材确实裁剪，不限选材保留全部正文与真实计数。

    Bounded material selection truncates; unlimited selection retains full bodies and counts.
    """

    async def scenario():
        async with app_at(tmp_path / "data", ReviewModel()) as app:
            created = await create_session(app, tmp_path / "project")
            pid = created.task.project_id
            service = app.sessions.evolution
            content = "evidence " * 10000 + "TAIL"
            feedback = await service.feedback(
                SaveEvolutionFeedback(
                    project_id=pid,
                    feedback_id=str(uuid4()),
                    text=content,
                )
            )
            params = GenerateEvolutionCandidate(
                project_id=pid,
                feedback_ids=[feedback.feedback_id],
                mode="propose" if directed else "investigate",
                target=EvolutionTarget(kind="project_rule", identity="AGENTS.md")
                if directed
                else None,
            )
            await app.dispatch("evolution.configure", {"project_id": pid, "input_chars": 10})
            limited = await service.preview(params)
            assert limited.included_chars == 10
            await app.dispatch("evolution.configure", {"project_id": pid, "input_chars": None})
            unlimited = await service.preview(params)
            material = next(m for m in unlimited.materials if m.kind == "feedback")
            assert material.content == content and not material.truncated
            assert unlimited.included_chars >= len(content)
            assert unlimited.input_chars is None and unlimited.omitted_materials == 0

    asyncio.run(scenario())
