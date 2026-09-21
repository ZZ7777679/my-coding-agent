"""实际会话控制器的离线模型验收，项目文件和存储使用真实实现。

Offline-model acceptance of the real session controller, file tools and durable storage.
"""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from my_agent.changes.store import ChangeStore
from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError
from my_agent.goals.types import GoalBudget, GoalControl, GoalCreated, GoalCriterion
from my_agent.memory.types import MemorySettings
from my_agent.models.types import ModelTurn, TokenUsage, ToolCall
from my_agent.rpc.application import RpcApplication
from my_agent.rpc.dto import CredentialInfo
from my_agent.sessions.recovery_types import SessionRecovered
from my_agent.sessions.types import (
    GoalInputQueued,
    RunAccepted,
    RunFinished,
    ToolCompleted,
    ToolSkipped,
)


def turn(*calls, text=""):
    """生成完整且可配对的模型结果，不伪造工具完成。

    Build a complete pairable model turn without inventing tool completion.
    """
    return ModelTurn(
        text=text,
        tool_calls=list(calls),
        native={
            "role": "assistant",
            "content": text or None,
            **(
                {
                    "tool_calls": [
                        {
                            "id": call.tool_call_id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in calls
                    ]
                }
                if calls
                else {}
            ),
        },
        usage=TokenUsage(input_tokens=1, output_tokens=1),
    )


def call(name, **arguments):
    """每次工具调用使用独立身份。

    Give each actual tool call a distinct identity.
    """
    return ToolCall(tool_call_id=str(uuid4()), name=name, arguments=arguments)


def evidence(messages):
    """从真实来源索引读取文件执行证据，而非猜测序号。

    Read file execution evidence from the actual index instead of guessing sequences.
    """
    index = json.loads(messages[-1]["content"])
    item = next(item for item in index["evidence"] if item.get("tool_name") == "create_file")
    return {
        **{key: item[key] for key in ("session_id", "run_id", "seq", "kind")},
        "expectation": "succeeded",
    }


@asynccontextmanager
async def app_at(directory, model):
    """真实应用装配只替换模型；关闭时回收后端和单写者。

    Replace only the model in real app composition and clean up its backend and writer.
    """
    app = RpcApplication(
        resolve_data_dir(str(directory)),
        ResolvedCredential(
            None, CredentialInfo(env_var="OPENCODE_API_KEY", source="none", present=False)
        ),
        None,
    )
    app.sessions.model_factory = lambda: model
    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "test",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": 1,
            },
        )
        yield app
    finally:
        await app.close()


async def create_session(app, project):
    """登记隔离空目录并由用户路径创建任务 / 会话。

    Register an isolated empty project and create its task and session through the user path.
    """
    project.mkdir()
    opened = await app.dispatch("projects.open", {"path": str(project)})
    created = await app.dispatch(
        "tasks.create",
        {
            "operation_id": str(uuid4()),
            "project_id": opened.active_project.project_id,
            "model_id": "glm-5.3-flash",
            "fields": {"title": "Goal test", "goal": "Build small files"},
        },
    )
    # M2 调度用例只测前台请求；M3 用例显式开启并验证独立维护。
    # M2 scenarios count foreground requests; M3 tests explicitly enable maintenance.
    await app.sessions.memory.configure(created.session.session_id, MemorySettings(automatic=False))
    return created


def definition(**budget):
    """固定原目标与条件，预算由各边界场景明确指定。

    Keep original criteria fixed while each scenario supplies its budget.
    """
    return GoalCreated(
        goal_id=str(uuid4()),
        objective="Create the requested files and report them",
        criteria=[GoalCriterion(criterion_id="files", description="Requested files are saved")],
        budget=GoalBudget(**budget),
    )


async def control(goals, session_id, action, **fields):
    """以最新显示版本发送明确用户操作。

    Send an explicit control against its latest view.
    """
    view = (await goals.list(session_id))[-1]
    return await goals.control(
        session_id,
        GoalControl(
            goal_id=view.goal_id,
            operation_id=str(uuid4()),
            expected_revision=view.revision,
            action=action,
            **fields,
        ),
    )


