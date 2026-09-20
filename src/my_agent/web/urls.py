"""公开 URL 检查，沿用系统 DNS / 代理，不选择连接方式。

Public URL checks that preserve system DNS/proxy routing rather than selecting it.
"""

import asyncio
import ipaddress
import socket

import httpx

from my_agent.errors import AgentError


def public_url(value: str) -> str:
    """拒绝凭据、非 HTTP 和显式本地目标，返回规范 URL。

    Reject credentials, non-HTTP schemes and explicit local targets; return a canonical URL.
    """
    try:
        url = httpx.URL(value)
        host = url.host.rstrip(".").lower()
        if (
            url.scheme not in {"http", "https"}
            or not host
            or url.userinfo
            or any(ord(char) < 33 for char in value)
            or host == "localhost"
            or host.endswith((".localhost", ".local", ".lan", ".internal"))
        ):
            raise ValueError("Unsupported public URL")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host:
                raise ValueError("Local hostname") from None
        else:
            if not address.is_global:
                raise ValueError("Local address")
        return str(url.copy_with(fragment=None))
    except (ValueError, httpx.InvalidURL) as exc:
        raise AgentError(
            "WEB_URL_DENIED", "仅支持无账号信息的公开 HTTP(S) 地址；本机预览请使用程序卡片。"
        ) from exc


async def validate_target(url: str) -> None:
    """拦截解析到本机 / 内网的目标；DNS 预检不是网络沙箱。

    Reject local/private resolutions; DNS preflight is not a network sandbox.
    """
    parsed = httpx.URL(public_url(url))
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            parsed.host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise AgentError("WEB_DNS", "网页域名解析失败，未修改系统 DNS。") from exc
    if not addresses:
        raise AgentError("WEB_DNS", "网页域名未返回可用地址。")
    for address in addresses:
        resolved = ipaddress.ip_address(address[4][0])
        # TUN 可用保留网段映射公开域名；不把它当作真实内网服务或更改路由。
        # TUN may map public names into a benchmark range; preserve that route metadata.
        synthetic = resolved.version == 4 and resolved in ipaddress.ip_network("198.18.0.0/15")
        if not resolved.is_global and not synthetic:
            raise AgentError(
                "WEB_URL_DENIED", "网页地址解析到了本机或内网，公开网页工具未访问该目标。"
            )
