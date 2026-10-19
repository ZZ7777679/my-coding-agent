"""协作只替换模型，运行、工具、RPC 和存储均使用真实实现。

Collaboration checks replace only models, retaining real runtime, tools, RPC and storage.
"""

import asyncio
import json
from uuid import uuid4

import pytest

from my_agent.collaboration.types import CollaborationRequestParams
from my_agent.errors import AgentError
from my_agent.memory.types import MemorySettings
from my_agent.sessions.types import RunAccepted
from tests.python.test_goal_controller import (
    app_at,
    call,
    control,
    create_session,
    definition,
    turn,
)


class CollaborationModel:
    """按实际协作工具结果推进；可由场景控制接收方忙碌状态。

    Advance through actual collaboration results with a controllably busy recipient.
    """

    def __init__(self):
        """保存调用身份、公开工具输出及可控等待。 Keep identities, tool output and a test gate."""
        self.calls = []
        self.outputs = []
        self.busy = asyncio.Event()
        self.release = asyncio.Event()
        self.source = None
        self.target = None
        self.step = 0
        self.fail_target = False

    def check_available(self):
        """不访问凭据或网络。 Do not access credentials or networking."""

    async def complete(self, **kwargs):
        """来源会话用真实工具发送与等待，接收方返回带私有哨兵的完整回合。

        The source uses actual delivery/wait tools; the recipient returns a private native sentinel.
        """
        identity = kwargs["session_id"]
        self.calls.append(identity)
        messages = kwargs["messages"]
        prompt = next(item["content"] for item in reversed(messages) if item["role"] == "user")
        if identity == self.target and self.fail_target:
            raise AgentError("MODEL_NETWORK", "Simulated recipient connection failure")
        if prompt == "hold" or (
            identity == self.target and "Goal objective" in messages[0]["content"]
        ):
            self.busy.set()
            await kwargs["on_reasoning"]("Uncommitted peer reasoning")
            await self.release.wait()
        if identity == self.source and prompt == "delegate":
            if messages[-1]["role"] == "tool":
                self.outputs.append(json.loads(messages[-1]["content"]))
            self.step += 1
            if self.step == 1:
                return turn(call("list_collaborators"))
            if self.step == 2:
                assert self.outputs[-1]["links"][0]["target_session_id"] == self.target
                return turn(call("read_session", target_session_id=self.target))
            if self.step == 3:
                assert "private-native-sentinel" not in json.dumps(self.outputs[-1])
                return turn(
                    call(
                        "request_collaboration",
                        target_session_id=self.target,
                        objective="Confirm the startup command",
                    )
                )
            if self.step == 4:
                return turn(call("read_collaboration", request_id=self.outputs[-1]["request_id"]))
            assert self.outputs[-1]["status"] == "completed"
            return turn(text="Received the peer's actual result")
        result = turn(text="Use the selected Python to start a static server")
        result.native["reasoning_content"] = "private-native-sentinel"
        return result


async def pair(app, project):
    """用户路径创建同任务两个会话，不自动安排协作。

    Create two task sessions through user APIs without automatically linking them.
    """
    task = await create_session(app, project)
    peer = await app.dispatch(
        "sessions.create",
        {
            "project_id": task.task.project_id,
            "task_id": task.task.task_id,
            "model_id": "glm-5.3-flash",
            "operation_id": str(uuid4()),
            "role": "Research",
            "scope": "Confirm startup instructions",
        },
    )
    await app.sessions.memory.configure(peer.session_id, MemorySettings(automatic=False))
    return task.session.session_id, peer.session_id


async def connect(app, source, target):
    """用户提前约定只读角色协作。 Arrange a read-only collaboration as the user."""
    return await app.dispatch(
        "collaboration.connect",
        {
            "source_session_id": source,
            "target_session_id": target,
            "scope": "Implementation can ask Research for startup instructions",
            "mode": "plan",
        },
    )


async def finish(app, identity):
    """等待已知活动句柄，不把观察超时当作运行完成。

    Await a known live handle without treating observation timeout as completion.
    """
    active = app.sessions.active_for(identity)
    if active is not None:
        await asyncio.wait_for(asyncio.shield(active.task), 5)


