"""不携带凭据的 TLS 分段对照，保持证书验证。 Credential-free TLS comparisons with verification."""

import argparse
import asyncio
import json
import ssl
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from my_agent.config import MODEL_DEFAULTS

ROOT = Path(__file__).resolve().parents[2]


def hello_summary(context, host):
    """只记录 ClientHello 大小与密钥交换组，不输出握手字节。

    Report ClientHello size and key-share groups without dumping handshake bytes.
    """
    output = ssl.MemoryBIO()
    connection = context.wrap_bio(ssl.MemoryBIO(), output, server_hostname=host)
    try:
        connection.do_handshake()
    except ssl.SSLWantReadError:
        pass
    raw = output.read()
    data = raw[9:]
    offset = 34
    offset += 1 + data[offset]
    offset += 2 + int.from_bytes(data[offset : offset + 2], "big")
    offset += 1 + data[offset]
    end = offset + 2 + int.from_bytes(data[offset : offset + 2], "big")
    offset += 2
    shares = []
    while offset + 4 <= end:
        kind = int.from_bytes(data[offset : offset + 2], "big")
        length = int.from_bytes(data[offset + 2 : offset + 4], "big")
        value = data[offset + 4 : offset + 4 + length]
        offset += 4 + length
        if kind == 51:
            pos = 2
            while pos + 4 <= len(value):
                group = int.from_bytes(value[pos : pos + 2], "big")
                size = int.from_bytes(value[pos + 2 : pos + 4], "big")
                shares.append({"group_hex": hex(group), "bytes": size})
                pos += 4 + size
    return {"hello_bytes": len(raw), "key_shares": shares}


async def measure(case, host):
    """分别计时 TCP 与 TLS，连接失败也仅记录类型。 Time TCP/TLS and report only failure types."""
    context = httpx.create_ssl_context()
    if case == "x25519":
        context.set_ecdh_curve("X25519")
    result = {"case": case, **hello_summary(context, host)}
    writer = None
    started = time.perf_counter()
    try:
        async with asyncio.timeout(40):
            _, writer = await asyncio.open_connection(host, 443)
            connected = time.perf_counter()
            result["tcp_dns_ms"] = round((connected - started) * 1000, 3)
            await writer.start_tls(context, server_hostname=host, ssl_handshake_timeout=35)
            result["tls_ms"] = round((time.perf_counter() - connected) * 1000, 3)
            channel = writer.get_extra_info("ssl_object")
            result.update(status="connected", tls_version=channel.version())
    except Exception as exc:
        result.update(status="failed", code=type(exc).__name__)
    finally:
        if writer:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 2)
            except (OSError, TimeoutError):
                result["close_status"] = "peer_close_incomplete"
    result["total_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return result


def main():
    """交替运行八次无 HTTP / API key 的连接并保存报告。

    Alternate eight TLS-only connections without HTTP/API keys and retain the report.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable-network", action="store_true", required=True)
    args = parser.parse_args()
    if not args.enable_network:
        parser.error("Explicit network opt-in required")
    root = ROOT / ".artifacts/tests" / ("tls-latency-" + uuid4().hex[:12])
    root.mkdir(parents=True)
    host = urlparse(str(MODEL_DEFAULTS["base_url"])).hostname
    report = {"openssl": ssl.OPENSSL_VERSION, "certificate_verification": True, "results": []}
    for case in ["default", "x25519"] * 4:
        result = asyncio.run(measure(case, host))
        report["results"].append(result)
        (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)
    print(str(root / "report.json"), flush=True)


if __name__ == "__main__":
    main()
