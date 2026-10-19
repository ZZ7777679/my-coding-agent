"""任务工作图的真实持久化和模拟模型闭环。

Persist task graphs and exercise offline model execution.
"""

import asyncio
from uuid import uuid4

import pytest

from my_agent.errors import AgentError
from my_agent.goals.types import GoalControl
from my_agent.sessions.types import RequestStarted
from tests.python.test_collaboration import finish
from tests.python.test_goal_controller import app_at, call, create_session, turn
from tests.python.test_spaces import save_team, team


class WorkModel:
    """只替换模型，工作工具和接续仍使用真实实现。

    Replace the model only; use production work tools and continuation.
    """

    def __init__(self):
        """保留请求材料和可配置响应序列。 Keep actual requests and controlled responses."""
        self.steps = []
        self.requests = []
        self.fail = False
        self.hold = False
        self.entered = asyncio.Event()

    def check_available(self):
        """离线模型无需凭据。 Offline model needs no credentials."""

    async def complete(self, **kwargs):
        """按序给出工具或回答，故障使用真实业务错误。

        Return sequenced calls or actual failure semantics.
        """
        self.requests.append(kwargs)
        if self.fail:
            raise AgentError("MODEL_NETWORK", "Isolated network failure")
        if self.hold:
            self.entered.set()
            await asyncio.Event().wait()
        return self.steps.pop(0) if self.steps else turn(text="Done with this request")


async def wait_goal(app, session_id):
    """等待现有 Goal 驱动，不把观察超时当作完成。 Await the existing goal driver explicitly."""
    driver = app.sessions.goals.drivers.get(session_id)
    if driver:
        await asyncio.wait_for(asyncio.shield(driver.task), 5)


def test_graph_snapshot_runs_feedback_and_restart(tmp_path):
    """模板、工作定义、阶段 Skill 和反馈结果跨重启保留。

    Keep snapshots, definitions, stage skills and feedback across restart.
    """

    async def scenario():
        """通过正式 RPC 和真实文件存储验证，零外网。 Exercise production RPC and storage offline."""
        model = WorkModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            task_id = created.task.task_id
            config = team()
            owner = config["members"][0]["member_id"]
            await save_team(app, task_id, config)
            before = set((tmp_path / "data" / "sessions").iterdir())
            graph = await app.dispatch("spaces.work_graph", {"task_id": task_id})
            assert graph.suggested_items
            build = next(item for item in graph.suggested_items if item.stage_id == "implement")
            review = next(item for item in graph.suggested_items if item.stage_id == "review")
            build.title = "Build counter"
            # Missing dependencies and feedback cycles remain planning facts, not save gates.
            # 缺少依赖和反馈环是计划事实，不成为保存或普通执行门槛。
            build.depends_on = ["not-planned"]
            build.feedback_to = [review.work_id]
            review.feedback_to = [build.work_id]
            graph = await app.dispatch(
                "spaces.work_graph_save",
                {
                    "task_id": task_id,
                    "operation_id": str(uuid4()),
                    "expected_revision": graph.task.revision,
                    "items": [build.model_dump(), review.model_dump()],
                },
            )
            assert before == set((tmp_path / "data" / "sessions").iterdir())
            assert model.requests == []
            assert list((tmp_path / "project").iterdir()) == []
            with pytest.raises(AgentError) as unbound:
                await app.dispatch(
                    "spaces.work_graph_start",
                    {
                        "task_id": task_id,
                        "operation_id": str(uuid4()),
                        "work_ids": [build.work_id],
                        "member_id": owner,
                    },
                )
            assert unbound.value.code == "SPACE_MEMBER_UNBOUND"
            await app.dispatch("spaces.start", {"task_id": task_id})
            space = (await app.dispatch("spaces.get", {"task_id": task_id})).space
            session = next(b.session_id for b in space.bindings if b.member_id == owner)
            params = {
                "task_id": task_id,
                "operation_id": str(uuid4()),
                "work_ids": [build.work_id],
                "member_id": owner,
            }
            await app.dispatch("spaces.work_graph_start", params)
            await finish(app, session)
            graph = await app.dispatch("spaces.work_graph", {"task_id": task_id})
            assert graph.items[0].status == "planned"  # Run success is not work completion.
            assert graph.task.workflow.session_stages[session] == "implement"
            assert graph.activity.messages[-1].work_ids == [build.work_id]
            count = len(model.requests)
            await app.dispatch("spaces.work_graph_start", params)
            assert len(model.requests) == count
            draft_revision = graph.task.revision
            # One continuous objective revisits implementation after feedback then finishes.
            # 一个持续目标中，反馈后再次进入实现，再完成目标。
            model.steps = [
                turn(
                    call(
                        "manage_space_work",
                        work_id=review.work_id,
                        action="claim",
                        status="in_progress",
                    )
                ),
                turn(
                    call(
                        "manage_space_work",
                        work_id=review.work_id,
                        action="result",
                        status="completed",
                        result="Adjust the button label",
                    )
                ),
                turn(
                    call(
                        "report_work",
                        summary="Review returned actionable feedback",
                        outcome="continue",
                        next_action="Apply the authorized label fix",
                        work_items=[
                            build.model_copy(
                                update={
                                    "title": "Model proposes another title",
                                    "scope": "Different scope",
                                    "status": "in_progress",
                                }
                            ).model_dump()
                        ],
                    )
                ),
                turn(
                    call(
                        "manage_space_work",
                        work_id=build.work_id,
                        action="claim",
                        status="in_progress",
                    )
                ),
                turn(
                    call(
                        "manage_space_work",
                        work_id=build.work_id,
                        action="result",
                        status="completed",
                        result="Label updated",
                    )
                ),
                turn(call("report_work", summary="Selected work complete", outcome="complete")),
            ]
            await app.dispatch(
                "spaces.work_graph_start",
                {
                    **params,
                    "operation_id": str(uuid4()),
                    "work_ids": [build.work_id, review.work_id],
                    "continuous": True,
                    "instruction": "Review the change and fix findings",
                },
            )
            await wait_goal(app, session)
            graph = await app.dispatch("spaces.work_graph", {"task_id": task_id})
            assert all(item.status == "completed" for item in graph.items)
            # 后台进度不拒绝未改动定义的旧草稿；已有结果也不能被草稿覆盖。
            # Background progress permits an old definition draft without losing live results.
            graph = await app.dispatch(
                "spaces.work_graph_save",
                {
                    "task_id": task_id,
                    "operation_id": str(uuid4()),
                    "expected_revision": draft_revision,
                    "items": [build.model_dump(), review.model_dump()],
                },
            )
            assert all(item.status == "completed" for item in graph.items)
            assert graph.task.workflow.session_stages[session] == "implement"
            assert (await app.sessions.goals.list(session))[-1].status == "completed"
            assert (
                len(
                    {
                        output.run_id
                        for output in graph.activity.outputs
                        if output.origin_id == graph.activity.rounds[-1].round_id
                    }
                )
                == 2
            )
            log = app.sessions.store.load(session)
            materials = [
                fact.data.context.materials
                for fact in log.facts
                if isinstance(fact.data, RequestStarted) and fact.data.context is not None
            ]
            assert any(
                any(m.kind == "skill" and "review" in (m.source_id or "") for m in group)
                for group in materials
            )
            assert any(
                any(m.kind == "skill" and "implement" in (m.source_id or "") for m in group)
                for group in materials
            )
            # A report can update progress but cannot rewrite user-maintained node definitions.
            # 报告可更新进度，不能覆盖用户维护的工作定义。
            assert graph.items[0].title == "Build counter"
        async with app_at(tmp_path / "data", WorkModel()) as restored:
            graph = await restored.dispatch("spaces.work_graph", {"task_id": task_id})
            assert len(graph.task.work.planned_items) == 2
            assert len(graph.activity.messages) == 1 and len(graph.activity.rounds) == 1
            assert graph.items[0].feedback_to == [review.work_id]
            assert graph.items[0].result == "Label updated"

    asyncio.run(scenario())


