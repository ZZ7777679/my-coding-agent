"""MCP 工具适配；发现和调用沿用主循环预算与事实。

MCP adaptation keeps discovery and calls in the main loop budget and fact stream.
"""

import json

# SDK 依赖暂无类型声明，只在此边界引用运行时 API。
# This SDK dependency is untyped; confine its runtime API to this boundary.
from jsonschema import SchemaError  # type: ignore[import-untyped]
from jsonschema.validators import validator_for  # type: ignore[import-untyped]
from pydantic import Field, ValidationError
from referencing import Registry
from referencing.exceptions import Unresolvable

from my_agent.errors import AgentError
from my_agent.mcp_client.service import McpService
from my_agent.mcp_client.types import McpParams
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor


def validate_arguments(schema: JsonObject, arguments: JsonObject) -> None:
    """发送前按服务 schema 验证；未派发参数错误可修正，不读取外部引用。

    Validate server schemas before dispatch; input errors are recoverable without remote refs.
    """
    try:
        validator_type = validator_for(schema)
        validator_type.check_schema(schema)
        # 空 registry 仅解析本 schema 内引用，不取网络或本机资源。
        # An empty registry resolves local schema references, never network/filesystem resources.
        registry: Registry[object] = Registry()
        valid = validator_type(schema, registry=registry).is_valid(arguments)
    except (SchemaError, Unresolvable) as exc:
        raise AgentError(
            "MCP_SCHEMA_INVALID", "工具参数定义无效或引用不可解析，请刷新服务目录。"
        ) from exc
    if not valid:
        raise AgentError(
            "INVALID_TOOL_ARGUMENTS", "请按已发现的 MCP 工具 schema 修正参数；尚未派发。"
        )


class DiscoverMcpArgs(ModelData):
    """搜索工具并选择下一请求需要的定义。 Discover and select next-request tool definitions."""

    server_id: str
    query: str = ""
    names: list[str] = Field(default_factory=list)


class McpResourceArgs(ModelData):
    """浏览或读取服务公开资源。 Browse or read public server resources."""

    server_id: str
    uri: str = ""
    cursor: str | None = None
    templates: bool = False


