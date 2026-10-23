"""桌面设计会话的离线模型样本。 Offline model sample for desktop team design."""

import asyncio
import json
from uuid import UUID, uuid5

from goal_model import response


async def design_turn(**kwargs):
    """读取再改图，支持流式观测；不替换业务服务。

    Read and revise graphs with observable streaming, without replacing business services.
    """
    messages = kwargs["messages"]
    prompt = next(m["content"] for m in reversed(messages) if m["role"] == "user")
    if messages[-1]["role"] != "tool":
        await kwargs["on_text"]("正在设计团队，稍后会更新右侧协作图。")
        await asyncio.sleep(1)
        return response("read_team_design", {})
    data = json.loads(messages[-1]["content"])
    if "config" in data:
        identity = UUID(kwargs["session_id"])
        first, second = str(uuid5(identity, "implement")), str(uuid5(identity, "review"))
        config = data["config"] or {
            "receiver_member_id": first,
            "members": [
                {
                    "member_id": first,
                    "name": "实现协调者",
                    "role": "实现与协调",
                    "model_id": "glm-5.3-flash",
                },
                {
                    "member_id": second,
                    "name": "审查成员",
                    "role": "独立审查",
                    "model_id": "deepseek-v4.1-flash",
                },
            ],
            "edges": [
                {
                    "edge_id": str(uuid5(identity, "feedback")),
                    "source_member_id": second,
                    "target_member_id": first,
                    "kind": "feedback",
                    "label": "审查反馈",
                }
            ],
        }
        if "改名" in prompt:
            config["members"][0]["name"] = "页面实现负责人"
        return response("save_team_draft", {"config": config})
    return response(text="团队和协作图已更新，可以继续调整，或确认并开始工作。")
