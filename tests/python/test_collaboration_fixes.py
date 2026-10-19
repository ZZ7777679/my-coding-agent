"""审查发现的协作行为回归，模型替身之外均使用真实服务。

Regression checks for collaboration review findings using real services with fake models.
"""

import asyncio
import json
from uuid import uuid4

from my_agent.collaboration.types import CollaborationPageParams
from my_agent.sessions.types import RunAccepted, ToolCompleted
from my_agent.spaces.team_types import SpaceChatMessage
from my_agent.storage import write_document
from tests.python.test_collaboration import connect, finish, pair
from tests.python.test_goal_controller import app_at, call, create_session, definition, turn
from tests.python.test_spaces import save_team, team
from tests.python.test_work_graph import WorkModel, wait_goal


def test_unarranged_peer_is_feedback_and_readonly_goal_stays_readonly(tmp_path):
    """未投递反馈不停止 Goal，审查接续仍只读且实际错误保留。

    Admission feedback preserves the goal and review continuation remains read-only.
    """

    async def scenario():
        """复用真实协作工具与 Goal 接续。

        Exercise actual collaboration tools and goal continuation.
        """
        model = WorkModel()
        async with app_at(tmp_path / "data", model) as app:
            source, target = await pair(app, tmp_path / "project")
            model.steps = [
                turn(call("request_collaboration", target_session_id=target, objective="Review")),
                turn(text="There is no arrangement; returning the actionable feedback"),
            ]
            await app.sessions.start(source, str(uuid4()), "Ask reviewer", None)
            await finish(app, source)
            assert (await app.sessions.view(source)).summary.run.status == "completed"
            assert len(model.requests) == 2
            goal = definition(max_requests=5).model_copy(update={"method": "review"})
            model.steps = [
                turn(call("request_collaboration", target_session_id=target, objective="Review")),
                turn(
                    call(
                        "report_work",
                        summary="Continue the review after reporting the unavailable peer",
                        outcome="continue",
                        next_action="Review locally",
                        work_items=[
                            {
                                "work_id": "review",
                                "title": "Review",
                                "scope": "Inspect files",
                                "method": "review",
                                "status": "in_progress",
                            }
                        ],
                    )
                ),
                turn(call("report_work", summary="Review complete", outcome="complete")),
            ]
            await app.sessions.goals.create(source, goal)
            await wait_goal(app, source)
            assert (await app.sessions.goals.list(source))[-1].status == "completed"
            log = await app.worker.call(app.sessions.store.load, source)
            accepted = [
                f.data
                for f in log.facts
                if isinstance(f.data, RunAccepted) and f.data.goal_id == goal.goal_id
            ]
            assert [r.mode for r in accepted] == ["plan", "plan"]
            output = next(f.data.result for f in log.facts if isinstance(f.data, ToolCompleted))
            assert json.loads(output.content)["cause_code"] == "COLLABORATION_NOT_LINKED"
            page = await app.sessions.collaboration.page(CollaborationPageParams(session_id=source))
            assert not page.requests

    asyncio.run(scenario())


def test_discovery_wait_cancel_summaries_and_shared_file_provenance(tmp_path):
    """真实工具查询来源、等待到期和精确取消不误停其他工作。

    Real tools expose provenance and cancel exact requests without stopping unrelated runs.
    """

    async def scenario():
        """仅替换模型，接纳、运行、文件与持久化均走正式服务。

        Replace only the model, exercising production admission, execution, files and storage.
        """
        model = WorkModel()
        async with app_at(tmp_path / "data", model) as app:
            source, target = await pair(app, tmp_path / "project")
            service = app.sessions.collaboration
            page = await service.page(CollaborationPageParams(session_id=source))
            assert page.reason == "no_agreements_configured"
            assert page.candidates[0].session_id == target
            assert not page.worker_enabled and page.worker_reason
            await app.dispatch(
                "workers.configure",
                {
                    "session_id": source,
                    "settings": {"enabled": True},
                },
            )
            assert (await service.page(CollaborationPageParams(session_id=source))).worker_enabled
            # 没有 peer 约定，仍可查看同任务文件来源；不会扩大到其他任务。
            # Shared artifact provenance is task-scoped, independent of peer history grants.
            model.steps = [turn(call("create_file", path="shared.py", content="value = 1\n"))]
            await app.sessions.start(target, str(uuid4()), "Create", None, "normal")
            await finish(app, target)
            model.steps = [turn(call("list_changes", scope="task", path="shared.py"))]
            await app.sessions.start(source, str(uuid4()), "Inspect provenance", None)
            await finish(app, source)
            log = await app.worker.call(app.sessions.store.load, source)
            output = [f.data.result for f in log.facts if isinstance(f.data, ToolCompleted)][-1]
            shared = json.loads(output.content)
            assert shared["changes"][0]["session_id"] == target
            assert "sha256" not in output.content
            assert shared["coverage"]
            change_id = shared["changes"][0]["change_id"]
            model.steps = [
                turn(call("read_change", scope="task", session_id=target, change_id=change_id))
            ]
            await app.sessions.start(source, str(uuid4()), "Inspect diff", None)
            await finish(app, source)
            await connect(app, source, target)
            assert (
                await service.page(CollaborationPageParams(session_id=source))
            ).reason == "ready"
            model.hold = True
            await app.sessions.start(target, str(uuid4()), "hold", None)
            await asyncio.wait_for(model.entered.wait(), 3)
            unrelated_run = app.sessions.active_for(target).run_id
            request = await app.dispatch(
                "collaboration.request",
                {
                    "operation_id": str(uuid4()),
                    "source_session_id": source,
                    "target_session_id": target,
                    "objective": "Review later",
                },
            )
            pending = await service.result(source, request.request_id, wait=True, wait_seconds=0.03)
            assert pending.status == "queued" and pending.reason
            assert app.sessions.active_for(target).run_id == unrelated_run
            model.hold = False
            model.steps = [
                turn(call("cancel_collaboration", request_id=request.request_id)),
                turn(call("read_collaboration", request_id=request.request_id)),
                turn(call("read_session", target_session_id=target, summary_only=True)),
            ]
            await app.sessions.start(
                source, str(uuid4()), "Cancel queued work and read status", None
            )
            await finish(app, source)
            assert (await app.sessions.view(source)).summary.run.status == "completed"
            assert app.sessions.active_for(target).run_id == unrelated_run
            assert (
                await service.result(source, request.request_id, wait=False)
            ).status == "cancelled"
            await app.sessions.cancel(unrelated_run)
            await finish(app, target)
            summary = await service.peer_summary(source, target)
            assert summary["summary"]["session_id"] == target
            assert summary["waiting_reason"]

    asyncio.run(scenario())


