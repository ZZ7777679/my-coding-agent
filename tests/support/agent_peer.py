"""桌面 / stdio 验收的模型替身，产品入口不加载它。

Model substitute for desktop/stdio acceptance; never loaded by the product entry point.
"""

import asyncio
import json
import os
import re
import sys
from uuid import uuid4

from goal_model import goal_turn, response

from my_agent.bootstrap import build_sessions
from my_agent.config import resolve_data_dir
from my_agent.errors import AgentError
from my_agent.models.timing import RequestTiming
from my_agent.models.types import ModelTurn, TokenUsage, ToolCall
from my_agent.rpc import application
from my_agent.rpc.server import read_parent_credential, serve


class DesktopModel:
    """真实服务中的可控模型替身，允许超八秒等待与显式错误。

    Controlled model inside the real service, supporting long waits and explicit failures.
    """

    def check_available(self):
        """不读取或使用真实凭据。

        Do not read or use real credentials.
        """
        return None

    async def complete(self, **kwargs):
        """读真实夹具文件后流式回答，wait 请求等待取消。

        Read fixtures, then stream or wait for cancel.
        """
        messages = kwargs["messages"]
        if messages[0]["content"].startswith("Investigate selected evidence"):
            return evolution_turn(messages)
        if messages[0]["content"].startswith("Write one concise continuation brief"):
            return response(
                text="Earlier task: use Python standard library; keep the page offline."
            )
        if messages[0]["content"].startswith("Extract only reusable"):
            return response(
                text=json.dumps(
                    {
                        "entries": [
                            {"fields": {"title": "Offline", "content": "Use bundled assets."}}
                        ]
                    }
                )
            )
        prompt = next(
            message["content"] for message in reversed(messages) if message["role"] == "user"
        )
        if (
            "Goal mode:" in messages[0]["content"]
            or "ordinary question interrupting" in messages[0]["content"]
        ):
            return await goal_turn(messages)
        if prompt.startswith("m3:"):
            if prompt == "m3: lookup" and messages[-1]["role"] != "tool":
                return response("read_history", {"query": "desktop history", "max_chars": 100})
            return response(text="M3 local desktop sample completed. " * 20).model_copy(
                update={"usage": TokenUsage(input_tokens=123456, output_tokens=77)}
            )
        if prompt.startswith("goal-chat:"):
            return response(text="普通问题已回答，等待中的 Goal 没有恢复。")
        if prompt.startswith("recovery:create"):
            return response("create_file", {"path": "recovery.txt", "content": "saved once"})
        if prompt.startswith("recovery:check"):
            assert any(
                "INTERRUPTED_RESULT_RECONCILED" in (item.get("content") or "") for item in messages
            )
            return response(text="已接续核对后的历史，未重跑旧工具。")
        if prompt.startswith("files:"):
            return await file_turn(prompt, **kwargs)
        if prompt.startswith("program:"):
            return program_turn(prompt, messages)
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
        await timing.received(32)
        await timing.set_phase("reasoning")
        thoughts = ("先定位 main.py 的入口。", "再核对第 2 行的返回值。")
        for thought in thoughts:
            await kwargs["on_reasoning"](thought)
            await asyncio.sleep(0.35)
        for text in ("已读取 main.py。", "第 2 行返回 42。"):
            await timing.received(len(text.encode("utf-8")))
            await timing.text()
            await kwargs["on_text"](text)
            await asyncio.sleep(0.3)
        # 仅独立的 wait 标记触发等待，简报中的 waited_seconds 不改变替身行为。
        # Only a standalone wait marker pauses; brief fields such as waited_seconds do not.
        if re.search(r"\bwait\b", prompt):
            await asyncio.Event().wait()
        await timing.set_phase("completed")
        return ModelTurn(
            text="main.py:2 返回 42。<script>不执行脚本</script>",
            reasoning="".join(thoughts),
            tool_calls=[],
            native={
                "role": "assistant",
                "content": "main.py:2 returns 42",
                "reasoning_content": "".join(thoughts),
                "provider_state": "private-native-sentinel",
            },
            usage=TokenUsage(input_tokens=25, output_tokens=16),
        )