class SequenceModel:
    """按实际上下文推进两个工作单元，插话只读回答。

    Advance two work units from actual context and answer interruptions read-only.
    """

    def __init__(self):
        """保留请求数和工作步骤。

        Keep request counts and work steps.
        """
        self.calls = 0
        self.step = 0

    def check_available(self):
        """不连接 provider。

        Do not connect to a provider.
        """

    async def complete(self, **kwargs):
        """从真实索引报告进度，完整工作单元间不多调总结请求。

        Report real indexed progress without additional summarization requests between units.
        """
        self.calls += 1
        messages = kwargs["messages"]
        if "ordinary question interrupting" in messages[0]["content"]:
            assert any(
                "Create the requested files and report them" in str(message.get("content"))
                for message in messages[1:]
            )
            names = {tool["function"]["name"] for tool in kwargs["tools"]}
            assert "create_file" not in names and "report_work" not in names
            return turn(text="The first file is saved; the goal will continue.")
        self.step += 1
        if self.step == 1:
            return turn(
                call("create_file", path="one.txt", content="one"),
                call("create_file", path="must-not-execute.txt", content="skip"),
            )
        if self.step in {2, 5}:
            return turn(call("read_work_status"))
        if self.step == 4:
            assert '"work_id": "second"' in messages[0]["content"]
            return turn(call("create_file", path="two.txt", content="two"))
        if self.step in {3, 6}:
            final = self.step == 6
            source = evidence(messages)
            return turn(
                call(
                    "report_work",
                    **{
                        "summary": "Both files saved" if final else "First file saved",
                        "outcome": "complete" if final else "continue",
                        "next_action": "" if final else "Create the second requested file",
                        "criteria": [
                            {
                                "criterion_id": "files",
                                "status": "met" if final else "unmet",
                                "explanation": "Observed saved files",
                                "evidence": [source],
                            }
                        ],
                        "work_items": [
                            {
                                "work_id": "second" if final else "first",
                                "title": "Save requested file",
                                "scope": "Requested files",
                                "status": "completed",
                                "evidence": [source],
                                "depends_on": ["first"] if final else [],
                            },
                            *(
                                []
                                if final
                                else [
                                    {
                                        "work_id": "second",
                                        "title": "Save second file",
                                        "scope": "two.txt",
                                        "status": "planned",
                                        "depends_on": ["first"],
                                    }
                                ]
                            ),
                        ],
                    },
                )
            )
        raise AssertionError("Unexpected extra model request")


class BlockingTools:
    """只在首次真实写入前留出确定性插话窗口，工具逻辑仍为生产实现。

    Gate the first real write for deterministic interruption, retaining production tool behavior.
    """

    def __init__(self, delegate, entered, release):
        """保存该运行的委托和测试事件。

        Bind the run's delegate and test events.
        """
        self.delegate, self.entered, self.release = delegate, entered, release

    def definitions(self):
        """保留真实工具 schema。

        Preserve real tool schemas.
        """
        return self.delegate.definitions()

    def is_mutating(self, name):
        """保留真实写入分类。

        Preserve real mutation classification.
        """
        return self.delegate.is_mutating(name)

    async def execute(self, tool_call):
        """已开始的写入等明确释放，再执行一次真实操作。

        Release an already-started write before performing its actual operation exactly once.
        """
        if tool_call.name == "create_file" and tool_call.arguments["path"] == "one.txt":
            self.entered.set()
            await self.release.wait()
        return await self.delegate.execute(tool_call)


def test_goal_continuation_question_boundary_and_idempotency(tmp_path):
    """普通问题在完整工具边界执行，原目标继续，重复输入不产生额外请求。

    Answer at a paired tool boundary, continue the original goal and deduplicate repeated input.
    """

    async def scenario():
        """驱动真实文件 / 任务同步，整个过程不使用网络。

        Drive real files and task synchronization without network access.
        """
        model = SequenceModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            session_id = created.session.session_id
            goals = app.sessions.goals
            entered, release = asyncio.Event(), asyncio.Event()
            factory = app.sessions.tool_factory
            app.sessions.tool_factory = lambda context: BlockingTools(
                factory(context), entered, release
            )
            goal = definition(max_requests=7, max_tools=6)
            await goals.create(session_id, goal)
            driver = goals.driver(session_id)
            await asyncio.wait_for(entered.wait(), 3)
            question_id = str(uuid4())
            for _ in range(2):
                await app.sessions.start(session_id, question_id, "What is saved?", None, "normal")
            assert len((await goals.list(session_id))[0].pending_inputs) == 1
            assert model.calls == 1
            release.set()
            await asyncio.wait_for(driver.task, 5)
            view = (await goals.list(session_id))[0]
            assert view.status == "completed", view
            assert view.usage.requests == 7 and view.usage.tools == 6
            assert view.usage.reserved_seconds == 0 and view.usage.active_seconds > 0
            assert view.objective == goal.objective and view.criteria == goal.criteria
            assert view.pending_inputs == []
            assert (tmp_path / "project" / "one.txt").read_text() == "one"
            assert (tmp_path / "project" / "two.txt").read_text() == "two"
            assert not (tmp_path / "project" / "must-not-execute.txt").exists()
            log = app.sessions.store.load(session_id)
            assert log.issue is None and log.context()[1]
            runs = [fact.data for fact in log.facts if isinstance(fact.data, RunAccepted)]
            assert [run.goal_role for run in runs] == ["work", "question", "work", "work"]
            assert [run.work_id for run in runs] == [None, None, None, "second"]
            assert [run.method for run in runs] == [
                "implement",
                "discuss",
                "implement",
                "implement",
            ]
            assert all(run.method_version == "1" for run in runs)
            assert next(
                fact.data for fact in log.facts if isinstance(fact.data, RunFinished)
            ).checkpoint
            assert sum(isinstance(fact.data, ToolSkipped) for fact in log.facts) == 1
            assert sum(isinstance(fact.data, GoalInputQueued) for fact in log.facts) == 1
            task = app.tasks.store.get(created.task.task_id)
            assert task.fields.status == "active"
            assert {item.item.work_id: item.item.status for item in task.work.items} == {
                "first": "completed",
                "second": "completed",
            }
            await goals.create(session_id, goal)
            await app.sessions.start(session_id, question_id, "What is saved?", None, "normal")
            assert model.calls == 7 and goals.driver(session_id) is None

    asyncio.run(scenario())


