"""合作空间专用讨论与确认启动契约。

Dedicated team design and launch contracts.
"""

from typing import Literal

from pydantic import Field

from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData, ModelId
from my_agent.spaces.types import SpaceConfig, SpaceParams


class OpenTeamDesignParams(SpaceParams):
    """首次打开时选择模型，已有会话保留选择。

    Choose the initial model without resetting existing sessions.
    """

    model_id: ModelId


class SaveTeamDesignParams(SpaceParams):
    """保存未发送输入或当前图，不创建成员。

    Save unsent input or the current graph without creating members.
    """

    input_text: str | None = None
    config: SpaceConfig | None = None


class SendTeamDesignParams(SpaceParams):
    """在专用会话讨论或追加要求。

    Discuss or steer in the dedicated session.
    """

    operation_id: EntityId
    content: str


class StartTeamDesignParams(SpaceParams):
    """确认当前图并启动，操作身份用于避免重复工作。

    Confirm the graph and start with an idempotent operation identity.
    """

    operation_id: EntityId
    config: SpaceConfig


class TeamDesignLaunch(ModelData):
    """保留逐步启动事实和局部失败。

    Retain launch steps and partial failures.
    """

    operation_id: EntityId
    config: SpaceConfig
    objective: str
    stage: Literal["accepted", "saved", "assembled", "started"] = "accepted"
    error: str | None = None


class TeamDesignView(ModelData):
    """保存设计关联，不复制会话日志。

    Persist design associations without duplicating session logs.
    """

    task_id: EntityId
    session_id: EntityId
    initial_model_id: ModelId
    input_text: str = ""
    objective: str = ""
    config: SpaceConfig | None = None
    revision: int = 0
    launches: list[TeamDesignLaunch] = Field(default_factory=list)
