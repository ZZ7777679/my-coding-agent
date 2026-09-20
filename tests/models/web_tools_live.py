"""显式验证真实主模型 → Go 搜索 → 网页读取，不替换产品组件。

Opt in to a real main-model, Go search and public-page workflow without component substitutes.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.models.types import ModelId
from my_agent.rpc.application import RpcApplication
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.types import AuxiliaryStarted, ToolCompleted, ToolStarted

ROOT = Path(__file__).resolve().parents[2]


async def run(
    model_id: ModelId, directory: Path, resume: dict[str, object] | None = None
) -> dict[str, object]:
    """隔离项目 / 元数据，以真实 Plan 模式执行一次有界联网请求。

    Isolate project and metadata, running one bounded real Plan-mode web request.
    """
    project = directory / "empty-project"
    project.mkdir(parents=True, exist_ok=True)
    app = RpcApplication(resolve_data_dir(str(directory / "data")), resolve_credential(), None)
    started = time.monotonic()
    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "live-web-check",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": DEFAULTS["data_schema_version"],
            },
        )
        if resume is None:
            opened = await app.dispatch("projects.open", {"path": str(project)})
            created = await app.dispatch(
                "tasks.create",
                {
                    "operation_id": str(uuid4()),
                    "project_id": opened.active_project.project_id,
                    "model_id": model_id,
                    "fields": {"title": "真实联网检查", "goal": "核对 Python 官方 JSON 文档"},
                },
            )
            identity = created.session.session_id
        else:
            identity = resume["session_id"]
            if not isinstance(identity, str):
                raise ValueError("Resume report has no session ID")
        limits = RunLimits.model_validate(
            {
                **DEFAULTS["run"],
                "max_requests": 5,
                "max_tools": 5,
                "max_seconds": 180,
                "request_timeout_seconds": 90,
                "max_output_tokens": 2048,
            }
        )
        await app.sessions.start(
            identity,
            str(uuid4()),
            (
                "使用历史中已经取得的搜索来源继续，不要重复搜索。"
                if resume
                else "请实际调用 web_search 一次，"
                "查询 Python JSON official documentation site:docs.python.org。"
            )
            + "随后用 web_fetch 实际读取一个返回的 Python 官方来源，"
            "简短说明 json.dumps 的用途并附来源 URL。"
            "这是工具接入检查，不读写项目文件、不执行命令、不创建工作报告。"
            "不要只凭已有知识回答。",
            limits,
            "plan",
        )
        active = app.sessions.active_for(identity)
        if active is None or active.task is None:
            raise RuntimeError("No accepted live run")
        await active.task
        view = await app.sessions.view(identity)
        log = app.sessions.store.load(identity)
        cards = [entry.web_result for entry in view.entries if entry.web_result is not None]
        outcome = view.summary.run
        success = (
            outcome is not None
            and outcome.status == "completed"
            and any(card.kind == "web.search" and card.sources for card in cards)
            and any(card.kind == "web.page" and card.content for card in cards)
            and any(entry.kind == "assistant" and entry.text for entry in view.entries)
            and not list(project.iterdir())
        )
        return {
            "result": "passed" if success else "incomplete",
            "model": model_id,
            "session_id": identity,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "run": outcome.model_dump(mode="json") if outcome else None,
            "auxiliary_requests": [
                fact.data.model_dump(mode="json")
                for fact in log.facts
                if isinstance(fact.data, AuxiliaryStarted)
            ],
            "tools": [
                fact.data.call.name for fact in log.facts if isinstance(fact.data, ToolStarted)
            ],
            "tool_errors": [
                json.loads(fact.data.result.content)
                for fact in log.facts
                if isinstance(fact.data, ToolCompleted) and fact.data.result.is_error
            ],
            "sources": [card.model_dump(mode="json") for card in cards],
            "answer": [
                entry.text for entry in view.entries if entry.kind == "assistant" and entry.text
            ],
            "project_unchanged": not list(project.iterdir()),
        }
    finally:
        await app.close()


def main() -> None:
    """真实调用必须显式启用，报告只进入隔离验收目录。

    Require live-call opt-in and retain reports only in an isolated acceptance directory.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument("--resume-report", type=Path)
    args = parser.parse_args()
    if not args.enable_real_models:
        return
    resume = None
    if args.resume_report:
        source = args.resume_report.resolve()
        if not source.is_relative_to((ROOT / ".artifacts/tests").resolve()):
            parser.error("Resume only an isolated test report under .artifacts/tests")
        resume = json.loads(source.read_text(encoding="utf-8"))
        directory = source.parent
    else:
        directory = ROOT / ".artifacts/tests" / ("web-live-" + uuid4().hex[:12])
    report = asyncio.run(run("glm-5.3-flash", directory, resume))
    path = directory / ("report-resume-" + uuid4().hex[:8] + ".json" if resume else "report.json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "result": report["result"],
                "elapsed_seconds": report["elapsed_seconds"],
                "tools": report["tools"],
                "tool_errors": report["tool_errors"],
                "report": str(path),
            },
            ensure_ascii=False,
        )
    )
    if report["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
