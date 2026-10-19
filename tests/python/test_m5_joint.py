"""空白计数器的最小 M5 联合场景；三种路由另复用团队定向用例。

Minimal M5 counter integration; reuse focused team tests for the three routing modes.
"""

import asyncio
import copy
import json
import sys
from uuid import uuid4

from my_agent.attachments.types import AttachmentParams, ImportAttachment
from my_agent.documents.types import DocumentParams, SaveDocumentParams
from my_agent.models.types import ToolCall
from my_agent.sessions.types import RequestStarted, ToolCompleted, ToolStarted
from my_agent.spaces.team_types import (
    SpaceChatParams,
    StartSpaceRoundParams,
    StopSpaceRoundParams,
    UpdateSpaceWorkParams,
)
from my_agent.spaces.types import SaveSpaceParams, SpaceConfig, SpaceParams, SpaceStartParams
from tests.python.test_collaboration import finish
from tests.python.test_goal_controller import app_at, call, create_session, turn
from tests.python.test_spaces import team

COUNTER = (
    "<!doctype html><html><head><title>Counter</title></head><body>"
    '<button id="increment">+</button><output id="count">1</output>'
    '<script>let count = 1; document.getElementById("increment").onclick = () => {'
    'count += 1; document.getElementById("count").textContent = String(count);};'
    "</script></body></html>\n"
)


class JointModel:
    """离线决策脚本只替换模型；文件、Goal、命令和材料使用实际服务。

    Script only offline decisions; files, goals, commands and materials use actual services.
    """

    def __init__(self) -> None:
        """按会话保持动作与可控阻塞，保存真实请求材料。

        Keep per-session decisions and gates while capturing real request materials.
        """
        self.queues: dict[str, list[ToolCall | str]] = {}
        self.entered: dict[str, asyncio.Event] = {}
        self.release: dict[str, asyncio.Event] = {}
        self.inputs: list[tuple[str, list[dict]]] = []

    def check_available(self) -> None:
        """不读取凭据或调用网络。 Avoid credentials and networking."""

    async def complete(self, **kwargs):
        """完整回合驱动正式工具；阻塞仅用于停止归属验证。

        Drive actual tools with complete turns; gates verify stop ownership only.
        """
        instruction = kwargs["messages"][0]["content"]
        if instruction.startswith("Extract only reusable"):
            return turn(text='{"entries": []}')
        if instruction.startswith("Write one concise continuation brief"):
            return turn(text="Counter source and review are saved in the selected project.")
        session_id = kwargs["session_id"]
        self.inputs.append((session_id, copy.deepcopy(kwargs["messages"])))
        if session_id in self.release:
            self.entered[session_id].set()
            await self.release[session_id].wait()
        action = self.queues[session_id].pop(0)
        if isinstance(action, ToolCall):
            text = action.arguments.get("summary", "") if action.name == "report_work" else ""
            return turn(action, text=text)
        return turn(text=action)


