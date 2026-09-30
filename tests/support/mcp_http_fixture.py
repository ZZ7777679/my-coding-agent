"""桌面连接表单的本地 HTTP MCP 样本，仅接受合成令牌。

Local HTTP MCP fixture for desktop setup, accepting only a synthetic token.
"""

import socket

import uvicorn
from starlette.responses import PlainTextResponse

from tests.support.mcp_catalog_fixture import server


def main() -> None:
    """在系统分配的端口上服务，输出端口供桌面检查使用。

    Serve on an OS-assigned port and report it to the desktop check."""
    inner = server.streamable_http_app()

    async def endpoint(scope, receive, send):
        """不把令牌写入返回值或日志。

        Keep the synthetic token out of results and logs."""
        if scope["type"] == "http":
            if dict(scope["headers"]).get(b"authorization") != b"Bearer desktop-fixture-token":
                await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
                return
        await inner(scope, receive, send)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        print(listener.getsockname()[1], flush=True)
        runtime = uvicorn.Server(uvicorn.Config(endpoint, log_level="error"))
        runtime.run(sockets=[listener])


if __name__ == "__main__":
    main()