def test_graph_failure_stops_and_user_stop_preserves_history(tmp_path):
    """真实故障终止原 Goal；用户停止不丢失工作图。

    Stop the existing Goal on failure and retain the graph on explicit cancellation.
    """

    async def scenario():
        """复用实际停止和持久化路径。 Reuse actual stop and persistence paths."""
        model = WorkModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            task_id = created.task.task_id
            config = team()
            owner = config["members"][0]["member_id"]
            config["initial_work_items"] = [
                {"work_id": "build", "title": "Build", "scope": "Build", "status": "planned"}
            ]
            await save_team(app, task_id, config)
            space = (await app.dispatch("spaces.start", {"task_id": task_id})).space
            session = next(b.session_id for b in space.bindings if b.member_id == owner)
            params = {
                "task_id": task_id,
                "operation_id": str(uuid4()),
                "work_ids": ["build"],
                "member_id": owner,
                "continuous": True,
            }
            model.fail = True
            await app.dispatch("spaces.work_graph_start", params)
            await wait_goal(app, session)
            goals = await app.sessions.goals.list(session)
            assert goals[-1].status != "active"
            calls = len(model.requests)
            await app.dispatch("spaces.work_graph", {"task_id": task_id})
            assert len(model.requests) == calls == 1
            model.fail, model.hold = False, True
            current = (await app.sessions.goals.list(session))[-1]
            await app.sessions.goals.control(
                session,
                GoalControl(
                    goal_id=current.goal_id,
                    operation_id=str(uuid4()),
                    expected_revision=current.revision,
                    action="resume",
                ),
            )
            await asyncio.wait_for(model.entered.wait(), 5)
            await app.dispatch("spaces.stop", {"task_id": task_id, "member_id": owner})
            assert (await app.sessions.goals.list(session))[-1].status != "active"
            graph = await app.dispatch("spaces.work_graph", {"task_id": task_id})
            assert len(graph.activity.rounds) == 1 and len(graph.items) == 1

    asyncio.run(scenario())
