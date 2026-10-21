"""隔离人工 Trace 的双模型调查、多候选与采用验收，显式联网。

Opt-in dual-model investigation, multiple proposals and adoption from isolated artificial traces.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, load_config, model_config_text, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.evolution.types import (
    EvolutionControl,
    EvolutionSettings,
    EvolutionSource,
    GenerateEvolutionCandidate,
    SaveEvolutionFeedback,
)
from my_agent.execution.environments import inherited_environment
from my_agent.models.types import ModelTurn, TokenUsage
from my_agent.rpc.application import RpcApplication
from my_agent.sessions.types import AssistantCommitted, RequestStarted, RunAccepted, RunFinished
from my_agent.storage import atomic_write

RULES = (
    "# Working rules\nUse concise English.\nNever disclose credentials.\n"
    "Always run the entire repository test suite before every edit.\n"
)
CODE = "def sum_values(values):\n    return sum(values) + 1\n"
CORRECTION = (
    "There are two independent observed issues. The user explicitly wants checks focused on "
    "changed behavior, with broader testing only when justified; the old project rule instead "
    "requires the full suite before every edit. Separately, sum_values([1, 2]) returned 4 instead "
    "of 3, and sum_values([]) returned 1 instead of 0. Find the relevant resources in the target "
    "source project, preserve unrelated requirements, and distinguish a rule correction from "
    "an implementation bug. Evidence comes from another explicitly selected fixture project."
)


async def make_fixture(app, root, model):
    """通过真实单写者存储人工事实，来源项目与采用项目分开。

    Append artificial facts through the real writer, separating source and adoption projects.
    """
    source, target = root / "business-evidence", root / "harness-source"
    source.mkdir(parents=True)
    target.mkdir()
    (source / "fixture-notes.txt").write_text(
        "Artificial acceptance fixture; no personal history or live model execution.\n",
        encoding="utf-8",
    )
    (target / "AGENTS.md").write_text(RULES, encoding="utf-8")
    (target / "calculator.py").write_text(CODE, encoding="utf-8")
    opened = await app.dispatch("projects.open", {"path": str(source)})
    source_pid = opened.active_project.project_id
    session = await app.sessions.create(source_pid, model)
    log = await app.sessions._load(session.session_id)
    limits = load_config(app.storage.location).run
    for prompt, reply in (
        (
            "For this small edit, run only relevant checks. Do not run the whole suite every time.",
            "The current project rule requires the full suite before every edit, so I would run it "
            "unconditionally. This is an artificial trace illustrating the conflicting rule.",
        ),
        (
            "Observed fixture defect: sum_values([1,2]) is 4, expected 3; sum_values([]) is 1, "
            "expected 0. The issue remains unresolved. Correct implementation, not usage advice.",
            "The calculator implementation adds one to sum(values). This artificial observation "
            "records the defect; no correction or verification has been performed in this trace.",
        ),
    ):
        run, message = str(uuid4()), str(uuid4())
        values = [
            RunAccepted(
                operation_id=str(uuid4()), prompt=prompt, limits=limits, requested_limits=None
            ),
            RequestStarted(message_id=message, model_id=model),
            AssistantCommitted(
                message_id=message,
                model_id=model,
                turn=ModelTurn(
                    text=reply,
                    tool_calls=[],
                    native={"role": "assistant", "content": reply},
                    usage=TokenUsage(input_tokens=None, output_tokens=None),
                ),
            ),
            RunFinished(status="completed", code=None, message="Artificial fixture recorded"),
        ]
        for value in values:
            await app.worker.call(app.sessions.store.append, log, value, run)
    selected = EvolutionSource(
        session_id=session.session_id, scope="session", through_seq=log.facts[-1].seq
    )
    opened = await app.dispatch("projects.open", {"path": str(target)})
    target_pid = opened.active_project.project_id
    feedback = await app.sessions.evolution.feedback(
        SaveEvolutionFeedback(
            project_id=target_pid, feedback_id=str(uuid4()), text=CORRECTION, sources=[selected]
        )
    )
    return target_pid, target, feedback.feedback_id, selected


def check_code(target):
    """在隔离目录检查采用后的代码，子进程沿生产筛选移除凭据变量。

    Check adopted code in the isolated directory with production credential filtering.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import runpy,sys; f=runpy.run_path(sys.argv[1])['sum_values']; "
            "assert f([1,2]) == 3; assert f([]) == 0; assert f([-3,1]) == -2",
            str(target / "calculator.py"),
        ],
        cwd=target,
        env=inherited_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


