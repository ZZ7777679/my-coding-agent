"""M8 恢复语义定向验证，模型替身配合真实会话、工具、持久化和 Trace。

Target M8 recovery using model fixtures with real sessions, tools, persistence and Trace.
"""

import asyncio
from uuid import uuid4

import pytest

from my_agent.config import DEFAULTS
from my_agent.errors import AgentError
from my_agent.models.failures import ModelResponseError
from my_agent.models.types import TokenUsage
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.trace import trace_items
from my_agent.sessions.types import RequestFailed, RunFinished, ToolStarted
from tests.python.test_delegation import WorkerModel, setup
from tests.python.test_goal_controller import app_at, call, turn


def test_retry_keeps_partial_evidence_and_never_replays_tools(tmp_path):
    """工具已保存后断流，显式重试只发模型请求，部分文字不注入接续消息。

    Retry only the model after a saved tool; partial prose stays out of continuation messages.
    """

    class RetryingModel(WorkerModel):
        """先创建文件、再断流、最后完成，记录每次真实适配调用。

        Create a file, fail the stream, then finish while recording every adapter call.
        """

        async def complete(self, **kwargs):
            """使用实际回调发送部分输出与明确的临时错误。

            Send partial output through real callbacks and a classified transient failure.
            """
            self.requests.append(kwargs)
            if len(self.requests) == 1:
                return turn(call("create_file", path="note.txt", content="saved"))
            if len(self.requests) == 2:
                await kwargs["on_text"]("Interrupted unique prose")
                await kwargs["on_reasoning"]("Interrupted visible reasoning")
                raise ModelResponseError(
                    "MODEL_STREAM_ERROR",
                    "Fixture stream disconnected",
                    TokenUsage(input_tokens=5, output_tokens=2),
                    None,
                    phase="response_stream",
                )
            assert "Interrupted unique prose" not in str(kwargs["messages"])
            return turn(text="Continued after transient fault")

    async def scenario():
        """只用隔离项目，核对使用量、配对、Trace 和重载。

        Verify usage, pairing, Trace and reload in an isolated project.
        """
        model = RetryingModel()
        root, data = tmp_path / "project", tmp_path / "data"
        async with app_at(data, model) as app:
            await setup(app, model, root)
            limits = RunLimits.model_validate(
                {**DEFAULTS["run"], "model_retry_attempts": 1, "model_retry_delay_seconds": 0.0}
            )
            await app.sessions.start(
                model.owner, str(uuid4()), "Create one file", limits, mode="normal"
            )
            active = app.sessions.active_for(model.owner)
            await asyncio.wait_for(asyncio.shield(active.task), 8)
            view = await app.sessions.view(model.owner)
            assert view.summary.run.status == "completed", view.summary
            assert view.summary.run.requests == 3 and view.summary.run.tools == 1
            log = await app.sessions._load(model.owner)
            assert sum(isinstance(f.data, ToolStarted) for f in log.facts) == 1
            failed = next(f.data for f in log.facts if isinstance(f.data, RequestFailed))
            assert failed.usage.input_tokens == 5
            assert failed.diagnostic_id
            diagnostic = app.sessions.diagnostics.read(failed.diagnostic_id)
            assert diagnostic.request_id == failed.message_id
            assert "Fixture stream disconnected" in diagnostic.causes[0].message
            assert failed.partial_text == "Interrupted unique prose"
            assert failed.partial_reasoning == "Interrupted visible reasoning"
            requests = [r for r in trace_items(log) if r.kind == "request.started"]
            assert [r.status for r in requests] == ["completed", "failed", "completed"]
            assert requests[1].usage == failed.usage
            assert requests[1].diagnostic_ids == [failed.diagnostic_id]
            assert log.context()[1]
            assert root.joinpath("note.txt").read_text() == "saved"
        async with app_at(data, model) as app:
            view = await app.sessions.view(model.owner)
            assert any(e.partial_text == "Interrupted unique prose" for e in view.entries)
            assert len(model.requests) == 3

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "code,attempts,limit,expected",
    [
        ("MODEL_CONNECT_ERROR", 0, None, "failed"),
        ("AUTHENTICATION_FAILED", 3, None, "failed"),
        ("QUOTA_EXCEEDED", 3, None, "failed"),
        ("HTTP_ERROR", 3, None, "failed"),
        ("MODEL_CONNECT_ERROR", 2, 1, "budget_exceeded"),
    ],
)
def test_retry_defaults_and_nonretryable_failures(tmp_path, code, attempts, limit, expected):
    """默认关闭，认证／余额／请求拒绝不重试，有限总预算约束重试。

    Default off, no auth/quota/input retry, and finite cumulative budgets still apply.
    """

    class FailingModel(WorkerModel):
        """每次请求明确返回同一故障。

        Return the same explicit failure on every request.
        """

        async def complete(self, **kwargs):
            """计数并返回公开错误，绝不触发工具。

            Count and raise a public error without executing tools.
            """
            self.requests.append(kwargs)
            raise AgentError(code, "Fixture failure", phase="connecting")

    async def scenario():
        """每个用例独立运行并检查没有隐藏的额外请求。

        Run isolated cases and check for hidden extra requests.
        """
        model = FailingModel()
        async with app_at(tmp_path / "data", model) as app:
            await setup(app, model, tmp_path / "project")
            limits = RunLimits.model_validate(
                {
                    **DEFAULTS["run"],
                    "model_retry_attempts": attempts,
                    "max_requests": limit,
                    "model_retry_delay_seconds": 0.0,
                }
            )
            await app.sessions.start(model.owner, str(uuid4()), "One request", limits)
            active = app.sessions.active_for(model.owner)
            await asyncio.wait_for(asyncio.shield(active.task), 5)
            run = (await app.sessions.view(model.owner)).summary.run
            assert run.status == expected, run
            assert run.remediation
            assert len(model.requests) == run.requests == 1
            assert not app.sessions.active_runs

    asyncio.run(scenario())


