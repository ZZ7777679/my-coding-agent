"""运行时输出契约，不导入 CLI / RPC 或具体存储。

Runtime output contracts independent of adapters.
"""

from typing import Protocol

from my_agent.models.types import ModelProgress
from my_agent.sessions.types import Fact, FactData


class RunSink(Protocol):
    """关键事实与瞬时文本分开提交。 Submit critical facts separately from transient text."""

    async def commit(self, data: FactData) -> Fact:
        """返回已保存事实及身份，失败向运行时传播。

        Return the durable fact and its identity, propagating persistence failure.
        """
        ...

    async def text(self, message_id: str, delta: str) -> None:
        """发布带消息身份的瞬时文本。 Publish transient text associated with its message."""
        ...

    async def reasoning(self, message_id: str, delta: str) -> None:
        """发布模型返回的可见思考文本，独立于正文。

        Publish visible reasoning separately from text.
        """
        ...

    async def progress(self, message_id: str, progress: ModelProgress) -> None:
        """发布实际请求阶段，不包含原生模型内容。 Publish actual phases without native content."""
        ...
