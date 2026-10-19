"""M5 B 使用离线模型验证真实团队生成与协作执行。

Verify real M5 B team generation and collaboration using offline models.
"""

import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import pytest

from my_agent.errors import AgentError
from my_agent.runtime.loop import recoverable_tool_error
from my_agent.spaces.team_service import SpaceTeamService
from my_agent.spaces.team_tools import SpaceTeamTools
from my_agent.spaces.team_types import (
    CopyTeamTemplateParams,
    GenerateTeamParams,
    ImportTeamTemplateParams,
    SaveTeamTemplateParams,
    SpaceChatParams,
    StartSpaceRoundParams,
    StopSpaceRoundParams,
    TeamTemplateParams,
    UpdateSpaceWorkParams,
)
from my_agent.spaces.types import SaveSpaceParams, SpaceConfig, SpaceParams, SpaceStartParams
from tests.python.test_collaboration import finish
from tests.python.test_goal_controller import app_at, call, create_session, turn
from tests.python.test_spaces import team


class TeamModel:
    """只替换模型响应，保存和执行使用正式工具。

    Replace only model responses while production tools own saving and execution.
    """

    def __init__(self, config):
        """记录请求对象及用于停止的可控等待。

        Record request recipients and controllable stop gates.
        """
        self.config = config
        self.calls = []
        self.saved = False
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()
        self.hold = False
        self.work_actions = {}

    def check_available(self):
        """不调用外网或凭据。 Avoid networking and credentials."""

    async def complete(self, **kwargs):
        """生成使用真实草稿工具；Goal 用现有工作报告收尾。

        Generate through the real draft tool and finish goals through existing work reports.
        """
        self.calls.append(kwargs["session_id"])
        if self.hold:
            self.entered.set()
            await self.gate.wait()
        names = [item["function"]["name"] for item in kwargs["tools"]]
        actions = self.work_actions.get(kwargs["session_id"], [])
        if "manage_space_work" in names and actions:
            return turn(call("manage_space_work", **actions.pop(0)))
        if "save_team_draft" in names and not self.saved:
            self.saved = True
            return turn(
                call(
                    "save_team_draft",
                    config=self.config,
                    initial_work_items=[
                        {
                            "work_id": "build",
                            "title": "Build page",
                            "scope": "Build the requested page",
                            "status": "planned",
                        }
                    ],
                )
            )
        if "Goal objective" in kwargs["messages"][0]["content"]:
            return turn(
                call(
                    "report_work", summary="The assigned objective is complete", outcome="complete"
                ),
                text="Public goal result",
            )
        await kwargs["on_text"]("Public team answer")
        return turn(text="Public team answer")


def service_at(app):
    """独立服务实例复用正式装配并接入真实工具。

    Reuse production composition and install the real draft tool for this service instance.
    """
    service = SpaceTeamService(app.spaces)
    previous = app.sessions.tool_factory
    app.sessions.tool_factory = lambda context: SpaceTeamTools(context, previous(context), service)
    return service