def evolution_turn(messages):
    """用真实调查工具读取跨项目证据和两个不同目标；不调用真实模型。

    Read cross-project evidence and two targets through real investigation tools without a model.
    """
    payload = json.loads(next(m["content"] for m in messages if m["role"] == "user"))
    results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
    index = next((r for r in results if "search_scope" in r), None)
    if index is None:
        return response("index_review_evidence", {"query": "read_file"})
    body = next((r for r in results if "text" in r and "session_id" in r), None)
    if body is None and index["items"]:
        row = index["items"][0]
        return response(
            "read_review_evidence",
            {
                "session_id": row["session_id"],
                "seq": row["seq"],
                "limit": 32000,
            },
        )
    if payload.get("directed_target"):
        return response(
            "submit_review",
            {
                "summary": "Selected representative reviewed.",
                "proposals": [
                    {
                        "finding_id": "directed",
                        "title": "Focused project guidance",
                        "rationale": "Use selected evidence.",
                        "target": payload["directed_target"],
                        "after": "Read relevant files and explain results briefly.\n",
                    }
                ],
            },
        )
    guidance = {"kind": "tool_guidance", "identity": "read_file", "scope": "project"}
    code = {"kind": "code", "identity": "answer.py", "scope": "project"}
    for target in (guidance, code):
        if not any(r.get("target") == target for r in results):
            return response("read_review_resource", {"target": target})
    sources = (
        [
            {
                "session_id": body["session_id"],
                "run_id": body["run_id"],
                "seq": body["seq"],
                "scope": "event",
                "through_seq": body["through_seq"],
            }
        ]
        if body
        else []
    )
    findings = [
        {
            "finding_id": "reading-guidance",
            "title": "Clarify reading usage",
            "explanation": "The selected read trace supports a focused tool usage clarification.",
            "category": "tool_usage",
            "targets": [guidance],
            "sources": sources,
            "unknowns": [],
        },
        {
            "finding_id": "answer-implementation",
            "title": "Correct answer implementation",
            "explanation": "The target fixture implementation is a separate code proposal.",
            "category": "implementation",
            "targets": [code],
            "sources": sources,
            "unknowns": ["This fixture does not establish improvement on real tasks."],
        },
    ]
    selected = payload.get("findings_to_address") or findings
    after = {
        "reading-guidance": "Read relevant files before proposing changes.\n",
        "answer-implementation": "value = 2\n",
    }
    proposals = (
        [
            {
                "finding_id": finding["finding_id"],
                "title": finding["title"],
                "rationale": finding["explanation"],
                "target": finding["targets"][0],
                "after": after[finding["finding_id"]],
            }
            for finding in selected
        ]
        if payload["mode"] == "propose"
        else []
    )
    report = {
        "summary": "Selected evidence reviewed; usage and implementation are separate findings.",
        "findings": selected,
        "proposals": proposals,
    }
    # 故意省略必填字段一次，真实工具反馈后修正，不让格式问题中止调查。
    # Omit one required field once, then repair actual tool feedback without failing the review.
    if not any("INVALID_TOOL_ARGUMENTS" in json.dumps(result) for result in results):
        return response(
            "submit_review", {key: value for key, value in report.items() if key != "summary"}
        )
    return response("submit_review", report)


async def file_turn(prompt, **kwargs):
    """驱动实际文件工具，不替换存储或权限。

    Drive real file tools without mocking their policy.
    """
    messages = kwargs["messages"]
    previous = json.loads(messages[-1]["content"]) if messages[-1]["role"] == "tool" else None
    name, arguments = None, {}
    if previous is None:
        if "edit" in prompt:
            name, arguments = "read_file", {"path": "src/main.py"}
        else:
            name, arguments = (
                "create_file",
                {
                    "path": "docs/plan.md" if "document" in prompt else "src/main.py",
                    "content": "# Plan\n" if "document" in prompt else "print(1)\n",
                },
            )
    elif "edit" in prompt and "change_id" not in previous:
        name, arguments = (
            "edit_file",
            {
                "path": "src/main.py",
                "old_text": "print(1)",
                "new_text": "print(2)",
            },
        )
    if name:
        identifier = str(uuid4())
        return ModelTurn(
            text="",
            tool_calls=[ToolCall(tool_call_id=identifier, name=name, arguments=arguments)],
            native={
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": identifier,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments)},
                    }
                ],
            },
            usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    return ModelTurn(
        text="文件操作已完成；未运行代码。",
        tool_calls=[],
        native={"role": "assistant", "content": "File operation completed."},
        usage=TokenUsage(input_tokens=1, output_tokens=1),
    )