def test_goal_progress_without_report_gates_or_argument_abort(tmp_path):
    """参数可修正，正文可续跑，简单报告与未齐全的工作图不再阻塞。

    Correct arguments, continue text-only turns and accept simple reports or partial work graphs.
    """

    class MissingCriteriaModel:
        """只替换模型，实际执行文件写入、参数反馈与 Goal 结算。

        Substitute only the model; exercise actual file writes, feedback and Goal settlement.
        """

        calls = 0
        report = None

        def check_available(self):
            """不连接真实模型。

            Never connect to a real model.
            """

        async def complete(self, **kwargs):
            """模型根据反馈修正参数，最后无需补造证据表即可收尾。

            Correct rejected arguments from feedback and finish without manufacturing a proof table.
            """
            self.calls += 1
            report_tool = next(
                item["function"]
                for item in kwargs["tools"]
                if item["function"]["name"] == "report_work"
            )
            schema = report_tool["parameters"]
            assert "use continue, complete or wait" in report_tool["description"]
            assert "use return" not in report_tool["description"]
            assert set(schema["required"]) == {"summary", "outcome"}
            assert "return" not in schema["properties"]["outcome"]["enum"]
            assert "minItems" not in schema["properties"]["criteria"]
            if self.calls == 1:
                return turn(call("create_file", path="index.html"))
            if self.calls == 2:
                assert "INVALID_TOOL_ARGUMENTS" in kwargs["messages"][-1]["content"]
                return turn(call("create_file", path="index.html", content="<h1>Saved</h1>"))
            if self.calls == 3:
                return turn(text="The file is saved; preparing a progress report.")
            if self.calls == 4:
                return turn(
                    call(
                        "report_work",
                        summary="Progress recorded without a complete dependency graph",
                        outcome="continue",
                        next_work_id="not-in-this-goal",
                        work_items=[
                            {
                                "work_id": "page",
                                "title": "Page",
                                "scope": "index.html",
                                "status": "in_progress",
                                "depends_on": ["later-item"],
                            }
                        ],
                    )
                )
            if self.calls == 5:
                self.report = {
                    "outcome": "complete",
                    "summary": "The requested page was saved.",
                    "work_items": [
                        {
                            "work_id": "page",
                            "title": "Create the page",
                            "scope": "index.html",
                            "status": "completed",
                        }
                    ],
                }
                return turn(
                    call("report_work", **self.report),
                    call("create_file", path="must-not-run.txt", content="not authorized"),
                )
            raise AssertionError("No extra request after completion")

    async def scenario():
        """旧会话无需额外任务 / 引用配置，全程只实际创建一次文件。

        A legacy taskless session needs no extra metadata setup and writes the file only once.
        """
        model = MissingCriteriaModel()
        async with app_at(tmp_path / "data", model) as app:
            project = tmp_path / "project"
            project.mkdir()
            opened = await app.dispatch("projects.open", {"path": str(project)})
            session = await app.sessions.create(opened.active_project.project_id, "glm-5.3-flash")
            session_id, goals = session.session_id, app.sessions.goals
            await goals.create(session_id, definition(max_requests=6))
            await asyncio.wait_for(goals.driver(session_id).task, 4)
            assert model.calls == 5
            assert (await goals.list(session_id))[0].status == "completed"
            assert (project / "index.html").read_text() == "<h1>Saved</h1>"
            assert not (project / "must-not-run.txt").exists()
            assert goals.driver(session_id) is None and app.sessions.active_for(session_id) is None
            log = app.sessions.store.load(session_id)
            assert log.context()[1]
            assert sum(isinstance(fact.data, ToolSkipped) for fact in log.facts) == 1

    asyncio.run(scenario())


