"""短期本机 OAuth 回调，不记录请求地址或授权码。

Temporary loopback OAuth callback without logging URLs or authorization codes.
"""

import asyncio
import secrets
from contextlib import suppress
from urllib.parse import parse_qs, urlsplit

from mcp.shared.auth import AuthorizationCodeResult

from my_agent.errors import AgentError


class OAuthCallback:
    """一次授权持有一个 IPv4 loopback 监听器与结果。

    Own one IPv4 loopback listener and result for one authorization attempt.
    """

    def __init__(self) -> None:
        """只建立内存状态，start 后才占用端口。

        Allocate state; bind a port only on start."""
        self.server: asyncio.Server | None = None
        self.result: asyncio.Future[AuthorizationCodeResult] = (
            asyncio.get_running_loop().create_future()
        )
        self.state = ""
        self.uri = ""
        self.clients: set[asyncio.Task[None]] = set()

    async def start(self, port: int) -> str:
        """监听本机，固定端口冲突时如实失败。

        Bind loopback and report a configured port conflict without changing it."""
        try:
            self.server = await asyncio.start_server(self._accept, "127.0.0.1", port)
        except OSError as exc:
            raise AgentError(
                "MCP_OAUTH_CALLBACK", "无法监听 OAuth 回调端口；请关闭占用程序或调整回调端口。"
            ) from exc
        actual_port = self.server.sockets[0].getsockname()[1]
        self.uri = f"http://127.0.0.1:{actual_port}/oauth/callback"
        return self.uri

    def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """跟踪已接收连接，退出时不遗留等待请求。

        Track accepted connections so shutdown leaves no pending requests."""
        task = asyncio.create_task(self._respond(reader, writer))
        self.clients.add(task)
        task.add_done_callback(self.clients.discard)

    async def _respond(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """只接收 GET 回调；无效 state 不消耗正在等待的登录。

        Accept GET callbacks; an unrelated state does not consume the pending login.
        """
        try:
            async with asyncio.timeout(10):
                header = await reader.readuntil(b"\r\n\r\n")
            method, target, _ = header.split(b"\r\n", 1)[0].decode("ascii").split(" ", 2)
            url = urlsplit(target)
            params = parse_qs(url.query)
            status, text = 400, "无效的授权回调。请返回应用重新打开授权网页。"
            states = params.get("state", [])
            if method == "GET" and url.path == "/oauth/callback":
                valid = (
                    len(states) == 1
                    and self.state
                    and secrets.compare_digest(states[0], self.state)
                )
                if valid and not self.result.done():
                    if params.get("error"):
                        self.result.set_exception(
                            AgentError("MCP_OAUTH_DENIED", "服务商未批准此次授权；原有登录保留。")
                        )
                        status, text = 200, "此次授权未完成。可关闭此页，返回应用查看。"
                    elif len(params.get("code", [])) == 1:
                        self.result.set_result(
                            AuthorizationCodeResult(
                                code=params["code"][0],
                                state=states[0],
                                iss=params.get("iss", [None])[0],
                            )
                        )
                        status, text = 200, "授权回调已收到，正在换取令牌。请返回应用查看最终结果。"
            body = (
                '<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
                f"<title>My Coding Agent</title><h2>My Coding Agent</h2><p>{text}</p>"
            ).encode()
            writer.write(
                f"HTTP/1.1 {status} {'OK' if status == 200 else 'Bad Request'}\r\n"
                "Content-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\n"
                "Referrer-Policy: no-referrer\r\nConnection: close\r\n"
                f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                + body
            )
            await writer.drain()
        except (
            OSError,
            ValueError,
            UnicodeError,
            TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            # 非回调流量只关闭当前 HTTP 连接，不取消正常登录。
            # Malformed/non-callback traffic closes this connection, not the login attempt.
            return
        finally:
            writer.close()
            # 对端断开不改变授权结果，也不能吞掉宿主取消。
            # Peer disconnect does not alter auth results or swallow owner cancellation.
            with suppress(OSError):
                await writer.wait_closed()

    async def wait(self) -> AuthorizationCodeResult:
        """结果只交 SDK 换取令牌，不进入 RPC。

        Deliver the result to the SDK only, never RPC."""
        return await self.result

    async def close(self) -> None:
        """关闭监听和已接受连接并取走异常，避免后台遗留。

        Close listeners/clients and consume pending errors without background leaks."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        clients = list(self.clients)
        for task in clients:
            task.cancel()
        await asyncio.gather(*clients, return_exceptions=True)
        if not self.result.done():
            self.result.cancel()
        elif not self.result.cancelled():
            self.result.exception()
