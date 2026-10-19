"""显式验证 Go 的 DeepSeek 原生搜索；仅保存脱敏结构，不安装搜索服务。

Opt in to a Go native-search probe and retain sanitized evidence without integration.
"""

import argparse
import asyncio
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

from my_agent.bootstrap import build_model_http
from my_agent.config import DEFAULTS, MAX_FRAME_BYTES
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.models.endpoints import GO_BASE_URL, GO_MESSAGES_URL
from my_agent.models.go import GoClient
from my_agent.models.http import public_request_headers
from my_agent.models.native_search import NativeSearchClient
from my_agent.models.types import ModelProgress
from my_agent.runtime.settings import RunLimits

ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = "deepseek-v4.1-flash"
QUERY = "Python 3.13 release notes site:python.org"


def safe_text(value: object, secret: str) -> str:
    """脱敏后截断外部短字段，不保存完整响应。 Redact before clipping external short fields."""
    if not isinstance(value, str):
        return ""
    value = value.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(?:oc_sk_|sk[-_]|bearer\s+)[A-Za-z0-9_.-]+", "[REDACTED]", value)[:800]


def summarize(payload: object, secret: str) -> dict[str, object]:
    """只提取结果块、来源、用量和清洗后的错误，不保存正文。

    Extract result blocks, sources, usage and sanitized errors without model prose.
    """
    if not isinstance(payload, dict):
        return {"result": "unexpected_payload"}
    blocks = payload.get("content", [])
    blocks = [item for item in blocks if isinstance(item, dict)] if isinstance(blocks, list) else []
    result_blocks = [item for item in blocks if item.get("type") == "web_search_tool_result"]
    sources = []
    search_errors = []
    for block in result_blocks:
        content = block.get("content", [])
        if isinstance(content, dict):
            search_errors.append(safe_text(content.get("error_code"), secret))
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "web_search_result":
                    sources.append(
                        {
                            "url": safe_text(item.get("url"), secret),
                            "title": safe_text(item.get("title"), secret),
                        }
                    )
    error = payload.get("error")
    usage = payload.get("usage", {})
    result: dict[str, object] = {
        "result": "native_results_received" if sources else "native_search_not_confirmed",
        "response_type": safe_text(payload.get("type"), secret),
        "response_model": safe_text(payload.get("model"), secret),
        "stop_reason": safe_text(payload.get("stop_reason"), secret),
        "block_types": [safe_text(item.get("type"), secret) for item in blocks],
        "search_result_blocks": len(result_blocks),
        "sources": sources,
        "search_errors": search_errors,
        "usage": {
            key: usage[key]
            for key in ("input_tokens", "output_tokens")
            if isinstance(usage, dict) and type(usage.get(key)) is int
        },
    }
    if error:
        result["error"] = (
            {
                "type": safe_text(error.get("type"), secret),
                "message": safe_text(error.get("message"), secret),
            }
            if isinstance(error, dict)
            else safe_text(error, secret)
        )
    return result


def save_report(path: Path, report: dict[str, object]) -> None:
    """在独立诊断目录写入无凭据报告。 Write credential-free evidence in an isolated directory."""
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def probe(args: argparse.Namespace, path: Path) -> dict[str, object]:
    """复用受信凭据与 HTTP 装配，仅向 Go 发送一次有界请求。

    Reuse trusted credentials and HTTP composition for exactly one bounded Go request.
    """
    endpoint = GO_MESSAGES_URL
    report: dict[str, object] = {
        "started_at": datetime.now(UTC).isoformat(),
        "endpoint": endpoint,
        "model": MODEL_ID,
        "mode": "production-search" if args.production_client else "native-search",
        "attempts": 0,
        "request_budget": 1,
        "timeout_seconds": args.timeout_seconds,
        "max_tokens": args.max_tokens,
        "max_search_uses": 1,
        "response_limit_bytes": None if args.production_client else args.max_response_bytes,
        "query": QUERY,
        "network_policy": "unchanged_httpx_environment_no_redirects_no_retries",
    }
    credential = resolve_credential()
    if credential.secret is None:
        report.update(result="credential_unavailable", credential_state=credential.info.source)
        save_report(path, report)
        return report
    secret = credential.secret.get_secret_value()
    headers = {
        **public_request_headers(str(uuid4())),
        "x-api-key": secret,
        "Authorization": "Bearer " + secret,
        "anthropic-version": "2023-06-01",
        "Accept": "application/json",
    }
    prompt = (
        "Perform a web search for the query: " + QUERY + ". Use web_search once and cite sources."
    )
    body: dict[str, object] = {
        "model": MODEL_ID,
        "max_tokens": args.max_tokens,
        "stream": False,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
    }
    pool = build_model_http()
    started = time.perf_counter()
    try:
        report["attempts"] = 1
        save_report(path, report)
        if args.production_client:

            async def observe(progress: ModelProgress) -> None:
                """只记录时序，不保存正文。 Record timing without bodies."""
                report["progress"] = progress.model_dump()

            client = NativeSearchClient(GoClient(credential, GO_BASE_URL, pool), MODEL_ID)
            result = await client.search(
                QUERY,
                1,
                str(uuid4()),
                RunLimits.model_validate(
                    {
                        **DEFAULTS["run"],
                        "request_timeout_seconds": int(args.timeout_seconds),
                        "max_output_tokens": args.max_tokens,
                    }
                ),
                observe,
            )
            report.update(
                result="native_results_received"
                if result.sources
                else "native_search_not_confirmed",
                sources=[{"url": item.url, "title": item.title} for item in result.sources],
                usage=result.usage.model_dump(),
                search_uses=result.search_uses,
            )
            return report
        async with asyncio.timeout(args.timeout_seconds), pool.borrow() as client:
            async with client.stream(
                "POST", endpoint, headers=headers, json=body, timeout=args.timeout_seconds
            ) as response:
                report["http_status"] = response.status_code
                report["content_type"] = response.headers.get("content-type", "")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    report["received_bytes"] = len(data)
                    if len(data) > args.max_response_bytes:
                        report["failure_cause"] = "response_limit"
                        raise ValueError("Response exceeds the existing frame budget")
                report.update(summarize(json.loads(data), secret))
                if not response.is_success:
                    report["result"] = "http_error"
    except AgentError as error:
        report.update(result="production_error", code=error.code, message=error.message)
    except (httpx.HTTPError, TimeoutError, ValueError) as error:
        # 异常文本可能包含认证信息，只记录类型。 Exception messages may contain credentials.
        report.update(result="transport_or_payload_error", error_type=type(error).__name__)
    finally:
        await pool.close()
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        save_report(path, report)
    return report


def main() -> None:
    """要求显式开启真实调用；每次运行创建独立报告，不加入默认回归。

    Require live-call opt-in, create a fresh report and stay outside default regression.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=90)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--max-response-bytes", type=int, default=8 * MAX_FRAME_BYTES)
    parser.add_argument("--production-client", action="store_true")
    args = parser.parse_args()
    if (
        not 0 < args.timeout_seconds < float("inf")
        or min(args.max_tokens, args.max_response_bytes) <= 0
    ):
        parser.error("Use a finite positive timeout and positive token budget")
    directory = ROOT / ".artifacts/tests" / ("go-native-search-" + uuid4().hex[:12])
    directory.mkdir(parents=True)
    path = directory / "report.json"
    report = asyncio.run(probe(args, path))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(path)
    if report.get("result") != "native_results_received":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