def test_collaboration_tools_queue_and_public_result(tmp_path):
    """有约定才可互访；忙时排队，只发一次并返回精确结果，读取不泄露原生字段。

    Require grants, queue busy recipients, deliver once and return exact public results.
    """

    async def scenario():
        """从生产 RPC 到实际工具等待，验证双方身份与独立账本。

        Exercise real RPC and tool waiting with both identities and independent ledgers.
        """
        model = CollaborationModel()
        async with app_at(tmp_path / "data", model) as app:
            source, target = await pair(app, tmp_path / "project")
            model.source, model.target = source, target
            with pytest.raises(AgentError) as missing:
                await app.dispatch(
                    "collaboration.history",
                    {"source_session_id": source, "target_session_id": target},
                )
            assert missing.value.code == "COLLABORATION_NOT_LINKED"
            await connect(app, source, target)
            with pytest.raises(AgentError) as reversed_link:
                await app.dispatch(
                    "collaboration.history",
                    {"source_session_id": target, "target_session_id": source},
                )
            assert reversed_link.value.code == "COLLABORATION_NOT_LINKED"
            with pytest.raises(AgentError) as write_request:
                await app.dispatch(
                    "collaboration.request",
                    {
                        "source_session_id": source,
                        "target_session_id": target,
                        "operation_id": str(uuid4()),
                        "objective": "Write code",
                        "mode": "normal",
                    },
                )
            assert write_request.value.code == "COLLABORATION_MODE"
            assert not model.calls
            await app.sessions.start(target, str(uuid4()), "hold", None)
            await asyncio.wait_for(model.busy.wait(), 3)
            assert (await app.sessions.view(target)).stream_reasoning
            committed = await app.dispatch(
                "collaboration.history",
                {"source_session_id": source, "target_session_id": target},
            )
            assert not committed.stream_reasoning and not committed.stream_text
            assert committed.stream_model_id is None and committed.model_progress is None
            await app.sessions.start(source, str(uuid4()), "delegate", None)
            async with asyncio.timeout(5):
                while True:
                    page = await app.dispatch("collaboration.list", {"session_id": source})
                    if page.requests:
                        break
                    await asyncio.sleep(0.01)
            request = page.requests[0]
            assert request.status == "queued"
            assert request.target_run_id is None
            assert len([item for item in model.calls if item == target]) == 1
            model.release.set()
            await finish(app, source)
            result = await app.sessions.collaboration.result(source, request.request_id, wait=True)
            assert result.status == "completed"
            assert result.result_seq and result.target_run_id
            assert result.result == "Use the selected Python to start a static server"
            assert (await app.sessions.view(source)).summary.run.status == "completed"
            target_view = await app.sessions.view(target)
            assert any(entry.kind == "collaboration.request" for entry in target_view.entries)
            assert len([item for item in model.calls if item == target]) == 2
            count = len(model.calls)
            history = await app.dispatch(
                "collaboration.history", {"source_session_id": source, "target_session_id": target}
            )
            assert history.watermark > 0 and not history.stream_text
            assert "private-native-sentinel" not in history.model_dump_json()
            assert len(model.calls) == count
            log = await app.worker.call(app.sessions.store.load, target)
            assert (
                sum(
                    isinstance(f.data, RunAccepted)
                    and f.data.collaboration_id == request.request_id
                    for f in log.facts
                )
                == 1
            )
            assert not list((tmp_path / "project").iterdir())
            model.step = 0
            model.outputs.clear()
            model.fail_target = True
            await app.sessions.start(source, str(uuid4()), "delegate", None)
            await finish(app, source)
            failed = (await app.sessions.view(source)).summary.run
            assert failed.status == "failed" and failed.code == "TOOL_FAILED"
            failed_request = next(
                item
                for item in (
                    await app.dispatch("collaboration.list", {"session_id": source})
                ).requests
                if item.status == "failed"
            )
            assert failed_request.target_run_id != result.target_run_id
            assert (
                model.step == 4
            )  # 没有再向模型发送失败后的自动修复请求。 No automatic repair request.

    asyncio.run(scenario())


