"""任务快照与运行控制分离。 Workflow snapshots remain separate from execution control."""

import asyncio
from uuid import uuid4

from tests.python.test_goal_controller import app_at, create_session


def test_templates_snapshot_and_task_edits_preserve_reports(tmp_path):
    """实际 RPC 保存、重载、切换和删除不重写旧任务。

    Real RPC saving, reloading, switching and deletion preserve existing task data.
    """

    async def scenario():
        """无模型请求的持久化检查。 Persistence check without model calls."""
        async with app_at(tmp_path / "data", None) as app:
            initial = await create_session(app, tmp_path / "project")
            templates = await app.dispatch("workflows.list", {})
            template = templates.templates[0].model_copy(deep=True)
            template.template_id = "personal-copy"
            template.name = "Copy"
            await app.dispatch("workflows.save", {"template": template.model_dump()})
            created = await app.dispatch(
                "tasks.create",
                {
                    "operation_id": str(uuid4()),
                    "project_id": initial.task.project_id,
                    "model_id": "glm-5.3-flash",
                    "fields": {"title": "Counter", "goal": "Implement"},
                    "workflow_template_id": template.template_id,
                },
            )
            task = created.task
            assert task.workflow.template.name == "Copy"
            template.name = "Changed"
            await app.dispatch("workflows.save", {"template": template.model_dump()})
            saved = await app.dispatch("tasks.get", {"task_id": task.task_id})
            assert saved.workflow.template.name == "Copy"
            flow = saved.workflow.model_copy(deep=True)
            flow.current_stage_id = "implement"
            flow.session_stages[created.session.session_id] = "review"
            result = await app.dispatch(
                "tasks.workflow",
                {
                    "task_id": task.task_id,
                    "operation_id": str(uuid4()),
                    "expected_revision": task.revision,
                    "workflow": flow.model_dump(),
                },
            )
            assert result.fields == task.fields and result.work == task.work
            assert not app.sessions.active_runs
            log = await app.sessions._load(created.session.session_id)
            text, materials = await app.worker.call(app.sessions.skills.materials, log)
            assert "This session's stage: review" in text
            assert any(m.kind == "workflow" for m in materials)
            await app.dispatch("workflows.remove", {"template_id": "personal-copy"})
            assert app.tasks.store.get(task.task_id).workflow == flow
            # 老任务没有新增字段仍可读取；用户可显式关闭流程。
            # Old task records remain readable and users can explicitly remove a workflow.
            legacy = task.model_dump()
            legacy.pop("workflow")
            assert type(task).model_validate(legacy).workflow is None

    asyncio.run(scenario())