def test_graph_edits_long_input_and_growing_history_restore(tmp_path):
    """当前图可删除并恢复，长输入与增长历史跨重启可读。

    Persist graph removal/restoration, long input and growing history across restart.
    """

    async def scenario():
        """同一隔离任务验证定义、分配、分页与真实保存。

        Exercise definitions, ownership, paging and actual persistence in one isolated task.
        """
        model = WorkModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            task_id = created.task.task_id
            config = team()
            owner = config["members"][0]["member_id"]
            node = {
                "work_id": "generated",
                "title": "Review",
                "scope": "Review files",
                "status": "planned",
                "method": "review",
                "stage_id": "review",
                "position": {"x": 100, "y": 180},
            }
            config["initial_work_items"] = [node]
            await save_team(app, task_id, config)
            graph = await app.dispatch("spaces.work_graph", {"task_id": task_id})
            graph = await app.dispatch(
                "spaces.work_graph_save",
                {
                    "task_id": task_id,
                    "operation_id": str(uuid4()),
                    "expected_revision": graph.task.revision,
                    "items": [],
                },
            )
            assert not graph.items
            assert graph.task.work.removed_work_ids == ["generated"]
            model.steps = [
                turn(
                    call("report_work", summary="Late report", outcome="return", work_items=[node])
                )
            ]
            await app.sessions.start(created.session.session_id, str(uuid4()), "Late report", None)
            await finish(app, created.session.session_id)
            graph = await app.dispatch("spaces.work_graph", {"task_id": task_id})
            assert not graph.items
            graph = await app.dispatch(
                "spaces.work_graph_save",
                {
                    "task_id": task_id,
                    "operation_id": str(uuid4()),
                    "expected_revision": graph.task.revision,
                    "items": [node],
                    "owner_changes": {"generated": owner},
                },
            )
            assert graph.items[0].owner_member_id == owner
            assert graph.items[0].position.x == 100
            assert not graph.task.work.removed_work_ids
            await app.dispatch("spaces.start", {"task_id": task_id})
            space = (await app.dispatch("spaces.get", {"task_id": task_id})).space
            session = next(b.session_id for b in space.bindings if b.member_id == owner)
            result = await app.dispatch(
                "spaces.work_graph_start",
                {
                    "task_id": task_id,
                    "operation_id": str(uuid4()),
                    "work_ids": ["generated"],
                    "member_id": owner,
                    "instruction": "x" * 16000,
                },
            )
            assert result.messages[-1].content.endswith("x" * 16000)
            await finish(app, session)
            record = await app.worker.call(app.team.store.chat, task_id)
            for index in range(100):
                record.view.messages.append(
                    SpaceChatMessage(
                        message_id=str(uuid4()),
                        content="\u5ba1" * 15000,
                        mode="normal",
                        created_at=f"2099-01-01T00:{index // 60:02d}:{index % 60:02d}Z",
                        target_member_ids=[owner],
                    )
                )
            await app.worker.call(app.team.store.save_chat, record)
            recent = await app.dispatch("spaces.chat_view", {"task_id": task_id})
            older = await app.dispatch(
                "spaces.chat_view",
                {
                    "task_id": task_id,
                    "before_id": recent.next_before,
                },
            )
            assert len(recent.messages) == len(older.messages) == 20
            assert not (
                {m.message_id for m in recent.messages} & {m.message_id for m in older.messages}
            )
            legacy = record.model_copy(deep=True)
            legacy.view.messages = [
                SpaceChatMessage(
                    message_id=str(uuid4()),
                    content="Legacy snapshot retained",
                    mode="normal",
                    created_at="2020-01-01T00:00:00Z",
                    target_member_ids=[owner],
                )
            ]
            legacy.view.rounds = []
            legacy_path = tmp_path / "data" / "spaces" / f"{task_id}.chat.json"
            await app.worker.call(write_document, legacy_path, legacy)
        async with app_at(tmp_path / "data", model) as app:
            record = await app.worker.call(app.team.store.chat, task_id)
            assert len(record.view.messages) == 102
            assert record.view.messages[0].content == "Legacy snapshot retained"
            graph = await app.dispatch("spaces.work_graph", {"task_id": task_id})
            assert graph.items[0].position.y == 180
            assert graph.items[0].owner_member_id == owner

    asyncio.run(scenario())
