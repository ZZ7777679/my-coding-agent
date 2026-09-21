"""M2 任务保存、旧会话兼容与上下文的最小检查。

Focused M2 persistence and context checks.
"""

import asyncio
import json
from uuid import uuid4

import pytest

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError
from my_agent.models.types import ModelTurn, TokenUsage, ToolCall
from my_agent.rpc.application import RpcApplication
from my_agent.rpc.dto import CredentialInfo


class ContextModel:
    """只观察上下文并返回固定完整回合，不联网。

    Inspect context and return offline complete turns.
    """

    def __init__(self, update=None):
        """可在首请求内模拟另一个用户修改共同信息。

        Optionally update shared facts during a request.
        """
        self.inputs = []
        self.update = update

    def check_available(self):
        """不使用凭据。

        No credentials are used.
        """
        return None

    async def complete(self, **kwargs):
        """保存输入副本，工具回合后观察新版本。

        Capture inputs and observe the next task revision.
        """
        self.inputs.append(json.loads(json.dumps(kwargs["messages"])))
        if self.update and len(self.inputs) == 1:
            await self.update()
            call = ToolCall(tool_call_id="list", name="list_files", arguments={})
            return ModelTurn(
                text="",
                tool_calls=[call],
                native={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "list",
                            "type": "function",
                            "function": {"name": "list_files", "arguments": "{}"},
                        }
                    ],
                },
                usage=TokenUsage(input_tokens=1, output_tokens=1),
            )
        return ModelTurn(
            text="known",
            tool_calls=[],
            native={"role": "assistant", "content": "known"},
            usage=TokenUsage(input_tokens=1, output_tokens=1),
        )


def application(tmp_path):
    """每个场景独立数据根与无凭据装配。

    Isolate data and compose without credentials.
    """
    credential = ResolvedCredential(
        None, CredentialInfo(env_var="OPENCODE_API_KEY", source="none", present=False)
    )
    return RpcApplication(resolve_data_dir(str(tmp_path / "data")), credential, None)


async def initialize(app, project):
    """通过真实 RPC 选择空目录，不初始化 Git 或源码。

    Select an empty project through real RPC."""
    await app.dispatch(
        "initialize",
        {
            "app_version": "test",
            "protocol_version": DEFAULTS["protocol_version"],
            "data_schema_version": 1,
        },
    )
    project.mkdir(exist_ok=True)
    result = await app.dispatch("projects.open", {"path": str(project)})
    return result.active_project.project_id


def create_params(project_id, goal="阶段目标"):
    """生成用户创建请求，不隐含执行目标。

    Build a task creation request without executing it."""
    return {
        "operation_id": str(uuid4()),
        "project_id": project_id,
        "model_id": "glm-5.3-flash",
        "fields": {"title": "Task", "goal": goal},
    }


def test_task_updates_refresh_next_request_without_per_tool_revision_gate(tmp_path):
    """共同信息更新在下一请求可见，不把元数据变化当工具审批。

    Refresh shared information on the next request without a per-tool metadata gate."""

    async def scenario():
        """通过实际装配验证逐请求范围与失败终态。

        Verify scope and failures through real composition."""
        app = application(tmp_path)
        project = tmp_path / "empty"
        try:
            project_id = await initialize(app, project)
            task = await app.dispatch("tasks.create", create_params(project_id))
            session = task.session.session_id

            class ChangedScopeModel(ContextModel):
                """模型响应期间模拟用户改变约束。

                Simulate changed constraints during model response."""

                async def complete(self, **kwargs):
                    """当前工具正常执行，下一请求读取更新后的共同信息。

                    Execute current tools and observe updated shared context in the next request."""
                    if self.inputs:
                        assert "Updated project note" in kwargs["messages"][0]["content"]
                        return await super().complete(**kwargs)
                    self.inputs.append(kwargs["messages"])
                    await app.dispatch(
                        "tasks.update",
                        {
                            "task_id": task.task.task_id,
                            "operation_id": str(uuid4()),
                            "expected_revision": task.task.revision,
                            "fields": {
                                **task.task.fields.model_dump(),
                                "constraints": "Updated project note",
                            },
                        },
                    )
                    calls = [
                        ToolCall(
                            tool_call_id=f"write-{i}",
                            name="create_file",
                            arguments={"path": f"file{i}.txt", "content": "x"},
                        )
                        for i in range(2)
                    ]
                    return ModelTurn(
                        text="",
                        tool_calls=calls,
                        native={
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": c.tool_call_id,
                                    "type": "function",
                                    "function": {
                                        "name": c.name,
                                        "arguments": json.dumps(c.arguments),
                                    },
                                }
                                for c in calls
                            ],
                        },
                        usage=TokenUsage(input_tokens=1, output_tokens=1),
                    )

            app.sessions.model_factory = ChangedScopeModel
            await app.dispatch(
                "runs.start",
                {
                    "session_id": session,
                    "operation_id": str(uuid4()),
                    "prompt": "Create files",
                    "mode": "normal",
                    "limits": None,
                },
            )
            await app.sessions.active_for(session).task
            view = await app.sessions.view(session)
            assert view.summary.run.status == "completed" and view.summary.can_continue
            results = [e.result for e in view.entries if e.result]
            assert len(results) == 2 and all(not result.is_error for result in results)
            assert {path.name for path in project.iterdir()} == {"file0.txt", "file1.txt"}
        finally:
            await app.close()

    asyncio.run(scenario())