def test_cancel_during_retry_backoff_does_not_send_again(tmp_path):
    """重试退避期可立即停止，且保留失败尝试的部分文字。

    Cancel backoff promptly without another request, preserving partial failed-attempt text.
    """

    class WaitingModel(WorkerModel):
        """使用临时错误进入明确的等待阶段。

        Enter configured backoff through a transient error.
        """

        async def complete(self, **kwargs):
            """记录请求后中断可见流。

            Record the request then interrupt its visible stream.
            """
            self.requests.append(kwargs)
            await kwargs["on_text"]("Retained before backoff")
            raise AgentError("MODEL_STREAM_ERROR", "Fixture disconnect")

    async def scenario():
        """等待持久失败事实而非猜测延迟，再明确取消。

        Wait for the durable failure fact rather than guessing timing, then cancel explicitly.
        """
        model = WaitingModel()
        async with app_at(tmp_path / "data", model) as app:
            await setup(app, model, tmp_path / "project")
            limits = RunLimits.model_validate(
                {**DEFAULTS["run"], "model_retry_attempts": 2, "model_retry_delay_seconds": 20.0}
            )
            await app.sessions.start(model.owner, str(uuid4()), "Wait then cancel", limits)
            active = app.sessions.active_for(model.owner)
            async with asyncio.timeout(4):
                while not any(isinstance(f.data, RequestFailed) for f in active.log.facts):
                    await asyncio.sleep(0.01)
            await app.sessions.cancel(active.run_id)
            await asyncio.wait_for(asyncio.shield(active.task), 2)
            terminal = next(
                f.data for f in reversed(active.log.facts) if isinstance(f.data, RunFinished)
            )
            assert terminal.status == "cancelled"
            assert len(model.requests) == 1
            assert (await app.sessions.view(model.owner)).summary.run.effect_state == "not_executed"

    asyncio.run(scenario())
