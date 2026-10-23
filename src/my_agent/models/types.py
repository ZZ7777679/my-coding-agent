"""模型边界与完整回合；原生续接数据只在 Python 内使用。

Model contracts and complete turns; native continuation stays inside Python.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, PrivateAttr

from my_agent.errors import AgentError
from my_agent.runtime.settings import ModelLimits

ModelId = Literal["glm-5.3-flash", "deepseek-v4.1-flash"]
# 辅助接口有独立别名；保留历史身份，但不扩大主对话可选模型。
# Auxiliary endpoints have their own alias; retain history without expanding chat choices.
AuxiliaryModelId = ModelId | Literal["deepseek-flash"]
type JsonObject = dict[str, JsonValue]
type TextSink = Callable[[str], Awaitable[None]]


class ModelData(BaseModel):
    """内部模型数据的严格基类。 Strict base for internal model data."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ToolCall(ModelData):
    """完整参数对象，仍需工具权限校验。 Complete arguments still requiring tool policy checks."""

    tool_call_id: Annotated[str, Field(min_length=1, max_length=128)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    arguments: JsonObject


class ToolResult(ModelData):
    """按调用标识关联可公开工具结果。 Associate public tool output with its call ID."""

    tool_call_id: str
    content: str
    is_error: bool
    # 仅在内存中将原异常传给诊断边界，不能进入 JSON 或模型上下文。
    # Carry the original exception to the diagnostic boundary in memory, never JSON or context.
    _exception: AgentError | None = PrivateAttr(default=None)


class TokenUsage(ModelData):
    """服务实际返回的用量；未知保留 null。 Reported usage; unknown remains null."""

    input_tokens: Annotated[int, Field(ge=0)] | None
    output_tokens: Annotated[int, Field(ge=0)] | None
    # 缓存命中是输入的子集，不重复加入请求 / Goal 输入账本；未返回时不填零。
    # Cache hits are an input subset, not extra budget tokens; absence remains unknown.
    cached_input_tokens: Annotated[int, Field(ge=0)] | None = None


class ModelProgress(ModelData):
    """请求阶段与单调时钟耗时，不包含网络原文。 Request phases and timings without raw payloads."""

    phase: Literal[
        "preparing",
        "connecting",
        "tls",
        "waiting",
        "receiving",
        "reasoning",
        "text",
        "tool_arguments",
        "completed",
    ]
    elapsed_ms: Annotated[float, Field(ge=0)]
    first_text_ms: Annotated[float, Field(ge=0)] | None = None
    first_event_ms: Annotated[float, Field(ge=0)] | None = None
    response_headers_ms: Annotated[float, Field(ge=0)] | None = None
    connect_ms: Annotated[float, Field(ge=0)] | None = None
    tls_ms: Annotated[float, Field(ge=0)] | None = None
    response_complete: bool | None = None
    last_data_ms: Annotated[float, Field(ge=0)] | None = None
    received_bytes: Annotated[int, Field(ge=0)] | None = None


type ProgressSink = Callable[[ModelProgress], Awaitable[None]]


class ModelTurn(ModelData):
    """只提交完整回合，并独立保留原生续接。 Commit complete turns with separate native history."""

    text: str
    reasoning: str = ""
    tool_calls: list[ToolCall]
    native: JsonObject
    usage: TokenUsage


class ModelClient(Protocol):
    """运行时需要的模型能力，不耦合 provider。 Provider-independent runtime model boundary."""

    def check_available(self) -> None:
        """检查本地前置条件，不发请求。 Check local prerequisites without a request."""
        ...

    async def complete(
        self,
        *,
        model_id: ModelId,
        session_id: str,
        messages: list[JsonObject],
        tools: list[JsonObject],
        limits: ModelLimits,
        on_text: TextSink,
        on_progress: ProgressSink | None = None,
        on_reasoning: TextSink | None = None,
    ) -> ModelTurn:
        """分别交付正文与可见思考，返回完整结果。 Stream text and visible reasoning separately."""
        ...