def test_goal_continues_after_missing_file_in_empty_project(tmp_path):
    """空项目没有常见文件时交回事实，模型可继续创建并完成 Goal。

    Missing files in empty projects are feedback; the model may create them and finish the Goal.
    """

    class MissingFileModel:
        """依据真实缺失与保存结果推进，不隐式重试。

        Advance from actual missing/save results.
        """

        calls = 0

        def check_available(self):
            """只使用离线模型。

            Use an offline model only.
            """

        async def complete(self, **kwargs):
            """读不存在文件、创建文件、报告完成。

            Read a missing file, create it, then report.
            """
            self.calls += 1
            if self.calls == 1:
                return turn(call("read_file", path="README.md"))
            result = json.loads(kwargs["messages"][-1]["content"])
            if self.calls == 2:
                assert result["code"] == "FILE_NOT_FOUND"
                return turn(call("create_file", path="README.md", content="A new project\n"))
            assert result["status"] == "applied"
            return turn(call("report_work", summary="Created README", outcome="complete"))

    async def scenario():
        """隔离空项目内保留同一 Goal 与工具历史。

        Keep one Goal and tool history in an isolated empty project.
        """
        model = MissingFileModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            identity = created.session.session_id
            await app.sessions.goals.create(identity, definition())
            await asyncio.wait_for(app.sessions.goals.driver(identity).task, 4)
            assert (await app.sessions.goals.list(identity))[-1].status == "completed"
            assert model.calls == 3
            assert (tmp_path / "project" / "README.md").read_text() == "A new project\n"

    asyncio.run(scenario())


