"""无认证公开网页读取与基础 HTML 正文提取。 Credential-free public fetching and HTML extraction."""

import asyncio
import re
from html.parser import HTMLParser

import httpx

from my_agent import __version__
from my_agent.errors import AgentError
from my_agent.runtime.settings import RunLimits
from my_agent.storage import utc_now
from my_agent.web.types import FetchArgs, WebPageResult
from my_agent.web.urls import public_url, validate_target


class PageText(HTMLParser):
    """提取可读文本和代码，忽略活动 / 隐藏元素，不执行脚本。

    Extract readable text and code, ignoring active/hidden elements without executing scripts.
    """

    def __init__(self) -> None:
        """保持标签栈、正文和标题。 Keep an element stack, body and title."""
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.parts: list[str] = []
        self.title: list[str] = []
        self.pre = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """记录隐藏状态并保留结构换行。 Track hidden state and structural line breaks."""
        attributes = dict(attrs)
        hidden = (
            (bool(self.stack) and self.stack[-1][1])
            or tag in {"script", "style", "noscript", "template", "svg", "iframe"}
            or "hidden" in attributes
            or attributes.get("aria-hidden") == "true"
            or bool(
                re.search(
                    r"(?:display\s*:\s*none|visibility\s*:\s*hidden)",
                    attributes.get("style") or "",
                    re.I,
                )
            )
        )
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append((tag, hidden))
        if not hidden:
            if tag in {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr", "section", "article"}:
                self.parts.append("\n")
            if tag == "pre":
                self.pre += 1
                self.parts.append("\n```\n")

    def handle_endtag(self, tag: str) -> None:
        """容忍不完整 HTML，同时关闭对应可见代码块。 Tolerate partial HTML and close code blocks."""
        index = next(
            (i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag), None
        )
        if index is None:
            return
        hidden = self.stack[index][1]
        del self.stack[index:]
        if not hidden and tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.parts.append("\n```\n")
        elif not hidden and tag in {
            "p",
            "div",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "tr",
            "section",
            "article",
        }:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        """只追加可见文本，代码区域保留空白。 Append visible text and preserve code whitespace."""
        if self.stack and self.stack[-1][1]:
            return
        if any(tag == "title" for tag, _ in self.stack):
            self.title.append(data)
        elif not any(tag == "head" for tag, _ in self.stack):
            self.parts.append(data if self.pre else re.sub(r"\s+", " ", data))


class PageHttpClient(httpx.AsyncClient):
    """预检服从 HTTPX 实际路由，不在代理解析之前强制本机 DNS。

    Follow HTTPX's selected transport so proxy-resolved names need no local DNS preflight.
    """

    async def validate_destination(self, value: str) -> None:
        """直连才检查解析结果；代理和 NO_PROXY 选择完全沿用客户端。

        Check resolved addresses only on direct routes; reuse the client's proxy/NO_PROXY choice.
        """
        # HTTPX 没有公开路由查询 API；局部使用锁定依赖的同一传输选择方法。
        # HTTPX exposes no public route query; reuse its pinned transport selector in this adapter.
        if self._transport_for_url(httpx.URL(value)) is self._transport:
            await validate_target(value)


class PageFetcher:
    """每次读取使用独立无认证客户端，不借用模型池或浏览器 Cookie。

    Use a separate unauthenticated client per fetch, never the model pool or browser cookies.
    """

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """注入测试传输，生产沿用系统网络。 Inject test transport; preserve system routing."""
        self.transport = transport

    async def fetch(self, args: FetchArgs, limits: RunLimits, max_redirects: int) -> WebPageResult:
        """逐跳校验和有界下载，返回纯文本、最终 URL 与继续读取位置。

        Validate each hop and bound downloads; return text, final URL and continuation offset.
        """
        requested = current = public_url(args.url)
        redirects: list[str] = []
        text: str
        try:
            async with (
                asyncio.timeout(limits.request_timeout_seconds),
                PageHttpClient(
                    transport=self.transport,
                    follow_redirects=False,
                    headers={
                        "User-Agent": f"my-coding-agent/{__version__}",
                        "Accept": "text/html, text/plain, application/json",
                    },
                    timeout=limits.request_timeout_seconds,
                ) as client,
            ):
                while True:
                    await client.validate_destination(current)
                    # 响应 Cookie 也不用于下一跳，任何网页均不继承认证状态。
                    # Do not even forward response cookies on the next hop.
                    client.cookies.clear()
                    async with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise AgentError("WEB_REDIRECT", "网页重定向缺少目标地址。")
                            if len(redirects) >= max_redirects:
                                raise AgentError(
                                    "WEB_REDIRECT_LIMIT", "重定向次数达到本次工具参数上限。"
                                )
                            current = public_url(str(response.url.join(location)))
                            redirects.append(current)
                            continue
                        content_type = (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .lower()
                            .strip()
                        )
                        if not (
                            content_type.startswith("text/")
                            or content_type.endswith(("+json", "+xml"))
                            or content_type
                            in {"application/json", "application/xhtml+xml", "application/xml"}
                        ):
                            raise AgentError(
                                "WEB_CONTENT_TYPE",
                                "该资源不是支持的文本 / HTML；本工具不下载二进制文件。",
                            )
                        data = bytearray()
                        download_truncated = False
                        async for chunk in response.aiter_bytes():
                            remaining = limits.max_file_bytes - len(data)
                            data.extend(chunk[:remaining])
                            if len(chunk) > remaining:
                                download_truncated = True
                                break
                        try:
                            text = data.decode(response.encoding or "utf-8", errors="replace")
                        except LookupError as exc:
                            raise AgentError(
                                "WEB_ENCODING", "网页声明的字符编码不受支持。"
                            ) from exc
                        break
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise AgentError("WEB_TIMEOUT", "网页读取超时，未自动重试。") from exc
        except httpx.HTTPError as exc:
            raise AgentError("WEB_NETWORK", "网页请求失败，未自动重试或修改网络配置。") from exc
        title = current
        if content_type in {"text/html", "application/xhtml+xml"}:
            parser = PageText()
            parser.feed(text)
            parser.close()
            title = "".join(parser.title).strip() or current
            text = "".join(parser.parts).strip()
        end = min(len(text), args.offset + (args.max_chars or limits.max_tool_bytes))
        return WebPageResult(
            kind="web.page",
            requested_url=requested,
            url=current,
            title=title,
            content_type=content_type,
            status_code=response.status_code,
            content=text[args.offset : end],
            retrieved_at=utc_now(),
            redirects=redirects,
            offset=args.offset,
            next_offset=end if end < len(text) else None,
            truncated=end < len(text) or download_truncated,
            download_truncated=download_truncated,
        )
