"""子工作通过真实调度器验证，共享预算且不生成正式会话。

Exercise real worker scheduling and budgets without creating formal sessions.
"""

import asyncio
import json
from uuid import uuid4

import pytest

from my_agent.config import DEFAULTS
from my_agent.errors import AgentError
from my_agent.memory.types import MemorySettings
from tests.python.test_goal_controller import app_at, call, create_session, definition, turn


class WorkerModel:
    """控制孩子等待以观察停止和计费。

    Control child waiting to observe cleanup and accounting.
    """

    def __init__(self):
        """保存真实请求和场景门闩。

        Keep actual requests and scenario gates.
        """
        self.owner = None
        self.requests = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.hold = False

    def check_available(self):
        """无网络依赖。

        No network dependency.
        """

    async def complete(self, **kwargs):
        """父请求先派工作再读取结果，孩子使用独立上下文。

        The parent delegates and reads results; the child uses independent context.
        """
        self.requests.append(kwargs)
        messages = kwargs["messages"]
        names = {tool["function"]["name"] for tool in kwargs["tools"]}
        if kwargs["session_id"] != self.owner:
            assert "spawn_worker" not in names
            self.started.set()
            if self.hold:
                await self.release.wait()
            return turn(text="Independent research is complete")
        if "spawn_worker" not in names:
            return turn(text="No delegation available")
        outputs = [json.loads(msg["content"]) for msg in messages if msg["role"] == "tool"]
        if not outputs:
            return turn(
                call("spawn_worker", objective="Read startup instructions", scope="Read only")
            )
        if len(outputs) == 1:
            return turn(call("read_worker", worker_id=outputs[0]["worker_id"]))
        return turn(text="Combined the actual child result")


async def setup(app, model, path):
    """明确关闭本场景无关的空闲整理。

    Disable unrelated maintenance for this scenario.
    """
    created = await create_session(app, path)
    model.owner = created.session.session_id
    await app.sessions.memory.configure(model.owner, MemorySettings(automatic=False))
    return created


def test_workers_share_budget_and_remain_internal(tmp_path):
    """实际工具委派和结果回读，父账本包含孩子消耗。

    Actual delegation and result tools include child usage in the parent ledger.
    """

    async def scenario():
        model = WorkerModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await setup(app, model, tmp_path / "project")
            sid = model.owner
            await app.dispatch(
                "workers.configure", {"session_id": sid, "settings": {"enabled": True}}
            )
            await app.sessions.start(sid, str(uuid4()), "Delegate independent research", None)
            active = app.sessions.active_for(sid)
            await asyncio.wait_for(asyncio.shield(active.task), 8)
            result = await app.sessions.view(sid)
            assert result.summary.run.status == "completed", result.summary.run
            assert result.summary.run.requests == len(model.requests) == 4
            page = await app.dispatch("workers.list", {"session_id": sid})
            assert page.workers[0].status == "completed", page
            assert page.workers[0].result == "Independent research is complete"
            sessions = await app.sessions.list(created.task.project_id, None, 50)
            assert [item.session_id for item in sessions.sessions] == [sid]
            assert app.sessions.active_runs == {}

    asyncio.run(scenario())


def test_configuring_live_workers_keeps_event_waits_responsive(tmp_path, monkeypatch):
    """运行中关闭委派仍可接收孩子结果，不忙循环。

    Disabling delegation during work preserves child results without busy waiting.
    """

    async def scenario():
        """模型门闩控制在途请求；探针防止旧缺陷挂死测试。

        Hold the model request and bound the old busy-loop defect in the probe.
        """
        model = WorkerModel()
        model.hold = True
        async with app_at(tmp_path / "data", model) as app:
            await setup(app, model, tmp_path / "project")
            sid = model.owner
            await app.dispatch(
                "workers.configure", {"session_id": sid, "settings": {"enabled": True}}
            )
            await app.sessions.start(sid, str(uuid4()), "Delegate independent work", None)
            active = app.sessions.active_for(sid)
            await asyncio.wait_for(model.started.wait(), 5)
            await asyncio.sleep(0.05)
            service = app.sessions.delegations
            event = service.changed
            wait = event.wait
            calls = 0

            async def observed_wait():
                """限次仅为测试看门狗，不进入产品调度。

                Bound the regression probe only, never production scheduling.
                """
                nonlocal calls
                calls += 1
                if calls >= 32:
                    raise RuntimeError("busy event loop")
                return await wait()

            monkeypatch.setattr(event, "wait", observed_wait)
            await app.dispatch(
                "workers.configure", {"session_id": sid, "settings": {"enabled": False}}
            )
            await asyncio.sleep(0)
            assert calls < 32
            assert service.watcher and not service.watcher.done()
            assert not service.changed.is_set()
            model.release.set()
            await asyncio.wait_for(asyncio.shield(active.task), 5)
            page = await service.page(sid)
            assert not page.settings.enabled
            assert page.workers[0].status == "completed"

    asyncio.run(scenario())


