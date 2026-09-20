"""通过生产模型客户端独立测试每个模型。 Test each model through the production client."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from math import ceil
from time import monotonic
from uuid import uuid4

from my_agent.errors import AgentError
from my_agent.models.connections import (
    ModelConnectionProbeParams,
    ModelConnectionResult,
    ModelConnectionState,
)
from my_agent.models.types import ModelClient, ModelId, ModelProgress, TokenUsage
from my_agent.runtime.settings import RunLimits


class ModelConnectionTests:
    """在当前后端内存保存各模型的独立结果，不创建项目或会话。

    Keep independent model test results in backend memory without projects or sessions.
    """

    def __init__(self, models: Sequence[ModelId]) -> None:
        """仅建立未测试状态，不联网。 Create untested state without networking."""
        self._states = {
            model: ModelConnectionState(
                model_id=model, testing=False, progress=None, last_test=None
            )
            for model in models
        }
        self._progress_at: dict[ModelId, float] = {}

    def snapshot(self) -> list[ModelConnectionState]:
        """返回独立快照，只推进等待时钟，切换诊断页不重置收包间隔。

        Copy state and advance only the waiting clock so reopening diagnostics preserves data gaps.
        """
        states = [state.model_copy(deep=True) for state in self._states.values()]
        for state in states:
            observed_at = self._progress_at.get(state.model_id)
            progress = state.progress
            if (
                state.testing
                and progress is not None
                and progress.phase != "completed"
                and observed_at is not None
            ):
                state.progress = progress.model_copy(
                    update={"elapsed_ms": progress.elapsed_ms + (monotonic() - observed_at) * 1000}
                )
        return states

    async def test(
        self, params: ModelConnectionProbeParams, client: ModelClient, limits: RunLimits
    ) -> None:
        """只对选定模型发一次短请求，保留实际首字阶段并禁止自动重试。

        Make one short request for the selected model, preserving timings without retries.
        """
        state = self._states[params.model_id]
        if state.testing:
            raise AgentError("MODEL_PROBE_BUSY", "该模型已有测试正在运行，请等待结果。")
        state.testing = True
        state.progress = ModelProgress(phase="preparing", elapsed_ms=0)
        self._progress_at[params.model_id] = monotonic()
        code, message, remediation = "MODEL_TEST_FAILED", "模型测试未完成。", "请显式重试。"
        usage: TokenUsage | None = None

        async def observe(progress: ModelProgress) -> None:
            """按目标模型记录时序，不借用全局最近请求。 Track this model's own timing only."""
            state.progress = progress
            self._progress_at[params.model_id] = monotonic()

        async def discard_text(_delta: str) -> None:
            """只计时，不保存或公开测试回答。 Discard test text; timings are tracked separately."""

        try:
            # 外层保留小数期限；内层整数预算向上取整，避免提前截断用户等待时间。
            # Keep the exact outer deadline; round the integer inner budget up, never down.
            request_limits = limits.model_copy(
                update={"request_timeout_seconds": ceil(params.timeout_seconds)}
            )
            async with asyncio.timeout(params.timeout_seconds):
                turn = await client.complete(
                    model_id=params.model_id,
                    session_id=str(uuid4()),
                    messages=[{"role": "user", "content": "Reply with OK only."}],
                    tools=[],
                    limits=request_limits,
                    on_text=discard_text,
                    on_progress=observe,
                )
            usage = turn.usage
            if turn.tool_calls:
                raise AgentError("MODEL_PROTOCOL", "模型测试返回了未请求的工具调用，未执行。")
            code, message, remediation = "OK", "该模型已返回完整文本响应。", ""
        except TimeoutError:
            code, message, remediation = (
                "MODEL_REQUEST_TIMEOUT",
                f"模型测试达到设定的 {params.timeout_seconds:g} 秒总时限。",
                "结合最后收包间隔判断等待情况；最后输出阶段不能证明连接正常。未自动重试。",
            )
        except AgentError as exc:
            code, message, remediation = exc.code, exc.message, exc.remediation
        except asyncio.CancelledError:
            code, message, remediation = "CANCELLED", "模型测试已取消。", "需要时重新测试。"
            raise
        finally:
            state.testing = False
            self._progress_at.pop(params.model_id, None)
            state.last_test = ModelConnectionResult(
                finished_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                code=code,
                message=message,
                remediation=remediation,
                progress=state.progress,
                usage=usage,
            )