def test_user_handoff_and_readonly_review(tmp_path):
    """用户安排真正读取基线 / 编辑，暂停来源 Goal 而不影响无关会话；Review 拒绝写入。

    User arrangements read baselines/edit, pause only the source goal and enforce read-only review.
    """

    async def scenario():
        """复用实际协作调度、文件工具和 Goal 生命周期。

        Exercise actual collaboration dispatch, file tools and goal lifecycle.
        """
        source_busy, other_busy = asyncio.Event(), asyncio.Event()
        source, target, other = "", "", ""
        hold_source = False
        review_write = False
        stages = {"handoff": 0, "review": 0}

        class ArrangementModel:
            """根据本次明确安排调用工具，不伪造文件结果。

            Call tools for the current arrangement without inventing file results.
            """

            def check_available(self):
                """无网络与凭据依赖。 No network or credential dependency."""

            async def complete(self, **kwargs):
                """来源可等待，接收方按真实工具结果选择下一步。

                Hold source work and advance recipients from actual tool output.
                """
                identity = kwargs["session_id"]
                messages = kwargs["messages"]
                previous = (
                    json.loads(messages[-1]["content"]) if messages[-1]["role"] == "tool" else None
                )
                if identity == other:
                    other_busy.set()
                    await asyncio.Event().wait()
                if identity == source:
                    if hold_source:
                        source_busy.set()
                        await asyncio.Event().wait()
                    return (
                        turn(text="Saved source artifact")
                        if previous
                        else turn(
                            call("create_file", path="index.html", content="<h1>Counter</h1>\n")
                        )
                    )
                prompt = next(
                    item["content"] for item in reversed(messages) if item["role"] == "user"
                )
                kind = "review" if prompt.startswith("User-arranged review") else "handoff"
                assert identity == target and prompt.startswith("User-arranged ")
                if kind == "review":
                    names = {item["function"]["name"] for item in kwargs["tools"]}
                    assert "edit_file" not in names and "run_command" not in names
                    assert "代码审查" in messages[0]["content"]
                    if review_write:
                        return turn(
                            call("create_file", path="forbidden.txt", content="not allowed")
                        )
                else:
                    assert "工作交接 / Handoff" in messages[0]["content"]
                    assert "User notes: Preserve all other work" in prompt
                stages[kind] += 1
                step = stages[kind]
                if step == 1:
                    return turn(call("list_changes", session_id=source))
                if step == 2:
                    assert previous["changes"][0]["path"] == "index.html"
                    assert "before_sha256" not in previous["changes"][0]
                    assert "after_sha256" not in previous["changes"][0]
                    return turn(
                        call(
                            "read_change",
                            session_id=source,
                            change_id=previous["changes"][0]["change_id"],
                        )
                    )
                if step == 3:
                    assert "+<h1>Counter</h1>" in previous["diff"]
                    assert "before_sha256" not in previous["summary"]
                    assert "after_sha256" not in previous["summary"]
                    if kind == "review":
                        return turn(
                            text="index.html:1: no actionable findings; runtime not checked"
                        )
                    return turn(call("read_file", path="index.html"))
                if step == 4:
                    return turn(
                        call(
                            "edit_file",
                            path="index.html",
                            old_text="Counter",
                            new_text="My Counter",
                        )
                    )
                return turn(text="Title changed; other work retained")

        async with app_at(tmp_path / "data", ArrangementModel()) as app:
            source, target = await pair(app, tmp_path / "project")
            source_view = (await app.sessions.view(source)).summary
            unrelated = await app.dispatch(
                "sessions.create",
                {
                    "project_id": source_view.project_id,
                    "task_id": source_view.task_id,
                    "model_id": "glm-5.3-flash",
                    "operation_id": str(uuid4()),
                },
            )
            other = unrelated.session_id
            await app.sessions.start(source, str(uuid4()), "seed", None, "normal")
            await finish(app, source)
            hold_source = True
            goal = await app.sessions.goals.create(source, definition())
            await asyncio.wait_for(source_busy.wait(), 3)
            await app.sessions.start(other, str(uuid4()), "other work", None)
            await asyncio.wait_for(other_busy.wait(), 3)
            unrelated_run = app.sessions.active_for(other).run_id
            review_params = {
                "operation_id": str(uuid4()),
                "source_session_id": source,
                "target_session_id": target,
                "kind": "review",
                "objective": "Review index.html only",
            }
            review = await app.dispatch("collaboration.arrange", review_params)
            review_result = await asyncio.wait_for(
                app.sessions.collaboration.result(source, review.request_id, wait=True), 8
            )
            assert review_result.status == "completed", review_result.reason
            assert review_result.brief.task.task_id == source_view.task_id
            assert review_result.brief.source_goal.status == "active"
            assert app.sessions.active_for(source) is not None
            assert app.sessions.active_for(other).run_id == unrelated_run
            assert (tmp_path / "project" / "index.html").read_text() == "<h1>Counter</h1>\n"
            handoff_params = {
                "operation_id": str(uuid4()),
                "source_session_id": source,
                "target_session_id": target,
                "kind": "handoff",
                "objective": "Only change the title",
                "notes": "Preserve all other work",
                "transfer_goal_id": goal.goal_id,
            }
            handoff = await app.dispatch("collaboration.arrange", handoff_params)
            result = await asyncio.wait_for(
                app.sessions.collaboration.result(source, handoff.request_id, wait=True), 8
            )
            assert result.status == "completed", result.reason
            assert result.brief.source_goal.status == "paused"
            assert result.brief.source_run.goal_id == goal.goal_id
            assert (await app.sessions.goals.list(source))[-1].status == "paused"
            assert app.sessions.active_for(source) is None
            assert app.sessions.active_for(other).run_id == unrelated_run
            assert (tmp_path / "project" / "index.html").read_text() == "<h1>My Counter</h1>\n"
            repeated = await app.dispatch("collaboration.arrange", handoff_params)
            assert repeated.target_run_id == result.target_run_id
            target_run = (await app.sessions.view(target)).summary.run
            assert target_run.mode == "normal" and target_run.method == "handoff"
            review_write = True
            rejected = await app.dispatch(
                "collaboration.arrange", {**review_params, "operation_id": str(uuid4())}
            )
            rejected = await asyncio.wait_for(
                app.sessions.collaboration.result(source, rejected.request_id, wait=True), 8
            )
            assert rejected.status == "failed"
            assert not (tmp_path / "project" / "forbidden.txt").exists()
            assert app.sessions.active_for(other).run_id == unrelated_run
            review_write = False
            stages["review"] = 0
            retry = await app.dispatch(
                "collaboration.arrange", {**review_params, "operation_id": str(uuid4())}
            )
            retry = await asyncio.wait_for(
                app.sessions.collaboration.result(source, retry.request_id, wait=True), 8
            )
            assert retry.status == "completed", retry.reason
            assert retry.target_run_id != rejected.target_run_id
            assert app.sessions.active_for(other).run_id == unrelated_run
            await app.sessions.cancel(unrelated_run)
            await finish(app, other)

    asyncio.run(scenario())


