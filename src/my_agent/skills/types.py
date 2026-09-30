"""资源目录与选择契约。 Resource catalog and selection contracts."""

from typing import Literal

from pydantic import Field

from my_agent.models.types import ModelData
from my_agent.sessions.types import SessionId


class SkillParams(ModelData):
    """指定项目与可选会话。 Identify a project and optional session."""

    project_id: str | None = None
    session_id: SessionId | None = None


class SkillOrigin(ModelData):
    """记录下载来源，不作为执行门槛。 Record download provenance without an execution gate."""

    repository: str
    ref: str
    revision: str | None = None
    directory: str
    downloaded_at: str


class SkillItem(ModelData):
    """来源、覆盖关系及资源位置。 Provenance, shadowing and resource location."""

    skill_id: str
    name: str
    description: str
    source: Literal["builtin", "user", "project"]
    path: str
    resource_base: str
    version: str
    enabled: bool = True
    shadowed_by: str | None = None
    origin: SkillOrigin | None = None


class SkillCatalog(ModelData):
    """轻量目录与明确的局部错误。 Lightweight catalog with explicit local errors."""

    items: list[SkillItem]
    selected: list[str] = Field(default_factory=list)
    rule_paths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    user_directory: str
    project_directory: str


class SkillReadParams(SkillParams):
    """读取一项原始文本。 Read one original resource."""

    skill_id: str


class SkillDocument(ModelData):
    """资源详情与原文。 Resource details and original text."""

    item: SkillItem
    content: str


class SaveSkillParams(SkillParams):
    """显式创建或修改用户 / 项目资源。 Explicit user/project resource edits."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    content: str
    scope: Literal["user", "project"] = "user"
    overwrite: bool = False
    import_directory: str | None = None


class SelectSkillsParams(SkillParams):
    """会话引用不复制正文。 Session references do not copy bodies."""

    selected: list[str]


class EnableSkillParams(SkillReadParams):
    """保存一项资源的启停。 Persist resource enablement."""

    enabled: bool


class SkillSettings(ModelData):
    """用户设置与会话选项分别存储。 Store preferences separately from session choices."""

    disabled: list[str] = Field(default_factory=list)
    selected: list[str] = Field(default_factory=list)
    material_archives: dict[str, str] = Field(default_factory=dict)
