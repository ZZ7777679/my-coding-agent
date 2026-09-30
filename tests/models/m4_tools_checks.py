"""隔离 M4 双模型验收；十二次请求 / 十五分钟，不自动重试。

Isolated M4 live acceptance: twelve calls/fifteen minutes, without retries.
"""

import argparse
import asyncio
import json
import os
import socket
import sys
import time
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, load_config, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.memory.types import MemorySettings
from my_agent.rpc.application import RpcApplication
from my_agent.sessions.types import ToolCompleted, ToolStarted


async def check(root: Path, resume: bool = False) -> bool:
    """只发送合成项目材料。 Send synthetic project material only."""
    report = {"request_limit": 12, "time_limit_seconds": 900, "requests": [], "results": []}
    previous: dict[str, dict] = {}
    if resume:
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        previous = {row["model"]: row for row in report["results"]}
        report["supplement_from_request"] = len(report["requests"])
        report["request_limit"] = len(report["requests"]) + 6
        report["time_limit_seconds"] = 300
    started = time.monotonic()
    app = RpcApplication(resolve_data_dir(str(root / "data")), resolve_credential(), None)
    factory = app.sessions.model_factory

    def save():
        """调用前后保存计量，不写凭据。

        Save accounting without credentials before and after calls.
        """
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    class Metered:
        """包装现有 Go 客户端。 Meter the existing Go client."""

        def __init__(self):
            """复用连接池。 Reuse the connection pool."""
            self.client = factory()

        def check_available(self):
            """使用生产凭据路径。 Use the production credential path."""
            self.client.check_available()

        async def complete(self, **kwargs):
            """已发送及失败请求均占用预算。 Count sent and failed requests."""
            if (
                len(report["requests"]) >= report["request_limit"]
                or time.monotonic() - started >= report["time_limit_seconds"]
            ):
                raise AgentError("ACCEPTANCE_BUDGET", "Isolated acceptance budget exhausted")
            row = {"model": kwargs["model_id"], "status": "started"}
            report["requests"].append(row)
            save()
            tick = time.monotonic()
            try:
                result = await self.client.complete(**kwargs)
                row.update(
                    status="completed",
                    usage=result.usage.model_dump(),
                    tools=[t.name for t in result.tool_calls],
                )
                return result
            except Exception as exc:
                row.update(status="failed", error=type(exc).__name__)
                raise
            finally:
                row["seconds"] = round(time.monotonic() - tick, 3)
                save()

    app.sessions.model_factory = Metered
    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "acceptance",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": 1,
            },
        )
        for model_id in ("glm-5.3-flash", "deepseek-v4.1-flash"):
            if resume and previous[model_id]["passed"]:
                continue
            project = root / model_id / "project"
            project.mkdir(parents=True, exist_ok=resume)
            (project / "AGENTS.md").write_text(
                "Use one self-contained HTML file. No external assets.\n", encoding="utf-8"
            )
            opened = await app.dispatch("projects.open", {"path": str(project)})
            pid = opened.active_project.project_id
            created = (
                None
                if resume
                else await app.dispatch(
                    "tasks.create",
                    {
                        "operation_id": str(uuid4()),
                        "project_id": pid,
                        "model_id": model_id,
                        "fields": {
                            "title": "M4 counter",
                            "goal": "Build and click a minimal counter",
                        },
                    },
                )
            )
            sid = previous[model_id]["session_id"] if resume else created.session.session_id
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            await app.dispatch(
                "skills.save",
                {
                    "project_id": pid,
                    "name": "counter-check",
                    "overwrite": True,
                    "content": (
                        "---\nname: counter-check\n"
                        "description: Build and verify a minimal counter\n"
                        "---\nCreate one HTML counter with an Add button and count. "
                        "Click once and confirm 0 changes to 1. Save a screenshot. "
                        "Use returned MCP callable names and page references.\n"
                    ),
                },
            )
            if created:
                flow = created.task.workflow.model_copy(deep=True)
                flow.current_stage_id = "implement"
                await app.dispatch(
                    "tasks.workflow",
                    {
                        "task_id": created.task.task_id,
                        "operation_id": str(uuid4()),
                        "expected_revision": created.task.revision,
                        "workflow": flow.model_dump(),
                    },
                )
            if executable := os.environ.get("MY_AGENT_TEST_BROWSER"):
                browser = (
                    app.sessions.mcp.config()
                    .servers[0]
                    .model_copy(update={"browser_executable": executable})
                )
                await app.dispatch("mcp.save", {"project_id": pid, "server": browser.model_dump()})
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            url = f"http://127.0.0.1:{port}/"
            prompt = (
                "Complete this small acceptance task with tools, then answer briefly. "
                "First load user:counter-check and discover browser tools by exact names "
                "browser_navigate, browser_click, browser_take_screenshot, browser_evaluate. "
                + (
                    "index.html already exists; use it without recreating it. "
                    if resume
                    else "Create index.html: a tiny counter, initial count 0, Add button. "
                )
                + "The prior test app exited, so start a preview using start_service with "
                + json.dumps(
                    {
                        "command": {
                            "kind": "program",
                            "program": sys.executable,
                            "arguments": ["-m", "http.server", str(port), "--bind", "127.0.0.1"],
                        },
                        "ready_url": url,
                    }
                )
                + ". Navigate the temporary browser there, click Add once, confirm count 1 "
                "from the actual page result, and save counter.png. Keep the service for the user. "
                "Group independent tool requests in one response where useful. This check has "
                "6 model responses; avoid unrelated exploration or extra reports. "
                "A saved screenshot does not mean you have visually inspected its pixels."
            )
            if resume and "counter.png" in previous[model_id].get("artifacts", []):
                prompt = (
                    "The previous tool round finished the browser verification and saved "
                    "counter.png before the test's request budget was reached. "
                    "Give a brief final answer based on those recorded results. "
                    "The test app has since restarted and stopped the preview; report that fact. "
                    "Do not restart the service, repeat tools, or claim visual pixel inspection."
                )
            remaining = report["time_limit_seconds"] - (time.monotonic() - started)
            limits = load_config(app.storage.location).run.model_copy(
                update={
                    "max_requests": min(6, report["request_limit"] - len(report["requests"])),
                    "max_seconds": max(1, int(min(420, remaining))),
                    "request_timeout_seconds": 120,
                }
            )
            await app.sessions.start(sid, str(uuid4()), prompt, limits, mode="normal")
            await asyncio.wait_for(app.sessions.active_for(sid).task, max(1, remaining))
            view = await app.sessions.view(sid)
            log = await app.sessions._load(sid)
            completed = [f.data.result for f in log.facts if isinstance(f.data, ToolCompleted)]
            names = [f.data.call.name for f in log.facts if isinstance(f.data, ToolStarted)]
            artifacts = await app.dispatch("mcp.list", {"project_id": pid, "session_id": sid})
            passed = (
                view.summary.run.status == "completed"
                and (project / "index.html").is_file()
                and "load_skill" in names
                and "discover_mcp_tools" in names
                and "start_service" in names
                and "counter.png" in artifacts.artifacts
                and any('"browser_click"' in r.content and not r.is_error for r in completed)
            )
            result = {
                "model": model_id,
                "passed": passed,
                "status": view.summary.run.status,
                "code": view.summary.run.code,
                "requests": view.summary.run.requests,
                "tools": view.summary.run.tools,
                "session_id": sid,
                "project_id": pid,
                "artifacts": artifacts.artifacts,
                "tool_names": names,
                "supplement": resume,
            }
            report["results"].append(result)
            save()
            print(json.dumps(result), flush=True)
        latest = {row["model"]: row for row in report["results"]}
        return all(row["passed"] for row in latest.values())
    finally:
        await app.close()
        report["supplement_elapsed_seconds" if resume else "elapsed_seconds"] = round(
            time.monotonic() - started, 3
        )
        save()


def main():
    """真实验收显式启用，默认 CI 不运行。 Require explicit opt-in outside normal CI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument(
        "--resume-report", type=Path, help="Explicit six-call supplement for incomplete models"
    )
    args = parser.parse_args()
    if not args.enable_real_models:
        raise SystemExit("Explicit opt-in required")
    root = (
        args.resume_report.resolve().parent
        if args.resume_report
        else (
            Path(__file__).resolve().parents[2]
            / ".artifacts/tests"
            / ("m4-live-" + uuid4().hex[:12])
        )
    )
    root.mkdir(parents=True, exist_ok=bool(args.resume_report))
    print(str(root / "report.json"), flush=True)
    raise SystemExit(0 if asyncio.run(check(root, bool(args.resume_report))) else 1)


if __name__ == "__main__":
    main()
