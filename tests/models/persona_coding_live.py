"""用普通用户表达评估两种模型的最小代码闭环。

Evaluate a small coding journey with ordinary user instructions on both models.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from my_agent.config import DEFAULTS, load_config, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.memory.types import MemorySettings
from my_agent.models.failures import ModelResponseError
from my_agent.models.go import TurnBuffer
from my_agent.rpc.application import RpcApplication
from my_agent.sessions.types import AssistantCommitted, ToolCompleted, ToolStarted

PROMPT = (
    "请直接在这个空项目里做一个最小 Python 命令行加法器 add.py，"
    "接收两个整数参数并打印和。用 2 和 3 实际运行一次，再用 -2 和 5 运行一次。"
    "只用标准库，不安装依赖，不建立复杂目录。最后简短告诉我文件在哪、怎么用和实际结果。"
)
FOLLOWUP = (
    "沿用现有 add.py，在原文件增加可选 --abs 开关，只在提供该开关时打印和的绝对值。"
    "保留原有两个整数参数的用法。实际运行 -2 -3 --abs 确认得到 5，"
    "再运行 -2 -3 确认原用法仍得到 -5。无需新增文档或报告工具，最后简短报告实际结果。"
)


async def evaluate(
    root: Path,
    resume: bool = False,
    diagnostics: bool = False,
    followup: bool = False,
    finish_report: bool = False,
) -> None:
    """真实服务仅接收隔离项目，初次和明确追加需求分别限十二请求。

    Send isolated material with separate twelve-call initial and explicit follow-up budgets.
    """
    report = (
        json.loads((root / "report.json").read_text(encoding="utf-8"))
        if resume
        else {"prompt": PROMPT, "request_limit": 12, "requests": [], "results": []}
    )
    if followup or finish_report:
        # 追加需求有独立实验预算，先保存原结果，绝不自动重放失败任务。
        # A new assignment has its own evaluation budget; preserve the original report first.
        (root / ("report-before-followup-" + uuid4().hex[:8] + ".json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report["request_limit"] = len(report["requests"]) + (2 if finish_report else 12)
        if followup:
            report["followup_prompt"] = FOLLOWUP
    report["diagnostics"] = diagnostics
    spent = report.get("seconds", 0)
    time_budget = spent + (120 if finish_report else 300) if followup or finish_report else 600
    previous = {row["model"]: row for row in report["results"]}
    started = time.monotonic()
    app = RpcApplication(resolve_data_dir(str(root / "data")), resolve_credential(), None)
    factory = app.sessions.model_factory

    def save() -> None:
        """逐请求保存事实，不保存凭据或原生 provider 状态。

        Save request facts without credentials or native provider state.
        """
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    class ObservedModel:
        """保留生产模型调用，只记录请求数与正文首字时间。

        Keep production model calls while observing request counts and first-text timing.
        """

        def __init__(self) -> None:
            """复用已有模型工厂及连接池。 Reuse the existing factory and pool."""
            self.client = factory()

        def check_available(self) -> None:
            """调用既有凭据检查。 Use the existing credential check."""
            self.client.check_available()

        async def complete(self, **kwargs):
            """观察而不改变模型参数；失败也计入本次评估预算。

            Observe without changing model inputs and count failed attempts too.
            """
            if (
                len(report["requests"]) >= report["request_limit"]
                or spent + time.monotonic() - started >= time_budget
            ):
                raise AgentError("EVALUATION_BUDGET", "Isolated evaluation budget exhausted")
            row = {"model": kwargs["model_id"], "status": "started"}
            if diagnostics:
                row.update(
                    limits=kwargs["limits"].model_dump(),
                    events={},
                    callback_ms={"text": 0.0, "reasoning": 0.0, "progress": 0.0},
                    accept_inclusive_ms=0.0,
                )
            report["requests"].append(row)
            tick = time.monotonic()
            on_text = kwargs["on_text"]

            async def observe_text(delta):
                """正文首字独立计时；不把思考计为正文。

                Time the first answer delta separately from reasoning.
                """
                if delta and "first_text_seconds" not in row:
                    row["first_text_seconds"] = round(time.monotonic() - tick, 3)
                await on_text(delta)

            kwargs["on_text"] = observe_text
            original_accept = TurnBuffer.accept

            async def observe_accept(buffer, value, on_text, limit, on_reasoning=None):
                """只统计事件种类和处理耗时，不保存流原文。

                Count event kinds and processing time without retaining stream payloads.
                """
                choices = value.get("choices") or []
                delta = choices[0].get("delta", {}) if choices else {}
                for kind, key in (
                    ("reasoning", "reasoning_content"),
                    ("text", "content"),
                    ("tool_arguments", "tool_calls"),
                ):
                    if delta.get(key):
                        stats = row["events"].setdefault(
                            kind, {"count": 0, "first_seconds": time.monotonic() - tick}
                        )
                        stats["count"] += 1
                        stats["last_seconds"] = time.monotonic() - tick
                mark = time.perf_counter()
                try:
                    return await original_accept(buffer, value, on_text, limit, on_reasoning)
                finally:
                    row["accept_inclusive_ms"] += (time.perf_counter() - mark) * 1000

            def measured_sink(kind, sink):
                """测量生产回调等待，不向其中引入磁盘写入。

                Time production callbacks without introducing disk writes inside them.
                """

                async def deliver(value):
                    """逐片段交付原回调，保留取消与异常。

                    Deliver each original callback, preserving cancellation and errors.
                    """
                    mark = time.perf_counter()
                    try:
                        if sink is not None:
                            await sink(value)
                    finally:
                        row["callback_ms"][kind] += (time.perf_counter() - mark) * 1000

                return deliver

            if diagnostics:
                for kind in ("text", "reasoning", "progress"):
                    key = "on_" + kind
                    kwargs[key] = measured_sink(kind, kwargs.get(key))
            save()
            try:
                if diagnostics:
                    # 定向观察器仅替换解析入口包装，原生产解析器和参数原样调用。
                    # A scoped observer wraps the production parser without changing its inputs.
                    with patch.object(TurnBuffer, "accept", observe_accept):
                        result = await self.client.complete(**kwargs)
                else:
                    result = await self.client.complete(**kwargs)
                row.update(
                    status="completed",
                    usage=result.usage.model_dump(),
                    tools=[call.name for call in result.tool_calls],
                )
                return result
            except Exception as exc:
                row.update(status="failed", error=type(exc).__name__)
                if isinstance(exc, AgentError):
                    row["code"] = exc.code
                if isinstance(exc, ModelResponseError):
                    row["usage"] = exc.usage.model_dump()
                raise
            finally:
                if diagnostics and self.client.http.last_request is not None:
                    row["progress"] = self.client.http.last_request.progress.model_dump()
                row["seconds"] = round(time.monotonic() - tick, 3)
                save()
                print(json.dumps(row), flush=True)

    app.sessions.model_factory = ObservedModel
    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "user-evaluation",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": 1,
            },
        )
        for model_id in ("glm-5.3-flash", "deepseek-v4.1-flash"):
            prior = previous.get(model_id)
            if (
                prior
                and prior.get("run", {}).get("status") == "completed"
                and not followup
                and not finish_report
            ):
                continue
            if len(report["requests"]) >= report["request_limit"]:
                break
            project = root / model_id / "project"
            if prior:
                sid = prior["session_id"]
            else:
                project.mkdir(parents=True)
                opened = await app.dispatch("projects.open", {"path": str(project)})
                created = await app.dispatch(
                    "tasks.create",
                    {
                        "operation_id": str(uuid4()),
                        "project_id": opened.active_project.project_id,
                        "model_id": model_id,
                        "fields": {"title": "小型加法器", "goal": "直接实现并实际运行加法器"},
                    },
                )
                sid = created.session.session_id
            # 本轮只评价编码闭环，不另消耗自动记忆提取请求。
            # This coding-only sample omits background memory extraction requests.
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            remaining = max(1, int(time_budget - spent - (time.monotonic() - started)))
            configured = load_config(app.storage.location).run
            limits = configured.model_copy(
                update={
                    "max_requests": min(
                        1 if finish_report else 6,
                        report["request_limit"] - len(report["requests"]),
                    )
                    if diagnostics
                    else report["request_limit"] - len(report["requests"]),
                    "max_seconds": min(300, remaining),
                    "request_timeout_seconds": configured.request_timeout_seconds
                    if diagnostics
                    else 120,
                }
            )
            prompt = (
                "刚才的修改和运行已经完成，现在只根据已有工具结果简短报告。"
                "不要调用任何工具，不要再次修改文件或运行命令。"
                if finish_report
                else FOLLOWUP
                if followup
                else "继续完成刚才的任务。"
                if prior
                else PROMPT
            )
            await app.sessions.start(sid, str(uuid4()), prompt, limits, mode="normal")
            try:
                await asyncio.wait_for(app.sessions.active_for(sid).task, min(310, remaining))
            except TimeoutError:
                report["results"].append({"model": model_id, "status": "evaluation_timeout"})
                save()
                break
            view = await app.sessions.view(sid)
            log = await app.sessions._load(sid)
            results = [fact.data for fact in log.facts if isinstance(fact.data, ToolCompleted)]
            result = {
                "model": model_id,
                "supplement": resume,
                "followup": followup,
                "finish_report": finish_report,
                "project": str(project),
                "session_id": sid,
                "run": view.summary.run.model_dump(),
                "tool_names": [
                    fact.data.call.name for fact in log.facts if isinstance(fact.data, ToolStarted)
                ],
                "tool_results": [item.result.model_dump() for item in results],
                "answers": [
                    fact.data.turn.text
                    for fact in log.facts
                    if isinstance(fact.data, AssistantCommitted)
                ],
                "files": [
                    str(path.relative_to(project)) for path in project.rglob("*") if path.is_file()
                ],
            }
            report["results"].append(result)
            save()
            print(json.dumps({"model": model_id, "status": view.summary.run.status}), flush=True)
    finally:
        await app.close()
        report["seconds"] = round(spent + time.monotonic() - started, 3)
        save()


def main() -> None:
    """只有显式调用才运行真实模型，产物集中保存。

    Run live models only on explicit invocation and keep artifacts together.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument("--resume-report", type=Path)
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--followup", action="store_true")
    parser.add_argument("--finish-report", action="store_true")
    args = parser.parse_args()
    if (args.followup or args.finish_report) and not args.resume_report:
        parser.error("Follow-up modes require --resume-report for isolated existing sessions")
    if args.followup and args.finish_report:
        parser.error("Choose a new assignment or a report-only request, not both")
    root = (
        args.resume_report.resolve().parent
        if args.resume_report
        else Path(__file__).resolve().parents[2]
        / ".artifacts/tests"
        / ("persona-coding-live-" + uuid4().hex[:12])
    )
    root.mkdir(parents=True, exist_ok=bool(args.resume_report))
    print(str(root / "report.json"), flush=True)
    asyncio.run(
        evaluate(
            root, bool(args.resume_report), args.diagnostics, args.followup, args.finish_report
        )
    )


if __name__ == "__main__":
    main()
