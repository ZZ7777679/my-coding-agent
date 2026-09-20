"""显式启用且有预算的真实双模型工具验收。 Explicit, budgeted real-model tool acceptance."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from my_agent.bootstrap import build_sessions
from my_agent.config import load_config, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.models.types import ModelId
from my_agent.projects import ProjectService
from my_agent.sessions.types import AssistantCommitted, RequestStarted, ToolCompleted
from my_agent.storage import Storage
from my_agent.worker import BusinessWorker

ROOT = Path(__file__).resolve().parents[2]


async def verify(model_id: ModelId, root: Path, resume: Path | None = None) -> dict[str, object]:
    """在无秘密的隔离项目中执行至多三个请求。 Use at most three requests on an isolated fixture."""
    data_root = resume.parents[1] if resume else root / model_id / "data"
    project = data_root.parent / "project"
    source = 'def read_timeout(options):\n    return options.get("timeout") or 30\n'
    if resume is None:
        project.mkdir(parents=True)
        (project / "main.py").write_text(source, encoding="utf-8", newline="\n")
    elif not resume.resolve().is_relative_to(ROOT / ".artifacts/tests"):
        raise SystemExit("Only isolated acceptance sessions may be resumed")
    storage = Storage(resolve_data_dir(str(data_root)))
    worker = BusinessWorker()
    service = build_sessions(storage, worker, resolve_credential())
    try:
        with storage.writer():
            view = ProjectService(storage).open(path=str(project))
            assert view.active_project is not None
            if resume is None:
                session = await service.create(view.active_project.project_id, model_id)
                remaining = 3
                prompt = (
                    "Read main.py using read_file. Explain why passing timeout=0 returns 30, "
                    "cite the file and line, and suggest the minimal correction. "
                    "Do not edit files or run commands."
                )
            else:
                session = (await service.view(resume.name)).summary
                if session.model_id != model_id:
                    raise SystemExit("Resume model mismatch")
                previous = service.store.load(session.session_id)
                remaining = 3 - sum(isinstance(f.data, RequestStarted) for f in previous.facts)
                if remaining <= 0:
                    raise SystemExit("Acceptance request budget exhausted")
                prompt = (
                    "Continue using the completed read_file results already in this conversation. "
                    "Do not call tools again. Explain why timeout=0 returns 30, "
                    "cite main.py and the line, and suggest the minimal correction."
                )
            limits = load_config(storage.location).run.model_copy(
                update={
                    "max_requests": remaining,
                    "max_tools": 3,
                    "max_seconds": 180,
                    "request_timeout_seconds": 160,
                    "max_output_tokens": 4096,
                }
            )
            await service.start(
                session.session_id,
                str(uuid4()),
                prompt,
                limits,
            )
            active = service.active_for(session.session_id)
            assert active is not None and active.task is not None
            await active.task
            result = await service.view(session.session_id)
            log = service.last_log
            assert log is not None
            tools = [fact.data for fact in log.facts if isinstance(fact.data, ToolCompleted)]
            turns = [fact.data for fact in log.facts if isinstance(fact.data, AssistantCommitted)]
            answer = turns[-1].turn.text if turns else ""
            run = result.summary.run
            assert run is not None
            passed = (
                run.status == "completed"
                and any(
                    not tool.result.is_error and "options.get" in tool.result.content
                    for tool in tools
                )
                and "main.py" in answer
                and "0" in answer
                and "30" in answer
                and (project / "main.py").read_text(encoding="utf-8") == source
            )
            # 公开结果只记录用量与结果；原生回合留在忽略提交的隔离数据根。
            # Report public counts/outcomes; native turns remain in ignored isolated storage.
            return {
                "model": model_id,
                "passed": passed,
                "status": run.status,
                "code": run.code,
                "message": run.message,
                "requests": run.requests,
                "total_session_requests": sum(
                    isinstance(f.data, RequestStarted) for f in log.facts
                ),
                "explicit_retry": resume is not None,
                "tools": run.tools,
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "session_id": session.session_id,
                "answer": answer,
            }
    finally:
        await service.close()
        worker.close()


def main() -> None:
    """必须显式启用真实模型；不属于默认 pytest / CI。 Require explicit opt-in outside default CI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument("--model", choices=["glm-5.3-flash", "deepseek-v4.1-flash"])
    parser.add_argument("--resume-session-dir", type=Path)
    args = parser.parse_args()
    if not args.enable_real_models:
        raise SystemExit("Explicit opt-in required")
    root = ROOT / ".artifacts/tests" / ("go-roundtrip-" + uuid4().hex[:12])
    root.mkdir(parents=True)
    reports = []
    if args.resume_session_dir and not args.model:
        parser.error("--resume-session-dir requires --model")
    for model_id in [args.model] if args.model else ["glm-5.3-flash", "deepseek-v4.1-flash"]:
        report = asyncio.run(verify(model_id, root, args.resume_session_dir))
        reports.append(report)
        (root / "report.json").write_text(
            json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {key: value for key, value in report.items() if key != "answer"}, ensure_ascii=True
            ),
            flush=True,
        )
    print(str(root / "report.json"), flush=True)
    if not all(report["passed"] for report in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
