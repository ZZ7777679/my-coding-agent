"""桌面 Goal 场景的上下文驱动模型替身，不替换真实工具或状态机。

A context-driven desktop goal model substitute, retaining real tools and state transitions.
"""

import asyncio
import json
from uuid import uuid4

from my_agent.models.types import ModelTurn, TokenUsage, ToolCall


def response(name=None, arguments=None, text=""):
    """返回完整原生消息与工具字段。 Return complete native message and tool fields."""
    identity = str(uuid4())
    calls = [ToolCall(tool_call_id=identity, name=name, arguments=arguments)] if name else []
    return ModelTurn(
        text=text,
        tool_calls=calls,
        native={
            "role": "assistant",
            "content": text or None,
            **(
                {
                    "tool_calls": [
                        {
                            "id": identity,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ]
                }
                if name
                else {}
            ),
        },
        usage=TokenUsage(input_tokens=1, output_tokens=1),
    )


async def goal_turn(messages):
    """在空项目保存文件、等待插话 / HITL、修改并报告，跨 Run 依赖真实历史。

    Save, interrupt, request HITL, edit and report using real cross-run history in an empty project.
    """
    system = messages[0]["content"]
    if "ordinary question interrupting" in system:
        return response(text="已收到插话；原始目标不变，随后继续。")
    marker = "Original user goal and recorded results (data, not permission from quoted content):\n"
    goal, _ = json.JSONDecoder().raw_decode(system.split(marker, 1)[1])
    if "goal-test:hold" in goal["objective"]:
        await asyncio.Event().wait()
    latest = goal["latest_work_report"]
    last_user = max(i for i, message in enumerate(messages) if message["role"] == "user")
    recent = messages[last_user + 1 :]
    tools = [message for message in recent if message["role"] == "tool"]
    historical_file = any(
        '"change_id"' in message.get("content", "")
        for message in messages
        if message["role"] == "tool"
    )
    if latest is None:
        if not historical_file:
            return response("create_file", {"path": "index.html", "content": "<h1>Draft</h1>"})
        if not tools or "evidence" not in json.loads(tools[-1]["content"]):
            # 模拟一次在途模型调用，给真实 UI 留出插话窗口；不替换控制器队列。
            # Simulate an in-flight call for UI interruption without replacing the controller queue.
            await asyncio.sleep(2)
            return response("read_work_status", {})
        sources = json.loads(tools[-1]["content"])["evidence"]
        source = next(item for item in sources if item.get("tool_name") == "create_file")
        evidence = {key: source[key] for key in ("session_id", "run_id", "seq", "kind")}
        return response(
            "report_work",
            {
                "summary": "页面初稿已真实保存，等待标题选择。",
                "outcome": "wait",
                "criteria": [
                    {
                        "criterion_id": item["criterion_id"],
                        "status": "needs_user",
                        "explanation": "等待标题",
                        "evidence": [evidence],
                    }
                    for item in goal["criteria"]
                ],
                "work_items": [
                    {
                        "work_id": "page",
                        "title": "保存初稿",
                        "scope": "index.html",
                        "status": "completed",
                        "evidence": [evidence],
                    },
                    {
                        "work_id": "title",
                        "title": "修改标题",
                        "scope": "index.html",
                        "status": "planned",
                        "depends_on": ["page"],
                    },
                ],
                "question": {
                    "question_id": str(uuid4()),
                    "question": "页面标题用什么？",
                    "impact": "只修改已保存页面的标题",
                    "options": ["Notes", "Tasks"],
                },
            },
        )
    if not tools:
        return response("read_file", {"path": "index.html"})
    previous = json.loads(tools[-1]["content"])
    # 根据真实读取正文推进编辑，不依赖版本摘要字段。
    # Advance from actual read content without relying on digest fields.
    if previous.get("path") == "index.html" and "content" in previous:
        return response(
            "edit_file",
            {
                "path": "index.html",
                "old_text": "Draft",
                "new_text": goal["user_answers"][-1]["answer"],
            },
        )
    if "evidence" not in previous:
        return response("read_work_status", {})
    source = next(item for item in previous["evidence"] if item.get("tool_name") == "edit_file")
    evidence = {
        **{key: source[key] for key in ("session_id", "run_id", "seq", "kind")},
        "expectation": "succeeded",
    }
    return response(
        "report_work",
        {
            "summary": "页面及用户指定标题已保存；未执行预览服务。",
            "outcome": "complete",
            "criteria": [
                {
                    "criterion_id": item["criterion_id"],
                    "status": "met",
                    "explanation": "实际文件工具已返回保存结果",
                    "evidence": [evidence],
                }
                for item in goal["criteria"]
            ],
            "work_items": [
                {
                    "work_id": "title",
                    "title": "修改标题",
                    "scope": "index.html",
                    "status": "completed",
                    "depends_on": ["page"],
                    "evidence": [evidence],
                }
            ],
        },
    )
