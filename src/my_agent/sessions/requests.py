"""请求正文作为按需读取的产物，不放入历史页。 Keep request bodies out of history pages."""

import json
import logging
from pathlib import Path
from uuid import UUID

from my_agent.errors import AgentError
from my_agent.models.types import JsonObject


def save_request(directory: Path, message_id: str, body: JsonObject) -> None:
    """保存适配器交给 HTTP 客户端的 JSON；失败仅影响此检查产物。

    Save the adapter's outgoing JSON; capture failure only affects inspection.
    """
    # Trace DTO 可独立导入；仅写入端需要配置依赖的存储设施。
    # Trace DTOs stay importable without loading configuration-backed storage.
    from my_agent.storage import atomic_write

    try:
        path = directory / "requests" / f"{UUID(message_id)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, json.dumps(body, ensure_ascii=False, indent=2))
    except (OSError, AgentError):
        # 不把可选诊断写入变成模型运行门槛，也不隐瞒降级。
        # Optional inspection storage must not gate model execution; report degradation.
        logging.getLogger(__name__).warning("TRACE_REQUEST_CAPTURE_FAILED request=%s", message_id)


def read_request(directory: Path | None, message_id: str) -> str:
    """读取保存的原请求，旧记录缺失时不从当前状态重建。

    Read the saved request; never reconstruct missing history from current state.
    """
    try:
        if directory is not None:
            return (directory / "requests" / f"{UUID(message_id)}.json").read_text(encoding="utf-8")
    except (FileNotFoundError, ValueError):
        pass
    except (OSError, UnicodeError):
        return json.dumps(
            {"_trace": "请求快照读取失败；原请求状态与历史记录未改变。"}, ensure_ascii=False
        )
    return json.dumps(
        {
            "_trace": "未保存完整请求 JSON（旧记录或当时未成功采集）；"
            "材料清单不是完整请求，不能据此还原。"
        },
        ensure_ascii=False,
    )
