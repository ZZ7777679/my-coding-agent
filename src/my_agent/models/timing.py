"""按真实传输事件测量首字，绝不保存头或正文。 Time actual transport events without payloads."""

from time import perf_counter

from my_agent.models.types import ModelProgress, ProgressSink


class RequestTiming:
    """单次请求的可公开计时器；网络追踪只取事件名。 Per-request timing using trace names only."""

    def __init__(self, sink: ProgressSink | None) -> None:
        """从模型入口起算，包含流回调等待，不包含入口前的工作。

        Start at the model call, including awaited stream callbacks but excluding earlier work.
        """
        self.sink = sink
        self.started = perf_counter()
        self.progress = ModelProgress(phase="preparing", elapsed_ms=0.0, received_bytes=0)
        self.network_started: dict[str, float] = {}
        self.last_published_ms = 0.0

    def milliseconds(self) -> float:
        """返回单调毫秒，避免系统时间调整影响。 Return monotonic elapsed milliseconds."""
        return round((perf_counter() - self.started) * 1000, 3)

    async def publish(self, phase: ModelProgress | None = None) -> None:
        """阶段变化和结束时通知，不逐 token 存储。 Publish phases without per-token writes."""
        if phase is not None:
            self.progress = phase
        self.progress = self.progress.model_copy(update={"elapsed_ms": self.milliseconds()})
        self.last_published_ms = self.progress.elapsed_ms
        if self.sink is not None:
            await self.sink(self.progress)

    async def set_phase(self, phase: str) -> None:
        """仅在阶段改变时发布，连续片段的收包统计沿用节流。

        Publish phase changes only; consecutive deltas retain throttled byte updates.
        """
        if self.progress.phase == phase:
            return
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

    async def received(self, size: int) -> None:
        """记录真实收包而非推测模型在线；展示节流不影响超时或数据处理。

        Track actual data; display throttling never affects timeouts or processing.
        """
        now = self.milliseconds()
        self.progress = self.progress.model_copy(
            update={
                "last_data_ms": now,
                "received_bytes": (self.progress.received_bytes or 0) + size,
            }
        )
        # 每秒最多额外发布一次收包统计；不逐 token 写磁盘，也不发送网络心跳。
        # Publish byte counters at most once per second, without token writes or network heartbeats.
        if now - self.last_published_ms >= 1000:
            await self.publish()

    async def event(self, phase: str | None) -> None:
        """记录当前片段的阶段，不把历史思考内容误当作当前活动。

        Record the current delta's phase instead of treating old reasoning as present activity.
        """
        first = self.progress.first_event_ms is None
        if first:
            self.progress = self.progress.model_copy(update={"first_event_ms": self.milliseconds()})
        if phase is not None and phase != self.progress.phase:
            await self.set_phase(phase)
        elif first:
            await self.publish()

    async def text(self) -> None:
        """只对首个非空正文计时。 Time only the first nonempty answer delta."""
        if self.progress.first_text_ms is None:
            self.progress = self.progress.model_copy(update={"first_text_ms": self.milliseconds()})
            await self.set_phase("text")
