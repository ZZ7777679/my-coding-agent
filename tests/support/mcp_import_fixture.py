"""导入验证的本地进程，仅检查合成变量，不回显值。

Local import fixture checks synthetic variables without echoing values.
"""

import os
from pathlib import Path

from mcp.server import MCPServer

server = MCPServer("Import fixture")


@server.tool()
def check_environment() -> dict[str, object]:
    """返回配置是否生效及工作目录。 Report configuration presence and working directory."""
    return {
        "configured": os.environ.get("MCP_IMPORT_TOKEN") == "isolated-local-token",
        "cwd": str(Path.cwd()),
    }


@server.resource("fixture://note")
def note() -> str:
    """提供固定的只读资源。 Provide a fixed read-only resource."""
    return "import-resource"


if __name__ == "__main__":
    server.run(transport="stdio")
