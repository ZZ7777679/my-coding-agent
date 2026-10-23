"""运行中补充的真实持久化、工具边界和显式接续。

Durable mid-run input, actual tool boundaries and explicit continuation.
"""

import asyncio
from uuid import uuid4

import pytest

from my_agent.errors import AgentError
from my_agent.sessions.types import RunAccepted, RunInputApplied, RunInputQueued, ToolSkipped
from my_agent.tools.files import FileTools
from tests.python.test_goal_controller import app_at, call, create_session, turn


@pytest.mark.parametrize("during_tool", [False, True])
def test_append_during_model_or_tool_preserves_order_and_run(tmp_path, monkeypatch, during_tool):
    """边界前不运行旧计划的后续工具，补充按序且只消费一次。

    Reconsider unstarted tools and consume ordered supplements exactly once in the same run.
    """

    async def scenario():
        """使用真实文件工具与队列，模型只控制等待点。 Use real files and controlled model waits."""
        entered, release = asyncio.Event(), asyncio.Event()
        seen = []

        class Model:
            """记录实际模型材料。 Record actual assembled model inputs."""

            def check_available(self):
                """离线可用。 Available offline."""

            async def complete(self, **kwargs):
                """第一回合留出追加窗口。 Gate the first turn for supplements."""
                seen.append(kwargs["messages"][:])
                if len(seen) == 1:
                    if not during_tool:
                        entered.set()
                        await release.wait()
                    return turn(
                        call("create_file", path="first.txt", content="first"),
                        call("create_file", path="obsolete.txt", content="old plan"),
                    )
                if len(seen) == 2:
                    return turn(call("create_file", path="updated.txt", content="new plan"))
                return turn(text="Updated task completed")

        original = FileTools.execute

        async def gate(self, invocation):
            """已开始的工具先完成，不被追加要求取消。 Finish the in-flight tool before steering."""
            if during_tool and invocation.arguments.get("path") == "first.txt":
                entered.set()
                await release.wait()
            return await original(self, invocation)

        monkeypatch.setattr(FileTools, "execute", gate)
        async with app_at(tmp_path / "data", Model()) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            started = await app.sessions.start(
                sid, str(uuid4()), "Original task", None, mode="normal"
            )
            running = app.sessions.active_for(sid).task
            await asyncio.wait_for(entered.wait(), 5)
            operation = str(uuid4())
            for op, text in [
                (operation, "First correction"),
                (operation, "First correction"),
                (str(uuid4()), "Second constraint"),
            ]:
                result = await app.sessions.start(sid, op, text, None, mode="normal")
                assert result.run.run_id == started.run.run_id
            view = await app.sessions.view(sid)
            assert [e.text for e in view.entries if e.input_status == "queued"] == [
                "First correction",
                "Second constraint",
            ]
            release.set()
            await asyncio.wait_for(running, 10)
            view = await app.sessions.view(sid)
            assert view.summary.run.status == "completed", view.summary.run
            assert (tmp_path / "project/first.txt").exists() == during_tool
            assert not (tmp_path / "project/obsolete.txt").exists()
            assert (tmp_path / "project/updated.txt").read_text() == "new plan"
            users = [m["content"] for m in seen[1] if m["role"] == "user"]
            assert users[-2:] == ["First correction", "Second constraint"]
            log = await app.sessions._load(sid)
            assert log.context()[1] and not log.pending_inputs()
            assert sum(isinstance(f.data, RunAccepted) for f in log.facts) == 1
            assert sum(isinstance(f.data, RunInputQueued) for f in log.facts) == 2
            assert sum(isinstance(f.data, RunInputApplied) for f in log.facts) == 2
            assert any(isinstance(f.data, ToolSkipped) for f in log.facts)
            assert all(e.input_status == "in_context" for e in view.entries if e.input_status)

    asyncio.run(scenario())


def test_failure_keeps_supplement_until_explicit_restart(tmp_path):
    """真实失败不自动重试，重启后明确继续才处理未消费补充。

    Failure never retries automatically; explicit continuation consumes persisted supplements.
    """

    async def scenario():
        """重开同一隔离数据根，验证消息顺序和幂等。

        Reopen the data root and check order/idempotency.
        """
        entered, release = asyncio.Event(), asyncio.Event()
        seen = []

        class Model:
            """第一次失败，第二次观察材料。 Fail once and then inspect continuation inputs."""

            def check_available(self):
                """离线可用。 Available offline."""

            async def complete(self, **kwargs):
                """已收到补充后产生服务故障。 Fail after the supplement was durably queued."""
                seen.append(kwargs["messages"][:])
                if len(seen) == 1:
                    entered.set()
                    await release.wait()
                    raise AgentError("SERVICE_ERROR", "fixture unavailable")
                return turn(text="Resumed")

        model = Model()
        operation = str(uuid4())
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            await app.sessions.start(sid, str(uuid4()), "Original", None)
            running = app.sessions.active_for(sid).task
            await asyncio.wait_for(entered.wait(), 5)
            await app.sessions.start(sid, operation, "Pending correction", None)
            release.set()
            await asyncio.wait_for(running, 10)
            assert (await app.sessions.view(sid)).summary.run.status == "failed"
        async with app_at(tmp_path / "data", model) as app:
            await app.sessions.start(sid, operation, "Pending correction", None)
            assert app.sessions.active_for(sid) is None and len(seen) == 1
            await app.sessions.start(sid, str(uuid4()), "Continue with latest choice", None)
            await app.sessions.active_for(sid).task
            users = [m["content"] for m in seen[-1] if m["role"] == "user"]
            assert users[-2:] == ["Pending correction", "Continue with latest choice"]
            assert (await app.sessions.view(sid)).summary.can_continue

    asyncio.run(scenario())