def test_paused_goal_and_restart_do_not_dispatch(tmp_path):
    """协作不会恢复暂停 Goal；队列重启后暂存，用户仍可精确取消。

    Collaboration never resumes paused goals; restart holds queued work for explicit control.
    """

    async def scenario():
        """保留真实 Goal 状态和请求身份，重启不产生模型请求。

        Preserve goal/request identities and make no model request on restart.
        """
        model = CollaborationModel()
        async with app_at(tmp_path / "data", model) as app:
            source, target = await pair(app, tmp_path / "project")
            model.target = target
            await connect(app, source, target)
            # 在首模型请求中等待，再通过已有用户控制暂停。
            # Wait in the first model request, then pause through the existing user control.
            original = model.complete

            async def waiting(**kwargs):
                """仅本次 Goal 等待，避免依赖提示词格式。

                Hold this goal without prompt-format coupling.
                """
                model.calls.append(kwargs["session_id"])
                model.busy.set()
                await asyncio.Event().wait()

            model.complete = waiting
            goal = await app.sessions.goals.create(target, definition())
            await asyncio.wait_for(model.busy.wait(), 3)
            await control(app.sessions.goals, target, "pause")
            model.complete = original
            params = {
                "operation_id": str(uuid4()),
                "source_session_id": source,
                "target_session_id": target,
                "objective": "Confirm startup instructions",
            }
            request = await app.dispatch("collaboration.request", params)
            repeated = await app.dispatch("collaboration.request", params)
            assert repeated.request_id == request.request_id
            result = await app.sessions.collaboration.result(source, request.request_id, wait=True)
            assert result.status == "queued" and "paused" in result.reason
            assert (await app.sessions.goals.list(target))[-1].goal_id == goal.goal_id
            assert (await app.sessions.goals.list(target))[-1].status == "paused"
            assert len(model.calls) == 1
        model.calls.clear()
        async with app_at(tmp_path / "data", model) as app:
            page = await app.dispatch("collaboration.list", {"session_id": target})
            assert page.requests[0].status == "held"
            assert page.requests[0].request_id == request.request_id
            assert not model.calls and not app.sessions.active_runs
            cancelled = await app.dispatch(
                "collaboration.control", {"request_id": request.request_id, "action": "cancel"}
            )
            assert cancelled.status == "cancelled"
            assert (await app.sessions.goals.list(target))[-1].status == "paused"

    asyncio.run(scenario())