class McpTools:
    """动态定义沿既有 ToolExecutor 调度。 Dynamic definitions use the existing executor."""

    def __init__(self, context: ToolContext, delegate: ToolExecutor, service: McpService) -> None:
        """绑定本次项目与会话。 Bind the current project and session."""
        self.context, self.delegate, self.service = context, delegate, service
        self.params = McpParams(project_id=context.project_id, session_id=context.session_id)

    def is_mutating(self, name: str) -> bool:
        """服务注解用于模式提示，普通执行无需新增审批。

        Use server annotations for mode routing, without new approvals for normal execution.
        """
        if name in {"discover_mcp_tools", "mcp_resources"}:
            return False
        binding = self.service.selected.get(self.context.session_id, {}).get(name)
        if binding:
            annotation = binding[1].get("annotations")
            return not (isinstance(annotation, dict) and annotation.get("readOnlyHint") is True)
        return self.delegate.is_mutating(name)

    def definitions(self) -> list[JsonObject]:
        """初始仅提供发现入口，按需发布外部工具 schema。

        Start with discovery and publish selected external tool schemas on demand.
        """
        result = self.delegate.definitions()
        for name, model, description in (
            (
                "discover_mcp_tools",
                DiscoverMcpArgs,
                "Discover a server's tools. Empty query/names returns short catalog only; "
                "A query or exact names activates matching schemas on the next request. "
                "Use the returned callable names, never guess them.",
            ),
            (
                "mcp_resources",
                McpResourceArgs,
                "List MCP resources (or templates=true) with cursor; uri reads a listed resource.",
            ),
        ):
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": model.model_json_schema(),
                    },
                }
            )
        for name, (server, tool) in self.service.selected.get(self.context.session_id, {}).items():
            if self.context.mode == "plan" and self.is_mutating(name):
                continue
            if (
                self.context.read_roots is not None
                and self.service.transports.get(server) == "stdio"
            ):
                # 仍保留已选择身份；切回支持的模式后恢复，当前请求不诱导无效调用。
                # Retain selections for supported modes without advertising unusable calls.
                continue
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": f"{server}/{tool['name']}: {tool.get('description', '')}",
                        "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                    },
                }
            )
        return result

    async def execute(self, call: ToolCall) -> ToolResult:
        """解析来源，执行一次调用；不吞取消或重复副作用。

        Resolve origin and execute once, preserving cancellation and side-effect identity.
        """
        binding = self.service.selected.get(self.context.session_id, {}).get(call.name)
        if call.name not in {"discover_mcp_tools", "mcp_resources"} and binding is None:
            return await self.delegate.execute(call)
        try:
            if call.name == "discover_mcp_tools":
                args = DiscoverMcpArgs.model_validate(call.arguments)
                connection = await self.service.connect(self.params, args.server_id)
                await connection.call("tools/list", {})
                tools = connection.tools
                selected = [
                    tool
                    for tool in tools
                    if str(tool.get("name")) in args.names
                    or (
                        args.query
                        and args.query.casefold()
                        in (
                            str(tool.get("name")) + " " + str(tool.get("description", ""))
                        ).casefold()
                    )
                ]
                value: JsonObject = {
                    "server_id": args.server_id,
                    "catalog": [
                        {"name": t["name"], "description": t.get("description", "")} for t in tools
                    ],
                    "activated": [
                        entry
                        for entry in self.service.select_tools(
                            self.context.session_id, args.server_id, selected
                        )
                    ],
                }
            elif call.name == "mcp_resources":
                resource = McpResourceArgs.model_validate(call.arguments)
                connection = await self.service.connect(self.params, resource.server_id)
                method = (
                    "resources/read"
                    if resource.uri
                    else "resources/templates/list"
                    if resource.templates
                    else "resources/list"
                )
                value = await connection.call(
                    method, {"uri": resource.uri, "cursor": resource.cursor}
                )
            elif binding:
                if self.context.mode == "plan" and self.is_mutating(call.name):
                    raise AgentError(
                        "INVALID_TOOL_ARGUMENTS", "Plan 模式不执行改变状态的外部工具。"
                    )
                schema = binding[1].get("inputSchema", {"type": "object"})
                if not isinstance(schema, dict):
                    raise AgentError("MCP_SCHEMA_INVALID", "工具参数定义不是对象，请刷新服务目录。")
                validate_arguments(schema, call.arguments)
                connection = await self.service.connect(self.params, binding[0])
                value = await connection.call(
                    "tools/call", {"name": binding[1]["name"], "arguments": call.arguments}
                )
            else:
                raise AgentError("INVALID_TOOL_ARGUMENTS", "请先发现并选择工具。")
            value = await self.service.normalize(self.params, value)
            failed = value.get("isError") is True
            if failed:
                value = {
                    "code": "MCP_TOOL_FAILED",
                    "message": "外部工具返回失败。",
                    "result": value,
                }
            source: JsonObject = (
                {"server_id": binding[0], "tool_name": binding[1]["name"]} if binding else {}
            )
            if source:
                value["mcp_source"] = source
            text = json.dumps(value, ensure_ascii=False)
            if (
                len(text.encode("utf-8")) > self.context.limits.max_tool_bytes
                and self.context.archive_output
            ):
                identity = await self.context.archive_output(text)
                text = json.dumps(
                    {
                        "artifact_id": identity,
                        "preview": text[: self.context.limits.max_tool_bytes // 4],
                        "truncated": True,
                        "read_tool": "read_history",
                        "mcp_source": source,
                    },
                    ensure_ascii=False,
                )
            return ToolResult(tool_call_id=call.tool_call_id, content=text, is_error=failed)
        except ValidationError:
            error = {"code": "INVALID_TOOL_ARGUMENTS", "message": "请按 MCP 工具定义提供参数。"}
        except AgentError as exc:
            error = {"code": exc.code, "message": exc.message}
        return ToolResult(
            tool_call_id=call.tool_call_id,
            content=json.dumps(error, ensure_ascii=False),
            is_error=True,
        )
