"""显式启用的 M5 双模型图片验收，全部材料为隔离合成图片。

Opt-in M5 image acceptance for both models using only isolated synthetic images.
"""

import argparse
import asyncio
import base64
import json
import random
import struct
import time
import zlib
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.context.types import ContextSettings
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.memory.types import MemorySettings
from my_agent.models.types import (
    JsonObject,
    ModelId,
    ModelProgress,
    ModelTurn,
    ProgressSink,
    TextSink,
    TokenUsage,
)
from my_agent.rpc.application import RpcApplication
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.types import AssistantCommitted


def png_chunk(kind: bytes, data: bytes) -> bytes:
    """写标准 PNG 数据块，不依赖图像库。 Encode a standard PNG chunk without image libraries."""
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def synthetic_image(path: Path) -> dict[str, str]:
    """随机排列四种颜色与中心白圆，答案不写入文件名或提示词。

    Randomize quadrant colors and a white circle; keep answers out of filenames and prompts.
    """
    palette = {
        "red": (230, 30, 30),
        "green": (30, 190, 60),
        "blue": (30, 70, 230),
        "yellow": (245, 215, 20),
    }
    colors = list(palette)
    random.SystemRandom().shuffle(colors)
    width, height = 360, 240
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # PNG filter None
        for x in range(width):
            quadrant = (2 if y >= height // 2 else 0) + (1 if x >= width // 2 else 0)
            distance = (x - width // 2) ** 2 + (y - height // 2) ** 2
            pixel = (255, 255, 255) if distance < 32**2 else palette[colors[quadrant]]
            if 32**2 <= distance < 35**2:
                pixel = (0, 0, 0)
            rows.extend(pixel)
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(bytes(rows))) + png_chunk(b"IEND", b"")
    path.write_bytes(png)
    return {
        **dict(zip(("top_left", "top_right", "bottom_left", "bottom_right"), colors, strict=True)),
        "center_shape": "circle",
        "center_color": "white",
    }


def image_count(messages: list[JsonObject]) -> int:
    """只计当前请求图片块，不打印 URL 或 Base64。 Count image blocks without logging their data."""
    count = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            count += sum(
                isinstance(part, dict) and part.get("type") == "image_url" for part in content
            )
    return count


def parsed_answer(text: str) -> dict[str, str] | None:
    """提取模型实际 JSON 回答，不以 HTTP 成功代替视觉理解。 Parse actual image observations."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
        return None
    return {k: v.strip().lower() for k, v in value.items()}


async def check(root: Path, request_limit: int, time_limit_seconds: int) -> bool:
    """走生产 RPC、附件与 Go 客户端，并用离线续接核对原图不会自动重带。

    Exercise production RPC, attachments and Go; verify no replay with offline followups.
    """
    started = time.monotonic()
    credential = resolve_credential()
    if credential.secret is None:
        raise AgentError("CREDENTIAL_UNAVAILABLE", "图片验收没有可用凭据；未发送请求。")
    app = RpcApplication(resolve_data_dir(str(root / "data")), credential, None)
    factory = app.sessions.model_factory
    requests: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    report: dict[str, object] = {
        "request_limit": request_limit,
        "time_limit_seconds": time_limit_seconds,
        "scope": "synthetic_images_only_no_retries",
        "requests": requests,
        "results": results,
    }
    report_path = root / "report.json"
    offline = False

    def save() -> None:
        """只保存公开用量、结果与图像验收事实。

        Persist public accounting and image evidence only.
        """
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    class ObservedClient:
        """包装真实 Go 调用，离线续接明确标为模拟。

        Wrap real Go calls and label offline followups.
        """

        def __init__(self) -> None:
            """复用生产连接池与凭据构造路径。

            Reuse production connection and credential construction.
            """
            self.client = factory()

        def check_available(self) -> None:
            """仅使用生产可用性检查。 Use the production availability check."""
            self.client.check_available()

        async def complete(
            self,
            *,
            model_id: ModelId,
            session_id: str,
            messages: list[JsonObject],
            tools: list[JsonObject],
            limits: RunLimits,
            on_text: TextSink,
            on_progress: ProgressSink | None = None,
            on_reasoning: TextSink | None = None,
        ) -> ModelTurn:
            """真实请求前保存计数，后续模拟只观察图片块数量。

            Count live calls and inspect offline blocks.
            """
            row: dict[str, object] = {
                "model_id": model_id,
                "session_id": session_id,
                "images": image_count(messages),
                "offline": offline,
                "status": "started",
            }
            if offline:
                row["status"] = "simulated"
                requests.append(row)
                if row["images"] != 0:
                    raise AgentError("IMAGE_REPLAY", "第二 Run 自动重复了历史原图。")
                text = "OFFLINE_HISTORY_CHECK"
                await on_text(text)
                return ModelTurn(
                    text=text,
                    tool_calls=[],
                    native={"role": "assistant", "content": text},
                    usage=TokenUsage(input_tokens=None, output_tokens=None),
                )
            if (
                sum(not request["offline"] for request in requests) >= request_limit
                or time.monotonic() - started >= time_limit_seconds
            ):
                raise AgentError("ACCEPTANCE_BUDGET", "隔离图片验收预算已用尽，未发送请求。")
            requests.append(row)
            save()
            tick = time.monotonic()

            async def observe(progress: ModelProgress) -> None:
                """只保留阶段计时，不保留思考或网络原文。

                Keep public timing without reasoning/network payloads.
                """
                row["progress"] = progress.model_dump()
                if on_progress is not None:
                    await on_progress(progress)

            try:
                turn = await self.client.complete(
                    model_id=model_id,
                    session_id=session_id,
                    messages=messages,
                    tools=tools,
                    limits=limits,
                    on_text=on_text,
                    on_progress=observe,
                    on_reasoning=on_reasoning,
                )
                row.update(
                    status="completed",
                    usage=turn.usage.model_dump(),
                    returned_tools=[call.name for call in turn.tool_calls],
                )
                return turn
            except AgentError as exc:
                row.update(status="failed", code=exc.code, message=exc.message)
                raise
            finally:
                row["seconds"] = round(time.monotonic() - tick, 3)
                save()

    app.sessions.model_factory = ObservedClient
    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "m5-image-acceptance",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": DEFAULTS["data_schema_version"],
            },
        )
        for model_id in ("glm-5.3-flash", "deepseek-v4.1-flash"):
            directory = root / model_id
            project = directory / "project"
            project.mkdir(parents=True)
            opened = await app.dispatch("projects.open", {"path": str(project)})
            project_id = opened.active_project.project_id
            session = await app.dispatch(
                "sessions.create", {"project_id": project_id, "model_id": model_id}
            )
            session_id = session.session_id
            await app.sessions.memory.configure(session_id, MemorySettings(automatic=False))
            await app.sessions.contexts.configure(session_id, ContextSettings(automatic=False))
            expected = synthetic_image(directory / "pattern.png")
            data = (directory / "pattern.png").read_bytes()
            # 上传或导入二者各测一种；说明与文件名不泄露预期颜色布局。
            # Exercise upload and import separately; metadata reveals no expected color arrangement.
            if model_id == "glm-5.3-flash":
                imported = await app.dispatch(
                    "attachments.import",
                    {
                        "session_id": session_id,
                        "path": str(directory / "pattern.png"),
                        "purpose": "Describe actual visual content",
                    },
                )
                attachment_id = imported.attachment_id
            else:
                uploaded = await app.dispatch(
                    "attachments.chunk",
                    {
                        "session_id": session_id,
                        "name": "pattern.png",
                        "mime": "image/png",
                        "data": base64.b64encode(data).decode("ascii"),
                        "final": True,
                        "purpose": "Describe actual visual content",
                    },
                )
                assert uploaded.complete and uploaded.attachment is not None
                attachment_id = uploaded.attachment_id
            limits = RunLimits.model_validate(DEFAULTS["run"]).model_copy(
                update={
                    "max_requests": 1,
                    "max_seconds": 180,
                    "request_timeout_seconds": 150,
                    "max_output_tokens": 1200,
                }
            )
            prompt = (
                "Inspect the image directly. Do not use tools. Return only a JSON object with keys "
                "top_left, top_right, bottom_left, bottom_right, center_shape, center_color. "
                "The first four values describe the background colors in those quadrants. "
                "Each color should be one basic English color word. center_shape describes the "
                "simple shape in the center and center_color its fill color. No commentary."
            )
            offline = False
            await app.dispatch(
                "runs.start",
                {
                    "session_id": session_id,
                    "operation_id": str(uuid4()),
                    "prompt": prompt,
                    "limits": limits.model_dump(),
                    "mode": "plan",
                    "attachment_ids": [attachment_id],
                },
            )
            active = app.sessions.active_for(session_id)
            assert active is not None and active.task is not None
            await asyncio.wait_for(
                active.task, max(1, time_limit_seconds - (time.monotonic() - started))
            )
            view = await app.sessions.view(session_id)
            log = await app.worker.call(app.sessions.store.load, session_id)
            answers = [
                f.data.turn.text for f in log.facts if isinstance(f.data, AssistantCommitted)
            ]
            answer = answers[-1] if answers else ""
            parsed = parsed_answer(answer)
            run = view.summary.run
            row: dict[str, object] = {
                "model_id": model_id,
                "session_id": session_id,
                "project_id": project_id,
                "attachment_id": attachment_id,
                "expected": expected,
                "answer": answer,
                "observed": parsed,
                "status": run.status if run else "missing",
                "code": run.code if run else None,
                "image_understanding": bool(
                    run and run.status == "completed" and parsed == expected
                ),
            }
            results.append(row)
            save()
            if run and run.status == "completed":
                offline = True
                await app.dispatch(
                    "runs.start",
                    {
                        "session_id": session_id,
                        "operation_id": str(uuid4()),
                        "prompt": "This is an offline followup; no image has been attached.",
                        "limits": limits.model_dump(),
                        "mode": "plan",
                        "attachment_ids": [],
                    },
                )
                active = app.sessions.active_for(session_id)
                assert active is not None and active.task is not None
                await asyncio.wait_for(active.task, 30)
                followup = await app.sessions.view(session_id)
                row["offline_no_image_replay"] = bool(
                    followup.summary.run and followup.summary.run.status == "completed"
                )
                save()
            print(
                json.dumps(
                    {
                        key: value
                        for key, value in row.items()
                        if key not in {"answer", "expected", "observed"}
                    }
                ),
                flush=True,
            )
        return all(
            row["image_understanding"] and row.get("offline_no_image_replay") for row in results
        )
    finally:
        await app.close()
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["real_requests"] = sum(not row["offline"] for row in requests)
        save()
        print(str(report_path), flush=True)


def main() -> None:
    """预算只用于显式验收，不写成产品限制或修改日常数据。

    Budgets apply to acceptance only; no product restrictions or personal-data changes.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument("--request-limit", type=int, default=4)
    parser.add_argument("--time-limit-seconds", type=int, default=480)
    args = parser.parse_args()
    root = (
        Path(__file__).resolve().parents[2] / ".artifacts/tests" / ("m5-images-" + uuid4().hex[:12])
    )
    root.mkdir(parents=True)
    print(str(root / "report.json"), flush=True)
    raise SystemExit(
        0 if asyncio.run(check(root, args.request_limit, args.time_limit_seconds)) else 1
    )


if __name__ == "__main__":
    main()
