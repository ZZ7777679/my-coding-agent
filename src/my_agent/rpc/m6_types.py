"""M6 公开边界类型，不依赖业务服务。 M6 public types without service dependencies."""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.checkpoints.types import (
    CheckpointPage,
    CheckpointParams,
    PreviewCheckpointParams,
    RestoreCheckpointParams,
    RestorePreview,
    RestoreResult,
)
from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData
from my_agent.workflow.style_types import (
    ApplyWorkStyle,
    CaptureWorkStyle,
    ParseWorkStyle,
    SaveWorkStyle,
    WorkStyle,
    WorkStyleCatalog,
    WorkStyleDefault,
    WorkStyleQuery,
)


class NavigationItemName(ModelData):
    """导航项的明确身份及显示名。 Explicit navigation identity and display name."""

    kind: Literal["project", "task", "session"]
    id: EntityId
    name: Annotated[str, Field(min_length=1, max_length=256, pattern=r"\S")]


class RenameNavigationParams(NavigationItemName):
    """用户重命名操作，区别于目录移动或会话归属。

    User rename, distinct from directory moves or membership changes.
    """

    operation_id: EntityId


M6_TYPES = (
    NavigationItemName,
    RenameNavigationParams,
    CheckpointPage,
    CheckpointParams,
    PreviewCheckpointParams,
    RestoreCheckpointParams,
    RestorePreview,
    RestoreResult,
    WorkStyle,
    WorkStyleCatalog,
    WorkStyleQuery,
    SaveWorkStyle,
    CaptureWorkStyle,
    WorkStyleDefault,
    ParseWorkStyle,
    ApplyWorkStyle,
)
