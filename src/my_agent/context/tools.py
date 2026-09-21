"""模型按需回读当前会话材料。

Model-driven read-back of current-session material.
"""

import json
from typing import Annotated

from pydantic import Field, ValidationError

from my_agent.context.service import ContextService
from my_agent.context.types import HistoryParams, HistoryQuery
from my_agent.errors import AgentError
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor


class StatusQuery(ModelData):
    """按材料序号分页查看，不把长清单再次全部灌回模型。

    Page material metadata instead of reinjecting the whole list.
    """

    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 20


class ContextTools:
    """在既有工具链加入历史、状态与宿主压缩入口。

    Add history, status and host compaction to the existing tool chain.
    """

    def __init__(
        self, context: ToolContext, delegate: ToolExecutor, service: ContextService
    ) -> None:
        """固定宿主会话身份。

        Bind the host-supplied session identity.
        """
        self.context, self.delegate, self.service = context, delegate, service

    def definitions(self) -> list[JsonObject]:
        """提供搜索、统计和按原序号分段读取。

        Offer search, counts and fragments by original sequence.
        """
        result: list[JsonObject] = [
            *self.delegate.definitions(),
            {
                "type": "function",
                "function": {
                    "name": "read_history",
                    "description": (
                        "Search or read committed public history in THIS session. Use "
                        "query for a literal matching fragment, entry_seq and offset for a "
                        "large entry. after_seq/through_seq bound the source range. "
                        "For continuation, clear query and pass next_offset as offset with "
                        "the same entry_seq or artifact_id; offset=0 reads from the start. "
                        "Reports match_unit, true character offsets and call_seq/result_seq "
                        "links when available. Use artifact_id for "
                        "archived long tool outputs. Read material references from "
                        "compaction here; never re-execute historical tools. Keyword searches "
                        "exclude history/status lookup calls and results unless "
                        "include_lookup_results=true; explicit entry_seq always reads the source. "
                        "Use a focused query or entry instead of loading all history."
                    ),
                    "parameters": HistoryQuery.model_json_schema(),
                },
            },
        ]
        for name, description in {
            "get_context_status": "Read current compaction state and the actual latest request "
            "material references. Use returned next_offset as offset for more materials. "
            "form describes the sent material: full=full source, summary=summary, "
            "fragment=source excerpt. Display previews do not describe input truncation. "
            "Optional; never a prerequisite for normal work.",
            "compact_context": "Start or reuse compaction of this session using the same model "
            "and existing run budget. Original history remains readable. The host adopts the "
            "summary at a complete request boundary; do not poll repeatedly.",
        }.items():
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": (
                            StatusQuery if name == "get_context_status" else ModelData
                        ).model_json_schema(),
                    },
                }
            )
        return result

    def is_mutating(self, name: str) -> bool:
        """历史读取不执行旧工具。

        Reading history never executes old tools.
        """
        return (
            False
            if name in {"read_history", "get_context_status", "compact_context"}
            else self.delegate.is_mutating(name)
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """按当前单次工具容量缩页，保留真实续读位置。

        Bound a page while retaining exact continuation offsets.
        """
        if call.name not in {"read_history", "get_context_status", "compact_context"}:
            return await self.delegate.execute(call)
        try:
            if call.name != "read_history":
                if call.name == "compact_context":
                    ModelData.model_validate(call.arguments)
                    view = await self.service.start(
                        self.context.session_id, self.context.request_sink
                    )
                    content = json.dumps(
                        {
                            "job": view.job.model_dump(mode="json") if view.job else None,
                            "adoption": "Adopted at a complete request boundary; history retained.",
                        },
                        ensure_ascii=False,
                    )
                else:
                    query_status = StatusQuery.model_validate(call.arguments)
                    view = await self.service.view(self.context.session_id)
                    # 元信息只列来源，不把全部历史预览再次注入对话。
                    # Return source metadata rather than injecting every history preview again.
                    request = view.last_request
                    materials = request.manifest.materials if request else []
                    end = min(len(materials), query_status.offset + query_status.limit)
                    metadata = {
                        "tokens": view.tokens.model_dump(mode="json"),
                        "automatic_compaction": view.settings.automatic,
                        "trigger": {
                            "unit": "estimated_tokens",
                            "limit": view.trigger_tokens,
                            "estimated_input": view.estimated_input_tokens,
                            "estimated_history": view.estimated_history_tokens,
                            "basis": view.estimate_basis,
                        },
                        "policy": view.settings.model_dump(mode="json"),
                        "job": view.job.model_dump(mode="json") if view.job else None,
                        "last_request": request.model_dump(
                            mode="json", exclude={"manifest": {"materials"}}
                        )
                        if request
                        else None,
                        "total_materials": len(materials),
                        "material_forms": {
                            "full": "Full source content was sent.",
                            "summary": "The generated summary was sent, not the original history.",
                            "fragment": "An excerpt was sent; use its read reference for more.",
                        },
                    }
                    while True:
                        content = json.dumps(
                            {
                                **metadata,
                                "materials": [
                                    item.model_dump(
                                        mode="json", exclude={"preview", "preview_complete"}
                                    )
                                    for item in materials[query_status.offset : end]
                                ],
                                "next_offset": end if end < len(materials) else None,
                            },
                            ensure_ascii=False,
                        )
                        if (
                            len(content.encode("utf-8")) <= self.context.limits.max_tool_bytes
                            or end <= query_status.offset + 1
                        ):
                            break
                        end -= 1
                return ToolResult(tool_call_id=call.tool_call_id, content=content, is_error=False)
            query = HistoryQuery.model_validate(call.arguments)
            params = HistoryParams(session_id=self.context.session_id, **query.model_dump())
            log = await self.service.sessions._load(self.context.session_id)
            while True:
                page = await self.service.sessions.worker.call(
                    self.service.store.history, log, params
                )
                content = page.model_dump_json()
                if len(content.encode("utf-8")) <= self.context.limits.max_tool_bytes:
                    break
                params = params.model_copy(
                    update={"limit": 1, "max_chars": max(1, params.max_chars // 2)}
                )
                if params.max_chars == 1:
                    raise AgentError(
                        "INVALID_TOOL_ARGUMENTS", "单页元信息超出工具预算，请增加输出预算。"
                    )
            return ToolResult(tool_call_id=call.tool_call_id, content=content, is_error=False)
        except ValidationError:
            error = {"code": "INVALID_TOOL_ARGUMENTS", "message": "参数不符合上下文工具定义。"}
        except AgentError as exc:
            error = {"code": exc.code, "message": exc.message}
        return ToolResult(
            tool_call_id=call.tool_call_id,
            content=json.dumps(error, ensure_ascii=False),
            is_error=True,
        )
