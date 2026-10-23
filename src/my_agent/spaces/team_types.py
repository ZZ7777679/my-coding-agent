"""团队草稿、模板与群聊关联契约。

Team drafts, templates and group-chat references.
"""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.goals.types import GoalBudget
from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData
from my_agent.runtime.modes import RunMode
from my_agent.runtime.settings import RunLimits
from my_agent.spaces.types import SpaceConfig, SpaceParams
from my_agent.workflow.types import Description, WorkId, WorkItem, WorkObjective


class SaveTeamDraftArgs(ModelData):
    """模型提交的可编辑团队，不创建会话。

    Model-authored editable team without session creation.
    """

    config: SpaceConfig
    initial_work_items: list[WorkItem] = Field(default_factory=list)
    objective: str | None = None


class UpdateSpaceWorkParams(SpaceParams):
    """单写者更新可选工作归属，不改变 Goal 接纳规则。

    Single-writer updates to optional work ownership without changing goal admission.
    """

    work_id: WorkId
    operation_id: EntityId
    member_id: EntityId | None = None
    action: Literal["assign", "claim", "release", "result"]
    run_id: EntityId | None = None
    result: str | None = None
    status: Literal["planned", "in_progress", "completed", "waiting"] | None = None


class GenerateTeamParams(SpaceParams):
    """在用户选择的现有会话执行只读生成。

    Generate through a selected existing read-only session.
    """

    session_id: EntityId
    operation_id: EntityId
    objective: Description
    organisation: Literal["central", "hierarchical", "peer"] = "central"
    discussion: bool = False


class TeamGeneration(ModelData):
    """真实生成请求及待用户采用的草稿。

    Real generation request and a draft awaiting user adoption.
    """

    params: GenerateTeamParams
    expected_revision: int | None
    run_id: EntityId | None = None
    draft: SaveTeamDraftArgs | None = None
    error: str | None = None
    created_at: str = ""


class SpaceChatParams(SpaceParams):
    """普通消息仅路由给明确接收成员。

    Route ordinary messages only to selected recipients.
    """

    operation_id: EntityId
    content: WorkObjective
    target_member_ids: list[EntityId] = Field(default_factory=list)
    mode: RunMode = "normal"
    work_ids: list[WorkId] = Field(default_factory=list)


class SpaceChatPageParams(SpaceParams):
    """按实际消息 / 轮次身份读取较早历史。

    Read older history by actual message or round identity.
    """

    before_id: EntityId | None = None
    limit: int = Field(default=20, ge=1, le=100)


class StartSpaceRoundParams(SpaceParams):
    """用户明确启动合作目标；默认由接收成员协调。

    Explicitly start a cooperative goal via the receiver.
    """

    operation_id: EntityId
    objective: WorkObjective
    target_member_ids: list[EntityId] = Field(default_factory=list)
    budget: GoalBudget = Field(default_factory=GoalBudget)
    limits: RunLimits | None = None
    work_ids: list[WorkId] = Field(default_factory=list)


class StopSpaceRoundParams(SpaceParams):
    """停止指定成员或整轮，不重试失败工作。

    Stop a member or round without retrying failures.
    """

    round_id: EntityId | None = None
    member_id: EntityId | None = None


class SpaceExecution(ModelData):
    """宿主记录实际投递与执行关联。

    Host-recorded delivery and execution references.
    """

    member_id: EntityId
    session_id: EntityId
    operation_id: EntityId
    run_id: EntityId | None = None
    goal_id: EntityId | None = None
    request_id: EntityId | None = None
    error: str | None = None


class SpaceChatMessage(ModelData):
    """持久用户消息与接收对象快照。 Durable user message and recipient snapshots."""

    message_id: EntityId
    content: str
    mode: RunMode
    target_member_ids: list[EntityId]
    created_at: str
    executions: list[SpaceExecution] = Field(default_factory=list)
    work_ids: list[WorkId] = Field(default_factory=list)


class SpaceRound(ModelData):
    """空间轮次引用已有 Goal，不运行自己的循环。

    A space round references existing goals without another loop.
    """

    round_id: EntityId
    objective: str
    created_at: str
    budget: GoalBudget
    limits: RunLimits | None = None
    executions: list[SpaceExecution] = Field(default_factory=list)
    stopped: bool = False
    work_ids: list[WorkId] = Field(default_factory=list)


class SpacePublicOutput(ModelData):
    """精确 Run 的公开回答，思考和工具留在 Trace。

    Public answers from exact runs, with internals in Trace.
    """

    member_id: EntityId
    session_id: EntityId
    run_id: EntityId | None
    origin_id: EntityId | None = None
    waiting_for: EntityId | None = None
    message_id: EntityId | None = None
    seq: int | None = None
    text: str = ""
    streaming: bool = False
    process_epoch: EntityId | None = None
    delta_index: int = 0
    status: str
    error: str | None = None


class SpaceChatView(ModelData):
    """消息和轮次历史，加真实运行公开投影。

    Message and round history with real execution projections.
    """

    task_id: EntityId
    messages: list[SpaceChatMessage] = Field(default_factory=list)
    rounds: list[SpaceRound] = Field(default_factory=list)
    generations: list[TeamGeneration] = Field(default_factory=list)
    outputs: list[SpacePublicOutput] = Field(default_factory=list)
    next_before: EntityId | None = None


class SpaceChatRecord(ModelData):
    """内部关联记录，不复制会话事实。

    Internal associations without duplicating session facts.
    """

    schema_version: Literal[1] = 1
    view: SpaceChatView


class TeamTemplate(ModelData):
    """可分享的团队配置快照，不包含实际会话绑定。

    Shareable team configuration without actual session bindings.
    """

    schema_version: Literal[1] = 1
    template_id: EntityId
    name: Annotated[str, Field(min_length=1, max_length=256, pattern=r"\S")]
    description: str = ""
    draft: SaveTeamDraftArgs
    updated_at: str


class SaveTeamTemplateParams(ModelData):
    """保存或更新一个团队模板。 Save or update one team template."""

    template_id: EntityId
    name: Annotated[str, Field(min_length=1, max_length=256, pattern=r"\S")]
    description: str = ""
    draft: SaveTeamDraftArgs


class TeamTemplateParams(ModelData):
    """按稳定身份读取模板。 Read a template by stable identity."""

    template_id: EntityId


class CopyTeamTemplateParams(TeamTemplateParams):
    """显式复制模板为独立快照。

    Explicitly copy a template into an independent snapshot.
    """

    new_template_id: EntityId
    name: Annotated[str, Field(min_length=1, max_length=256, pattern=r"\S")]


class ImportTeamTemplateParams(ModelData):
    """导入 JSON 为新的本地模板，不绑定会话。

    Import JSON as a new local template without session bindings.
    """

    template_id: EntityId
    content: str


class TeamTemplatesResult(ModelData):
    """本机模板目录。 Local team template catalog."""

    templates: list[TeamTemplate]


class TeamTemplateExport(ModelData):
    """供用户保存的 UTF-8 JSON 文本。

    UTF-8 JSON text for explicit user export.
    """

    content: str