def test_generation_templates_claims_and_restart(tmp_path, monkeypatch):
    """生成不创建成员；模板快照、承接和来源重启后保留。

    Generation creates no members; template snapshots, claims and provenance survive restart.
    """

    async def scenario():
        """检查真实工具、单写者保存和恢复，不联网。

        Check actual tools, writer persistence and recovery offline.
        """
        config = team()
        model = TeamModel(config)
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            service = service_at(app)
            before = set((tmp_path / "data" / "sessions").iterdir())
            params = GenerateTeamParams(
                task_id=created.task.task_id,
                session_id=created.session.session_id,
                operation_id=str(uuid4()),
                objective="Build a page with review",
                organisation="peer",
            )
            generated = await service.generate(params)
            assert generated.run_id
            await finish(app, params.session_id)
            view = await service.chat_view(SpaceParams(task_id=params.task_id))
            draft = view.generations[-1].draft
            assert draft and draft.initial_work_items[0].work_id == "build"
            # 保存过的真实生成 Run 仍用于核对参数反馈，不伪造另一个授权入口。
            # Reuse the actual generation Run to check feedback without inventing a grant.
            context = replace(
                await app.document_context(params.session_id), mode="plan", run_id=generated.run_id
            )
            tools = app.sessions.tool_factory(context)
            bad_call = call("save_team_draft")
            feedback = await tools.execute(bad_call)
            assert feedback.is_error and recoverable_tool_error(bad_call, feedback)
            no_space = call("manage_space_work", work_id="build", action="claim")
            feedback = await tools.execute(no_space)
            assert feedback.is_error and recoverable_tool_error(no_space, feedback)
            assert draft.config.initial_work_items[0].work_id == "build"
            assert before == set((tmp_path / "data" / "sessions").iterdir())
            assert (await app.spaces.get(SpaceParams(task_id=params.task_id))).space is None
            await app.spaces.save(
                SaveSpaceParams(task_id=params.task_id, expected_revision=None, config=draft.config)
            )
            saved = await service.save_template(
                SaveTeamTemplateParams(template_id=str(uuid4()), name="Portable team", draft=draft)
            )
            copied = await service.copy_template(
                CopyTeamTemplateParams(
                    template_id=saved.template_id, new_template_id=str(uuid4()), name="Copy"
                )
            )
            exported = await service.export_template(
                TeamTemplateParams(template_id=copied.template_id)
            )
            imported = await service.import_template(
                ImportTeamTemplateParams(template_id=str(uuid4()), content=exported.content)
            )
            assert imported.draft == saved.draft
            assert "session_ids" not in exported.content
            first, second = [member["member_id"] for member in config["members"]]
            claimed = await service.update_work(
                UpdateSpaceWorkParams(
                    task_id=params.task_id,
                    operation_id=str(uuid4()),
                    work_id="build",
                    member_id=first,
                    action="claim",
                )
            )
            assert claimed.work.assignments[0].owner_member_id == first
            with pytest.raises(AgentError) as conflict:
                await service.update_work(
                    UpdateSpaceWorkParams(
                        task_id=params.task_id,
                        operation_id=str(uuid4()),
                        work_id="build",
                        member_id=second,
                        action="claim",
                    )
                )
                assert conflict.value.code == "SPACE_WORK_CLAIMED"

            assembled = await app.spaces.start(SpaceStartParams(task_id=params.task_id))
            member_session = next(
                item.session_id for item in assembled.space.bindings if item.member_id == first
            )
            model.work_actions[member_session] = [
                {"work_id": "build", "action": "claim"},
                {"work_id": "build", "action": "result", "result": "Reviewed plan saved"},
                {"work_id": "build", "action": "release"},
            ]
            started = await app.sessions.start(
                member_session,
                str(uuid4()),
                "Claim, report and release this plan work",
                None,
                "plan",
            )
            await finish(app, member_session)
            member_context = replace(
                await app.document_context(member_session), mode="plan", run_id=started.run.run_id
            )
            member_tools = app.sessions.tool_factory(member_context)
            definition = next(
                item["function"]
                for item in member_tools.definitions()
                if item["function"]["name"] == "manage_space_work"
            )
            assert set(definition["parameters"]["properties"]) == {
                "work_id",
                "action",
                "result",
                "status",
            }
            assert not member_tools.is_mutating("manage_space_work")
            task = await app.worker.call(app.tasks.store.get, params.task_id)
            assignment = task.work.assignments[0]
            assert assignment.owner_member_id is None and assignment.claim_status == "released"
            assert assignment.run_id == started.run.run_id
            assert assignment.result == "Reviewed plan saved"
            assert list((tmp_path / "project").iterdir()) == []
            for bad_arguments in (
                {"work_id": "unknown", "action": "claim"},
                {"work_id": "build", "action": "result"},
                {"work_id": "build", "action": "claim", "member_id": second},
            ):
                invalid_work = call("manage_space_work", **bad_arguments)
                feedback = await member_tools.execute(invalid_work)
                assert feedback.is_error and recoverable_tool_error(invalid_work, feedback)
                assert json.loads(feedback.content)["code"] == "INVALID_TOOL_ARGUMENTS"

            def fail_assignment(*args):
                """真实保存故障继续停止，不当作可修正参数反馈。

                Actual save failures still stop instead of becoming correctable feedback.
                """
                raise AgentError("DATA_WRITE_FAILED", "Isolated metadata save failure")

            with monkeypatch.context() as failure_patch:
                failure_patch.setattr(app.tasks.store, "assign_work", fail_assignment)
                with pytest.raises(AgentError) as save_failure:
                    await member_tools.execute(
                        call("manage_space_work", work_id="build", action="claim")
                    )
                assert save_failure.value.code == "DATA_WRITE_FAILED"
            example = draft.model_copy(deep=True)
            example.config.members[0].scope = "Explain how C:\\Users\\example works; edit src only."
            saved_example = await service.save_template(
                SaveTeamTemplateParams(template_id=str(uuid4()), name="Path example", draft=example)
            )
            assert saved_example.draft.config.members[0].scope == example.config.members[0].scope
            call_count = len(model.calls)
            task_id = params.task_id
        async with app_at(tmp_path / "data", model) as app:
            service = service_at(app)
            restored = await service.chat_view(SpaceParams(task_id=task_id))
            assert restored.generations[-1].draft == draft
            assert len((await service.templates()).templates) == 4
            task = await app.worker.call(app.tasks.store.get, task_id)
            assert task.work.assignments[0].owner_member_id is None
            assert task.work.assignments[0].result == "Reviewed plan saved"
            assert len(model.calls) == call_count

    asyncio.run(scenario())


