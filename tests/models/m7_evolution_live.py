"""双模型隔离资源／代码改进验收，显式联网。

Opt-in dual-model resource/code evolution acceptance using isolated fixtures.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, load_config, resolve_data_dir
from my_agent.context.types import ContextSettings
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.evolution.types import (
    EvolutionControl,
    EvolutionExperimentParams,
    EvolutionSettings,
    EvolutionTarget,
    GenerateEvolutionCandidate,
)
from my_agent.execution.types import ProgramCommand, RunCommandArgs
from my_agent.memory.types import MemorySettings
from my_agent.rpc.application import RpcApplication
from my_agent.sessions.types import AssistantCommitted, RequestStarted


async def evaluate(root: Path) -> bool:
    """最多八请求，原项目与个人会话完全不参与。

    Use at most eight requests without involving personal projects or historical conversations.
    """
    report = {"requests": [], "cases": []}
    start = time.monotonic()
    app = RpcApplication(resolve_data_dir(str(root / "data")), resolve_credential(), None)
    factory = app.sessions.model_factory

    def save():
        """仅保存隔离样本结果及用量。 Save isolated results and usage only."""
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    class ObservedModel:
        """测量生产客户端，不替换网络或响应解析。 Observe the real client and response parser."""

        def __init__(self):
            """共享原生产工厂。 Reuse the production factory."""
            self.client = factory()

        def check_available(self):
            """只使用受信凭据入口。 Use the trusted credential boundary."""
            self.client.check_available()

        async def complete(self, **kwargs):
            """预算仅用于本次实验，错误不自动重试。

            Apply experiment-only budgets without retries.
            """
            if len(report["requests"]) >= 8 or time.monotonic() - start > 600:
                raise AgentError("EVALUATION_BUDGET", "Isolated test budget reached")
            kwargs["limits"] = kwargs["limits"].model_copy(
                update={
                    "request_timeout_seconds": 90,
                    "max_output_tokens": 4096,
                }
            )
            row = {"model": kwargs["model_id"], "status": "started"}
            report["requests"].append(row)
            tick = time.monotonic()
            try:
                result = await self.client.complete(**kwargs)
                row.update(status="completed", usage=result.usage.model_dump())
                return result
            except Exception as exc:
                row.update(
                    status="failed",
                    code=exc.code if isinstance(exc, AgentError) else type(exc).__name__,
                )
                raise
            finally:
                row["seconds"] = round(time.monotonic() - tick, 3)
                save()
                print(json.dumps(row, ensure_ascii=True), flush=True)

    app.sessions.model_factory = ObservedModel
    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "m7-live",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": 1,
            },
        )
        service = app.sessions.evolution
        for model in ("glm-5.3-flash", "deepseek-v4.1-flash"):
            project = root / model
            project.mkdir()
            rules = "Use simple language. Do not modify files unless the request asks for it.\n"
            original = "def sum_values(values):\n    return sum(values) + 1\n"
            (project / "AGENTS.md").write_text(rules, encoding="utf-8")
            (project / "calculator.py").write_text(original, encoding="utf-8")
            opened = await app.dispatch("projects.open", {"path": str(project)})
            pid = opened.active_project.project_id
            await app.worker.call(
                service.store.configure, EvolutionSettings(project_id=pid, model_id=model)
            )
            marker = "M7-GLM" if model.startswith("glm") else "M7-DS"
            row = {"model": model, "passed": False}
            report["cases"].append(row)
            for kind, name, instruction in (
                (
                    "project_rule",
                    "AGENTS.md",
                    f"Preserve existing rules. Add that every answer starts with {marker}. "
                    "Keep under 80 words.",
                ),
                (
                    "code",
                    "calculator.py",
                    "Fix the off-by-one error: sum_values([1,2]) must return 3. "
                    "Keep the function name.",
                ),
            ):
                job = await service.generate(
                    GenerateEvolutionCandidate(
                        project_id=pid,
                        target=EvolutionTarget(kind=kind, identity=name),
                        instruction=instruction,
                    )
                )
                await service.jobs[job.job_id][1]
                row[kind] = job.model_dump(mode="json")
                if job.status != "completed":
                    return False
                if kind == "code":
                    experiment = await service.experiment(
                        EvolutionExperimentParams(
                            project_id=pid,
                            candidate_id=job.candidate_id,
                            command=RunCommandArgs(
                                command=ProgramCommand(
                                    kind="program",
                                    program=sys.executable,
                                    arguments=[
                                        "-c",
                                    "from calculator import sum_values; "
                                    "assert sum_values([1,2]) == 3",
                                    ],
                                )
                            ),
                        )
                    )
                    await service.jobs[experiment.job_id][1]
                    row["experiment"] = experiment.model_dump(mode="json")
                    if experiment.status != "completed" or [
                        p.summary.exit_code for p in experiment.programs
                    ] != [1, 0]:
                        return False
                await service.control(
                    EvolutionControl(project_id=pid, candidate_id=job.candidate_id, action="apply")
                )
                if kind == "code":
                    await service.control(
                        EvolutionControl(
                            project_id=pid, candidate_id=job.candidate_id, action="revert"
                        )
                    )
                    if (project / name).read_text(encoding="utf-8") != original:
                        return False
            session = await app.sessions.create(pid, model)
            await app.sessions.memory.configure(session.session_id, MemorySettings(automatic=False))
            await app.sessions.contexts.configure(
                session.session_id, ContextSettings(automatic=False)
            )
            limits = load_config(app.storage.location).run.model_copy(
                update={"max_requests": 1, "max_seconds": 120}
            )
            await app.sessions.start(
                session.session_id,
                str(uuid4()),
                "Explain in one short sentence that you follow this project's rules. No tools.",
                limits,
                mode="plan",
            )
            await app.sessions.active_for(session.session_id).task
            log = await app.sessions._load(session.session_id)
            answers = [
                f.data.turn.text for f in log.facts if isinstance(f.data, AssistantCommitted)
            ]
            requests = [f.data for f in log.facts if isinstance(f.data, RequestStarted)]
            row["answer"] = answers[-1] if answers else ""
            row["rules_in_manifest"] = any(
                r.context
                and any(
                    m.kind == "project_rules" and marker in m.preview for m in r.context.materials
                )
                for r in requests
            )
            row["passed"] = row["rules_in_manifest"] and marker in row["answer"]
            save()
        return all(row["passed"] for row in report["cases"])
    finally:
        await app.close()
        report["seconds"] = round(time.monotonic() - start, 3)
        save()


def main():
    """明确选择联网，结果集中保存。 Require opt-in network use and centralize outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.parse_args()
    root = (
        Path(__file__).resolve().parents[2] / ".artifacts/tests" / ("m7-live-" + uuid4().hex[:12])
    )
    root.mkdir(parents=True)
    print(str(root / "report.json"), flush=True)
    if not asyncio.run(evaluate(root)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
