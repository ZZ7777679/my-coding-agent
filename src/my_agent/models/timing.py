"""按真实传输事件测量首字，绝不保存头或正文。 Time actual transport events without payloads."""

from time import perf_counter

from my_agent.models.types import ModelProgress, ProgressSink


class RequestTiming:
    """单次请求的可公开计时器；网络追踪只取事件名。 Per-request timing using trace names only."""

    def __init__(self, sink: ProgressSink | None) -> None:
        """从模型入口起算，不包含 UI / 存储。 Start at the model call, excluding UI/storage."""
        self.sink = sink
        self.started = perf_counter()
        self.progress = ModelProgress(phase="preparing", elapsed_ms=0.0)
        self.network_started: dict[str, float] = {}

    def milliseconds(self) -> float:
        """返回单调毫秒，避免系统时间调整影响。 Return monotonic elapsed milliseconds."""
        return round((perf_counter() - self.started) * 1000, 3)

    async def publish(self, phase: ModelProgress | None = None) -> None:
        """阶段变化和结束时通知，不逐 token 存储。 Publish phases without per-token writes."""
        if phase is not None:
            self.progress = phase
        self.progress = self.progress.model_copy(update={"elapsed_ms": self.milliseconds()})
        if self.sink is not None:
            await self.sink(self.progress)

    async def set_phase(self, phase: str) -> None:
        """校验自有阶段标识后发布。 Validate an application-owned phase before publishing."""
        await self.publish(
            ModelProgress.model_validate({**self.progress.model_dump(), "phase": phase})
        )

    async def trace(self, name: str, info: dict[str, object]) -> None:
        """忽略 trace 内容，避免泄露凭据；连接时间包含库内部 DNS。

        Ignore trace payloads; connect timing includes the library's DNS work.
        """
        for operation, phase, field in (
            ("connect_tcp", "connecting", "connect_ms"),
            ("start_tls", "tls", "tls_ms"),
        ):
            if name.endswith(f".{operation}.started"):
                self.network_started[operation] = perf_counter()
                await self.set_phase(phase)
            elif (
                name.endswith((f".{operation}.complete", f".{operation}.failed"))
                and operation in self.network_started
            ):
                elapsed = round((perf_counter() - self.network_started.pop(operation)) * 1000, 3)
                self.progress = self.progress.model_copy(update={field: elapsed})
        if name.endswith(".send_request_body.complete"):
            await self.set_phase("waiting")

    async def headers(self) -> None:
        """HTTP 响应头到达不等于正文到达。 Response headers do not count as answer text."""
        self.progress = self.progress.model_copy(
            update={"response_headers_ms": self.milliseconds()}
        )
        await self.set_phase("receiving")

    async def event(self, reasoning: bool) -> None:
        """记录首事件与思考阶段，不公开思考正文。 Record event/reasoning timing, never text."""
        first = self.progress.first_event_ms is None
        if first:
            self.progress = self.progress.model_copy(update={"first_event_ms": self.milliseconds()})
        if reasoning and self.progress.phase not in {"reasoning", "text"}:
            await self.set_phase("reasoning")
        elif first:
            await self.publish()

    async def text(self) -> None:
        """只对首个非空正文计时。 Time only the first nonempty answer delta."""
        if self.progress.first_text_ms is None:
            self.progress = self.progress.model_copy(update={"first_text_ms": self.milliseconds()})
            await self.set_phase("text")
