"""搜索、来源与网页读取的严格数据契约。 Strict search, source and page contracts."""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.models.types import ModelData, ModelId, TokenUsage


class WebSettings(ModelData):
    """集中默认值；次数与重定向可由单次工具参数覆盖。

    Central defaults; tool arguments may override native search uses and redirect count.
    """

    search_model_id: ModelId
    search_max_uses: Annotated[int, Field(ge=1)]
    max_redirects: Annotated[int, Field(ge=0)]


class SearchArgs(ModelData):
    """只发送查询，不自动附带项目或聊天历史。 Send a query without project or chat history."""

    query: Annotated[str, Field(min_length=1, max_length=8000, pattern=r"\S")]
    max_uses: Annotated[int, Field(ge=1)] | None = None


class FetchArgs(ModelData):
    """按字符位置读取公开网页；大小仍受本次运行设置限制。

    Read a public page by character offset within the run's configured size budget.
    """

    url: Annotated[str, Field(min_length=1, max_length=8000)]
    offset: Annotated[int, Field(ge=0)] = 0
    max_chars: Annotated[int, Field(ge=1)] | None = None
    max_redirects: Annotated[int, Field(ge=0)] | None = None


class WebSource(ModelData):
    """只保存实际来源及可用摘录，不公开供应商不透明字段。

    Retain actual sources and available excerpts, excluding opaque provider fields.
    """

    url: str
    title: str
    excerpt: str = ""
    page_age: str | None = None


class WebSearchResult(ModelData):
    """原生搜索结果；模型总结和实际来源分别呈现。

    Native search results distinguish model summaries from actual sources.
    """

    kind: Literal["web.search"]
    query: str
    actual_queries: list[str]
    model_id: ModelId
    sources: list[WebSource]
    summary: str
    usage: TokenUsage
    search_uses: int
    retrieved_at: str
    truncated: bool = False


class WebPageResult(ModelData):
    """公开正文片段及读取状态，不宣称执行了网页脚本。

    A public text excerpt and retrieval status, without claiming script execution.
    """

    kind: Literal["web.page"]
    requested_url: str
    url: str
    title: str
    content_type: str
    status_code: int | None = None
    content: str
    retrieved_at: str
    redirects: list[str]
    offset: int
    next_offset: int | None
    truncated: bool
    download_truncated: bool


class OpenWebUrlParams(ModelData):
    """用户点击来源时打开 HTTP(S) 地址；宿主仍校验 URL。

    Open an HTTP(S) source on a user click; the host also validates the URL.
    """

    url: Annotated[str, Field(min_length=1, max_length=8000, pattern=r"^https?://[^\s]+$")]
