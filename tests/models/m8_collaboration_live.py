"""M8 显式联网的小型父子编码闭环，仅发送隔离样本。

Opt-in M8 parent/worker coding round with isolated fixture material only.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, load_config, resolve_data_dir
from my_agent.context.types import ContextSettings
from my_agent.credentials import resolve_credential
from my_agent.delegation.types import WorkerSettings
from my_agent.errors import AgentError
from my_agent.memory.types import MemorySettings
from my_agent.rpc.application import RpcApplication


async def evaluate(root: Path, retry_attempts: int = 0, model_id: str | None = None) -> bool:
    """每模型一个只读 worker 和一个文件，不运行用户项目。

    Use one read-only worker and one file per model, never a personal project.
    """
    started = time.monotonic()
    report = {
        "requests": [],
        "runs": [],
        "max_requests": 24,
        "max_seconds": 600,
        "retry_attempts": retry_attempts,
    }
    app = RpcApplication(resolve_data_dir(str(root / "data")), resolve_credential(), None)
    factory = app.sessions.model_factory

    def save():
        """只保存公开计量与隔离结果。 Save public metrics and isolated results only."""
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    class Observed:
        """保留生产传输与共享连接池。 Retain the production transport and pool."""

        def __init__(self):
            """从当前正式工厂取得客户端。 Use the current production factory."""
            self.client = factory()

        def check_available(self):
            """使用当前凭据解析器。 Use the existing credential resolver."""
            self.client.check_available()

        async def complete(self, **kwargs):
            """计实际请求；预算仅限验收脚本。 Count actual requests with evaluation-only limits."""
            if len(report["requests"]) >= 24 or time.monotonic() - started >= 600:
                raise AgentError("EVALUATION_BUDGET", "Isolated evaluation budget exhausted")
            row = {"model": kwargs["model_id"], "status": "started"}
            report["requests"].append(row)
            tick = time.monotonic()
            try:
                result = await self.client.complete(**kwargs)
                row.update(
                    status="completed",
                    tools=[t.name for t in result.tool_calls],
                    usage=result.usage.model_dump(),
                )
                return result
            except AgentError as exc:
                row.update(status="failed", code=exc.code, message=exc.message, phase=exc.phase)
                raise
            finally:
                row["seconds"] = round(time.monotonic() - tick, 3)
                save()

    app.sessions.model_factory = Observed
    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "m8-live-evaluation",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": DEFAULTS["data_schema_version"],
            },
        )
        for model in [model_id] if model_id else DEFAULTS["model"]["allowed_models"]:
            project = root / model
            project.mkdir()
            (project / "note.txt").write_text("VALUE=42\n", encoding="utf-8")
            opened = await app.dispatch("projects.open", {"path": str(project)})
            session = await app.sessions.create(opened.active_project.project_id, model)
            sid = session.session_id
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            await app.sessions.contexts.configure(sid, ContextSettings(automatic=False))
            await app.sessions.delegations.configure(
                sid, WorkerSettings(enabled=True, concurrency=2)
            )
            limits = load_config(app.storage.location).run.model_copy(
                update={
                    "max_requests": 12,
                    "max_tools": 16,
                    "max_seconds": 240,
                    "request_timeout_seconds": 90,
                    "max_output_tokens": 8192,
                    "model_retry_attempts": retry_attempts,
                }
            )
            prompt = (
                "This is a tiny collaboration check. Use exactly one internal research worker "
                "to read note.txt and report VALUE. Discover worker tools if needed. "
                "Read the worker result, then create checked.txt with VALUE=42 and finish "
                "in one sentence. No commands, installs, web, or extra work. Worker should "
                "use read_file once and answer. Do not invent worker results."
            )
            await app.sessions.start(sid, str(uuid4()), prompt, limits, mode="normal")
            active = app.sessions.active_for(sid)
            if active and active.task:
                await active.task
            view = (await app.sessions.view(sid)).summary.run
            workers = await app.sessions.delegations.page(sid)
            target = project / "checked.txt"
            passed = bool(
                view
                and view.status == "completed"
                and target.exists()
                and "42" in target.read_text(encoding="utf-8")
                and len(workers.workers) == 1
                and workers.workers[0].status == "completed"
            )
            report["runs"].append(
                {
                    "model": model,
                    "run": view.model_dump() if view else None,
                    "workers": [w.model_dump() for w in workers.workers],
                    "passed": passed,
                }
            )
            save()
            print(
                json.dumps(
                    {"model": model, "passed": passed, "status": view.status if view else None}
                ),
                flush=True,
            )
        return all(row["passed"] for row in report["runs"])
    finally:
        await app.close()
        report["seconds"] = round(time.monotonic() - started, 3)
        save()


def main() -> None:
    """显式启用真实模型，所有产物归集中测试根。 Opt in with artifacts under the shared test root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument("--retry-attempts", type=int, default=0)
    parser.add_argument("--model", choices=DEFAULTS["model"]["allowed_models"])
    args = parser.parse_args()
    root = (
        Path(__file__).resolve().parents[2] / ".artifacts/tests" / ("m8-live-" + uuid4().hex[:12])
    )
    root.mkdir(parents=True)
    print(str(root / "report.json"), flush=True)
    if not asyncio.run(evaluate(root, args.retry_attempts, args.model)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