def test_counter_team_files_goal_stop_materials_and_restart(tmp_path):
    """整合原项目工具、团队工作归属、独立停止、草稿材料与旧会话重启。

    Integrate in-place tools, team ownership, isolated stops, draft materials and legacy restart.
    """

    async def scenario():
        """实际命令只做源码核对；浏览点击与看图由独立真实验收负责。

        The real command checks source only; browser clicks and vision use separate live acceptance.
        """
        model = JointModel()
        config = team()
        config["initial_work_items"] = [
            {
                "work_id": "build",
                "title": "Build counter",
                "scope": "index.html",
                "status": "planned",
            },
            {
                "work_id": "review",
                "title": "Review counter",
                "scope": "initial count",
                "status": "planned",
            },
        ]
        first, second = [member["member_id"] for member in config["members"]]
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            task_id, legacy_id = created.task.task_id, created.session.session_id
            task_goal = created.task.fields.goal
            legacy_path = app.sessions.store.path(legacy_id)
            legacy_before = legacy_path.read_bytes()
            await app.spaces.save(
                SaveSpaceParams(
                    task_id=task_id,
                    expected_revision=None,
                    config=SpaceConfig.model_validate(config),
                )
            )
            assembled = await app.spaces.start(SpaceStartParams(task_id=task_id))
            assert assembled.space
            bindings = {
                binding.member_id: binding.session_id for binding in assembled.space.bindings
            }
            implementation, review = bindings[first], bindings[second]
            assert implementation and review
            for member, work in ((first, "build"), (second, "review")):
                await app.team.update_work(
                    UpdateSpaceWorkParams(
                        task_id=task_id,
                        operation_id=str(uuid4()),
                        work_id=work,
                        member_id=member,
                        action="claim",
                    )
                )
            model.queues[implementation] = [
                call("create_file", path="index.html", content=COUNTER),
                "Counter source created.",
            ]
            sent = await app.team.chat(
                SpaceChatParams(
                    task_id=task_id,
                    operation_id=str(uuid4()),
                    content="Build a single counter page",
                    target_member_ids=[first],
                )
            )
            build_run_id = sent.messages[-1].executions[0].run_id
            await finish(app, implementation)
            assert (tmp_path / "project/index.html").read_text(encoding="utf-8") == COUNTER
            assert not (tmp_path / "project/.git").exists()
            model.queues[review] = [
                call("read_file", path="index.html"),
                "Review: initialise the counter at zero.",
            ]
            await app.team.chat(
                SpaceChatParams(
                    task_id=task_id,
                    operation_id=str(uuid4()),
                    content="Review the initial count",
                    target_member_ids=[second],
                )
            )
            await finish(app, review)
            command = {
                "kind": "program",
                "program": sys.executable,
                "arguments": [
                    "-c",
                    "from pathlib import Path; "
                    "text=Path('index.html').read_text(encoding='utf-8'); "
                    "assert 'let count = 0' in text; assert 'count += 1' in text; "
                    "print('counter-source-verified')",
                ],
            }
            model.queues[implementation] = [
                call(
                    "edit_file", path="index.html", old_text='id="count">1', new_text='id="count">0'
                ),
                call(
                    "edit_file",
                    path="index.html",
                    old_text="let count = 1",
                    new_text="let count = 0",
                ),
                call("run_command", command=command),
                call(
                    "report_work",
                    summary="Counter initial value fixed; local source check passed.",
                    outcome="complete",
                ),
            ]
            fixed = await app.team.start_round(
                StartSpaceRoundParams(
                    task_id=task_id,
                    operation_id=str(uuid4()),
                    objective="Fix the review finding in the existing counter",
                    target_member_ids=[first],
                )
            )
            await finish(app, implementation)
            completed = await app.team.chat_view(SpaceParams(task_id=task_id))
            assert completed.rounds[-1].round_id == fixed.rounds[-1].round_id
            assert any("Counter initial value fixed" in output.text for output in completed.outputs)
            facts = app.sessions.store.load(implementation).facts
            command_ids = {
                fact.data.call.tool_call_id
                for fact in facts
                if isinstance(fact.data, ToolStarted) and fact.data.call.name == "run_command"
            }
            commands = [
                fact.data
                for fact in facts
                if isinstance(fact.data, ToolCompleted)
                and fact.data.result.tool_call_id in command_ids
            ]
            assert len(commands) == 1
            command_result = json.loads(commands[0].result.content)
            assert command_result["summary"]["exit_code"] == 0
            assert any(
                "counter-source-verified" in item["text"] for item in command_result["output"]
            )
            await app.team.update_work(
                UpdateSpaceWorkParams(
                    task_id=task_id,
                    operation_id=str(uuid4()),
                    work_id="build",
                    member_id=first,
                    action="result",
                    run_id=build_run_id,
                    result="index.html created in the original project",
                )
            )
            task = await app.worker.call(app.tasks.store.get, task_id)
            assert {item.work_id: item.owner_member_id for item in task.work.assignments} == {
                "build": first,
                "review": second,
            }
            assert task.fields.goal == task_goal
            document = await app.documents.read(
                DocumentParams(session_id=implementation, path="index.html")
            )
            draft_text = document.content.replace(
                "<title>Counter</title>", "<title>Counter draft</title>"
            )
            await app.documents.draft(
                SaveDocumentParams(
                    session_id=implementation,
                    path="index.html",
                    base_content=document.content,
                    content=draft_text,
                )
            )
            attachment = await app.attachments.import_file(
                ImportAttachment(
                    session_id=implementation,
                    path="index.html",
                    content=draft_text,
                    draft=True,
                    start_line=1,
                    end_line=1,
                    purpose="Unsaved counter title review",
                )
            )
            model.queues[implementation] = [
                "Draft material received without saving it to the project."
            ]
            await app.sessions.start(
                implementation,
                str(uuid4()),
                "Review this draft only",
                None,
                mode="normal",
                attachment_ids=[attachment.attachment_id],
            )
            await finish(app, implementation)
            captured = model.inputs[-1][1][-1]["content"]
            assert isinstance(captured, list) and any(
                draft_text in part.get("text", "") for part in captured
            )
            assert "Counter draft" not in (tmp_path / "project/index.html").read_text(
                encoding="utf-8"
            )
            material_request = next(
                fact.data
                for fact in reversed(app.sessions.store.load(implementation).facts)
                if isinstance(fact.data, RequestStarted)
            )
            assert any(
                material.kind == "attachment" and material.source_id == attachment.attachment_id
                for material in material_request.context.materials
            )
            # 同成员轮次停止不能取消另一个成员的独立普通请求。
            # Stopping a member round must not cancel another member's ordinary request.
            for session_id in (implementation, review):
                model.entered[session_id] = asyncio.Event()
                model.release[session_id] = asyncio.Event()
                model.queues[session_id] = ["Unrelated review completed."]
            await app.sessions.start(
                review, str(uuid4()), "Hold an unrelated review", None, mode="normal"
            )
            await asyncio.wait_for(model.entered[review].wait(), 3)
            round_id = str(uuid4())
            await app.team.start_round(
                StartSpaceRoundParams(
                    task_id=task_id,
                    operation_id=round_id,
                    objective="Hold the next counter work unit",
                    target_member_ids=[first],
                )
            )
            await asyncio.wait_for(model.entered[implementation].wait(), 3)
            await app.team.stop(StopSpaceRoundParams(task_id=task_id, round_id=round_id))
            assert app.sessions.active_for(review) is not None
            model.release[review].set()
            await finish(app, review)
            await finish(app, implementation)
            stopped = await app.team.chat_view(SpaceParams(task_id=task_id))
            assert stopped.rounds[-1].stopped
            paused = (await app.sessions.goals.list(implementation))[-1]
            assert paused.status == "paused"
            assert legacy_path.read_bytes() == legacy_before
            model_calls = len(model.inputs)
            project_bytes = (tmp_path / "project/index.html").read_bytes()
        async with app_at(tmp_path / "data", model) as app:
            restored = await app.team.chat_view(SpaceParams(task_id=task_id))
            assert restored.rounds[-1].round_id == round_id and restored.rounds[-1].stopped
            assert (await app.sessions.view(legacy_id)).summary.session_id == legacy_id
            assert legacy_path.read_bytes() == legacy_before
            snapshot = await app.attachments.read(
                AttachmentParams(session_id=implementation, attachment_id=attachment.attachment_id)
            )
            assert snapshot.attachment.draft and snapshot.text == draft_text
            assert (tmp_path / "project/index.html").read_bytes() == project_bytes
            assert len(model.inputs) == model_calls and not app.sessions.active_runs

    asyncio.run(scenario())