def test_task_restart_old_history_and_context_revisions(tmp_path):
    """旧日志原字节保留，新会话接续任务并在下次请求取新版本。

    Preserve old bytes and refresh task context at the next request boundary.
    """

    async def scenario():
        """共用真实存储和 RPC，仅模型使用替身。

        Use real persistence/RPC with a fake model only."""
        app = application(tmp_path)
        try:
            project = tmp_path / "project"
            project_id = await initialize(app, project)
            params = create_params(project_id)
            created = await app.dispatch("tasks.create", params)
            again = await app.dispatch("tasks.create", params)
            assert created == again
            assert list(project.iterdir()) == []
            old = await app.sessions.create(project_id, "deepseek-v4.1-flash")
            old_path = app.sessions.store.path(old.session_id)
            header = json.loads(old_path.read_text(encoding="utf-8"))
            for key in ("task_id", "creation_operation_id", "role", "scope"):
                header["data"].pop(key)
            old_bytes = (json.dumps(header) + "\n").encode("utf-8")
            old_path.write_bytes(old_bytes)
            assert (await app.sessions.view(old.session_id)).summary.task_id is None
            assignment = {
                "session_id": old.session_id,
                "task_id": created.task.task_id,
                "operation_id": str(uuid4()),
                "role": "接手",
                "scope": "界面",
            }
            await app.dispatch("sessions.assign", assignment)
            await app.dispatch("sessions.assign", assignment)
            assert old_path.read_bytes().startswith(old_bytes)
            assert len(old_path.read_bytes().splitlines()) == 2

            async def update():
                """在第一个请求期间更新任务，不能修改已经发出的快照。

                Update during a request without changing its already-sent snapshot.
                """
                await app.dispatch(
                    "tasks.update",
                    {
                        "task_id": created.task.task_id,
                        "operation_id": str(uuid4()),
                        "expected_revision": 1,
                        "fields": {
                            "title": "Task",
                            "goal": "阶段目标",
                            "decisions": "用户确认 SQLite",
                        },
                    },
                )

            model = ContextModel(update)
            app.sessions.model_factory = lambda: model
            await app.sessions.start(old.session_id, str(uuid4()), "只读取空目录", None)
            await app.sessions.active_for(old.session_id).task
            result = await app.sessions.view(old.session_id)
            assert result.summary.run.status == "completed"
            assert result.summary.model_id == "deepseek-v4.1-flash"
            assert len(model.inputs) == 2
            assert "阶段目标" in model.inputs[0][0]["content"]
            assert "用户确认 SQLite" not in model.inputs[0][0]["content"]
            assert "用户确认 SQLite" in model.inputs[1][0]["content"]
            log = app.sessions.store.load(old.session_id)
            assert [
                f.data.task_revision for f in log.facts if f.data.kind == "request.started"
            ] == [1, 2]
            next_session = await app.dispatch(
                "sessions.create",
                {
                    "project_id": project_id,
                    "task_id": created.task.task_id,
                    "operation_id": str(uuid4()),
                    "model_id": "glm-5.3-flash",
                },
            )
            next_model = ContextModel()
            app.sessions.model_factory = lambda: next_model
            await app.sessions.start(next_session.session_id, str(uuid4()), "接续工作", None)
            await app.sessions.active_for(next_session.session_id).task
            assert "用户确认 SQLite" in next_model.inputs[0][0]["content"]
            assert "只读取空目录" not in json.dumps(next_model.inputs[0], ensure_ascii=False)
            saved = old_path.read_bytes()
        finally:
            await app.close()
        reloaded = application(tmp_path)
        try:
            await initialize(reloaded, project)
            assert (
                await reloaded.dispatch("tasks.get", {"task_id": created.task.task_id})
            ).revision == 4
            restored = await reloaded.sessions.view(old.session_id)
            assert restored.summary.task_id == created.task.task_id
            assert restored.summary.role == "接手"
            assert old_path.read_bytes() == saved
            assert not reloaded.sessions.active_runs
        finally:
            await reloaded.close()

    asyncio.run(scenario())