async def evaluate(
    root,
    *,
    prepare_only=False,
    models=None,
    prior_report=None,
    resume_report=None,
    request_budget=16,
):
    """实验共享可调请求预算与10分钟；故障不重试，事实与费用逐步落盘。

    Share an adjustable request budget and ten minutes, saving actual facts without retries.
    """
    report = {
        "fixture_kind": "artificial_trace_real_session_store",
        "requests": [],
        "cases": [],
        "budget": {"requests": request_budget, "seconds": 600, "phases": "shared"},
    }
    started = time.monotonic()
    models = models or ("glm-5.3-flash", "deepseek-v4.1-flash")
    budget_started = time.time()
    if prior_report:
        prior_report = prior_report.resolve()
        previous = json.loads(prior_report.read_text(encoding="utf-8"))
        report["requests"] = previous["requests"]
        report["previous_report"] = str(prior_report)
        report["previous_request_count"] = len(report["requests"])
        stamp = prior_report.parent.stat()
        budget_started = getattr(stamp, "st_birthtime", stamp.st_ctime)
    previous_cases = {}
    data_root = root / "data"
    if resume_report:
        resume_report = resume_report.resolve()
        previous = json.loads(resume_report.read_text(encoding="utf-8"))
        previous_cases = {case["model"]: case for case in previous["cases"]}
        data_root = resume_report.parent / "data"
        report["supplements_report"] = str(resume_report)
        report["reused_isolated_data"] = str(data_root)
    app = RpcApplication(resolve_data_dir(str(data_root)), resolve_credential(), None)
    factory = app.sessions.model_factory
    phase = "preparing"

    def save():
        """只保存隔离结果，不保存凭据和网络请求原文。

        Save isolated outcomes without credentials or raw network requests.
        """
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    class ObservedModel:
        """使用生产网络客户端，只增加实验计量与统一上限。

        Use the production network client with experiment accounting and one shared budget.
        """

        def __init__(self):
            """复用受信模型工厂。 Reuse the trusted model factory."""
            self.client = factory()

        def check_available(self):
            """检查受信客户端，不输出凭据。 Check the client without exposing credentials."""
            self.client.check_available()

        async def complete(self, **kwargs):
            """记录真实请求与解析结果；服务错误立即返回，不自动重试。

            Record actual requests and parsed outcomes, propagating service errors without retries.
            """
            remaining = 600 - (time.time() - budget_started)
            if len(report["requests"]) >= request_budget or remaining <= 0:
                raise AgentError("EVALUATION_BUDGET", "Isolated investigation budget reached")
            row = {"model": kwargs["model_id"], "phase": phase, "status": "started"}
            report["requests"].append(row)
            tick = time.monotonic()
            try:
                async with asyncio.timeout(remaining):
                    turn = await self.client.complete(**kwargs)
                row.update(
                    status="completed",
                    usage=turn.usage.model_dump(),
                    tools=[call.name for call in turn.tool_calls],
                    text=turn.text,
                )
                return turn
            except Exception as exc:
                row.update(
                    status="failed",
                    code=exc.code if isinstance(exc, AgentError) else type(exc).__name__,
                )
                usage = getattr(exc, "usage", None)
                if usage is not None:
                    row["usage"] = usage.model_dump()
                raise
            finally:
                row["seconds"] = round(time.monotonic() - tick, 3)
                save()
                print(
                    json.dumps(
                        {key: value for key, value in row.items() if key != "text"},
                        ensure_ascii=True,
                    ),
                    flush=True,
                )

    app.sessions.model_factory = ObservedModel
    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "m7-investigation-live",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": 1,
            },
        )
        service = app.sessions.evolution
        for model in models:
            case = {"model": model, "passed": False}
            report["cases"].append(case)
            try:
                previous_case = previous_cases.get(model, {})
                previous_review = previous_case.get("investigate", {})
                if previous_review.get("status") == "completed":
                    pid = previous_case["project_id"]
                    target = Path(previous_case["target"])
                    selected = EvolutionSource.model_validate(previous_case["source"])
                    feedback = None
                    review = previous_review["job_id"]
                    phases = ("propose",)
                    case["investigate"] = previous_review
                    case["reused_review_job_id"] = review
                    case["independent_findings"] = len(previous_review["findings"]) >= 2
                else:
                    pid, target, feedback, selected = await make_fixture(app, root / model, model)
                    review = None
                    phases = ("investigate", "propose")
                case.update(project_id=pid, source=selected.model_dump(), target=str(target))
                if prepare_only:
                    case["prepared"] = True
                    continue
                case["baseline_code_check"] = await asyncio.to_thread(check_code, target)
                await app.worker.call(
                    service.store.configure, EvolutionSettings(project_id=pid, model_id=model)
                )
                for phase in phases:
                    config = load_config(app.storage.location)
                    remaining = int(600 - (time.time() - budget_started))
                    available_requests = request_budget - len(report["requests"])
                    if remaining <= 0 or available_requests <= 0:
                        raise AgentError("EVALUATION_BUDGET", "Isolated time budget reached")
                    limits = config.run.model_copy(
                        update={
                            "max_requests": available_requests,
                            "max_seconds": min(240, remaining),
                            "request_timeout_seconds": min(90, remaining),
                            "max_output_tokens": 4096,
                        }
                    )
                    await app.worker.call(
                        atomic_write,
                        config.path,
                        model_config_text(config.model, limits, config.http),
                    )
                    instruction = CORRECTION + (
                        " Investigate only: read the selected evidence and current target files, "
                        "then return independent findings without proposals. "
                        "Batch independent reads and finish with submit_review."
                        if phase == "investigate"
                        else " Continue findings. Propose separate corrections for both issues "
                        "at appropriate resources. Read current targets before returning complete "
                        "replacements. No commands or test claims. Finish with submit_review."
                    )
                    job = await service.generate(
                        GenerateEvolutionCandidate(
                            project_id=pid,
                            mode=phase,
                            review_job_id=review,
                            feedback_ids=[feedback] if review is None and feedback else [],
                            sources=[selected] if review is None else [],
                            instruction=instruction,
                        )
                    )
                    await service.jobs[job.job_id][1]
                    case[phase] = job.model_dump(mode="json")
                    save()
                    if job.status != "completed":
                        case["failure"] = "phase_" + job.status
                        break
                    if phase == "investigate":
                        case["independent_findings"] = len(job.findings) >= 2
                        if not case["independent_findings"]:
                            case["failure"] = "fewer_than_two_findings"
                            break
                    review = job.job_id
                if case.get("failure"):
                    continue
                candidates = [
                    await app.worker.call(service.store.candidate, pid, identity)
                    for identity in job.candidate_ids
                ]
                case["candidates"] = [candidate.model_dump(mode="json") for candidate in candidates]
                targets = {
                    (candidate.target.kind, candidate.target.identity) for candidate in candidates
                }
                case["multiple_targets"] = len(targets) >= 2
                if not case["multiple_targets"]:
                    case["failure"] = "fewer_than_two_targets"
                    continue
                adopted = []
                for candidate in candidates:
                    item = await service.control(
                        EvolutionControl(
                            project_id=pid, candidate_id=candidate.candidate_id, action="apply"
                        )
                    )
                    adopted.append(item.model_dump(mode="json"))
                case["adopted"] = adopted
                rules = (target / "AGENTS.md").read_text(encoding="utf-8")
                case["rules"] = rules
                case["rules_changed"] = rules != RULES
                case["rules_preserved"] = all(
                    rule in rules
                    for rule in ("Use concise English.", "Never disclose credentials.")
                )
                case["unconditional_rule_removed"] = (
                    "Always run the entire repository test suite before every edit." not in rules
                )
                case["code_check"] = await asyncio.to_thread(check_code, target)
                case["passed"] = (
                    case["rules_changed"]
                    and case["rules_preserved"]
                    and case["unconditional_rule_removed"]
                    and case["code_check"]["exit_code"] == 0
                )
            except Exception as exc:
                case["failure"] = exc.code if isinstance(exc, AgentError) else type(exc).__name__
            finally:
                save()
            if len(report["requests"]) >= request_budget or time.time() - budget_started >= 600:
                report["budget_reached"] = True
                break
        return len(report["cases"]) == len(models) and all(
            case.get("prepared") if prepare_only else case["passed"] for case in report["cases"]
        )
    finally:
        await app.close()
        report["seconds"] = round(time.monotonic() - started, 3)
        report["budget_wall_seconds"] = round(time.time() - budget_started, 3)
        save()


def main():
    """联网须明确启用，产物集中到独立测试目录。

    Require explicit network opt-in and keep outputs in a dedicated test directory.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--models", nargs="+", choices=("glm-5.3-flash", "deepseek-v4.1-flash"))
    parser.add_argument("--request-budget", type=int, default=16)
    parser.add_argument(
        "--resume-report",
        type=Path,
        help="Reuse successful isolated investigations; retain original outcomes",
    )
    parser.add_argument(
        "--prior-report", type=Path, help="Continue the same 16-request/10-minute experiment budget"
    )
    args = parser.parse_args()
    if not args.enable_real_models and not args.prepare_only:
        parser.error("Pass --enable-real-models for network acceptance, or --prepare-only")
    root = (
        Path(__file__).resolve().parents[2]
        / ".artifacts/tests"
        / ("m7-investigation-live-" + uuid4().hex[:12])
    )
    root.mkdir(parents=True)
    print(str(root / "report.json"), flush=True)
    if not asyncio.run(
        evaluate(
            root,
            prepare_only=args.prepare_only,
            models=args.models,
            prior_report=args.prior_report,
            resume_report=args.resume_report,
            request_budget=args.request_budget,
        )
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
