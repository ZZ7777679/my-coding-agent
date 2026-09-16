"""无凭据比较默认网络与现有 Windows 代理。 Compare routes without model credentials."""

import argparse
import asyncio
import json
import socket
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import getproxies
from uuid import uuid4

import httpx

from my_agent import __version__
from my_agent.config import MODEL_DEFAULTS

URL = str(MODEL_DEFAULTS["base_url"]) + "/models"


def endpoint(value: str | None) -> dict[str, object] | None:
    """只保留代理协议、主机和端口，不输出认证或路径。 Omit authentication and paths."""
    if not value:
        return None
    parsed = urlsplit(value if "://" in value else "http://" + value)
    return {"scheme": parsed.scheme, "host": parsed.hostname, "port": parsed.port}


def windows_proxy() -> str | None:
    """只读取当前 Windows HTTPS 代理，不修改设置。 Read the Windows HTTPS proxy only."""
    if sys.platform != "win32":
        return None
    # 仅 Windows 提供该标准库入口，读取当前启用的注册表代理。
    # This Windows-only stdlib helper reads the enabled registry proxy.
    from urllib.request import getproxies_registry

    return getproxies_registry().get("https")


def error_chain(error: BaseException) -> list[dict[str, object]]:
    """仅记录异常类别和数值错误码，省略可能含敏感数据的消息。 Record safe error facts."""
    chain: list[dict[str, object]] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        item: dict[str, object] = {"type": type(current).__name__}
        if isinstance(current, OSError):
            item["errno"] = current.errno
            item["winerror"] = getattr(current, "winerror", None)
        chain.append(item)
        current = current.__cause__ or current.__context__
    return chain


async def probe(name: str, proxy: str | None = None) -> dict[str, object]:
    """最多等待 20 秒读取响应头，不发模型生成或认证请求。 Bound a credential-free GET."""
    started = time.perf_counter()
    events: list[dict[str, object]] = []
    result: dict[str, object] = {"name": name, "trace": events}

    async def trace(event: str, info: dict[str, object]) -> None:
        """记录阶段时间及失败类型，不保存请求头或正文。 Keep only timing and error types."""
        item: dict[str, object] = {
            "name": event,
            "ms": round((time.perf_counter() - started) * 1000, 3),
        }
        failure = info.get("exception")
        if isinstance(failure, BaseException):
            item["error_chain"] = error_chain(failure)
        events.append(item)

    try:
        async with asyncio.timeout(20):
            async with httpx.AsyncClient(proxy=proxy, timeout=20, follow_redirects=False) as client:
                async with client.stream(
                    "GET",
                    URL,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "my-coding-agent/" + __version__,
                    },
                    extensions={"trace": trace},
                ) as response:
                    result["http_status"] = response.status_code
                    result["headers_ms"] = round((time.perf_counter() - started) * 1000, 3)
        result["status"] = "http_response_received"
    except (OSError, httpx.HTTPError) as exc:
        result["status"] = "connection_failed"
        result["error_chain"] = error_chain(exc)
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return result


async def main() -> None:
    """输出隔离诊断报告，不读取 API key 或更改系统设置。 Write an isolated safe report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-network", action="store_true")
    args = parser.parse_args()
    if not args.enable_network:
        parser.error("Network access requires --enable-network.")
    output = (
        Path(__file__).resolve().parents[2]
        / ".artifacts"
        / "tests"
        / ("network-path-" + uuid4().hex[:12])
    )
    output.mkdir(parents=True)
    proxies = getproxies()
    registry = windows_proxy()
    report: dict[str, object] = {
        "at": datetime.now(UTC).isoformat(),
        "url": URL,
        "model_requests": 0,
        "environment_or_registry_proxy": {
            name: endpoint(proxies.get(name)) for name in ("http", "https", "all")
        },
        "no_proxy_present": bool(proxies.get("no")),
        "windows_https_proxy": endpoint(registry),
        "note": "No explicit proxy does not bypass an active TUN.",
    }
    try:
        report["system_dns"] = sorted(
            {row[4][0] for row in socket.getaddrinfo("opencode.ai", 443, type=socket.SOCK_STREAM)}
        )
    except OSError as exc:
        report["dns_error"] = error_chain(exc)
    # 只比较当前路径与已经配置的代理，不切换系统模式或节点。
    # Compare existing paths without switching system mode or outbound nodes.
    cases = [probe("default_environment")]
    if registry:
        cases.append(probe("existing_windows_proxy_explicit", registry))
    report["results"] = await asyncio.gather(*cases)
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "data": report}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