def test_partial_creation_conflict_failed_save_and_damage(tmp_path, monkeypatch):
    """跨文件部分失败能显式接续；冲突和损坏不覆盖原数据。

    Recover partial creation explicitly and preserve data on conflicts and damage.
    """

    async def scenario():
        """复用一个隔离场景直接覆盖存储失败边界。

        Exercise storage failure boundaries in one isolated scenario.
        """
        app = application(tmp_path)
        try:
            project_id = await initialize(app, tmp_path / "project")
            original = app.sessions.create

            async def fail(*args, **kwargs):
                """模拟首会话写入失败。

                Simulate first-session failure.
                """
                raise AgentError("SESSION_SAVE_FAILED", "模拟失败")

            monkeypatch.setattr(app.sessions, "create", fail)
            params = create_params(project_id)
            partial = await app.dispatch("tasks.create", params)
            assert partial.session is None and partial.session_error
            assert partial.task.revision == 1
            monkeypatch.setattr(app.sessions, "create", original)
            complete = await app.dispatch("tasks.ensure_session", {"task_id": partial.task.task_id})
            assert complete.session.session_id == partial.task.initial_session_id
            assert (
                await app.dispatch("tasks.create", params)
            ).session.session_id == complete.session.session_id
            with pytest.raises(AgentError) as conflict:
                await app.dispatch(
                    "tasks.create", {**params, "fields": {"title": "different", "goal": "other"}}
                )
            assert conflict.value.code == "OPERATION_CONFLICT"
            path = app.tasks.store.path(partial.task.task_id)
            baseline = path.read_bytes()
            update = {
                "task_id": partial.task.task_id,
                "operation_id": str(uuid4()),
                "expected_revision": 1,
                "fields": {"title": "Task", "goal": "corrected"},
            }

            def fail_save(*args):
                """模拟原子替换失败，不写文件。

                Simulate replacement failure without writing."""
                raise AgentError("DATA_DIR_NOT_WRITABLE", "模拟保存失败")

            with monkeypatch.context() as patch:
                patch.setattr("my_agent.tasks.store.atomic_write", fail_save)
                with pytest.raises(AgentError):
                    await app.dispatch("tasks.update", update)
            assert path.read_bytes() == baseline
            saved = await app.dispatch("tasks.update", update)
            assert saved.revision == 2
            assert await app.dispatch("tasks.update", update) == saved
            with pytest.raises(AgentError) as stale:
                await app.dispatch("tasks.update", {**update, "operation_id": str(uuid4())})
            assert stale.value.code == "TASK_VERSION_CONFLICT"
            other_project = await initialize(app, tmp_path / "other")
            other = await app.sessions.create(other_project, "glm-5.3-flash")
            with pytest.raises(AgentError) as cross:
                await app.dispatch(
                    "sessions.assign",
                    {
                        "session_id": other.session_id,
                        "task_id": saved.task_id,
                        "operation_id": str(uuid4()),
                    },
                )
            assert cross.value.code == "TASK_PROJECT_MISMATCH"
            damaged = path.read_bytes() + b"broken\n"
            path.write_bytes(damaged)
            with pytest.raises(AgentError) as damage:
                await app.dispatch("tasks.get", {"task_id": saved.task_id})
            assert damage.value.code == "TASK_DAMAGED"
            page = await app.dispatch(
                "tasks.list", {"project_id": project_id, "cursor": None, "limit": 20}
            )
            assert page.unavailable_count == 1 and page.tasks == []
            assert path.read_bytes() == damaged
        finally:
            await app.close()

    asyncio.run(scenario())