def test_bidirectional_delivery_only_breaks_actual_wait_cycle(tmp_path):
    """允许双方投递；只解除实际互等，不撤销请求，取消等待后清理内存边。

    Allow bidirectional delivery; break live wait cycles without dropping requests or leaking waits.
    """

    async def scenario():
        """通过真实运行与请求存储检查往返投递。 Check round-trip delivery over real runs/storage."""
        model = CollaborationModel()
        async with app_at(tmp_path / "data", model) as app:
            source, target = await pair(app, tmp_path / "project")
            await connect(app, source, target)
            await connect(app, target, source)
            for identity in (source, target):
                await app.sessions.start(identity, str(uuid4()), "hold", None)
            service = app.sessions.collaboration
            runs = {
                identity: app.sessions.active_for(identity).run_id for identity in (source, target)
            }
            outbound = await service.submit(
                CollaborationRequestParams(
                    operation_id=str(uuid4()),
                    source_session_id=source,
                    target_session_id=target,
                    objective="Ask research",
                ),
                source_run_id=runs[source],
            )
            inbound = await service.submit(
                CollaborationRequestParams(
                    operation_id=str(uuid4()),
                    source_session_id=target,
                    target_session_id=source,
                    objective="Ask implementation for details",
                ),
                source_run_id=runs[target],
                parent_request_id=outbound.request_id,
            )
            assert outbound.status == inbound.status == "queued"
            pending = asyncio.create_task(
                service.result(
                    source,
                    outbound.request_id,
                    wait=True,
                    waiting_run_id=runs[source],
                )
            )
            async with asyncio.timeout(3):
                while not service.waiting:
                    await asyncio.sleep(0.01)
            blocked = await asyncio.wait_for(
                service.result(
                    target,
                    inbound.request_id,
                    wait=True,
                    waiting_run_id=runs[target],
                ),
                3,
            )
            assert blocked.status == "queued" and blocked.reason
            assert not pending.done()
            assert (
                await service.result(target, inbound.request_id, wait=False)
            ).reason != blocked.reason
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            assert not service.waiting

    asyncio.run(scenario())


