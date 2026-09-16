"""桌面 / stdio 验收的模型替身，产品入口不加载它。

Model substitute for desktop/stdio acceptance; never loaded by the product entry point.
"""

import asyncio
import sys
from uuid import uuid4

from my_agent.config import resolve_data_dir
from my_agent.errors import AgentError
from my_agent.models.timing import RequestTiming
from my_agent.models.types import ModelTurn, TokenUsage, ToolCall
from my_agent.projects import ProjectService
from my_agent.rpc import application
from my_agent.rpc.server import read_parent_credential, serve
from my_agent.sessions.service import SessionService
from my_agent.sessions.store import SessionStore


class DesktopModel:
    """真实服务中的可控模型替身，允许超八秒等待与显式错误。

    Controlled model inside the real service, supporting long waits and explicit failures.
    """

    def check_available(self):
        """不读取或使用真实凭据。 Do not read or use real credentials."""
        return None

    async def complete(self, **kwargs):
        """读真实夹具文件后流式回答，wait 请求等待取消。

        Read fixtures, then stream or wait for cancel.
        """
        messages = kwargs["messages"]
        prompt = next(
            message["content"] for message in reversed(messages) if message["role"] == "user"
        )
        if "fail" in prompt:
            raise AgentError("MODEL_TIMEOUT", "模型请求超时，可调整等待时间后重试。")
        if messages[-1]["role"] != "tool":
            identifier = str(uuid4())
            call = ToolCall(
                tool_call_id=identifier, name="read_file", arguments={"path": "main.py"}
            )
            return ModelTurn(
                text="",
                tool_calls=[call],
                native={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": identifier,
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path":"main.py"}'},
                        }
                    ],
                },
                usage=TokenUsage(input_tokens=10, output_tokens=8),
            )
        if "return 42" not in messages[-1]["content"]:
            raise AgentError("FIXTURE_MISMATCH", "验收夹具未按预期读取。")
        timing = RequestTiming(kwargs.get("on_progress"))
        await timing.set_phase("reasoning")
        await asyncio.sleep(0.3)
        for text in ("已读取 main.py。", "第 2 行返回 42。"):
            await timing.text()
            await kwargs["on_text"](text)
            await asyncio.sleep(0.3)
        if "wait" in prompt:
            await asyncio.Event().wait()
        await timing.set_phase("completed")
        return ModelTurn(
            text="main.py:2 返回 42。<script>不执行脚本</script>",
            tool_calls=[],
            native={
                "role": "assistant",
                "content": "main.py:2 returns 42",
                "reasoning_content": "private-native-sentinel",
            },
            usage=TokenUsage(input_tokens=25, output_tokens=16),
        )


def build_fake(storage, worker, credential, *, http=None):
    """测试装配替换模型，保留实际存储、运行、工具与 RPC。

    Replace only the model in the real stack.
    """
    return SessionService(SessionStore(storage), ProjectService(storage), worker, DesktopModel)


if __name__ == "__main__":
    application.build_sessions = build_fake
    credential = read_parent_credential(sys.stdin.buffer)
    serve(resolve_data_dir(sys.argv[1]), sys.stdin.buffer, sys.stdout.buffer, credential)
