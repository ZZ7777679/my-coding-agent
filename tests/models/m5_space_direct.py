"""以 DeepSeek 官方接口演示真实合作，仅发送隔离样例。

Demonstrate real collaboration through DeepSeek using only an isolated example.
"""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic import SecretStr

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.context.types import ContextSettings
from my_agent.credentials import read_windows_user, resolve_credential
from my_agent.errors import AgentError
from my_agent.memory.types import MemorySettings
from my_agent.models.go import GoClient
from my_agent.models.http import ModelHttpPool
from my_agent.models.types import (
    JsonObject,
    ModelId,
    ModelTurn,
    ProgressSink,
    RequestSink,
    TextSink,
)
from my_agent.rpc.application import RpcApplication
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.types import AssistantCommitted, ToolCompleted, ToolStarted

ENDPOINT = "https://api.deepseek.com"
API_MODEL = "deepseek-flash"
KEY_NAME = "DEEPSEEK_API_KEY"


def direct_key() -> SecretStr:
    """只读取明确名称，不输出或存储秘密。

    Read only the named credential without printing or persisting it.
    """
    value = os.environ.get(KEY_NAME, "")
    if not value.strip():
        value = read_windows_user(KEY_NAME) or ""
    if not value.strip():
        raise AgentError("CREDENTIAL_MISSING", "未找到 DEEPSEEK_API_KEY。")
    return SecretStr(value)


class DirectClient(GoClient):
    """借用产品流解析，直连身份仅由本演示注入。

    Reuse production streaming with a direct identity injected only by this demo.
    """

    def __init__(self, key: SecretStr, pool: ModelHttpPool) -> None:
        """显式官方模型映射，不把 DeepSeek key 放进 Go 凭据对象。

        Map the official model without storing a DeepSeek key as a Go credential.
        """
        super().__init__(
            resolve_credential(environ={}, platform="unused"),
            ENDPOINT,
            pool,
            request_model_id=API_MODEL,
        )
        self.direct_key = key

    def check_available(self) -> None:
        """构造前已解析明确凭据，此处不发送探测。

        The explicit credential was resolved before construction; no probe is sent here.
        """

    def request_headers(self, session_id: str, *, messages_api: bool = False) -> dict[str, str]:
        """仅向已指定官方客户端提供认证头。

        Supply authentication only to this explicitly selected official client.
        """
        return {
            "User-Agent": "my-coding-agent/m5-space-demo",
            "Authorization": "Bearer " + self.direct_key.get_secret_value(),
        }