def test_goal_continues_after_file_conflict_and_unreadable_change(tmp_path, monkeypatch):
    """真实写入冲突和坏历史仅返回局部错误，原 Goal 继续完成。

    Continue the original Goal after real write conflicts and damaged history.
    """
    project = tmp_path / "project"

    class CorrectingModel:
        """根据实际工具反馈重新读取、编辑并报告；不注入成功结果。

        Reread, edit and report from actual tool feedback without injecting successful results.
        """

        calls = 0
        change_id = None

        def check_available(self):
            """仅替换模型，不使用网络。

            Substitute only the model without network use.
            """

        async def complete(self, **kwargs):
            """按原任务推进，断言两次局部错误后仍能收到后续请求。

            Advance the same task and verify requests continue after both local errors.
            """
            self.calls += 1
            tools = [item for item in kwargs["messages"] if item["role"] == "tool"]
            previous = json.loads(tools[-1]["content"]) if tools else {}
            assert not {"sha256", "before_sha256", "after_sha256"}.intersection(previous)
            if self.calls == 1:
                return turn(call("create_file", path="main.py", content="print(1)\n"))
            if self.calls == 2:
                return turn(
                    call("edit_file", path="main.py", old_text="print(1)", new_text="print(2)")
                )
            if self.calls == 3:
                assert previous["code"] == "FILE_CHANGED"
                assert (project / "main.py").read_text() == "print(1)\n# external\n"
                return turn(call("read_file", path="main.py"))
            if self.calls == 4:
                assert "# external" in previous["content"]
                return turn(
                    call("edit_file", path="main.py", old_text="print(1)", new_text="print(2)")
                )
            if self.calls == 5:
                assert previous["status"] == "applied"
                self.change_id = previous["change_id"]
                return turn(call("read_change", change_id=self.change_id))
            if self.calls == 6:
                assert "+print(2)" in previous["diff"]
                assert "after_sha256" not in previous["summary"]
                path = app.changes.path(session_id, self.change_id)
                await asyncio.to_thread(path.write_text, "{", encoding="utf-8")
                return turn(call("read_change", change_id=self.change_id))
            if self.calls == 7:
                assert previous["code"] == "CHANGE_DAMAGED"
                return turn(call("list_changes"))
            if self.calls == 8:
                assert previous["unavailable_count"] == 1
                assert len(previous["changes"]) == 2
                assert all("after_sha256" not in item for item in previous["changes"])
                return turn(call("create_file", path="done.txt", content="done"))
            if self.calls == 9:
                assert previous["status"] == "applied"
                return turn(
                    call(
                        "report_work",
                        summary="Files saved; one historical diff could not be read.",
                        outcome="complete",
                    )
                )
            raise AssertionError("Unexpected extra model request")

    async def scenario():
        """在准备与保存之间制造一次外部改动，使用真实应用、文件与成果存储。

        Inject one external change between preparation and commit using the real application stack.
        """
        nonlocal app, session_id
        model = CorrectingModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, project)
            session_id = created.session.session_id
            original = ChangeStore.save
            changed = False

            def change_once(store, record):
                """只在首次编辑准备后修改文件，后续真实编辑正常执行。

                Change the file after the first edit preparation; later edits run normally.
                """
                nonlocal changed
                original(store, record)
                if (
                    not changed
                    and record.summary.operation == "edit"
                    and record.summary.status == "prepared"
                ):
                    changed = True
                    (project / "main.py").write_bytes(b"print(1)\n# external\n")

            monkeypatch.setattr(ChangeStore, "save", change_once)
            goals = app.sessions.goals
            await goals.create(session_id, definition(max_requests=10, max_tools=10))
            await asyncio.wait_for(goals.driver(session_id).task, 5)
            assert (await goals.list(session_id))[0].status == "completed"
            assert model.calls == 9
            assert (project / "main.py").read_bytes() == b"print(2)\n# external\n"
            assert (project / "done.txt").read_text() == "done"
            log = app.sessions.store.load(session_id)
            assert sum(isinstance(fact.data, RunAccepted) for fact in log.facts) == 1
            errors = [
                json.loads(fact.data.result.content)["code"]
                for fact in log.facts
                if isinstance(fact.data, ToolCompleted) and fact.data.result.is_error
            ]
            assert errors == ["FILE_CHANGED", "CHANGE_DAMAGED"]
            assert all(
                fact.data.status == "completed"
                for fact in log.facts
                if isinstance(fact.data, RunFinished)
            )

    app, session_id = None, None
    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("tool_name", "continuation"), [("create_file", "send"), ("run_command", "resume")]
)
def test_interrupted_effect_reconciliation_without_replay(tmp_path, tool_name, continuation):
    """新消息 / 接续直接核对丢失响应，保留来源、变化及幂等，不另确认或重做副作用。

    Send/resume reconciles lost responses with provenance and idempotency, no extra confirmation.
    """

    class InterruptedModel:
        """只提交一个实际动作及一个尚未开始的动作。

        Submit one actual effect and another call that must remain unstarted.
        """

        calls = 0

        def check_available(self):
            """不访问真实模型。

            Never access a real model.
            """

        async def complete(self, **kwargs):
            """恢复后只回答明确的新问题，不重新发送原始调用。

            After recovery answer only the new question without resending the old call.
            """
            self.calls += 1
            if self.calls > 1:
                assert any(
                    "INTERRUPTED_RESULT_RECONCILED" in (item.get("content") or "")
                    for item in kwargs["messages"]
                )
                if continuation == "resume":
                    return turn(
                        call(
                            "report_work",
                            summary="Observed saved output without replay",
                            outcome="wait",
                            criteria=[
                                {
                                    "criterion_id": "files",
                                    "status": "needs_user",
                                    "explanation": "Need the user's requested final filename",
                                }
                            ],
                            question={
                                "question_id": str(uuid4()),
                                "question": "What should the final file be named?",
                                "impact": "Determines the next file to create",
                            },
                        )
                    )
                return turn(text="已读取核对事实，未重跑旧动作。")
            first = (
                call("create_file", path="once.txt", content="saved once")
                if tool_name == "create_file"
                else call(
                    "run_command",
                    command={
                        "kind": "program",
                        "program": "python",
                        "arguments": [
                            "-c",
                            "from pathlib import Path; "
                            "Path('once.txt').write_text('saved once', encoding='utf-8')",
                        ],
                    },
                )
            )
            return turn(first, call("create_file", path="never.txt", content="must not execute"))

    async def scenario():
        """通过生产装配的实际取消制造丢失响应，并经公开 RPC 核对。

        Lose a response through real cancellation in production composition, then reconcile via RPC.
        """
        model = InterruptedModel()
        project = tmp_path / "project"
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, project)
            session_id = created.session.session_id
            if tool_name == "run_command":
                catalog = await app.dispatch(
                    "environments.save",
                    {
                        "project_id": created.task.project_id,
                        "environment_id": None,
                        "expected_revision": 0,
                        "name": "Test Python",
                        "definition": {
                            "kind": "python",
                            "scope": "absolute",
                            "interpreter": sys.executable,
                        },
                    },
                )
                await app.dispatch(
                    "environments.bind",
                    {
                        "project_id": created.task.project_id,
                        "environment_id": catalog.environments[0].record.environment_id,
                        "expected_revision": catalog.revision,
                        "trusted": True,
                        "mode": "direct",
                    },
                )
            saved = asyncio.Event()
            original_factory = app.sessions.tool_factory

            class Gate:
                """只延迟真实工具返回后的响应，不替换工具效果。

                Delay only the response after the real tool effect, without mocking that effect.
                """

                def __init__(self, context):
                    """保留实际工具装配。

                    Keep actual tool composition.
                    """
                    self.delegate = original_factory(context)

                def definitions(self):
                    return self.delegate.definitions()

                def is_mutating(self, name):
                    return self.delegate.is_mutating(name)

                async def execute(self, request):
                    """真实保存后等待取消，模拟结果提交前的中断。

                    Await cancellation after a real save, simulating interruption before commit.
                    """
                    result = await self.delegate.execute(request)
                    assert not result.is_error, result.content
                    saved.set()
                    await asyncio.Event().wait()
                    return result

            app.sessions.tool_factory = Gate
            goals = app.sessions.goals
            await goals.create(session_id, definition(max_requests=5))
            driver = goals.driver(session_id)
            await asyncio.wait_for(saved.wait(), 4)
            await control(goals, session_id, "pause")
            await asyncio.wait_for(driver.task, 4)
            assert (project / "once.txt").read_text() == "saved once"
            assert not (project / "never.txt").exists()
            assert not (await app.sessions.view(session_id)).summary.can_continue
            operation_id = str(uuid4())
            if tool_name == "create_file":
                (project / "once.txt").write_text("external edit", encoding="utf-8")
            before = app.sessions.store.path(session_id).read_bytes()
            content = (project / "once.txt").read_bytes()
            app.sessions.tool_factory = original_factory
            if continuation == "send":
                await app.sessions.start(session_id, operation_id, "Read saved observations", None)
                await app.sessions.active_for(session_id).task
            else:
                goal = (await goals.list(session_id))[0]
                resume = GoalControl(
                    goal_id=goal.goal_id,
                    operation_id=operation_id,
                    expected_revision=goal.revision,
                    action="resume",
                )
                await goals.control(session_id, resume)
                await goals.driver(session_id).task
            view = await app.sessions.view(session_id)
            assert view.summary.can_continue and view.summary.run.status == "completed"
            saved_recovery = next(
                fact.data
                for fact in app.sessions.store.load(session_id).facts
                if isinstance(fact.data, SessionRecovered)
            )
            assert saved_recovery.items[0].observation.state == "observed"
            assert saved_recovery.items[1].observation.state == "not_started"
            observation = saved_recovery.items[0].observation
            if tool_name == "create_file":
                assert observation.current_status == "changed"
            else:
                assert observation.current_status == "exited" and observation.exit_code == 0
            after = app.sessions.store.path(session_id).read_bytes()
            assert after.startswith(before) and len(after) > len(before)
            if continuation == "send":
                await app.sessions.start(session_id, operation_id, "Read saved observations", None)
            else:
                await goals.control(session_id, resume)
            assert app.sessions.store.path(session_id).read_bytes() == after
            assert (project / "once.txt").read_bytes() == content and model.calls == 2
            goal = (await goals.list(session_id))[0]
            expected_status = "paused" if continuation == "send" else "waiting"
            assert goal.status == expected_status
            assert goal.usage.requests == goal.usage.tools == (1 if continuation == "send" else 2)
        async with app_at(tmp_path / "data", model) as app:
            assert (await app.sessions.view(session_id)).summary.can_continue
            assert model.calls == 2 and (project / "once.txt").read_bytes() == content
            assert (await app.sessions.view(session_id)).summary.run.status == "completed"
            assert not (project / "never.txt").exists()
            assert (await app.sessions.goals.list(session_id))[0].status == expected_status

    asyncio.run(scenario())


