"""压缩第二版的显式双模型验收，仅发送隔离合成材料。

Opt-in dual-model compaction checks using isolated synthetic material only.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.context.service import SUMMARY_PROMPT
from my_agent.context.tokens import estimate_tokens
from my_agent.context.types import ContextSettings
from my_agent.context.window import records
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.memory.types import MemorySettings
from my_agent.models.types import ModelTurn, TokenUsage, ToolCall
from my_agent.rpc.application import RpcApplication
from my_agent.runtime.settings import RunLimits


def call(name, **arguments):
    """准备阶段使用生产工具参数。 Prepare a production tool call for synthetic seeding."""
    return ToolCall(tool_call_id=str(uuid4()), name=name, arguments=arguments)


def turn(*calls, text=""):
    """仅准备阶段构造响应，不把替身当真实验收。 Seed only; never count mocks as live proof."""
    native = {"role": "assistant", "content": text}
    if calls:
        native["tool_calls"] = [
            {
                "id": c.tool_call_id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
            }
            for c in calls
        ]
    return ModelTurn(
        text=text,
        native=native,
        tool_calls=list(calls),
        usage=TokenUsage(input_tokens=None, output_tokens=None),
    )


async def check(root: Path, scenario: str = "readback") -> bool:
    """按场景最多六或十次请求、十分钟，验证摘要及接续，不重试。

    Budget six or ten calls/ten minutes for compaction and continuation, without retries.
    """
    report_path = root / "report.json"
    report = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if report_path.exists()
        else {
            "request_limit": 10 if scenario == "mid-turn" else 6,
            "time_limit_seconds": 600,
            "requests": [],
            "results": [],
        }
    )
    report.setdefault("started_at_unix", root.stat().st_ctime)
    report.setdefault("scenario", scenario)
    scenario = report["scenario"]
    remaining = max(0, 600 - (time.time() - report["started_at_unix"]))
    app = RpcApplication(resolve_data_dir(str(root / "data")), resolve_credential(), None)
    original_factory = app.sessions.model_factory
    real = False
    seed_step = 0

    def save():
        """保存计量和隔离样本输出。 Save metrics and synthetic-sample output."""
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    class MeteredModel:
        """准备样本时使用替身，验收调用生产 Go 客户端。

        Seed with a substitute, then exercise the production Go client.
        """

        def __init__(self):
            """复用客户端和连接池。 Reuse the client and connection pool."""
            self.client = original_factory()

        def check_available(self):
            """真实请求才解析连接能力。 Check availability only for live requests."""
            if real:
                self.client.check_available()

        async def complete(self, **kwargs):
            """记录实际输入与时序，预算内每次调用最多发送一次。

            Record actual inputs/timing and send each budgeted call only once.
            """
            nonlocal seed_step
            if not real:
                seed_step += 1
                if seed_step == 1:
                    return turn(text="Historical inspection notes; no code was changed. " * 600)
                if seed_step == 2:
                    return turn(call("read_file", path="build.log", lines=400))
                if seed_step == 3:
                    return turn(call("read_file", path="notes.txt", lines=100))
                return turn(
                    text="Inspection complete; no repair performed. "
                    "Original tool output is in history."
                )
            count = sum(row["model_id"] == kwargs["model_id"] for row in report["requests"])
            if (
                len(report["requests"]) >= report["request_limit"]
                or count >= report["request_limit"] // 2
            ):
                raise AgentError("LIVE_BUDGET", "Real request budget exhausted")
            row = {
                "model_id": kwargs["model_id"],
                "purpose": "summary"
                if kwargs["messages"][0]["content"] == SUMMARY_PROMPT
                else "continuation",
                "estimated_input_tokens": estimate_tokens([kwargs["messages"], kwargs["tools"]]),
                "status": "started",
                "has_summary": any(
                    "Earlier conversation summary" in str(m.get("content"))
                    for m in kwargs["messages"]
                ),
                "tool_result_count": sum(m.get("role") == "tool" for m in kwargs["messages"]),
            }
            report["requests"].append(row)
            save()
            started = time.monotonic()
            original_text = kwargs["on_text"]

            async def on_text(delta):
                """首字计时独立于思考。 Time first answer text independently of reasoning."""
                if delta and "first_text_seconds" not in row:
                    row["first_text_seconds"] = round(time.monotonic() - started, 3)
                await original_text(delta)

            kwargs["on_text"] = on_text
            try:
                result = await self.client.complete(**kwargs)
                row.update(
                    status="completed",
                    usage=result.usage.model_dump(),
                    tools=[c.name for c in result.tool_calls],
                    text=result.text,
                )
                return result
            except AgentError as exc:
                row.update(status="failed", code=exc.code)
                raise
            finally:
                row["elapsed_seconds"] = round(time.monotonic() - started, 3)
                save()
                print(json.dumps({k: v for k, v in row.items() if k != "text"}), flush=True)

    app.sessions.model_factory = MeteredModel
    try:
        async with asyncio.timeout(remaining):
            await app.dispatch(
                "initialize",
                {
                    "app_version": "compaction-v2-check",
                    "protocol_version": DEFAULTS["protocol_version"],
                    "data_schema_version": 1,
                },
            )
            for model_id in ("glm-5.3-flash", "deepseek-v4.1-flash"):
                result = next((r for r in report["results"] if r["model_id"] == model_id), None)
                if result is not None:
                    if result.get("run_status") or result.get("error"):
                        continue
                    sid = result["session_id"]
                else:
                    real, seed_step = False, 0
                    project = root / model_id
                    project.mkdir()
                    lines = [
                        f"step {i}: build trace " + "ordinary detail " * 12 for i in range(220)
                    ]
                    lines[40] = (
                        "EXACT_ERROR: E_SYNTH_42: missing optional asset violet.css; "
                        "no repair performed"
                    )
                    (project / "build.log").write_text("\n".join(lines), encoding="utf-8")
                    (project / "notes.txt").write_text(
                        "User chose RiverDesk. Reset returns zero. No CDN. Port corrected to 8123.",
                        encoding="utf-8",
                    )
                    opened = await app.dispatch("projects.open", {"path": str(project)})
                    if scenario == "mid-turn":
                        current = [f"active step {i}: " + "tick " * 60 for i in range(200)]
                        current[-1] = "CURRENT_PHASE_READY_88"
                        (project / "active.log").write_text("\n".join(current), encoding="utf-8")
                    created = await app.sessions.create(opened.active_project.project_id, model_id)
                    sid = created.session_id
                    await app.sessions.contexts.configure(sid, ContextSettings(automatic=False))
                    await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
                    for prompt in (
                        "Synthetic project: title RiverDesk; reset returns zero; offline, no CDN. "
                        "Correction: port 8123, not the earlier 8124. Only inspect; "
                        "do not repair anything.",
                        "Inspect the build log and notes. Keep exact errors available in history.",
                    ):
                        await app.sessions.start(sid, str(uuid4()), prompt, None, mode="normal")
                        await app.sessions.active_for(sid).task
                    result = {"model_id": model_id, "session_id": sid}
                    report["results"].append(result)
                log = await app.sessions._load(sid)
                source_seq, source = next(
                    (seq, msg)
                    for seq, msg in records(log)
                    if msg.get("role") == "tool" and "E_SYNTH_42" in str(msg.get("content"))
                )
                offset = max(0, str(source["content"]).index("E_SYNTH_42") - 80)
                original = app.sessions.store.path(sid).read_bytes()
                real = True
                try:
                    if scenario == "readback" and not result.get("summary_applied"):
                        await app.sessions.contexts.start(sid)
                        await app.sessions.contexts.wait(sid)
                        view = await app.sessions.contexts.view(sid)
                        result.update(
                            summary_applied=bool(view.job.compression_applied),
                            before_tokens=view.job.history_before_tokens,
                            after_tokens=view.job.history_after_tokens,
                            raw_history_unchanged=app.sessions.store.path(sid).read_bytes()
                            == original,
                        )
                    if scenario == "readback" and not result["summary_applied"]:
                        continue
                    if scenario == "mid-turn":
                        await app.sessions.contexts.configure(
                            sid, ContextSettings(auto_trigger_tokens=32000)
                        )
                    prompt = (
                        "Continue this synthetic inspection. First make exactly one read_history "
                        "call with query='EXACT_ERROR:', max_chars=400 "
                        "to recover the exact error from the old log. "
                        "Then answer concisely in one final response: project title, reset value, "
                        "offline/CDN requirement, corrected port, exact error code and asset, "
                        "and whether any repair was performed. "
                        "No other tools, no edits, no memory writes and no additional requests."
                    )
                    limits = RunLimits.model_validate(
                        {
                            **DEFAULTS["run"],
                            "max_requests": 4 if scenario == "mid-turn" else 2,
                            "max_tool_bytes": 131072
                            if scenario == "mid-turn"
                            else DEFAULTS["run"]["max_tool_bytes"],
                            "max_seconds": 240,
                        }
                    )
                    if scenario == "mid-turn":
                        prompt = (
                            "Continue this synthetic inspection in this exact order: "
                            "First call read_file(path='active.log', lines=220). "
                            "Do not combine tools; wait for its result. "
                            f"Next call read_history(entry_seq={source_seq}, offset={offset}, "
                            "max_chars=400) to recover the exact old error. "
                            "Then answer once: project title, reset value, "
                            "offline/CDN requirement, "
                            "corrected port, exact error code and asset, any repairs performed, "
                            "and final CURRENT_PHASE marker from active.log. "
                            "No other tools, edits, memory writes or requests."
                        )
                    await app.sessions.start(sid, str(uuid4()), prompt, limits, mode="normal")
                    await app.sessions.active_for(sid).task
                    completed = await app.sessions.view(sid)
                    result["run_status"] = completed.summary.run.status
                    if scenario == "mid-turn":
                        view = await app.sessions.contexts.view(sid)
                        result.update(
                            summary_applied=bool(view.job and view.job.compression_applied),
                            automatic=bool(view.job and view.job.mode == "automatic"),
                            before_tokens=view.job.history_before_tokens if view.job else None,
                            after_tokens=view.job.history_after_tokens if view.job else None,
                            retained_tokens=view.job.retained_tokens if view.job else None,
                            raw_history_unchanged=app.sessions.store.path(sid)
                            .read_bytes()
                            .startswith(original),
                        )
                    rows = [
                        r
                        for r in report["requests"]
                        if r["model_id"] == model_id and r["purpose"] == "continuation"
                    ]
                    answer = rows[-1].get("text", "") if rows else ""
                    result["source_readback"] = any(
                        "read_history" in r.get("tools", []) for r in rows
                    )
                    result["answer"] = answer
                    result["exact_details_present"] = all(
                        term in answer for term in ("RiverDesk", "8123", "E_SYNTH_42", "violet.css")
                    )
                    if scenario == "mid-turn":
                        result["fresh_result_retained"] = "CURRENT_PHASE_READY_88" in answer
                        result["paired_tail_after_compaction"] = any(
                            r.get("has_summary") and r.get("tool_result_count", 0) > 0 for r in rows
                        )
                        if result["run_status"] == "completed":
                            await app.sessions.start(
                                sid,
                                str(uuid4()),
                                "New correction: use port 8127 from now on. "
                                "Confirm only the new port and project title, without tools.",
                                limits.model_copy(update={"max_requests": 1}),
                                mode="normal",
                            )
                            await app.sessions.active_for(sid).task
                            result["new_correction"] = "8127" in report["requests"][-1].get(
                                "text", ""
                            )
                except AgentError as exc:
                    result["error"] = exc.code
                finally:
                    save()
    except TimeoutError:
        report["error"] = "TIME_BUDGET_EXCEEDED"
    finally:
        await app.close()
        save()
        print(root / "report.json", flush=True)
    return len(report["results"]) == 2 and all(
        r.get("summary_applied")
        and r.get("raw_history_unchanged")
        and r.get("source_readback")
        and r.get("exact_details_present")
        and r.get("run_status") == "completed"
        and (
            scenario != "mid-turn"
            or (
                r.get("automatic")
                and r.get("fresh_result_retained")
                and r.get("paired_tail_after_compaction")
                and r.get("new_correction")
            )
        )
        for r in report["results"]
    )


def main():
    """仅显式启用后使用现有凭据。 Use existing credentials only with explicit opt-in."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", required=True, action="store_true")
    parser.add_argument("--resume-report", type=Path)
    parser.add_argument("--scenario", choices=("readback", "mid-turn"), default="readback")
    args = parser.parse_args()
    root = (
        args.resume_report.resolve().parent
        if args.resume_report
        else (
            Path(__file__).resolve().parents[2]
            / ".artifacts/tests"
            / ("compaction-v2-live-" + uuid4().hex[:12])
        )
    )
    root.mkdir(parents=True, exist_ok=bool(args.resume_report))
    raise SystemExit(0 if asyncio.run(check(root, args.scenario)) else 1)


if __name__ == "__main__":
    main()