async def demonstrate(root: Path, request_limit: int, seconds_limit: int) -> None:
    """真实群聊路由、代码工具和跨会话审查，保存实际结果。

    Run real group routing, file tools and cross-session review and save their results.
    """
    metadata = json.loads((root / "demo.json").read_text(encoding="utf-8"))
    report_path = root / "direct-report.json"
    if report_path.exists():
        raise AgentError("DEMO_ALREADY_RUN", "该示例已有直连报告；保留结果，不自动重放。")
    key = direct_key()
    started = time.monotonic()
    requests: list[dict[str, object]] = []
    report: dict[str, object] = {
        "provider": "deepseek-direct",
        "endpoint": ENDPOINT,
        "api_model": API_MODEL,
        "credential_name": KEY_NAME,
        "task_id": metadata["task_id"],
        "request_limit": request_limit,
        "seconds_limit": seconds_limit,
        "requests": requests,
    }

    def save() -> None:
        """记录脱敏计量和业务事实。 Save sanitized accounting and business facts."""
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    app = RpcApplication(
        resolve_data_dir(metadata["data"]),
        resolve_credential(environ={}, platform="unused"),
        None,
    )

    class Observed(DirectClient):
        """统一计量所有成员请求；不替换模型输出或工具。

        Meter every member without substituting model output or tools.
        """

        def __init__(self) -> None:
            """共享本次凭据与连接池。 Share this run's credential and pool."""
            super().__init__(key, app.http)

        async def complete(
            self,
            *,
            model_id: ModelId,
            session_id: str,
            messages: list[JsonObject],
            tools: list[JsonObject],
            limits: RunLimits,
            on_text: TextSink,
            on_progress: ProgressSink | None = None,
            on_reasoning: TextSink | None = None,
            on_request: RequestSink | None = None,
        ) -> ModelTurn:
            """在发送前计数，失败保留且不重试。

            Count before sending; preserve failure without retrying.
            """
            if len(requests) >= request_limit:
                raise AgentError("DEMO_BUDGET", "隔离演示请求预算已用完。")
            row: dict[str, object] = {
                "request": len(requests) + 1,
                "session_id": session_id,
                "status": "started",
            }
            requests.append(row)
            save()
            tick = time.monotonic()
            try:
                turn = await super().complete(
                    model_id=model_id,
                    session_id=session_id,
                    messages=messages,
                    tools=tools,
                    limits=limits,
                    on_text=on_text,
                    on_progress=on_progress,
                    on_reasoning=on_reasoning,
                    on_request=on_request,
                )
                row.update(
                    status="completed",
                    tools=[call.name for call in turn.tool_calls],
                    usage=turn.usage.model_dump(),
                )
                return turn
            except AgentError as exc:
                row.update(status="failed", code=exc.code, message=exc.message)
                raise
            finally:
                row["seconds"] = round(time.monotonic() - tick, 3)
                save()
                print(json.dumps(row, ensure_ascii=False), flush=True)

    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=30) as client:
            response = await client.get(
                ENDPOINT + "/models",
                headers={"Authorization": "Bearer " + key.get_secret_value()},
            )
            report["model_list_http_status"] = response.status_code
            if response.status_code != 200:
                raise AgentError("DIRECT_AUTH", f"官方模型目录返回 HTTP {response.status_code}。")
            ids = [item["id"] for item in response.json()["data"]]
            report["available_models"] = ids
            save()
            if API_MODEL not in ids:
                raise AgentError("DIRECT_MODEL", "官方目录中没有选定的模型标识。")
        await app.dispatch(
            "initialize",
            {
                "app_version": "m5-space-direct-demo",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": DEFAULTS["data_schema_version"],
            },
        )
        app.sessions.model_factory = Observed
        for binding in metadata["space"]["space"]["bindings"]:
            sid = binding["session_id"]
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            await app.sessions.contexts.configure(sid, ContextSettings(automatic=False))
        prompt = (
            "这是 DeepSeek 官方直连的隔离合作演示。请完成：在 index.html 创建无依赖的单页计数器，"
            "初始 0，提供 +1 和重置按钮。用已有协作工具找到审查者，发送只读检查请求，"
            "要求读取实际文件核对三项行为的代码实现，不改文件。等审查结果返回后简短汇总："
            "各成员做了什么、成果位置、审查发现，以及尚未进行浏览器实测。"
            "需要时更新已有 counter / review 工作状态。不要新增功能、安装依赖或创建正式会话。"
            "不要联网搜索，这个示例不需要外部资料；正常完成即返回用户。"
        )
        async with asyncio.timeout(seconds_limit):
            result = await app.dispatch(
                "spaces.chat",
                {
                    "task_id": metadata["task_id"],
                    "operation_id": str(uuid4()),
                    "content": prompt,
                },
            )
            report["initial_delivery"] = result.model_dump(mode="json")
            save()
            for binding in metadata["space"]["space"]["bindings"]:
                active = app.sessions.active_for(binding["session_id"])
                if active is not None and active.task is not None:
                    await active.task
        sessions = []
        for binding in metadata["space"]["space"]["bindings"]:
            sid = binding["session_id"]
            view = await app.sessions.view(sid)
            log = await app.worker.call(app.sessions.store.load, sid)
            sessions.append(
                {
                    "session_id": sid,
                    "run": view.summary.run.model_dump(mode="json") if view.summary.run else None,
                    "tools": [
                        f.data.call.model_dump()
                        for f in log.facts
                        if isinstance(f.data, ToolStarted)
                    ],
                    "results": [
                        f.data.result.model_dump()
                        for f in log.facts
                        if isinstance(f.data, ToolCompleted)
                    ],
                    "answers": [
                        f.data.turn.text
                        for f in log.facts
                        if isinstance(f.data, AssistantCommitted)
                    ],
                }
            )
        report["sessions"] = sessions
        chat = await app.dispatch("spaces.chat_view", {"task_id": metadata["task_id"]})
        report["chat"] = chat.model_dump(mode="json")
        report["file_created"] = (Path(metadata["project"]) / "index.html").is_file()
        report["members_completed"] = all(
            s["run"] and s["run"]["status"] == "completed" for s in sessions
        )
    except AgentError as exc:
        report["failure"] = {"code": exc.code, "message": exc.message}
    except (TimeoutError, httpx.HTTPError) as exc:
        report["failure"] = {
            "code": type(exc).__name__,
            "message": "演示等待或网络请求失败；未重试。",
        }
    finally:
        await app.close()
        save()
        print(
            json.dumps(
                {
                    "report": str(report_path),
                    "requests": len(requests),
                    "members_completed": report.get("members_completed"),
                    "failure": report.get("failure"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument("--max-requests", type=int, default=24)
    parser.add_argument("--max-seconds", type=int, default=600)
    options = parser.parse_args()
    asyncio.run(demonstrate(options.root.resolve(), options.max_requests, options.max_seconds))
