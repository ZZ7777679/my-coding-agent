"""仅重放一次模型请求的上下文，不执行工具、不写用户会话，观察停流来源。

Replay one model request context without tools or user-session writes to observe stream failures.
"""

import argparse
import asyncio
import json
import threading
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.models.types import ModelProgress
from my_agent.rpc.application import RpcApplication
from my_agent.runtime.modes import system_prompt
from my_agent.runtime.tools import ToolContext
from my_agent.sessions.store import SessionLog, SessionStore
from my_agent.sessions.types import RunAccepted, SessionCreated
from my_agent.storage import Storage
from my_agent.workflow.methods import load_method
from my_agent.workflow.tools import WorkflowTools

ROOT = Path(__file__).resolve().parents[2]


async def run(source_dir: Path, session_id: str, directory: Path) -> dict[str, object]:
    """读取最后一次普通请求的原始上下文，用生产客户端请求一次，仅保存公开时序。

    Replay the last ordinary request once through the production client, saving only public timing.
    """
    source = SessionStore(Storage(resolve_data_dir(str(source_dir)))).load(session_id)
    if source.issue:
        raise RuntimeError("Source session is incomplete")
    accepted = next(f for f in reversed(source.facts) if isinstance(f.data, RunAccepted))
    header = source.facts[0].data
    start = accepted.data
    if not isinstance(start, RunAccepted) or not isinstance(header, SessionCreated):
        raise RuntimeError("Source request or model unavailable")
    if accepted.run_id is None or start.goal_id is not None or header.task_id is not None:
        raise RuntimeError("This check handles an ordinary, taskless source request only")
    log = SessionLog(source.session_id, [f for f in source.facts if f.seq <= accepted.seq])
    messages, complete = log.context()
    if not complete:
        raise RuntimeError("Source context contains unpaired tools")
    project = directory / "unused-project"
    project.mkdir(parents=True)
    app = RpcApplication(resolve_data_dir(str(directory / "data")), resolve_credential(), None)
    latest = ModelProgress(phase="preparing", elapsed_ms=0)
    samples: list[dict[str, object]] = []
    last_sample_ms = 0.0
    code, message, tool_names = "NOT_CALLED", "", []

    async def observe(value: ModelProgress) -> None:
        """每五秒记录公开计时，不保存或打印请求 / 思考 / 回答正文。

        Sample public timing every five seconds without request, reasoning or response payloads.
        """
        nonlocal latest, last_sample_ms
        changed = latest.phase != value.phase
        latest = value
        if not samples or changed or value.elapsed_ms - last_sample_ms >= 5000:
            samples.append(value.model_dump())
            last_sample_ms = value.elapsed_ms

    async def discard_text(delta: str) -> None:
        """观察时序，不保存模型正文。 Observe timing without retaining answer text."""

    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "request-trace-check",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": DEFAULTS["data_schema_version"],
            },
        )
        context = ToolContext(
            root=project,
            limits=start.limits,
            stop=threading.Event(),
            project_id=header.project_id,
            session_id=source.session_id,
            run_id=accepted.run_id,
            mode=start.mode,
            plan_document=start.plan_document,
        )
        tools = WorkflowTools(context, app.sessions.tool_factory(context), log, app.worker)
        prompt = system_prompt(start.mode, start.plan_document) + tools.request_reference()
        if start.method is not None:
            prompt += "\n\nBundled work method:\n" + load_method(start.method).text
        client = app.sessions.model_factory()
        try:
            turn = await client.complete(
                model_id=header.model_id,
                session_id=source.session_id,
                messages=[{"role": "system", "content": prompt}, *messages],
                tools=tools.definitions(),
                limits=start.limits,
                on_text=discard_text,
                on_progress=observe,
            )
            code = "OK"
            tool_names = [call.name for call in turn.tool_calls]
        except AgentError as error:
            code, message = error.code, error.message
        return {
            "code": code,
            "message": message,
            "model": header.model_id,
            "source_session_id": source.session_id,
            "source_request_seq": accepted.seq,
            "request_count": 1,
            "request_timeout_seconds": start.limits.request_timeout_seconds,
            "final_progress": latest.model_dump(),
            "samples": samples,
            "returned_tool_names": tool_names,
            "executed_tools": 0,
        }
    finally:
        await app.close()


def main() -> None:
    """显式传入只读来源和真实调用开关，报告只保存到集中测试产物目录。

    Require a read-only source and live-call opt-in; keep artifacts in the shared test directory.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument("--source-data-dir", type=Path, required=True)
    parser.add_argument("--source-session", required=True)
    args = parser.parse_args()
    if not args.enable_real_models:
        return
    directory = ROOT / ".artifacts/tests" / ("request-trace-live-" + uuid4().hex[:12])
    report = asyncio.run(run(args.source_data_dir.resolve(), args.source_session, directory))
    path = directory / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, ensure_ascii=False))
    print(str(path))
    if report["code"] != "OK":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
