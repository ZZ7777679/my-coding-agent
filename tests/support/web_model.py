"""联网流程的离线模型与原生响应样本。 Offline model and native-response fixture for web flows."""

import json

from tests.support.goal_model import response

QUERY = "Python JSON official documentation"
PAGE_URL = "https://docs.python.org/3/library/json.html"


def native_response():
    """按已验证的 Messages 结果块构造来源，不用普通文本冒充搜索。

    Build the verified Messages block structure, not prose masquerading as native search.
    """
    return {
        "type": "message",
        "model": "deepseek-v4.1-flash",
        "stop_reason": "end_turn",
        "content": [
            {
                "type": "server_tool_use",
                "name": "web_search",
                "id": "search-1",
                "input": {"query": QUERY},
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": "search-1",
                "content": [
                    {
                        "type": "web_search_result",
                        "url": PAGE_URL,
                        "title": "Python JSON",
                        "encrypted_content": "opaque-not-for-the-ui",
                    }
                ],
            },
            {
                "type": "text",
                "text": "Python provides JSON encoding.",
                "citations": [
                    {
                        "type": "web_search_result_location",
                        "url": PAGE_URL,
                        "cited_text": "JSON encoder and decoder",
                    }
                ],
            },
        ],
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }


class WebModel:
    """当前主模型按来源完成搜索 / 读取，目标模式另保存报告。

    The main model searches and reads actual tool sources, with a goal report when applicable.
    """

    def __init__(self):
        """记录实际调用次数。 Track actual main-model calls."""
        self.calls = 0

    def check_available(self):
        """模型替身不读取密钥。 The model substitute does not read credentials."""

    async def complete(self, **kwargs):
        """使用真实工具返回形成下一步，不替换存储或工具。

        Follow actual tool output without substituting storage or tools.
        """
        self.calls += 1
        assert kwargs["model_id"] == "glm-5.3-flash"
        if self.calls == 1:
            return response("web_search", {"query": QUERY})
        if self.calls == 2:
            source = json.loads(kwargs["messages"][-1]["content"])
            assert source["model_id"] == "deepseek-v4.1-flash"
            return response("web_fetch", {"url": source["sources"][0]["url"]})
        if "Goal mode:" not in kwargs["messages"][0]["content"]:
            return response(text="已搜索并读取 Python 官方资料：" + PAGE_URL)
        if self.calls == 3:
            return response("read_work_status", {})
        index = json.loads(kwargs["messages"][-1]["content"])
        source = next(item for item in index["evidence"] if item.get("tool_name") == "web_fetch")
        reference = {key: source[key] for key in ("session_id", "run_id", "seq", "kind")}
        return response(
            "report_work",
            {
                "summary": "Official source searched and read",
                "outcome": "complete",
                "criteria": [
                    {
                        "criterion_id": "sources",
                        "status": "met",
                        "explanation": "Actual web tools returned references",
                        "evidence": [{**reference, "expectation": "succeeded"}],
                    }
                ],
            },
        )
