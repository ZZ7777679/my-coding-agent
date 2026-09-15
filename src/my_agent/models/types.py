"""供后续模型适配使用的内部草案，不属于当前公开 RPC。

Internal drafts for later model adapters, outside the current public RPC.
"""

from dataclasses import dataclass

from pydantic import JsonValue


@dataclass(frozen=True)
class ToolCall:
    """描述完整工具调用参数；该草案自身不提供执行授权。

    Describe complete tool-call arguments; this draft grants no execution permission.
    """

    tool_call_id: str
    name: str
    arguments: dict[str, JsonValue]


@dataclass(frozen=True)
class ToolResult:
    """按调用标识关联工具结果，区分业务失败与正常内容。

    Associate tool output with its call ID and distinguish errors from normal content.
    """

    tool_call_id: str
    content: str
    is_error: bool


@dataclass(frozen=True)
class ModelTurn:
    """描述一个模型回合的文本与工具调用，尚未接入执行循环。

    Describe turn text and tool calls; no execution loop is connected yet.
    """

    text: str
    tool_calls: tuple[ToolCall, ...]