def program_turn(prompt, messages):
    """空目录生成并启动真实 HTTP 程序，只有模型决策是替身。

    Generate and launch a real HTTP app in an empty project; substitute only model decisions.
    """
    last_user = max(i for i, message in enumerate(messages) if message["role"] == "user")
    completed = sum(message["role"] == "tool" for message in messages[last_user + 1 :])
    if prompt == "program:location":
        if not completed:
            return response(
                "run_command",
                {"command": json.dumps({"kind": "powershell", "script": "Get-Location"})},
            )
        result = json.loads(messages[-1]["content"])
        assert result["summary"]["exit_code"] == 0
        assert "Path" in "".join(chunk["text"] for chunk in result["output"])
        return response(text="已使用默认本机环境执行 Get-Location。")
    port = int(prompt.rsplit(":", 1)[1])
    source = (
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "import sys\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        content = b'<html><title>Empty project app</title><h1>Notes</h1>"
        '<textarea id=note></textarea><button onclick="localStorage.note='
        "document.getElementById(\\'note\\').value\">Save note</button></html>'\n"
        "        self.send_response(200)\n"
        "        self.send_header('Content-Type', 'text/html; charset=utf-8')\n"
        "        self.end_headers()\n"
        "        self.wfile.write(content)\n"
        "if '--describe' in sys.argv:\n"
        "    print('Notes app ready to launch', flush=True)\n"
        "else:\n"
        "    print('Starting Notes app', flush=True)\n"
        "    HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()\n"
    )
    steps = [
        ("create_file", {"path": "app.py", "content": source}),
        (
            "run_command",
            {
                "command": {
                    "kind": "program",
                    "program": "python",
                    "arguments": ["app.py", "--describe"],
                }
            },
        ),
        (
            "start_service",
            {
                "command": {
                    "kind": "program",
                    "program": "python",
                    "arguments": ["app.py", str(port)],
                },
                "ready_url": f"http://127.0.0.1:{port}/",
            },
        ),
    ]
    if completed >= len(steps):
        return ModelTurn(
            text="已创建并运行 Notes 小应用；服务保留到退出应用。",
            tool_calls=[],
            native={"role": "assistant", "content": "Application ready."},
            usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    name, arguments = steps[completed]
    identifier = str(uuid4())
    return ModelTurn(
        text="",
        tool_calls=[ToolCall(tool_call_id=identifier, name=name, arguments=arguments)],
        native={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": identifier,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        },
        usage=TokenUsage(input_tokens=1, output_tokens=1),
    )


class InterruptedResponseTools:
    """验收专用：真实写入后延迟响应，以实际取消制造未配对工具。

    Test-only delayed responses after real writes, producing unpaired calls via real cancellation.
    """

    def __init__(self, delegate):
        """保留实际工具实现。

        Retain the actual tool implementation.
        """
        self.delegate = delegate

    def definitions(self):
        return self.delegate.definitions()

    def is_mutating(self, name):
        return self.delegate.is_mutating(name)

    async def execute(self, call):
        """只为专用恢复场景延迟，其他场景直接返回真实结果。

        Delay only the dedicated recovery fixture and return real results for all other cases.
        """
        result = await self.delegate.execute(call)
        if call.name == "create_file" and call.arguments.get("path") == "recovery.txt":
            assert not result.is_error
            await asyncio.Event().wait()
        return result


def build_fake(storage, worker, credential, *, http=None, programs=None):
    """测试装配替换模型，保留实际存储、运行、工具与 RPC。

    Substitute the model, with a dedicated post-write response gate for interruption tests.
    """
    service = build_sessions(storage, worker, credential, http=http, programs=programs)
    service.model_factory = DesktopModel
    original = service.tool_factory
    service.tool_factory = lambda context: InterruptedResponseTools(original(context))
    return service


if __name__ == "__main__":
    if os.environ.get("MY_AGENT_TEST_SKILL_CATALOG") == "1":
        import httpx
        from online_skill_fixture import catalog_response

        from my_agent.skills.online import OnlineSkills

        def fixture_client(self, timeout):
            """仅桌面测试替换外网。 Substitute external HTTP only in the desktop test."""
            return httpx.AsyncClient(transport=httpx.MockTransport(catalog_response))

        OnlineSkills.client = fixture_client
    application.build_sessions = build_fake
    credential = read_parent_credential(sys.stdin.buffer)
    serve(resolve_data_dir(sys.argv[1]), sys.stdin.buffer, sys.stdout.buffer, credential)
