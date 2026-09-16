"""运行时输出契约，不导入 CLI / RPC 或具体存储。

Runtime output contracts independent of adapters.
"""

from typing import Protocol

from my_agent.models.types import ModelProgress
from my_agent.sessions.types import FactData


class RunSink(Protocol):
    """关键事实与瞬时文本分开提交。 Submit critical facts separately from transient text."""

    async def commit(self, data: FactData) -> None:
        """保存完整事实，失败必须向运行时传播。 Persist a complete fact and propagate failure."""
        ...

    async def text(self, message_id: str, delta: str) -> None:
        """发布带消息身份的瞬时文本。 Publish transient text associated with its message."""
        ...

    async def progress(self, message_id: str, progress: ModelProgress) -> None:
        """发布实际请求阶段，不包含原生模型内容。 Publish actual phases without native content."""
        ...
