"""显式比较 Go 路由与可选请求参数，不保存正文或凭据。

Compare Go routes and optional request fields without saving bodies or keys.
"""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx

from my_agent.bootstrap import build_model_http
from my_agent.credentials import resolve_credential
from my_agent.models.endpoints import GO_BASE_URL, LEGACY_GO_BASE_URL
from my_agent.models.go import GoClient
from my_agent.models.timing import RequestTiming


async def compare(timeout: float, payloads: bool, with_tool: bool) -> list[dict[str, object]]:
    """按所选对照发送少量短请求，首包到达后停止，不修改产品端点。

    Compare short requests, stop after arrival and leave product routes intact.
    """
    credential = resolve_credential()
    pool = build_model_http()
    model = GoClient(credential, GO_BASE_URL, pool)
    headers = model.request_headers(str(uuid4()))

    async def probe(base: str, case: str, extra: dict[str, object]) -> dict[str, object]:
        """报告 HTTP 和时序，失败只保留异常类别。

        Report HTTP status and timings; retain only exception classes on failure.
        """
        timing = RequestTiming(None)
        result: dict[str, object] = {"url": base + "/chat/completions", "case": case}
        try:
            async with asyncio.timeout(timeout), pool.borrow() as client:
                async with client.stream(
                    "POST",
                    str(result["url"]),
                    headers=headers,
                    json={
                        "model": "deepseek-v4.1-flash",
                        "messages": [{"role": "user", "content": "Reply with OK only."}],
                        "stream": True,
                        "max_tokens": 128,
                        **extra,
                    },
                    timeout=timeout,
                    extensions={"trace": timing.trace},
                ) as response:
                    await timing.headers()
                    result.update(
                        http_status=response.status_code,
                        content_type=response.headers.get("content-type"),
                    )
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            await timing.received(len(chunk))
                            result["result"] = "first_body_received"
                            break
        except (TimeoutError, httpx.HTTPError) as exc:
            result.update(result="failed", error_type=type(exc).__name__)
        await timing.publish()
        result["timing"] = timing.progress.model_dump()
        return result

    try:
        if with_tool:
            body = {
                "max_tokens": 4096,
                "stream_options": {"include_usage": True},
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "description": "Read a project file",
                            "parameters": {
                                "type": "object",
                                "properties": {"path": {"type": "string"}},
                                "required": ["path"],
                            },
                        },
                    }
                ],
            }
            return await asyncio.gather(
                probe(GO_BASE_URL, "current_with_tool", body),
                probe(LEGACY_GO_BASE_URL, "legacy_with_tool", body),
            )
        if payloads:
            cases = {
                "production": {
                    "max_tokens": 8192,
                    "tools": [],
                    "stream_options": {"include_usage": True},
                },
                "small_output": {
                    "max_tokens": 128,
                    "tools": [],
                    "stream_options": {"include_usage": True},
                },
                "without_empty_tools": {
                    "max_tokens": 8192,
                    "stream_options": {"include_usage": True},
                },
                "without_optional_fields": {"max_tokens": 8192},
            }
            return await asyncio.gather(
                *(probe(GO_BASE_URL, case, body) for case, body in cases.items())
            )
        return await asyncio.gather(
            probe(GO_BASE_URL, "current", {}), probe(LEGACY_GO_BASE_URL, "legacy", {})
        )
    finally:
        await pool.close()


def main() -> None:
    """将隔离诊断保存到测试产物目录。 Save opt-in probes under test artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=45)
    parser.add_argument("--compare-payloads", action="store_true")
    parser.add_argument("--with-tool", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(compare(args.timeout_seconds, args.compare_payloads, args.with_tool))
    root = (
        Path(__file__).resolve().parents[2] / ".artifacts/tests" / ("go-routes-" + uuid4().hex[:12])
    )
    root.mkdir(parents=True)
    report = {
        "requests": len(result),
        "model": "deepseek-v4.1-flash",
        "timeout_seconds": args.timeout_seconds,
        "results": result,
    }
    (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(root / "report.json")


if __name__ == "__main__":
    main()
