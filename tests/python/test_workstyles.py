"""组合工作方式及材料范围的定向检查。 Focused composite-workstyle and material-scope checks."""

import asyncio
from uuid import uuid4

from my_agent.spaces.context import member_context
from my_agent.spaces.types import SpaceBinding, SpaceConfig, SpaceView
from my_agent.workflow.types import WorkItem
from tests.python.test_context_memory import KnowledgeModel, run
from tests.python.test_goal_controller import app_at, call, create_session, turn
from tests.python.test_spaces import save_team, team
from tests.python.test_work_graph import WorkModel


def test_workstyle_snapshot_default_reuse_and_explicit_apply(tmp_path):
    """真实 RPC 保存与复用，保留任务快照、历史和一份首会话。

    Reuse through real RPC while retaining independent snapshots, history and one first session.
    """

    async def scenario():
        """全程离线；模板不启动模型或复制项目文件。

        Offline templates neither run models nor copy projects.
        """
        model = KnowledgeModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            task, sid = created.task, created.session.session_id
            config = team()
            config["members"][0]["scope"] = str(tmp_path / "project") + "/src"
            config["members"][0]["skill_ids"] = ["missing-but-optional"]
            config["initial_work_items"] = [
                {
                    "work_id": "implement",
                    "title": "Build",
                    "scope": "src",
                    "owner_member_id": config["members"][0]["member_id"],
                    "status": "completed",
                    "result": "OLD_RESULT",
                    "run_id": str(uuid4()),
                }
            ]
            await save_team(app, task.task_id, config)
            style = await app.dispatch(
                "workstyles.capture",
                {
                    "task_id": task.task_id,
                    "style_id": str(uuid4()),
                    "name": "Reusable",
                    "skill_ids": ["not-installed"],
                },
            )
            assert style.workflow and style.team.initial_work_items
            assert style.team.members[0].scope == "./src"
            assert style.team.initial_work_items[0].run_id is None
            assert style.team.initial_work_items[0].result is None
            assert style.team.initial_work_items[0].status == "planned"
            style = await app.dispatch("workstyles.save", {"style": style.model_dump()})
            await app.dispatch(
                "workstyles.default", {"project_id": task.project_id, "style_id": style.style_id}
            )
            args = {
                "project_id": task.project_id,
                "operation_id": str(uuid4()),
                "model_id": "glm-5.3-flash",
                "fields": {"title": "Second", "goal": "Keep this goal"},
            }
            second = await app.dispatch("tasks.create", args)
            assert second.task.workstyle.style_id == style.style_id
            assert (
                second.task.workstyle.team.members[0].member_id != style.team.members[0].member_id
            )
            assert (
                second.task.workstyle.team.initial_work_items[0].owner_member_id
                == second.task.workstyle.team.members[0].member_id
            )
            assert (await app.dispatch("tasks.create", args)).task == second.task
            second_space = (
                await app.dispatch("spaces.get", {"task_id": second.task.task_id})
            ).space
            assert second_space and not second_space.bindings
            before = set((tmp_path / "data/sessions").iterdir())
            style.name = "New library version"
            await app.dispatch("workstyles.save", {"style": style.model_dump()})
            assert (
                await app.worker.call(app.tasks.store.get, second.task.task_id)
            ).workstyle.name == "Reusable"
            standalone = await app.dispatch(
                "tasks.create",
                {**args, "operation_id": str(uuid4()), "use_project_workstyle": False},
            )
            assert standalone.task.workstyle is None
            current = await app.worker.call(app.tasks.store.get, task.task_id)
            original_space = (await app.dispatch("spaces.get", {"task_id": task.task_id})).space
            apply_args = {
                "task_id": task.task_id,
                "style_id": style.style_id,
                "operation_id": str(uuid4()),
                "expected_revision": current.revision,
                "expected_space_revision": original_space.revision,
            }
            adopted = await app.dispatch("workstyles.apply", apply_args)
            assert adopted.fields == current.fields
            assert len(app.tasks.store.history(task.task_id)) == 2
            assert (await app.dispatch("workstyles.apply", apply_args)) == adopted
            assert len(set((tmp_path / "data/sessions").iterdir()) - before) == 1
            # 缺少可选 Skill 只给资源提示，不阻断普通请求组装。
            # Missing optional Skills produce resource notices, not assembly failures.
            log = await app.worker.call(app.sessions.store.load, sid)
            material, _ = await app.worker.call(app.sessions.skills.materials, log)
            assert "not-installed" in material
            assert model.requests == []
            assert list((tmp_path / "project").iterdir()) == []
        async with app_at(tmp_path / "data", model) as restarted:
            catalog = await restarted.dispatch("workstyles.list", {"project_id": task.project_id})
            assert catalog.default_style_id == style.style_id
            assert (
                await restarted.worker.call(restarted.tasks.store.get, second.task.task_id)
            ).workstyle.name == "Reusable"

    asyncio.run(scenario())


