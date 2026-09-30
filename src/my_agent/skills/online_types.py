"""公开网站发现与安装契约。 Public website discovery and installation contracts."""

import json
from importlib.resources import files
from typing import Literal

from pydantic import Field

from my_agent.models.types import ModelData
from my_agent.skills.types import SkillItem, SkillOrigin

ONLINE_DEFAULTS = json.loads(
    files("my_agent").joinpath("defaults.json").read_text(encoding="utf-8")
)["skill_online"]


class OnlineSkillSearch(ModelData):
    """搜索公开目录，不携带应用凭据。

    Search a public catalog without application credentials.
    """

    query: str = Field(min_length=1)
    limit: int = Field(default=ONLINE_DEFAULTS["search_limit"], gt=0, le=100)
    timeout_seconds: float = Field(default=ONLINE_DEFAULTS["timeout_seconds"], gt=0)


class OnlineSkillInspect(ModelData):
    """下载明确来源，ref 和目录可覆盖链接解析结果。

    Download a source with optional ref/path overrides.
    """

    source: str = Field(min_length=1)
    ref: str = ""
    directory: str = ""
    timeout_seconds: float = Field(default=ONLINE_DEFAULTS["timeout_seconds"], gt=0)
    max_archive_mb: int = Field(default=ONLINE_DEFAULTS["max_archive_mb"], gt=0)


class OnlineSkillRead(ModelData):
    """读取已下载快照，不静默更新远程版本。

    Read a downloaded snapshot without a remote refresh.
    """

    preview_id: str
    path: str


class OnlineSkillInstall(OnlineSkillRead):
    """明确将所选方法保存为用户或项目资源。

    Explicitly install a user or project skill.
    """

    scope: Literal["user", "project"] = "user"
    project_id: str | None = None


class OnlineSkillCancel(ModelData):
    """只取消指定在线操作。 Cancel only the identified online operation."""

    operation_id: str


class OnlineSkillHit(ModelData):
    """网站的搜索条目，正文以仓库快照为准。

    Website hits; bodies come from repository snapshots.
    """

    name: str
    source: str
    url: str
    installs: int | None = None


class OnlineSkillCandidate(ModelData):
    """仓库中实际存在的 Skill。 A skill actually present in the repository."""

    name: str
    description: str
    path: str
    file_count: int
    bytes: int


class OnlineSkillPreview(ModelData):
    """预览身份指向当前保留的 ZIP。 Preview identity points to the retained ZIP."""

    preview_id: str
    origin: SkillOrigin
    skills: list[OnlineSkillCandidate]
    total: int
    issues: list[str] = Field(default_factory=list)


class OnlineSkillDocument(ModelData):
    """正文与文件清单的有限预览，安装仍保留完整文件。

    Bounded previews; installation keeps full files.
    """

    content: str
    truncated: bool
    files: list[str]
    file_count: int


class OnlineSkillStatus(ModelData):
    """在线页面共用真实操作状态，离开再回来可继续查看。

    Shared operation facts survive navigation.
    """

    operation_id: str = ""
    action: Literal["search", "inspect", "install"] | None = None
    status: Literal["idle", "running", "ready", "installed", "failed", "cancelled"] = "idle"
    message: str = ""
    query: str = ""
    hits: list[OnlineSkillHit] = Field(default_factory=list)
    preview: OnlineSkillPreview | None = None
    installed: SkillItem | None = None
    error_code: str | None = None
