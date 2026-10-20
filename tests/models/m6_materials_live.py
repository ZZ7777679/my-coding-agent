"""隔离比较全量／按需材料，并在同一会话跨模型接续。

Compare full/on-demand materials and cross-model continuation on isolated fixtures.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, load_config, resolve_data_dir
from my_agent.context.tokens import estimate_tokens
from my_agent.context.types import ContextSettings
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.memory.types import MemorySettings
from my_agent.models.failures import ModelResponseError
from my_agent.rpc.application import RpcApplication
from my_agent.sessions.types import AssistantCommitted, ToolCompleted, ToolStarted


async def evaluate(root: Path) -> bool:
    """四个短 Run 共用生产模型／工具；只记录隔离材料的计量与结果。

    Run four short production conversations, recording only fixture metrics and outcomes.
    """
    report = {"requests": [], "runs": [], "max_requests": 20, "max_seconds": 600}
    started = time.monotonic()
    app = RpcApplication(resolve_data_dir(str(root / "data")), resolve_credential(), None)
    factory = app.sessions.model_factory
    active_case = ""

    def save():
        """逐请求保存结果，不记录凭据或完整模型材料。 Save metrics, not secrets or raw payloads."""
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    class ObservedModel:
        """包装原工厂，参数与生产解析器保持原样。 Observe the production factory unchanged."""

        def __init__(self):
            """复用生产连接池。 Reuse the production connection pool."""
            self.client = factory()

        def check_available(self):
            """使用既有凭据状态检查。 Use the existing credential check."""
            self.client.check_available()

        async def complete(self, **kwargs):
            """记录实际定义与服务计量；失败保留且不自动重试。

            Record actual schemas and reported usage, retaining failures without retries.
            """
            if len(report["requests"]) >= 20 or time.monotonic() - started >= 600:
                raise AgentError("EVALUATION_BUDGET", "Isolated evaluation budget exhausted")
            row = {
                "case": active_case,
                "model": kwargs["model_id"],
                "status": "started",
                "tool_names": [item["function"]["name"] for item in kwargs["tools"]],
                "tool_tokens_estimated": estimate_tokens(kwargs["tools"]),
            }
            report["requests"].append(row)
            tick = time.monotonic()
            sink = kwargs["on_text"]

            async def text(delta):
                """思考不冒充正文首字。 Keep reasoning separate from answer first text."""
                if delta and "first_text_seconds" not in row:
                    row["first_text_seconds"] = round(time.monotonic() - tick, 3)
                await sink(delta)

            kwargs["on_text"] = text
            try:
                result = await self.client.complete(**kwargs)
                row.update(
                    status="completed",
                    usage=result.usage.model_dump(),
                    calls=[call.name for call in result.tool_calls],
                )
                return result
            except Exception as exc:
                # 测量边界保留错误类型并原样抛出，不能把失败算作通过。
                # This observation boundary records and rethrows failures, never passing them.
                row.update(status="failed", error=type(exc).__name__)
                if isinstance(exc, AgentError):
                    row["code"] = exc.code
                if isinstance(exc, ModelResponseError):
                    row["usage"] = exc.usage.model_dump()
                raise
            finally:
                row["seconds"] = round(time.monotonic() - tick, 3)
                if self.client.http.last_request is not None:
                    row["progress"] = self.client.http.last_request.progress.model_dump()
                save()
                print(json.dumps(row, ensure_ascii=True), flush=True)

    app.sessions.model_factory = ObservedModel
    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "m6-materials-evaluation",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": 1,
            },
        )
        for loading in ("all", "on_demand"):
            project = root / loading / "project"
            project.mkdir(parents=True)
            (project / "sample.py").write_text("VALUE = 42\n", encoding="utf-8")
            opened = await app.dispatch("projects.open", {"path": str(project)})
            session = await app.sessions.create(opened.active_project.project_id, "glm-5.3-flash")
            sid = session.session_id
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            await app.sessions.contexts.configure(
                sid, ContextSettings(automatic=False, tool_loading=loading)
            )
            for model, prompt, expected_tool in (
                (
                    "glm-5.3-flash",
                    "Read sample.py with the file tool. Report VALUE in one sentence. "
                    "Do not modify files or run commands.",
                    "read_file",
                ),
                (
                    "deepseek-v4.1-flash",
                    "Use the terminal-list capability (discover it if needed) to check existing "
                    "interactive terminals. Report their count and the VALUE already read in "
                    "sample.py. Do not open terminals, run commands or reread the file.",
                    "list_terminals",
                ),
            ):
                active_case = loading + "/" + model
                await app.sessions.select_model(sid, str(uuid4()), model)
                limits = load_config(app.storage.location).run.model_copy(
                    update={
                        "max_requests": 5,
                        "max_tools": 8,
                        "max_seconds": min(150, max(1, int(600 - (time.monotonic() - started)))),
                        "request_timeout_seconds": 100,
                        "max_output_tokens": 4096,
                    }
                )
                await app.sessions.start(sid, str(uuid4()), prompt, limits, mode="plan")
                active = app.sessions.active_for(sid)
                run_id = active.run_id
                await active.task
                log = await app.sessions._load(sid)
                facts = [fact.data for fact in log.facts if fact.run_id == run_id]
                # 验证保存的工具事实，不能只相信模型宣称已执行。
                # Verify persisted tool facts rather than a model's execution claim.
                view = (await app.sessions.view(sid)).summary.run
                calls = {
                    f.call.tool_call_id: f.call.name for f in facts if isinstance(f, ToolStarted)
                }
                completed = [f for f in facts if isinstance(f, ToolCompleted)]
                answers = [f.turn.text for f in facts if isinstance(f, AssistantCommitted)]
                answer = answers[-1] if answers else ""
                passed = (
                    view.status == "completed"
                    and any(
                        calls.get(f.result.tool_call_id) == expected_tool and not f.result.is_error
                        for f in completed
                    )
                    and "42" in answer
                    and (project / "sample.py").read_text(encoding="utf-8") == "VALUE = 42\n"
                )
                report["runs"].append(
                    {
                        "case": active_case,
                        "session_id": sid,
                        "run": view.model_dump(),
                        "tools": list(calls.values()),
                        "answer": answer,
                        "passed": passed,
                    }
                )
                save()
                if view.status != "completed":
                    return False
        return all(item["passed"] for item in report["runs"])
    finally:
        await app.close()
        report["seconds"] = round(time.monotonic() - started, 3)
        save()


def main() -> None:
    """显式联网，产物与样本统一落在隔离目录。 Opt in to network with isolated artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.parse_args()
    root = (
        Path(__file__).resolve().parents[2] / ".artifacts/tests" / ("m6-live-" + uuid4().hex[:12])
    )
    root.mkdir(parents=True)
    print(str(root / "report.json"), flush=True)
    if not asyncio.run(evaluate(root)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