def test_three_organisations_routes_busy_queue_and_goal_stop(tmp_path):
    """三种组织默认只路由接收方，多选和忙队列沿原服务执行。

    All organisations route only to the receiver by default;
    multi-target and busy work use existing services.
    """

    async def scenario():
        """检查路由、公开输出、同成员串行与停止来源。

        Check routes, public output, serial members and stop provenance.
        """
        config = team()
        model = TeamModel(config)
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            service = service_at(app)
            task_id = created.task.task_id
            await app.spaces.save(
                SaveSpaceParams(
                    task_id=task_id,
                    expected_revision=None,
                    config=SpaceConfig.model_validate(config),
                )
            )
            assembled = await app.spaces.start(SpaceStartParams(task_id=task_id))
            bindings = {item.member_id: item.session_id for item in assembled.space.bindings}
            first, second = [member["member_id"] for member in config["members"]]
            for organisation in ["central", "hierarchical", "peer"]:
                current = (await app.spaces.get(SpaceParams(task_id=task_id))).space
                await app.spaces.save(
                    SaveSpaceParams(
                        task_id=task_id,
                        expected_revision=current.revision,
                        config=current.config.model_copy(
                            update={"organisation": organisation, "receiver_member_id": second}
                        ),
                    )
                )
                before = len(model.calls)
                sent = await service.chat(
                    SpaceChatParams(
                        task_id=task_id, operation_id=str(uuid4()), content="Ordinary question"
                    )
                )
                assert sent.messages[-1].target_member_ids == [second]
                await finish(app, bindings[second])
                assert model.calls[before:] == [bindings[second]]
            multi = await service.chat(
                SpaceChatParams(
                    task_id=task_id,
                    operation_id=str(uuid4()),
                    content="@Implementation @Review Please answer",
                )
            )
            assert multi.messages[-1].target_member_ids == [first, second]
            await finish(app, bindings[first])
            await finish(app, bindings[second])
            public = await service.chat_view(SpaceParams(task_id=task_id))
            assert all("native" not in output.model_dump() for output in public.outputs)
            assert any(output.text == "Public team answer" for output in public.outputs)
            for message in public.messages:
                replies = [
                    output for output in public.outputs if output.origin_id == message.message_id
                ]
                assert {output.member_id for output in replies} == set(message.target_member_ids)
                assert all(output.waiting_for is None for output in replies)
            model.hold = True
            await service.chat(
                SpaceChatParams(
                    task_id=task_id,
                    operation_id=str(uuid4()),
                    content="hold",
                    target_member_ids=[first],
                )
            )
            await asyncio.wait_for(model.entered.wait(), 2)
            queued = await service.chat(
                SpaceChatParams(
                    task_id=task_id,
                    operation_id=str(uuid4()),
                    content="After current answer",
                    target_member_ids=[first],
                )
            )
            request_id = queued.messages[-1].executions[0].request_id
            assert request_id
            model.hold = False
            model.gate.set()
            await finish(app, bindings[first])
            for _ in range(100):
                request = await app.worker.call(
                    app.sessions.collaboration.store.request, request_id
                )
                if request.status == "completed":
                    break
                await asyncio.sleep(0.02)
            assert request.status == "completed"
            model.hold = True
            model.gate.clear()
            model.entered.clear()
            round_id = str(uuid4())
            active = await service.start_round(
                StartSpaceRoundParams(
                    task_id=task_id,
                    operation_id=round_id,
                    objective="Build and review the page",
                    target_member_ids=[second],
                )
            )
            assert active.rounds[-1].executions[0].goal_id
            await asyncio.wait_for(model.entered.wait(), 2)
            await service.stop(StopSpaceRoundParams(task_id=task_id, round_id=round_id))
            model.gate.set()
            await finish(app, bindings[second])
            restored = await service.chat_view(SpaceParams(task_id=task_id))
            assert restored.rounds[-1].stopped
            assert any(output.origin_id == round_id for output in restored.outputs)
            goals = await app.sessions.goals.list(bindings[second])
            assert goals[-1].status == "paused"

    asyncio.run(scenario())
