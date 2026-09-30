"""桌面内网站浏览契约，不将网页接入模型执行权限。

Desktop browsing contracts, separate from model tools.
"""

from typing import Literal

from pydantic import Field

from my_agent.models.types import ModelData


class SkillSiteControl(ModelData):
    """用户导航动作。 User navigation actions."""

    action: Literal["navigate", "back", "forward", "reload", "stop", "status"]
    url: str = ""


class SkillSiteLayout(ModelData):
    """原生网页位置及页面所有者，用于切换后隐藏。

    Native view bounds and owner for navigation cleanup.
    """

    owner_id: str
    visible: bool
    x: int = 0
    y: int = 0
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)


class SkillSiteState(ModelData):
    """真实页面状态，不把发起导航当成加载完成。

    Page facts, not navigation requests claimed as completion.
    """

    url: str
    title: str
    loading: bool
    can_back: bool
    can_forward: bool
    error: str


class SkillSiteSource(ModelData):
    """用户当前页面中的可导入来源。 An import source on the user's current page."""

    url: str
    label: str


class SkillSiteSources(ModelData):
    """仅返回来源链接，不发送整页正文。 Return source links, not the entire page body."""

    page_url: str
    sources: list[SkillSiteSource]
