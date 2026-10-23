"""专用设计、接续和一键组建使用真实业务服务。

Exercise dedicated design and launch through real services.
"""

import asyncio
import json
from uuid import uuid4

import pytest

from my_agent.errors import AgentError
from my_agent.spaces.design_types import (
    OpenTeamDesignParams,
    SaveTeamDesignParams,
    SendTeamDesignParams,
    StartTeamDesignParams,
)
from my_agent.spaces.types import SpaceConfig, SpaceParams
from tests.python.test_collaboration import finish
from tests.python.test_goal_controller import app_at, call, create_session, turn
from tests.python.test_space_team import service_at
from tests.python.test_spaces import team


class DesignModel:
    """只替换模型响应，实际图、会话和 Goal 均使用产品实现。

    Replace model output only; use production graphs, sessions and goals.
    """

    def __init__(self):
        """保留稳定成员和实际请求。

        Retain stable members and actual requests.
        """
        self.config = team()
        self.calls = []

    def check_available(self):
        """离线响应无需凭据。 Offline responses require no credentials."""

    async def complete(self, **kwargs):
        """读取当前图后修改，普通讨论无需保存。

        Read before editing; discussion needs no save.
        """
        self.calls.append(kwargs)
        messages = kwargs["messages"]
        names = [item["function"]["name"] for item in kwargs["tools"]]
        if "save_team_draft" not in names:
            return turn(call("report_work", summary="Done", outcome="complete"), text="Done")
        prompt = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        if "discuss only" in prompt:
            return turn(text="We can discuss without changing the graph.")
        if messages[-1]["role"] != "tool":
            return turn(call("read_team_design"))
        result = json.loads(messages[-1]["content"])
        if "config" in result:
            config = result["config"] or self.config
            if "rename" in prompt:
                config["members"][0]["name"] = "Coordinator updated"
            return turn(call("save_team_draft", config=config))
        return turn(text="The graph has been saved.")


def test_design_reopen_modify_and_launch(tmp_path):
    """讨论独立、原图修改、重启接续和重复启动不复制成员。

    Verify isolation, graph updates, restart recovery and idempotent launch.
    """

    async def scenario():
        """沿真实存储执行，不联网。

        Exercise real persistence without networking.
        """
        model = DesignModel()
        root = tmp_path / "data"
        async with app_at(root, model) as app:
            created = await create_session(app, tmp_path / "project")
            service = service_at(app)
            task_id = created.task.task_id
            params = OpenTeamDesignParams(task_id=task_id, model_id="glm-5.3-flash")
            view = await service.design.open(params)
            design_id = view.session_id
            assert design_id != created.session.session_id
            assert (await app.sessions.view(design_id)).summary.purpose == "team_design"
            assert (await service.design.open(params)).session_id == design_id
            before = await app.sessions.view(created.session.session_id)
            await service.design.send(
                SendTeamDesignParams(
                    task_id=task_id, operation_id=str(uuid4()), content="create team"
                )
            )
            await finish(app, design_id)
            view = await service.design.get(SpaceParams(task_id=task_id))
            assert view.config and len(view.config.members) == 2
            member_id = view.config.members[0].member_id
            await service.design.send(
                SendTeamDesignParams(
                    task_id=task_id, operation_id=str(uuid4()), content="rename coordinator"
                )
            )
            await finish(app, design_id)
            view = await service.design.get(SpaceParams(task_id=task_id))
            assert view.config.members[0].member_id == member_id
            assert view.config.members[0].name == "Coordinator updated"
            assert (
                await app.sessions.view(created.session.session_id)
            ).watermark == before.watermark
            await service.design.send(
                SendTeamDesignParams(
                    task_id=task_id, operation_id=str(uuid4()), content="discuss only"
                )
            )
            await finish(app, design_id)
            assert (await service.chat_view(SpaceParams(task_id=task_id))).generations[
                -1
            ].error is None
            await service.design.save(
                SaveTeamDesignParams(task_id=task_id, input_text="unfinished idea")
            )
            assert (await app.spaces.get(SpaceParams(task_id=task_id))).space is None
        async with app_at(root, model) as app:
            service = service_at(app)
            restored = await service.design.open(params)
            assert restored.session_id == design_id and restored.input_text == "unfinished idea"
            assert restored.config.members[0].member_id == member_id
            start = StartTeamDesignParams(
                task_id=task_id, operation_id=str(uuid4()), config=restored.config
            )
            launched = await service.design.start(start)
            assert launched.launches[-1].error is None
            assert launched.launches[-1].stage == "started"
            space = (await app.spaces.get(SpaceParams(task_id=task_id))).space
            ids = [b.session_id for b in space.bindings]
            assert len(ids) == 2 and design_id not in ids
            for session in ids:
                await finish(app, session)
            calls_before = len(model.calls)
            await service.design.start(start)
            assert len(model.calls) == calls_before
            assert [
                b.session_id
                for b in (await app.spaces.get(SpaceParams(task_id=task_id))).space.bindings
            ] == ids
            assert len((await service.chat_view(SpaceParams(task_id=task_id))).rounds) == 1

    asyncio.run(scenario())


def test_design_keeps_manual_edits_and_partial_assembly(tmp_path, monkeypatch):
    """并发人工编辑不被模型覆盖；局部组建失败可接续。

    Preserve manual edits and resume partial assembly without duplicates.
    """

    async def scenario():
        """注入一次真实边界失败，再复用已创建会话。

        Inject one boundary failure and reuse created sessions.
        """
        async with app_at(tmp_path / "data", DesignModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service = service_at(app)
            task_id = created.task.task_id
            view = await service.design.open(
                OpenTeamDesignParams(task_id=task_id, model_id="glm-5.3-flash")
            )
            config = SpaceConfig.model_validate(team())
            await service.design.save(SaveTeamDesignParams(task_id=task_id, config=config))
            await service.worker.call(
                service.design.read_for_model, task_id, view.session_id, "run"
            )
            changed = config.model_copy(deep=True)
            changed.members[0].name = "Manual edit"
            await service.design.save(SaveTeamDesignParams(task_id=task_id, config=changed))
            with pytest.raises(AgentError, match="read_team_design"):
                await service.worker.call(
                    service.design.save_generated, task_id, view.session_id, "run", config
                )
            assert (await service.design.get(SpaceParams(task_id=task_id))).config.members[
                0
            ].name == "Manual edit"
            original = app.sessions.create
            attempts = 0

            async def fail_second(*args, **kwargs):
                """只让第二个成员首次创建失败。

                Fail only the second member's first creation.
                """
                nonlocal attempts
                attempts += 1
                if attempts == 2:
                    raise AgentError("TEST_STORAGE_FAILURE", "isolated failure")
                return await original(*args, **kwargs)

            monkeypatch.setattr(app.sessions, "create", fail_second)
            start = StartTeamDesignParams(
                task_id=task_id, operation_id=str(uuid4()), config=changed
            )
            failed = await service.design.start(start)
            assert failed.launches[-1].error
            partial = (await app.spaces.get(SpaceParams(task_id=task_id))).space
            existing = [b.session_id for b in partial.bindings if b.session_id]
            assert len(existing) == 1
            monkeypatch.setattr(app.sessions, "create", original)
            recovered = await service.design.start(start)
            assert recovered.launches[-1].error is None
            space = (await app.spaces.get(SpaceParams(task_id=task_id))).space
            assert existing[0] in [b.session_id for b in space.bindings]
            for binding in space.bindings:
                await finish(app, binding.session_id)

    asyncio.run(scenario())
