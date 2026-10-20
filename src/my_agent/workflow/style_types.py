"""Reusable workstyle contracts; reusable definitions only."""

from pydantic import Field

from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData
from my_agent.spaces.types import SpaceConfig
from my_agent.workflow.templates import WorkflowTemplate


class WorkStyle(ModelData):
    """只含可复用定义，没有会话、运行、结果或凭据。

    Reusable definitions without sessions, runs or results.
    """

    style_id: EntityId
    name: str = Field(min_length=1)
    description: str = ""
    workflow: WorkflowTemplate | None = None
    team: SpaceConfig = Field(default_factory=SpaceConfig)
    skill_ids: list[str] = Field(default_factory=list)
    updated_at: str = ""


class WorkStyleProject(ModelData):
    """项目默认仅供未来新任务使用。 Project default for future tasks only."""

    project_id: EntityId


class WorkStyleQuery(ModelData):
    """全局目录可选附带项目默认。 Global catalog optionally includes a project default."""

    project_id: EntityId | None = None


class WorkStyleCatalog(ModelData):
    """组合目录和当前项目默认，不把单项故障当成空库。

    Catalog with project default and explicit issues.
    """

    styles: list[WorkStyle] = Field(default_factory=list)
    default_style_id: EntityId | None = None
    issues: list[str] = Field(default_factory=list)


class SaveWorkStyle(ModelData):
    """保存用户编辑的组合蓝图。 Save an edited composite blueprint."""

    style: WorkStyle


class CaptureWorkStyle(ModelData):
    """从任务生成预览，尚不写入模板库。 Preview a task-derived blueprint before library save."""

    task_id: EntityId
    style_id: EntityId
    name: str = Field(min_length=1)
    description: str = ""
    skill_ids: list[str] = Field(default_factory=list)


class WorkStyleDefault(WorkStyleProject):
    """显式设置或清除未来任务默认。 Set or clear the default for future tasks."""

    style_id: EntityId | None


class ParseWorkStyle(ModelData):
    """导入仅解析预览，不隐式安装资源。 Parse imported text without installing resources."""

    content: str


class ApplyWorkStyle(ModelData):
    """显式采用模板定义，保留已有任务目标和运行历史。

    Adopt definitions while keeping goals and run history.
    """

    task_id: EntityId
    style_id: EntityId
    operation_id: EntityId
    expected_revision: int = Field(ge=1)
    expected_space_revision: int | None = None
