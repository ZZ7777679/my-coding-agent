"""公开 OAuth 配置的 TLS 分段诊断，不读取凭据或修改网络。

Time public OAuth metadata TLS without credentials or network changes.
"""

import argparse
import asyncio
import json
import os
import ssl
import time
from datetime import UTC, datetime
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import getproxies
from uuid import uuid4

import certifi

from tests.models.network_path import endpoint, error_chain, windows_proxy


async def probe(args: argparse.Namespace) -> dict[str, object]:
    """保留验证、默认代理和阶段时序，不记录响应正文。

    Keep TLS validation, inherited proxies and stage timings without response bodies.
    """
    module = import_module(args.client)
    proxy = windows_proxy() if args.system_proxy else None
    verify = ssl.create_default_context(cafile=certifi.where()) if args.certifi else True
    events: list[dict[str, object]] = []
    report: dict[str, object] = {
        "at": datetime.now(UTC).isoformat(),
        "url": args.url,
        "client": args.client,
        "client_version": version(args.client),
        "certificate_store": "certifi" if args.certifi else "client_default",
        "route": "existing_windows_proxy" if args.system_proxy else "inherited",
        "proxy": endpoint(proxy or getproxies().get("https")),
        "certificate_env_present": {
            name: bool(os.environ.get(name)) for name in ("SSL_CERT_FILE", "SSL_CERT_DIR")
        },
        "trace": events,
    }
    started = time.perf_counter()

    async def trace(name: str, info: dict[str, object]) -> None:
        """只保留阶段名、时间、连接主机和异常类型。

        Retain only event names, timing, connected host and exception types.
        """
        item: dict[str, object] = {
            "event": name,
            "ms": round((time.perf_counter() - started) * 1000, 2),
        }
        if name.endswith("connect_tcp.started"):
            host = info.get("host")
            item["host"] = host.decode("ascii") if isinstance(host, bytes) else host
            item["port"] = info.get("port")
        failure = info.get("exception")
        if isinstance(failure, BaseException):
            item["errors"] = error_chain(failure)
        events.append(item)

    try:
        async with asyncio.timeout(args.timeout + 5):
            async with module.AsyncClient(
                timeout=args.timeout, verify=verify, proxy=proxy, follow_redirects=False
            ) as http:
                async with http.stream(
                    "GET",
                    args.url,
                    headers={"Accept": "application/json"},
                    extensions={"trace": trace},
                ) as response:
                    report["status"] = response.status_code
                    report["headers_ms"] = round((time.perf_counter() - started) * 1000, 2)
                    await response.aread()
                    report["bytes"] = len(response.content)
                    if response.status_code == 200:
                        metadata = response.json()
                        report["oauth_metadata"] = (
                            isinstance(metadata, dict)
                            and "issuer" in metadata
                            and "token_endpoint" in metadata
                        )
    except (OSError, module.HTTPError) as exc:
        report["errors"] = error_chain(exc)
    report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return report


def main() -> None:
    """显式运行一次公开 GET，将可复核报告存入集中产物目录。

    Explicitly run one public GET and save its evidence under the test artifact root.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-network", action="store_true")
    parser.add_argument("--client", choices=("httpx", "httpx2"), default="httpx2")
    parser.add_argument("--certifi", action="store_true")
    parser.add_argument("--system-proxy", action="store_true")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument(
        "--url", default="https://github.com/.well-known/oauth-authorization-server/login/oauth"
    )
    args = parser.parse_args()
    if not args.enable_network:
        parser.error("Use --enable-network for this credential-free public GET.")
    parsed = urlsplit(args.url)
    if parsed.username or parsed.password or parsed.query:
        parser.error("Use a public metadata URL without credentials or query parameters.")
    report = asyncio.run(probe(args))
    output = (
        Path(__file__).resolve().parents[2] / ".artifacts/tests" / ("mcp-tls-" + uuid4().hex[:12])
    )
    output.mkdir(parents=True)
    path = output / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(path), "result": report}, indent=2))


if __name__ == "__main__":
    main()
