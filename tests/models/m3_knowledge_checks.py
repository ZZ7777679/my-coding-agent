"""显式授权的 M3 双模型摘要与记忆验收，仅使用隔离样本。

Opt-in M3 compaction/memory checks using isolated synthetic samples only.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.context.types import ContextSettings
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.memory.types import MemoryQuery, MemorySettings
from my_agent.models.types import ModelTurn, TokenUsage
from my_agent.rpc.application import RpcApplication


async def check(root: Path) -> bool:
    """最多八次真实请求、十分钟；失败不重试，保存实际计量。

    Allow at most eight requests and ten minutes, recording actual use without retries.
    """
    report: dict = {"request_limit": 8, "time_limit_seconds": 600, "requests": [], "results": []}
    app = RpcApplication(resolve_data_dir(str(root / "data")), resolve_credential(), None)
    original_factory = app.sessions.model_factory
    real = False

    def save() -> None:
        """仅写时序、用量和公开结果。

        Write timings, usage and public results only.
        """
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    class MeteredModel:
        """样本准备不调用网络；正式阶段复用真实 Go 客户端。

        Prepare samples locally, then use the actual Go client for verification.
        """

        def __init__(self):
            """复用真实客户端装配。

            Reuse the real client composition.
            """
            self.client = original_factory()

        def check_available(self):
            """仅正式验收要求凭据。

            Require credentials only during live checks.
            """
            if real:
                self.client.check_available()

        async def complete(self, **kwargs):
            """切换模拟准备和有预算的真实请求。

            Switch between setup and budgeted live requests.
            """
            if not real:
                text = (
                    "Observed: counter starts at zero; reset returns to zero. Use "
                    "Python standard library and bundled assets; no CDN. "
                ) * 90
                return ModelTurn(
                    text=text,
                    tool_calls=[],
                    native={"role": "assistant", "content": text},
                    usage=TokenUsage(input_tokens=None, output_tokens=None),
                )
            if len(report["requests"]) >= 8:
                raise AgentError("LIVE_BUDGET", "Real request budget exhausted")
            row = {
                "model_id": kwargs["model_id"],
                "purpose": "memory"
                if kwargs["messages"][0]["content"].startswith("Extract only reusable")
                else "compaction",
                "status": "started",
            }
            report["requests"].append(row)
            save()
            started = time.monotonic()
            original_text = kwargs["on_text"]

            async def on_text(delta):
                """记录正文首字并转发内容。

                Record first text and forward content.
                """
                if delta and "first_text_seconds" not in row:
                    row["first_text_seconds"] = round(time.monotonic() - started, 3)
                await original_text(delta)

            kwargs["on_text"] = on_text
            try:
                result = await self.client.complete(**kwargs)
                row.update(
                    status="completed",
                    usage=result.usage.model_dump(),
                    output_chars=len(result.text),
                )
                return result
            except AgentError as exc:
                row.update(status="failed", code=exc.code)
                raise
            finally:
                row["elapsed_seconds"] = round(time.monotonic() - started, 3)
                save()
                print(json.dumps(row, ensure_ascii=False), flush=True)

    app.sessions.model_factory = MeteredModel
    try:
        async with asyncio.timeout(600):
            await app.dispatch(
                "initialize",
                {
                    "app_version": "m3-check",
                    "protocol_version": DEFAULTS["protocol_version"],
                    "data_schema_version": 1,
                },
            )
            for model_id in ("glm-5.3-flash", "deepseek-v4.1-flash"):
                real = False
                project = root / model_id
                project.mkdir()
                opened = await app.dispatch("projects.open", {"path": str(project)})
                created = await app.sessions.create(opened.active_project.project_id, model_id)
                sid = created.session_id
                await app.sessions.contexts.configure(sid, ContextSettings(automatic=False))
                await app.sessions.memory.configure(
                    sid, MemorySettings(automatic=False, maintenance_requests=1)
                )
                for index in range(4):
                    await app.sessions.start(
                        sid,
                        str(uuid4()),
                        f"Synthetic project fact {index}: use Python standard library; "
                        "counter offline, reset to zero.",
                        None,
                        mode="normal",
                    )
                    await app.sessions.active_for(sid).task
                original = app.sessions.store.path(sid).read_bytes()
                real = True
                result = {"model_id": model_id}
                try:
                    await app.sessions.contexts.start(sid)
                    await app.sessions.contexts.wait(sid)
                    view = await app.sessions.contexts.view(sid)
                    result["compaction"] = bool(view.checkpoint and view.checkpoint.text.strip())
                    result["raw_history_unchanged"] = (
                        app.sessions.store.path(sid).read_bytes() == original
                    )
                except AgentError as exc:
                    result["compaction_error"] = exc.code
                await app.sessions.memory.start(sid, after_seq=0)
                await asyncio.gather(*list(app.sessions.memory.jobs.values()))
                page = await app.sessions.memory.page(sid, MemoryQuery())
                result["memory_status"] = page.state.job.status if page.state.job else "missing"
                result["memory_count"] = len(page.entries)
                result["memory_message"] = page.state.job.message if page.state.job else ""
                report["results"].append(result)
                save()
                print(json.dumps(result, ensure_ascii=False), flush=True)
    except TimeoutError:
        report["error"] = "TIME_BUDGET_EXCEEDED"
    finally:
        await app.close()
        save()
        print(root / "report.json", flush=True)
    return len(report["results"]) == 2 and all(
        item.get("compaction")
        and item.get("raw_history_unchanged")
        and item.get("memory_status") == "completed"
        and item.get("memory_count", 0) > 0
        for item in report["results"]
    )


def main() -> None:
    """只接受显式真实模型开关。

    Require explicit real-model opt-in.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", required=True, action="store_true")
    parser.parse_args()
    root = (
        Path(__file__).resolve().parents[2] / ".artifacts/tests" / ("m3-models-" + uuid4().hex[:12])
    )
    root.mkdir(parents=True)
    raise SystemExit(0 if asyncio.run(check(root)) else 1)


if __name__ == "__main__":
    main()
