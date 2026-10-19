"""运行上下文接口与持久版本引用。 Runtime context contract and durable revision reference."""

from dataclasses import dataclass

from pydantic import Field

from my_agent.models.types import JsonObject, ModelData


class ContextMaterial(ModelData):
    """实际采用的材料来源与有界预览，不复制原生对话。

    Adopted source references and bounded previews, never native conversation state.
    """

    kind: str
    title: str
    form: str
    reason: str
    source_id: str | None = None
    revision: int | None = None
    preview: str = ""
    preview_complete: bool = True
    read_tool: str | None = None
    read_arguments: JsonObject = Field(default_factory=dict)


class ContextManifest(ModelData):
    """请求边界保存实际材料与单独标注的 token 估计。

    Persist actual materials and separately labelled token estimates at the request boundary.
    """

    materials: list[ContextMaterial] = Field(default_factory=list)
    message_count: int
    request_bytes: int
    tool_names: list[str]
    estimated_input_tokens: int | None = None
    estimated_fixed_tokens: int | None = None


@dataclass(frozen=True)
class PreparedWindow:
    """最终消息与同一次组装的材料清单一起交给运行循环。

    Deliver final messages and their material manifest together to the loop.
    """

    messages: list[JsonObject]
    materials: list[ContextMaterial]
    estimated_input_tokens: int | None = None


def describe_material(
    *,
    kind: str,
    title: str,
    form: str,
    reason: str,
    text: str = "",
    source_id: str | None = None,
    revision: int | None = None,
    read_tool: str | None = None,
    read_arguments: JsonObject | None = None,
) -> ContextMaterial:
    """预览只影响展示；实际输入不截断、不增加执行门槛。

    Bound display previews only, without truncating input or adding execution gates.
    """
    preview_chars = 600
    return ContextMaterial(
        kind=kind,
        title=title,
        form=form,
        reason=reason,
        source_id=source_id,
        revision=revision,
        read_tool=read_tool,
        read_arguments=read_arguments or {},
        preview=text[:preview_chars],
        preview_complete=len(text) <= preview_chars,
    )


@dataclass(frozen=True)
class SharedContext:
    """请求采用的任务版本与文本，不含其他会话原生历史。

    Task context excluding other sessions' native history.
    """

    task_id: str
    revision: int
    text: str
    additional_text: str = ""
    additional_materials: tuple[ContextMaterial, ...] = ()