def test_space_material_keeps_direct_neighbors_independent_of_order():
    """保留当前职责与直接依赖，远端工作只提供索引，顺序不扩大范围。

    Keep current duties and direct dependencies; remote work remains an order-independent index.
    """
    config = SpaceConfig.model_validate(team())
    owner = config.members[0].member_id
    sid = str(uuid4())
    config.initial_work_items = [
        WorkItem(
            work_id="own",
            title="Own",
            scope="src",
            status="planned",
            owner_member_id=owner,
            depends_on=["direct"],
        ),
        WorkItem(
            work_id="direct",
            title="Direct",
            scope="src",
            status="completed",
            depends_on=["remote"],
            result="DIRECT_RESULT",
        ),
        WorkItem(
            work_id="remote",
            title="Remote",
            scope="src",
            status="completed",
            result="REMOTE_LONG_RESULT" * 1000,
        ),
    ]
    space = SpaceView(
        task_id=str(uuid4()),
        project_id=str(uuid4()),
        revision=1,
        config=config,
        bindings=[SpaceBinding(member_id=owner, session_id=sid)],
        created_at="2026-10-19T00:00:00Z",
        updated_at="2026-10-19T00:00:00Z",
    )
    text, _ = member_context(space, sid)
    assert "DIRECT_RESULT" in text and "REMOTE_LONG_RESULT" not in text
    space.config.initial_work_items.reverse()
    again, _ = member_context(space, sid)
    assert "DIRECT_RESULT" in again and "REMOTE_LONG_RESULT" not in again


def test_apply_workstyle_replaces_stale_graph_state_without_erasing_history(tmp_path):
    """采用模板复位同名节点，保留其它工作、共同信息和历史。

    Reapply template nodes while retaining unrelated work, shared facts and history.
    """

    async def scenario():
        """真实 RPC 覆盖负责人、旧报告、删除标记、幂等与重启。

        Exercise ownership, old reports, tombstones, idempotency and restart through real RPC.
        """
        model = WorkModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            task_id, sid = created.task.task_id, created.session.session_id
            config = team()
            owner = config["members"][0]["member_id"]
            config["initial_work_items"] = [
                {"work_id": name, "title": name, "scope": "src", "status": "planned"}
                for name in ("build", "keep", "retired")
            ]
            space = await save_team(app, task_id, config)
            graph = await app.dispatch("spaces.work_graph", {"task_id": task_id})
            graph = await app.dispatch(
                "spaces.work_graph_save",
                {
                    "task_id": task_id,
                    "operation_id": str(uuid4()),
                    "expected_revision": graph.task.revision,
                    "items": [item.model_dump() for item in graph.items],
                    "owner_changes": {"build": owner},
                },
            )
            model.steps = [
                turn(
                    call(
                        "report_work",
                        summary="old results",
                        outcome="return",
                        work_items=[
                            {
                                "work_id": name,
                                "title": name,
                                "scope": "src",
                                "status": "completed",
                                "result": "old " + name,
                            }
                            for name in ("build", "keep")
                        ],
                    )
                ),
                turn(text="reported"),
            ]
            await run(app, sid, "report current work")
            style = await app.dispatch(
                "workstyles.capture",
                {"task_id": task_id, "style_id": str(uuid4()), "name": "Build again"},
            )
            style.team.initial_work_items = [
                item for item in style.team.initial_work_items if item.work_id == "build"
            ]
            await app.dispatch("workstyles.save", {"style": style.model_dump()})
            graph = await app.dispatch("spaces.work_graph", {"task_id": task_id})
            graph = await app.dispatch(
                "spaces.work_graph_save",
                {
                    "task_id": task_id,
                    "operation_id": str(uuid4()),
                    "expected_revision": graph.task.revision,
                    "items": [item.model_dump() for item in graph.items if item.work_id == "keep"],
                },
            )
            before = graph.task
            old_source = before.work.items[0].source
            params = {
                "task_id": task_id,
                "style_id": style.style_id,
                "operation_id": str(uuid4()),
                "expected_revision": before.revision,
                "expected_space_revision": space.revision,
            }
            adopted = await app.dispatch("workstyles.apply", params)
            graph = await app.dispatch("spaces.work_graph", {"task_id": task_id})
            items = {item.work_id: item for item in graph.items}
            assert set(items) == {"build", "keep"}
            new_owner = adopted.workstyle.team.initial_work_items[0].owner_member_id
            assert new_owner and new_owner != owner
            assert items["build"].owner_member_id == new_owner
            assert items["build"].status == "planned"
            assert items["build"].run_id is None and items["build"].result is None
            assert items["keep"].status == "completed" and items["keep"].result == "old keep"
            assert adopted.work.removed_work_ids == ["retired"]
            assert adopted.fields == before.fields
            assert adopted.work.last_report == before.work.last_report
            assignment = next(a for a in adopted.work.assignments if a.work_id == "build")
            assert assignment.owner_member_id == new_owner
            assert assignment.status == "planned" and assignment.run_id is None
            history = await app.worker.call(app.tasks.store.history, task_id)
            assert any(f.view == before for f in history)
            assert (await app.dispatch("workstyles.apply", params)) == adopted
            # 重复同步旧报告不能把旧完成状态重新灌入当前图。
            # Replaying an already recorded report must not repopulate the reset graph.
            again = await app.worker.call(app.tasks.store.record_report, sid, old_source.seq)
            assert again == adopted
        async with app_at(tmp_path / "data", model) as app:
            restored = await app.dispatch("spaces.work_graph", {"task_id": task_id})
            assert restored.items == graph.items

    asyncio.run(scenario())