class DecisionModel:
    """保存文件后提出 HITL，再模拟一次网络故障以验证明确接续。

    Save a file, request HITL and inject a network fault to verify explicit continuation.
    """

    def __init__(self):
        """保存固定问题身份和实际请求次数。

        Keep a stable question identity and request count.
        """
        self.calls, self.step = 0, 0
        self.question_id = str(uuid4())

    def check_available(self):
        """不读取凭据。

        Do not read credentials.
        """

    async def complete(self, **kwargs):
        """普通问答不会改变步骤；答复后故障不重试，恢复最终报告原目标。

        Chat does not advance work; failure never retries, and explicit recovery reports the goal.
        """
        self.calls += 1
        messages = kwargs["messages"]
        if "Goal mode:" not in messages[0]["content"]:
            return turn(text="An ordinary answer without goal resumption.")
        self.step += 1
        if self.step == 1:
            return turn(call("create_file", path="saved.txt", content="saved once"))
        if self.step == 2:
            return turn(
                call(
                    "report_work",
                    summary="File saved; waiting for choice",
                    outcome="wait",
                    criteria=[
                        {
                            "criterion_id": "files",
                            "status": "needs_user",
                            "explanation": "Need decision",
                        }
                    ],
                    question={
                        "question_id": self.question_id,
                        "question": "Finish with this file?",
                        "impact": "No additional files will be created",
                        "options": ["Yes", "No"],
                    },
                )
            )
        if self.step == 3:
            assert "Confirmed file" in messages[0]["content"]
            assert any("Confirmed file" in str(message.get("content")) for message in messages[1:])
            raise AgentError("MODEL_TIMEOUT", "simulated model failure")
        if self.step == 4:
            return turn(call("read_work_status"))
        if self.step == 5:
            return turn(
                call(
                    "report_work",
                    summary="Existing file delivered",
                    outcome="complete",
                    criteria=[
                        {
                            "criterion_id": "files",
                            "status": "met",
                            "explanation": "Saved file exists",
                            "evidence": [evidence(messages)],
                        }
                    ],
                )
            )
        raise AssertionError("Unexpected automatic retry")


