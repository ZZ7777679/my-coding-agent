"""用已持久的来源装配工具上下文，不改写原始结果。

Build tool context from durable provenance without rewriting stored results.
"""

import json

from my_agent.models.types import JsonObject
from my_agent.sessions.types import Fact, ToolCompleted, ToolSkipped


def tool_result_message(fact: Fact) -> JsonObject:
    """给 JSON 对象结果附上精确引用；实时与恢复历史使用同一投影。

    Attach exact references to JSON-object results, identically for live and restored history.
    """
    data = fact.data
    if not isinstance(data, (ToolCompleted, ToolSkipped)):
        raise ValueError("A tool result fact is required")
    content = data.result.content
    if isinstance(data, ToolCompleted) and fact.run_id:
        try:
            value = json.loads(content)
        except ValueError:
            value = None
        if isinstance(value, dict):
            # 序号来自保存完成的事实，不能由工具内容或模型推测。
            # The persisted fact supplies identity, never tool content or model guesses.
            value["_evidence"] = {
                "session_id": fact.session_id,
                "run_id": fact.run_id,
                "seq": fact.seq,
                "kind": "tool_result",
            }
            content = json.dumps(value, ensure_ascii=False)
    return {"role": "tool", "tool_call_id": data.result.tool_call_id, "content": content}