def test_goal_question_yields_collaboration_wait_and_resumes(tmp_path):
    """协作等待期间先回答插话，再继续原 Goal；不会取消接收方工作。

    Answer an interruption during a collaboration wait, then resume the Goal without stopping peers.
    """

    async def scenario():
        """真实控制器与工具只替换模型，接收方在受控事件上等待。

        Replace only models; real controllers/tools wait for a controlled peer event.
        """
        source, target = "", ""
        question_answered, release = asyncio.Event(), asyncio.Event()
        request_id = None

        class QuestionModel:
            """只用公开工具结果接续协作。 Resume collaboration using public tool results only."""

            def check_available(self):
                """不使用真实模型。 Use no live model."""

            async def complete(self, **kwargs):
                """接收方等待，来源回答插话后复用原请求。

                Hold the peer and reuse the original request after answering an interruption.
                """
                nonlocal request_id
                if kwargs["session_id"] == target:
                    await release.wait()
                    return turn(text="Peer work finished")
                if "ordinary question interrupting" in kwargs["messages"][0]["content"]:
                    question_answered.set()
                    return turn(text="The peer is still working; the original goal will continue.")
                previous = kwargs["messages"][-1]
                data = json.loads(previous["content"]) if previous["role"] == "tool" else {}
                if data.get("request_id"):
                    request_id = data["request_id"]
                if data.get("status") == "completed":
                    return turn(
                        call("report_work", summary="Peer work received", outcome="complete")
                    )
                if request_id:
                    return turn(call("read_collaboration", request_id=request_id))
                return turn(
                    call("request_collaboration", target_session_id=target, objective="Check")
                )

        async with app_at(tmp_path / "data", QuestionModel()) as app:
            source, target = await pair(app, tmp_path / "project")
            await connect(app, source, target)
            goals, service = app.sessions.goals, app.sessions.collaboration
            await goals.create(source, definition())
            driver = goals.driver(source)
            async with asyncio.timeout(4):
                while not service.waiting:
                    await asyncio.sleep(0.01)
            await app.sessions.start(source, str(uuid4()), "What is happening?", None, "normal")
            await asyncio.wait_for(question_answered.wait(), 3)
            assert not release.is_set()
            assert (await goals.list(source))[-1].status == "active"
            assert app.sessions.active_for(target) is not None
            release.set()
            await asyncio.wait_for(driver.task, 5)
            assert (await goals.list(source))[-1].status == "completed"
            assert not service.waiting

    asyncio.run(scenario())


def test_long_collaboration_result_and_history_are_readable_in_pages(tmp_path):
    """长中文结果与单条历史可按游标完整还原，不因默认工具容量中止运行。

    Reconstruct long Unicode results and history entries without default output-budget failures.
    """

    async def scenario():
        """真实协作与模型工具分页，验证换行、引号和多字节字符均保留。

        Exercise actual collaboration/tool paging, preserving newlines, quotes and Unicode.
        """
        source, target = "", ""
        answer = '结果 "quoted" \\ path\n' * 3500
        pieces, history = [], []
        stage = "submit"
        request_id, result_seq = None, None

        class LongResultModel:
            """按返回游标读取，不绕过工具。 Read through tools using returned cursors."""

            def check_available(self):
                """完全离线。 Stay offline."""

            async def complete(self, **kwargs):
                """接收方返回长文，来源顺序读取正文、历史及列表。

                Return a long peer answer, then read result pages, history pages and discovery.
                """
                nonlocal stage, request_id, result_seq
                if kwargs["session_id"] == target:
                    return turn(text=answer)
                if stage == "submit":
                    stage = "read"
                    return turn(
                        call("request_collaboration", target_session_id=target, objective="Read")
                    )
                data = json.loads(kwargs["messages"][-1]["content"])
                assert "code" not in data
                if stage == "read":
                    request_id = data["request_id"]
                    stage = "result"
                    return turn(call("read_collaboration", request_id=request_id))
                if stage == "result":
                    pieces.append(data["result"])
                    result_seq = data["result_seq"]
                    if data["next_offset"] is not None:
                        return turn(
                            call(
                                "read_collaboration",
                                request_id=request_id,
                                offset=data["next_offset"],
                            )
                        )
                    stage = "history"
                    return turn(
                        call(
                            "read_session", target_session_id=target, before_seq=result_seq, limit=1
                        )
                    )
                if stage == "history":
                    history.append(data["entry_json"])
                    if data["next_offset"] is not None:
                        return turn(
                            call(
                                "read_session",
                                target_session_id=target,
                                entry_seq=data["entry_seq"],
                                offset=data["next_offset"],
                            )
                        )
                    stage = "list"
                    return turn(call("list_collaborators"))
                assert data["requests"][0]["status"] == "completed"
                assert "result" not in data["requests"][0]
                return turn(text="Read all pages")

        async with app_at(tmp_path / "data", LongResultModel()) as app:
            source, target = await pair(app, tmp_path / "project")
            await connect(app, source, target)
            await app.sessions.start(source, str(uuid4()), "Read the peer result", None)
            await finish(app, source)
            view = await app.sessions.view(source)
            assert view.summary.run.status == "completed", view.summary.run.message
            assert "".join(pieces) == answer
            assert json.loads("".join(history))["text"] == answer

    asyncio.run(scenario())
