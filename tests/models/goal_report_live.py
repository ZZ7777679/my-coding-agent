"""显式验证真实 GLM 小 Goal 的文件与逐项报告，隔离用户数据。

Opt in to a real GLM small-goal file and criterion-report check, isolated from user data.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.goals.types import GoalBudget, GoalCreated, GoalCriterion
from my_agent.rpc.application import RpcApplication
from my_agent.rpc.dto import ProjectsView
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.types import ToolCompleted, ToolStarted

ROOT = Path(__file__).resolve().parents[2]


async def run(directory: Path) -> dict[str, object]:
    """真实调用生产 Goal / 文件工具，用自然需求检查完整报告，不预写模型答案。

    Exercise production goals and file tools with a natural request, not a prewritten model report.
    """
    project = directory / "empty-project"
    project.mkdir(parents=True)
    app = RpcApplication(resolve_data_dir(str(directory / "data")), resolve_credential(), None)
    started = time.monotonic()
    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "live-goal-report-check",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": DEFAULTS["data_schema_version"],
            },
        )
        opened = await app.dispatch("projects.open", {"path": str(project)})
        if not isinstance(opened, ProjectsView) or opened.active_project is None:
            raise RuntimeError("Isolated project not opened")
        session = await app.sessions.create(opened.active_project.project_id, "glm-5.3-flash")
        goals = app.sessions.goals
        if goals is None:
            raise RuntimeError("Goal service not composed")
        await goals.create(
            session.session_id,
            GoalCreated(
                goal_id=str(uuid4()),
                objective="先想好怎么做，再完成这个小页面。只需保存 HTML，不启动服务或安装依赖。",
                criteria=[
                    GoalCriterion(
                        criterion_id="criterion-1",
                        description=(
                            "生成一个简单加法计算器 index.html，包含两个数字输入框、"
                            "一个计算按钮和结果区域，用原生 HTML/JS。"
                        ),
                    )
                ],
                budget=GoalBudget(max_requests=5, max_tools=8, max_active_seconds=180),
                limits=RunLimits.model_validate(
                    {
                        **DEFAULTS["run"],
                        "max_requests": 5,
                        "max_tools": 8,
                        "max_seconds": 180,
                        "request_timeout_seconds": 90,
                        "max_output_tokens": 4096,
                    }
                ),
            ),
        )
        driver = goals.driver(session.session_id)
        if driver is None or driver.task is None:
            raise RuntimeError("Goal driver not started")
        await driver.task
        goal = (await goals.list(session.session_id))[0]
        view = await app.sessions.view(session.session_id)
        log = app.sessions.store.load(session.session_id)
        page = project / "index.html"
        passed = (
            goal.status == "completed"
            and goal.last_report is not None
            and len(goal.last_report.criteria) == 1
            and goal.last_report.criteria[0].criterion_id == "criterion-1"
            and goal.last_report.criteria[0].status == "met"
            and page.is_file()
            and page.stat().st_size > 0
        )
        return {
            "result": "passed" if passed else "incomplete",
            "model": "glm-5.3-flash",
            "session_id": session.session_id,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "goal": goal.model_dump(mode="json"),
            "run": view.summary.run.model_dump(mode="json") if view.summary.run else None,
            "tools": [
                fact.data.call.name for fact in log.facts if isinstance(fact.data, ToolStarted)
            ],
            "tool_errors": [
                json.loads(fact.data.result.content)
                for fact in log.facts
                if isinstance(fact.data, ToolCompleted) and fact.data.result.is_error
            ],
            "scope": "File creation and Goal reporting; no browser or arithmetic acceptance.",
        }
    finally:
        await app.close()


def main() -> None:
    """只在显式启用时消耗额度，报告归集中产物目录，不自动重试。

    Spend quota only on explicit opt-in, keeping centralized artifacts without automatic retries.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    args = parser.parse_args()
    if not args.enable_real_models:
        return
    directory = ROOT / ".artifacts/tests" / ("goal-report-live-" + uuid4().hex[:12])
    report = asyncio.run(run(directory))
    path = directory / "report.json"
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
