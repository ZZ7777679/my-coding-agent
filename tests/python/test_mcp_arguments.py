"""真实离线 SDK 错误与产品适配分类。 Real offline SDK errors and product adapter classification."""

import asyncio
import json
import threading
from uuid import uuid4

import pytest
from mcp.client import Client
from mcp.server import MCPServer

from my_agent.config import DEFAULTS
from my_agent.errors import AgentError
from my_agent.mcp_client.tools import McpTools, validate_arguments
from my_agent.models.types import ToolCall
from my_agent.runtime.loop import recoverable_tool_error
from my_agent.runtime.settings import RunLimits
from my_agent.runtime.tools import ToolContext


@pytest.mark.parametrize("schema", [{"type": 9}, {"$ref": "https://invalid.example/schema"}])
def test_invalid_or_external_schema_stops_without_fetch(schema):
    """不把服务定义错误当模型参数错误，不读取外部引用。

    Stop invalid server schemas without classifying them as input mistakes or fetching references.
    """
    with pytest.raises(AgentError) as failure:
        validate_arguments(schema, {})
    assert failure.value.code == "MCP_SCHEMA_INVALID"


def test_local_schema_references_remain_supported():
    """内部定义正常可用，无隐式类型转换。 Support local definitions without coercion."""
    schema = {
        "$defs": {"text": {"type": "string"}},
        "type": "object",
        "properties": {"text": {"$ref": "#/$defs/text"}},
        "required": ["text"],
    }
    validate_arguments(schema, {"text": "valid"})
    with pytest.raises(AgentError) as failure:
        validate_arguments(schema, {"text": 42})
    assert failure.value.code == "INVALID_TOOL_ARGUMENTS"


def test_mcp_parameters_are_recoverable_before_call_but_execution_errors_stop(tmp_path):
    """真实参数错误和执行错误分别处理，无网络或模型。

    Distinguish real parameter and execution errors without network or model requests.
    """

    async def scenario():
        """SDK 内存传输保留真实服务校验。 Use SDK memory transport with real server validation."""
        peer = MCPServer("Argument fixture")
        effects = []

        @peer.tool()
        def format_note(text: str) -> str:
            """合成副作用可计数。 Count synthetic side effects."""
            effects.append(text)
            if text == "fail":
                raise RuntimeError("synthetic execution failure")
            return text.strip()

        async with Client(peer) as client:
            tools = (await client.list_tools()).tools
            definition = tools[0].model_dump(mode="json", by_alias=True)
            raw = await client.call_tool("format_note", {"text": 42})
            assert raw.is_error and effects == []

            class Bridge:
                """适配器到真实 SDK；统计实际派发。 Bridge to the real SDK and count dispatches."""

                calls = 0

                async def call(self, method, arguments):
                    """仅一次执行，不自动重放。 Execute once without replays."""
                    assert method == "tools/call"
                    self.calls += 1
                    result = await client.call_tool(arguments["name"], arguments["arguments"])
                    return result.model_dump(mode="json", by_alias=True)

            bridge = Bridge()
            sid = str(uuid4())

            class Service:
                """只替换传输装配，不替换参数校验或服务行为。

                Replace transport composition, not argument validation or server behavior.
                """

                selected = {sid: {"fixture_note": ("fixture", definition)}}

                async def connect(self, params, server_id):
                    """返回已连接内存服务。 Return the connected memory service."""
                    return bridge

                async def normalize(self, params, value):
                    """样本没有图片或附件。 The fixture has no images or attachments."""
                    return value

            class Delegate:
                """样本只执行 MCP 工具。 Only MCP tools are used in this fixture."""

                def definitions(self):
                    """没有本地工具。 No local tools."""
                    return []

                def is_mutating(self, name):
                    """按有副作用处理。 Treat calls as mutating."""
                    return True

                async def execute(self, call):
                    """意外派发即失败。 Reject unexpected delegation."""
                    raise AssertionError("unexpected local tool")

            context = ToolContext(
                tmp_path,
                RunLimits.model_validate(DEFAULTS["run"]),
                threading.Event(),
                str(uuid4()),
                sid,
                str(uuid4()),
                "normal",
                None,
            )
            adapter = McpTools(context, Delegate(), Service())
            for arguments in ({}, {"text": 42}):
                call = ToolCall(tool_call_id=str(uuid4()), name="fixture_note", arguments=arguments)
                result = await adapter.execute(call)
                assert json.loads(result.content)["code"] == "INVALID_TOOL_ARGUMENTS"
                assert recoverable_tool_error(call, result)
                assert bridge.calls == 0 and effects == []
            for text, failed in ((" valid ", False), ("fail", True)):
                call = ToolCall(
                    tool_call_id=str(uuid4()), name="fixture_note", arguments={"text": text}
                )
                result = await adapter.execute(call)
                assert result.is_error is failed
                if failed:
                    assert json.loads(result.content)["code"] == "MCP_TOOL_FAILED"
                    assert not recoverable_tool_error(call, result)
            assert bridge.calls == 2 and effects == [" valid ", "fail"]

    asyncio.run(scenario())
