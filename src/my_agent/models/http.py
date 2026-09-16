"""后端持有的 HTTP 连接池，不选择网络路径。 Backend-owned HTTP pooling without route selection."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from my_agent import __version__
from my_agent.models.connections import ConnectionObservation, ConnectionStatus
from my_agent.models.types import ModelId, ModelProgress


def public_request_headers(session_id: str) -> dict[str, str]:
    """统一模型与辅助请求的公开标识，不添加凭据。 Share request identity without credentials."""
    return {"User-Agent": f"my-coding-agent/{__version__}", "x-opencode-session": session_id}


@dataclass(eq=False)
class ClientLease:
    """记录客户端借用者，退役后等待活动响应完成。 Track borrowers and defer retirement."""

    client: httpx.AsyncClient
    active: int = 0
    retired: bool = False


class ModelHttpPool:
    """按需创建客户端并统一关闭；不保存会话头或凭据。

    Lazily own one client without storing session headers or credentials.
    """

    def __init__(
        self,
        *,
        reuse_enabled: bool,
        keepalive_expiry: float | None,
        drain_timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """注入技术清理参数与测试传输；环境继承沿用 HTTPX。

        Inject cleanup settings/test transport while preserving HTTPX environment handling.
        """
        self.keepalive_expiry = keepalive_expiry
        self.drain_timeout_seconds = drain_timeout_seconds
        self.transport = transport
        self.reuse_enabled = reuse_enabled
        self._current: ClientLease | None = None
        self._clients: set[ClientLease] = set()
        self._closed = False
        self.last_request: ConnectionObservation | None = None
        self.last_probe: ConnectionObservation | None = None

    def _create(self) -> ClientLease:
        """创建客户端并登记清理责任，不主动联网。 Create a tracked client without networking."""
        if self._closed:
            raise RuntimeError("Model HTTP pool is closed")
        lease = ClientLease(
            httpx.AsyncClient(
                transport=self.transport,
                follow_redirects=False,
                limits=httpx.Limits(keepalive_expiry=self.keepalive_expiry),
            )
        )
        self._clients.add(lease)
        return lease

    def client(self) -> httpx.AsyncClient:
        """首次实际请求才建客户端，后续跨 run 复用。 Create on demand and reuse across runs."""
        if self._closed:
            raise RuntimeError("Model HTTP pool is closed")
        if not self.reuse_enabled:
            raise RuntimeError("Use borrow() when connection reuse is disabled")
        if self._current is None:
            self._current = self._create()
        return self._current.client

    @asynccontextmanager
    async def borrow(self) -> AsyncIterator[httpx.AsyncClient]:
        """借用到响应清理结束；关闭复用时每次创建并释放。 Borrow for one response lifecycle."""
        if self.reuse_enabled:
            self.client()
            assert self._current is not None  # client() 已建立 / created above
            lease = self._current
        else:
            lease = self._create()
            lease.retired = True
        lease.active += 1
        try:
            yield lease.client
        finally:
            lease.active -= 1
            if lease.retired and not lease.active:
                await self._dispose(lease)

    async def _dispose(self, lease: ClientLease) -> None:
        """关闭已无借用者的客户端并移除记录。 Close and remove an unused client."""
        await lease.client.aclose()
        self._clients.discard(lease)

    async def release(self) -> None:
        """释放现有池；活动请求完成后再关闭，新请求按需新建。

        Retire the current pool without interrupting active responses; new calls start fresh.
        """
        lease, self._current = self._current, None
        if lease is not None:
            lease.retired = True
            if not lease.active:
                await self._dispose(lease)

    async def set_reuse(self, enabled: bool) -> None:
        """立即更新后续请求策略，已有借用者正常退出。 Apply policy without cancelling borrowers."""
        if enabled != self.reuse_enabled:
            self.reuse_enabled = enabled
            await self.release()

    def status(self) -> ConnectionStatus:
        """只读内存快照，不创建客户端或探测网络。 Snapshot memory without creating connections."""
        return ConnectionStatus(
            reuse_enabled=self.reuse_enabled,
            client_created=self._current is not None,
            active_requests=sum(lease.active for lease in self._clients),
            pending_release=any(lease.retired and lease.active for lease in self._clients),
            last_request=self.last_request,
            last_probe=self.last_probe,
        )

    def record(
        self,
        progress: ModelProgress,
        code: str,
        *,
        probe: bool = False,
        http_status: int | None = None,
        models_confirmed: bool | None = None,
        model_id: ModelId | None = None,
    ) -> None:
        """只保留最近脱敏时序，不保存消息、头或异常原文。 Retain timing and stable codes only."""
        observation = ConnectionObservation(
            finished_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            code=code,
            http_status=http_status,
            models_confirmed=models_confirmed,
            progress=progress,
            model_id=model_id,
        )
        if probe:
            self.last_probe = observation
        else:
            self.last_request = observation

    async def close(self) -> None:
        """活动请求结束后释放连接池，重复关闭安全。 Close after active requests; safe to repeat."""
        self._closed = True
        self._current = None
        for lease in tuple(self._clients):
            await self._dispose(lease)
