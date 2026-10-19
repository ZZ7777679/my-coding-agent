"""空间配置与会话绑定分离的公开契约。

Public space configuration and separate bindings.
"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData, ModelId
from my_agent.workflow.types import WorkItem


class SpacePosition(ModelData):
    """用户保存的节点位置。

    User-saved node coordinates.
    """

    x: float = 0.0
    y: float = 0.0


class SpaceViewport(ModelData):
    """关系图的阅读位置与缩放。

    Graph reading position and zoom.
    """

    x: float = 0.0
    y: float = 0.0
    zoom: Annotated[float, Field(gt=0)] = 1.0


class SpaceLayout(ModelData):
    """与团队草稿独立保存的图展示设置。

    Graph presentation settings saved separately from team drafts.
    """

    graph_open: bool = True
    viewport: SpaceViewport | None = None


class SpaceMember(ModelData):
    """独立于会话的稳定成员身份与职责。

    Stable member identity and duties independent of sessions.
    """

    member_id: EntityId
    name: Annotated[str, Field(min_length=1, max_length=256, pattern=r"\S")]
    role: Annotated[str, Field(max_length=4096)] = ""
    scope: Annotated[str, Field(max_length=16000)] = ""
    model_id: ModelId
    skill_ids: list[str] = Field(default_factory=list)
    position: SpacePosition = Field(default_factory=SpacePosition)


class SpaceEdge(ModelData):
    """描述协作关系的有向连线，不是通信白名单。

    Descriptive directed links, not communication grants.
    """

    edge_id: EntityId
    source_member_id: EntityId
    target_member_id: EntityId
    kind: Literal["delegate", "result", "discuss", "feedback"]
    label: Annotated[str, Field(max_length=4096)] = ""


class SpaceConfig(ModelData):
    """可编辑组织预设、成员和图，允许反馈环。

    Editable organisation, members and graph allowing cycles.
    """

    organisation: Literal["central", "hierarchical", "peer"] = "central"
    receiver_member_id: EntityId | None = None
    members: list[SpaceMember] = Field(default_factory=list)
    edges: list[SpaceEdge] = Field(default_factory=list)
    initial_work_items: list[WorkItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "SpaceConfig":
        """只检查身份唯一和引用存在，不限制拓扑。

        Check identity and references without topology gates.
        """
        members = {member.member_id for member in self.members}
        if len(members) != len(self.members):
            raise ValueError("Member IDs must be unique")
        if len({edge.edge_id for edge in self.edges}) != len(self.edges):
            raise ValueError("Edge IDs must be unique")
        if self.receiver_member_id is not None and self.receiver_member_id not in members:
            raise ValueError("Receiver must reference an existing member")
        if any(
            edge.source_member_id not in members or edge.target_member_id not in members
            for edge in self.edges
        ):
            raise ValueError("Edges must reference existing members")
        return self


class SpaceBinding(ModelData):
    """当前会话与保留的历史，错误不冒充成功。

    Current session and retained history with explicit errors.
    """

    member_id: EntityId
    session_id: EntityId | None = None
    session_ids: list[EntityId] = Field(default_factory=list)
    error: str | None = None


class SpaceView(ModelData):
    """空间快照；普通配置保存不能覆盖绑定。

    Space snapshot with bindings preserved by config saves.
    """

    task_id: EntityId
    project_id: str
    revision: Annotated[int, Field(ge=1)]
    config: SpaceConfig
    bindings: list[SpaceBinding] = Field(default_factory=list)
    layout: SpaceLayout = Field(default_factory=SpaceLayout)
    created_at: str
    updated_at: str
    error: str | None = None


class SpaceParams(ModelData):
    """按任务读取空间，不自动迁移旧任务。

    Lookup a task space without migrating old tasks.
    """

    task_id: EntityId


class SaveSpaceParams(SpaceParams):
    """保存草稿；空版本只用于首次创建。

    Save a draft; a null revision creates the first snapshot.
    """

    expected_revision: Annotated[int, Field(ge=1)] | None
    config: SpaceConfig


class SpaceStartParams(SpaceParams):
    """显式组建已有成员的会话，不启动模型。

    Explicitly assemble member sessions without model calls.
    """


class SaveSpaceLayoutParams(SpaceParams):
    """只保存阅读位置，不覆盖团队编辑或会话绑定。

    Save reading position without replacing team edits or session bindings.
    """

    layout: SpaceLayout


class BindSpaceMemberParams(SpaceParams):
    """用户显式绑定已有会话或幂等创建新会话。

    Explicitly bind a session or idempotently create one.
    """

    member_id: EntityId
    session_id: EntityId | None = None
    operation_id: EntityId


class SpaceResult(ModelData):
    """缺失空间和已保存空间分别表达。

    Distinguish absent spaces from durable snapshots.
    """

    space: SpaceView | None


class SpaceBindingOperation(ModelData):
    """保存创建输入快照，重试不重建结果未知的会话。

    Preserve creation inputs for safe session retries.
    """

    operation_id: EntityId
    member_id: EntityId
    requested_session_id: EntityId | None
    session_id: EntityId
    member: SpaceMember
    completed: bool = False


class SpaceRecord(ModelData):
    """内部恢复记录，不将操作快照暴露给前端。

    Internal recovery state without public operation snapshots.
    """

    schema_version: Literal[1] = 1
    view: SpaceView
    operations: list[SpaceBindingOperation] = Field(default_factory=list)