def test_goal_hitl_failure_chat_and_budget_resume(tmp_path):
    """准确答复才接续；故障和预算停止，普通问题不解除停止也不自动修复。

    Resume only for the exact answer; failures and budgets stop work without chat-induced repair.
    """

    async def scenario():
        """核对累计用量、结果文件未重写和原目标保持。

        Check cumulative usage, unchanged saved files and the original objective.
        """
        model = DecisionModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            session_id, goals = created.session.session_id, app.sessions.goals
            await goals.create(session_id, definition(max_requests=3))
            await asyncio.wait_for(goals.driver(session_id).task, 4)
            view = (await goals.list(session_id))[0]
            assert view.status == "waiting" and view.question.question_id == model.question_id
            for action, fields, code in (
                ("resume", {}, "GOAL_NEEDS_ANSWER"),
                (
                    "answer",
                    {"question_id": str(uuid4()), "answer": "yes"},
                    "GOAL_QUESTION_MISMATCH",
                ),
            ):
                with pytest.raises(AgentError) as failure:
                    await control(goals, session_id, action, **fields)
                assert failure.value.code == code
            await app.sessions.start(session_id, str(uuid4()), "A casual question", None, "normal")
            await app.sessions.active_for(session_id).task
            assert (await goals.list(session_id))[0].status == "waiting"
            await control(
                goals, session_id, "answer", question_id=model.question_id, answer="Confirmed file"
            )
            await asyncio.wait_for(goals.driver(session_id).task, 4)
            assert (await goals.list(session_id))[0].status == "failed"
            modified = (tmp_path / "project" / "saved.txt").stat().st_mtime_ns
            await app.sessions.start(
                session_id, str(uuid4()), "Another casual question", None, "normal"
            )
            await app.sessions.active_for(session_id).task
            assert (await goals.list(session_id))[0].status == "failed"
            assert model.calls == 5
            await control(goals, session_id, "resume")
            await asyncio.wait_for(goals.driver(session_id).task, 4)
            view = (await goals.list(session_id))[0]
            assert view.status == "budget_exceeded" and view.code == "BUDGET_GOAL_REQUESTS"
            assert model.calls == 5 and view.usage.requests == 3
            await control(goals, session_id, "budget", budget=GoalBudget(max_requests=5))
            assert model.calls == 5 and goals.driver(session_id) is None
            await control(goals, session_id, "resume")
            await asyncio.wait_for(goals.driver(session_id).task, 4)
            view = (await goals.list(session_id))[0]
            assert view.status == "completed" and view.usage.requests == 5
            assert (tmp_path / "project" / "saved.txt").stat().st_mtime_ns == modified

    asyncio.run(scenario())


class WaitingModel:
    """在真实请求边界等待取消，检测超时及关闭不自动重试。

    Wait at the real request boundary to detect timeout and shutdown without automatic retries.
    """

    def __init__(self):
        """记录进入和清理事件。

        Track entry and cancellation cleanup.
        """
        self.entered = asyncio.Event()
        self.cleaned = asyncio.Event()
        self.calls = 0

    def check_available(self):
        """无需网络。

        Require no network.
        """

    async def complete(self, **kwargs):
        """等待控制器取消，始终发出清理确认。

        Wait for controller cancellation and always acknowledge cleanup.
        """
        self.calls += 1
        self.entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cleaned.set()


