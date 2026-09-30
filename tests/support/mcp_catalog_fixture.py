"""桌面目录验收使用本地 stdio MCP，不访问网络。

Local stdio MCP fixture for catalog UI checks, without network access.
"""

from typing import Annotated, Literal

from mcp.server import MCPServer
from pydantic import Field

server = MCPServer("Catalog fixture")


@server.tool(title="整理文本")
def format_note(
    text: Annotated[str, Field(description="要整理的文本。 Text to format.")],
    style: Literal["brief", "full"] = "brief",
) -> str:
    """按选择的样式整理文本。 Format text using the selected style."""
    return text if style == "full" else text.strip()


@server.tool(title="读取状态")
def read_status() -> str:
    """读取样本状态，无需参数。 Read fixture status without parameters."""
    return "ready"


if __name__ == "__main__":
    server.run(transport="stdio")