def test_worker_continuation_failure_does_not_return_old_answer(tmp_path):
    """续跑连接失败时，父子结果都保留本次原因而非旧成功答案。

    A failed continuation reports its current failure in both child and parent results.
    """

    class ContinuingModel(WorkerModel):
        """首轮成功，第二轮孩子连接失败的可控模型。

        Complete the first child run and fail its next connection.
        """

        def __init__(self):
            """记录复用的孩子与实际子请求次数。

            Track the reused worker and actual child request count.
            """
            super().__init__()
            self.worker_id = None
            self.child_calls = 0

        async def complete(self, **kwargs):
            """按当前用户回合选择委派或续跑，不拼接历史结果。

            Delegate or continue by the current user turn without copying old results.
            """
            if kwargs["session_id"] != self.owner:
                self.child_calls += 1
                if self.child_calls > 1:
                    raise AgentError("MODEL_CONNECTION_FAILED", "Current child connection failed")
                return turn(text="Old successful answer")
            messages = kwargs["messages"]
            last_user = max(i for i, msg in enumerate(messages) if msg["role"] == "user")
            outputs = [
                json.loads(msg["content"])
                for msg in messages[last_user + 1 :]
                if msg["role"] == "tool"
            ]
            if not outputs:
                if self.worker_id:
                    return turn(
                        call("continue_worker", worker_id=self.worker_id, prompt="Follow up")
                    )
                return turn(call("spawn_worker", objective="Independent work"))
            self.worker_id = outputs[0]["worker_id"]
            if len(outputs) == 1:
                return turn(call("read_worker", worker_id=self.worker_id))
            return turn(text="Owner finished")

    async def scenario():
        """真实调度两轮，核对错误来源并保留孩子历史。

        Schedule two actual runs and verify failure provenance with retained child history.
        """
        model = ContinuingModel()
        async with app_at(tmp_path / "data", model) as app:
            await setup(app, model, tmp_path / "project")
            sid = model.owner
            await app.dispatch(
                "workers.configure", {"session_id": sid, "settings": {"enabled": True}}
            )
            for prompt in ("First run", "Continue the worker"):
                await app.sessions.start(sid, str(uuid4()), prompt, None)
                active = app.sessions.active_for(sid)
                await asyncio.wait_for(asyncio.shield(active.task), 8)
            page = await app.sessions.delegations.page(sid)
            result = await app.sessions.view(sid)
            assert page.workers[0].status == "failed"
            assert page.workers[0].code == "MODEL_CONNECTION_FAILED"
            assert page.workers[0].result == "Current child connection failed"
            assert result.summary.run.message == "Current child connection failed"

    asyncio.run(scenario())


def test_invalid_worker_settings_only_disable_optional_delegation(tmp_path):
    """损坏委派配置不拦普通对话，查看报错且明确保存后恢复。

    Corrupt delegation settings allow chat, remain diagnosable, and recover on explicit save.
    """

    async def scenario():
        """真实加载错误不被缓存或改写为默认成功状态。

        Never cache or overwrite a real load failure as successful default settings.
        """
        model = WorkerModel()
        async with app_at(tmp_path / "data", model) as app:
            await setup(app, model, tmp_path / "project")
            sid = model.owner
            service = app.sessions.delegations
            path = app.sessions.store.path(sid).with_name("workers.json")
            path.write_text("{broken", encoding="utf-8")
            service.settings.pop(sid, None)
            await app.sessions.start(sid, str(uuid4()), "Ordinary conversation", None)
            active = app.sessions.active_for(sid)
            await asyncio.wait_for(asyncio.shield(active.task), 5)
            view = await app.sessions.view(sid)
            assert view.summary.run.status == "completed"
            assert path.read_text(encoding="utf-8") == "{broken"
            assert sid not in service.settings
            assert "spawn_worker" not in {
                tool["function"]["name"] for tool in model.requests[0]["tools"]
            }
            with pytest.raises(AgentError) as failure:
                await service.page(sid)
            assert failure.value.code == "DATA_INVALID"
            repaired = await app.dispatch(
                "workers.configure", {"session_id": sid, "settings": {"enabled": True}}
            )
            assert repaired.settings.enabled
            await app.sessions.start(sid, str(uuid4()), "Delegate after repair", None)
            active = app.sessions.active_for(sid)
            await asyncio.wait_for(asyncio.shield(active.task), 5)
            assert (await service.page(sid)).workers[0].status == "completed"

    asyncio.run(scenario())