def test_independent_goals_and_run_cancel_by_owner(tmp_path):
    """同项目两个 Goal 与普通运行可并发，停止一方不影响其他方。

    Run two goals and a normal request in one project; stopping one leaves the others running.
    """

    async def scenario():
        """经公开入口检查归属、独立取消与退出后的不自动恢复。

        Check ownership, isolated cancellation and no automatic restart through public entry points.
        """
        first_model, second_model, third_model = WaitingModel(), WaitingModel(), WaitingModel()
        async with app_at(tmp_path / "data", first_model) as app:
            created = await create_session(app, tmp_path / "project")
            first = created.session.session_id
            params = {
                "project_id": created.task.project_id,
                "task_id": created.task.task_id,
                "model_id": "glm-5.3-flash",
            }
            second = (await app.dispatch("sessions.create", params)).session_id
            third = (await app.dispatch("sessions.create", params)).session_id
            goals = app.sessions.goals
            await goals.create(first, definition())
            await asyncio.wait_for(first_model.entered.wait(), 3)
            app.sessions.model_factory = lambda: second_model
            await goals.create(second, definition())
            second_driver = goals.driver(second)
            await asyncio.wait_for(second_model.entered.wait(), 3)
            app.sessions.model_factory = lambda: third_model
            started = await app.sessions.start(third, str(uuid4()), "Independent question", None)
            await asyncio.wait_for(third_model.entered.wait(), 3)
            active = await app.dispatch("runs.active", {})
            assert {item.session_id for item in active.sessions} == {first, second, third}
            assert len({item.run.run_id for item in active.sessions}) == 3
            assert all(item.run.status == "running" for item in active.sessions)
            page = await app.sessions.list(created.task.project_id, None, 20)
            assert set(page.active_session_ids) == {first, second, third}
            for identity in (first, second, third):
                view = await app.sessions.view(identity)
                assert view.summary.run.requests == 1 and view.summary.run.status == "running"
            with pytest.raises(AgentError, match="此会话已有运行"):
                await app.sessions.start(third, str(uuid4()), "Duplicate concurrent request", None)
            second_run = next(
                item.run.run_id for item in active.sessions if item.session_id == second
            )
            await app.dispatch("runs.cancel", {"run_id": second_run})
            await asyncio.wait_for(second_driver.task, 3)
            assert second_model.cleaned.is_set()
            assert not first_model.cleaned.is_set() and not third_model.cleaned.is_set()
            assert (await goals.list(second))[0].status == "paused"
            assert (await goals.list(first))[0].status == "active"
            remaining = await app.dispatch("runs.active", {})
            assert {item.session_id for item in remaining.sessions} == {first, third}
            assert (await app.sessions.view(third)).summary.run.run_id == started.run.run_id
        assert first_model.cleaned.is_set() and third_model.cleaned.is_set()
        assert first_model.calls == second_model.calls == third_model.calls == 1
        async with app_at(tmp_path / "data", WaitingModel()) as restored:
            assert (await restored.dispatch("runs.active", {})).sessions == []
            assert (await restored.sessions.goals.list(first))[0].status == "interrupted"
            assert (await restored.sessions.goals.list(second))[0].status == "paused"
            assert (await restored.sessions.view(third)).summary.run.status == "interrupted"

    asyncio.run(scenario())


def test_goal_live_time_budget_shutdown_and_restart(tmp_path):
    """实时收紧累计时限生效，退出清理后重启只恢复记录。

    Apply a tighter live cumulative deadline; after shutdown, restart restores records only.
    """

    async def scenario():
        """检查真实单调计时与重启状态，不用离线墙钟推算。

        Check real monotonic time and restarted state without deriving runtime from offline clocks.
        """
        first = WaitingModel()
        async with app_at(tmp_path / "data", first) as app:
            created = await create_session(app, tmp_path / "project")
            session_id, goals = created.session.session_id, app.sessions.goals
            await goals.create(session_id, definition())
            driver = goals.driver(session_id)
            await asyncio.wait_for(first.entered.wait(), 3)
            await control(goals, session_id, "budget", budget=GoalBudget(max_active_seconds=0.1))
            await asyncio.wait_for(driver.task, 3)
            view = (await goals.list(session_id))[0]
            assert view.status == "budget_exceeded" and view.code == "BUDGET_GOAL_TIME"
            assert view.usage.requests == 1 and view.usage.reserved_seconds == 0
            assert 0 < view.usage.active_seconds < 2 and first.cleaned.is_set()
            await control(goals, session_id, "cancel")
            second = WaitingModel()
            app.sessions.model_factory = lambda: second
            await goals.create(session_id, definition(max_active_seconds=20))
            await asyncio.wait_for(second.entered.wait(), 3)
            accepted = next(
                fact.data
                for fact in reversed(app.sessions.active_for(session_id).log.facts)
                if isinstance(fact.data, RunAccepted)
            )
            assert accepted.active_time_limit_seconds <= 20
        assert second.cleaned.is_set()
        observation = WaitingModel()
        async with app_at(tmp_path / "data", observation) as app:
            goal = (await app.sessions.goals.list(session_id))[-1]
            assert goal.status == "interrupted" and goal.usage.requests == 1
            assert goal.usage.reserved_seconds == 0
            assert not app.sessions.active_runs and observation.calls == 0
            assert app.sessions.store.load(session_id).issue is None
            await app.sessions.start(session_id, str(uuid4()), "A new explicit question", None)
            await asyncio.wait_for(observation.entered.wait(), 3)
            assert observation.calls == 1
            assert app.sessions.store.load(session_id).issue is None

    asyncio.run(scenario())
