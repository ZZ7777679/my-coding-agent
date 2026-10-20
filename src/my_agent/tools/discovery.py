"""能力定义按需装配，不改变既有执行权限。 Load schemas on demand without changing permissions."""

import json

from pydantic import Field, ValidationError

from my_agent.context.store import ContextStore
from my_agent.context.types import ContextSettings
from my_agent.errors import AgentError
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor
from my_agent.worker import BusinessWorker


class DiscoverToolsArgs(ModelData):
    """支持查询、分页和显式加载／卸载。 Search, page, load or unload tool definitions."""

    query: str = ""
    names: list[str] = Field(default_factory=list)
    unload: list[str] = Field(default_factory=list)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1)


def tool_name(definition: JsonObject) -> str:
    """从真实 schema 读取身份。 Read identity from the actual schema."""
    function = definition.get("function")
    return str(function.get("name", "")) if isinstance(function, dict) else ""


class CapabilityTools:
    """保留会话工作集合；未加载只影响提示，不拒绝合法调用。

    Persist the session working set; missing schemas never deny otherwise valid calls.
    """

    def __init__(
        self,
        context: ToolContext,
        delegate: ToolExecutor,
        store: ContextStore,
        worker: BusinessWorker,
    ) -> None:
        """共享上下文策略与现有工具链。 Share context policy and the existing tool chain."""
        self.context, self.delegate, self.store, self.worker = context, delegate, store, worker
        self.settings = ContextSettings()

    async def refresh(self) -> None:
        """每次请求采用已保存策略；已发送的定义保持不变。

        Refresh saved policy for each request without changing an in-flight request.
        """
        try:
            self.settings = (
                await self.worker.call(self.store.read, self.context.session_id)
            ).settings
        except AgentError as exc:
            if exc.code not in {"DATA_INVALID", "DATA_UNAVAILABLE"}:
                raise
            # 上下文面板已报告派生状态损坏，不能阻断原本可用的工具。
            # Context preparation reports damaged optional state; retain usable tools.
            self.settings = ContextSettings(tool_loading="all")

    def is_mutating(self, name: str) -> bool:
        """发现仅改变定义集合。 Discovery only changes the schema working set."""
        return False if name == "discover_tools" else self.delegate.is_mutating(name)

    def definitions(self) -> list[JsonObject]:
        """核心与活跃定义按稳定注册顺序发送，MCP 继续使用原激活机制。

        Send core/active schemas in registration order; retain MCP's own activation mechanism.
        """
        selected = set(self.settings.core_tools) | set(self.settings.active_tools)
        unavailable = self.unavailable()
        definitions = [
            item
            for item in self.delegate.definitions()
            if tool_name(item) not in unavailable
            and (
                self.settings.tool_loading == "all"
                or tool_name(item) in selected
                or tool_name(item).startswith("mcp_")
            )
        ]
        definitions.append(
            {
                "type": "function",
                "function": {
                    "name": "discover_tools",
                    "description": (
                        "Search available tools by name/description (space-separated keywords). "
                        "Capabilities include files, execution, terminals, Git, code intelligence, "
                        "web, browser/MCP, context/history, memory, tasks, collaboration "
                        "and workers. "
                        "Empty query lists a paged catalog; query or exact names loads matching "
                        "schemas for the next request. Use unload to drop unused schemas. "
                        "execution_compatible describes the execution mode, not installation. "
                        "Incompatible entries include a reason and alternative tools. "
                        "No extra model routing or permission step is required."
                    ),
                    "parameters": DiscoverToolsArgs.model_json_schema(),
                },
            }
        )
        return definitions

    def unavailable(self) -> dict[str, str]:
        """描述尚未接入的入口，不把可选能力缺失变成执行门槛。

        Describe unsupported entry points without gating unrelated development tools.
        """
        return (
            {"code_insight": "LSP 尚未接入项目沙箱；请用 search / read_file 或沙箱命令查询代码。"}
            if self.context.read_roots is not None
            else {}
        )

    def _select(self, added: list[str], removed: list[str]) -> ContextSettings:
        """在单写者中只更新工作集合，保留并行保存的其他设置。

        Update only the working set on the writer, retaining other saved settings.
        """
        state = self.store.read(self.context.session_id)
        state.settings.active_tools = list(
            dict.fromkeys(
                [name for name in state.settings.active_tools if name not in removed] + added
            )
        )
        self.store.save(self.context.session_id, state)
        return state.settings

    async def execute(self, call: ToolCall) -> ToolResult:
        """发现本地目录并持久化精确身份，实际调用仍交给原工具。

        Discover local schemas and persist identities; execute through the original tool.
        """
        if call.name != "discover_tools":
            return await self.delegate.execute(call)
        try:
            args = DiscoverToolsArgs.model_validate(call.arguments)
        except ValidationError:
            return ToolResult(
                tool_call_id=call.tool_call_id,
                is_error=True,
                content=json.dumps(
                    {
                        "code": "INVALID_TOOL_ARGUMENTS",
                        "message": "使用 query/names/unload 和非负 offset、正数 limit。",
                    },
                    ensure_ascii=False,
                ),
            )
        catalog: list[JsonObject] = []
        unavailable = self.unavailable()
        for definition in self.delegate.definitions():
            function = definition.get("function")
            if isinstance(function, dict):
                name = str(function.get("name", ""))
                catalog.append(
                    {
                        "name": name,
                        "description": str(function.get("description", "")),
                        "execution_compatible": name not in unavailable,
                        "reason": unavailable.get(name, ""),
                        "alternatives": ["search", "read_file", "run_command"]
                        if name in unavailable
                        else [],
                    }
                )
        words = args.query.casefold().split()
        matches = [
            item
            for item in catalog
            if item["name"] in args.names
            or (
                not args.names
                and all(
                    word in (str(item["name"]) + " " + str(item["description"])).casefold()
                    for word in words
                )
            )
        ]
        page = matches[args.offset : args.offset + args.limit]
        activated = (
            [str(item["name"]) for item in page if item["execution_compatible"]]
            if words or args.names
            else []
        )
        if activated or args.unload:
            self.settings = await self.worker.call(self._select, activated, args.unload)
        value = {
            "catalog": page,
            "total": len(matches),
            "activated": activated,
            "active_tools": self.settings.active_tools,
            "next_offset": args.offset + len(page)
            if args.offset + len(page) < len(matches)
            else None,
            "unknown_names": [
                name for name in args.names if not any(i["name"] == name for i in catalog)
            ],
        }
        return ToolResult(
            tool_call_id=call.tool_call_id,
            is_error=False,
            content=json.dumps(value, ensure_ascii=False),
        )