def test_worker_stop_and_budget_failure_reap_children(tmp_path):
    """共同限额与明确停止均回收实际子运行。

    Shared limits and explicit stops reap actual children.
    """

    async def scenario():
        model = WorkerModel()
        model.hold = True
        async with app_at(tmp_path / "data", model) as app:
            await setup(app, model, tmp_path / "project")
            sid = model.owner
            await app.dispatch(
                "workers.configure", {"session_id": sid, "settings": {"enabled": True}}
            )
            await app.sessions.start(sid, str(uuid4()), "Delegate and wait", None)
            owner = app.sessions.active_for(sid)
            await asyncio.wait_for(model.started.wait(), 5)
            assert [item.session_id for item in await app.sessions.active_summaries()] == [sid]
            await app.sessions.cancel(owner.run_id)
            await asyncio.wait_for(asyncio.shield(owner.task), 5)
            assert not app.sessions.active_runs
            assert (await app.dispatch("workers.list", {"session_id": sid})).workers[
                0
            ].status == "cancelled"
        model = WorkerModel()
        async with app_at(tmp_path / "limited", model) as app:
            await setup(app, model, tmp_path / "limited-project")
            sid = model.owner
            await app.dispatch(
                "workers.configure", {"session_id": sid, "settings": {"enabled": True}}
            )
            await app.dispatch(
                "runs.start",
                {
                    "session_id": sid,
                    "operation_id": str(uuid4()),
                    "prompt": "Delegate",
                    "limits": {**DEFAULTS["run"], "max_requests": 1},
                    "mode": "normal",
                },
            )
            active = app.sessions.active_for(sid)
            await asyncio.wait_for(asyncio.shield(active.task), 5)
            summary = (await app.sessions.view(sid)).summary
            assert summary.run.status in {"failed", "budget_exceeded"}, summary
            assert len(model.requests) == 1
            assert not app.sessions.active_runs

    asyncio.run(scenario())


def test_goal_question_preserves_worker_and_original_budget(tmp_path):
    """插话回答不等待或停止孩子，原 Goal 恢复后读取真实结果。

    Questions neither wait for nor stop children; the original goal consumes their results.
    """

    class GoalWorker(WorkerModel):
        """按局部目标调度而不额外生成运行内核。

        Exercise the existing goal scheduler.
        """

        async def complete(self, **kwargs):
            """区分普通插话与原目标工作。

            Distinguish questions from the original goal.
            """
            if kwargs["session_id"] == self.owner:
                if "ordinary question interrupting" in kwargs["messages"][0]["content"]:
                    self.requests.append(kwargs)
                    return turn(text="Child still working; continuing the original goal")
                outputs = [
                    json.loads(msg["content"])
                    for msg in kwargs["messages"]
                    if msg["role"] == "tool"
                ]
                worker = next((item["worker_id"] for item in outputs if "worker_id" in item), None)
                if worker and any(item.get("status") == "completed" for item in outputs):
                    self.requests.append(kwargs)
                    return turn(
                        call(
                            "report_work",
                            summary="Received actual child result",
                            outcome="complete",
                        )
                    )
                if worker:
                    self.requests.append(kwargs)
                    return turn(call("read_worker", worker_id=worker))
            return await super().complete(**kwargs)

    async def scenario():
        model = GoalWorker()
        model.hold = True
        async with app_at(tmp_path / "data", model) as app:
            await setup(app, model, tmp_path / "project")
            sid = model.owner
            await app.dispatch(
                "workers.configure", {"session_id": sid, "settings": {"enabled": True}}
            )
            await app.sessions.goals.create(sid, definition(max_requests=12, max_tools=12))
            driver = app.sessions.goals.driver(sid)
            await asyncio.wait_for(model.started.wait(), 5)
            await app.sessions.start(sid, str(uuid4()), "How is it going?", None, mode="normal")
            async with asyncio.timeout(5):
                while not any(
                    "ordinary question interrupting" in req["messages"][0]["content"]
                    for req in model.requests
                ):
                    await asyncio.sleep(0.01)
                while (
                    app.sessions.active_for(sid)
                    and app.sessions.active_for(sid).goal.role == "question"
                ):
                    await asyncio.sleep(0.01)
            assert (await app.sessions.delegations.page(sid)).workers[0].status == "running"
            model.release.set()
            await asyncio.wait_for(asyncio.shield(driver.task), 6)
            goals = await app.sessions.goals.list(sid)
            assert goals[-1].status == "completed", goals[-1]
            assert goals[-1].usage.requests == len(model.requests)
            assert not app.sessions.active_runs

    asyncio.run(scenario())
