"""导航名称只改变元数据，跨重启与回退持久化。

Navigation labels persist without changing project content.
"""

import asyncio
from uuid import uuid4

from my_agent.checkpoints.types import ConversationRestored
from my_agent.sessions.types import SessionRenamed
from tests.python.test_context_memory import KnowledgeModel
from tests.python.test_goal_controller import app_at, create_session


def test_navigation_names_persist_without_changing_task_or_context(tmp_path):
    """真实 RPC 名称更新不移动文件、不覆盖目标、不进入模型上下文。

    Real RPC renames preserve files, goals and model context.
    """

    async def scenario():
        """重启读取与有效分支同时验证，使用隔离数据根。

        Check restart and effective history in isolated storage.
        """
        model = KnowledgeModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            task, sid = created.task, created.session.session_id
            pid = task.project_id
            names = {"project": "项目别名", "task": "任务别名", "session": "会话别名"}
            ids = {"project": pid, "task": task.task_id, "session": sid}
            for kind, entity_id in ids.items():
                params = {
                    "kind": kind,
                    "id": entity_id,
                    "name": names[kind],
                    "operation_id": str(uuid4()),
                }
                first = await app.dispatch("navigation.rename", params)
                assert first.name == names[kind]
                assert await app.dispatch("navigation.rename", params) == first
            saved_task = await app.worker.call(app.tasks.store.get, task.task_id)
            assert saved_task.fields.model_copy(update={"title": task.fields.title}) == task.fields
            assert saved_task.revision == task.revision + 1
            assert saved_task.work == task.work
            opened = await app.dispatch("projects.open", {"path": str(tmp_path / "project")})
            assert opened.active_project.project_id == pid
            assert opened.active_project.name == names["project"]
            assert not list((tmp_path / "project").iterdir())
            log = await app.worker.call(app.sessions.store.load, sid)
            assert len([f for f in log.facts if isinstance(f.data, SessionRenamed)]) == 1
            assert log.context()[0] == []
            await app.worker.call(
                app.sessions.store.append,
                log,
                ConversationRestored(
                    operation_id=str(uuid4()),
                    checkpoint_id=str(uuid4()),
                    before_seq=2,
                    message="test rewind",
                ),
                None,
            )
            assert any(isinstance(f.data, SessionRenamed) for f in log.effective_facts())
        async with app_at(tmp_path / "data", model) as restarted:
            view = await restarted.sessions.view(sid)
            assert view.summary.title == names["session"]
            assert view.summary.task_id == task.task_id
            assert (
                await restarted.worker.call(restarted.tasks.store.get, task.task_id)
            ).fields.title == names["task"]
            projects = await restarted.dispatch("projects.open", {"project_id": pid})
            assert projects.active_project.name == names["project"]

    asyncio.run(scenario())
