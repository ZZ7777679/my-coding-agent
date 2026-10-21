"""记忆条目、设置和维护状态。

Memory entries, settings and maintenance state.
"""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.context.types import UsageSummary
from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData, ModelId, TokenUsage


class MemoryFields(ModelData):
    """用户可维护的知识正文；其余来源由宿主填写。

    Editable knowledge; the host supplies provenance.
    """

    title: Annotated[str, Field(min_length=1, max_length=256)]
    content: Annotated[str, Field(min_length=1, max_length=64000)]
    scope: Literal["project", "user"] = "project"
    category: str = "fact"
    tags: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    valid_from: str | None = None
    valid_until: str | None = None
    supersedes: list[EntityId] = Field(default_factory=list)
    related_ids: list[EntityId] = Field(default_factory=list)
    source_ids: list[EntityId] = Field(default_factory=list)
    stale: bool = False
    pinned: bool = False
    enabled: bool = True


class MemoryTraceSource(ModelData):
    """宿主实际读取的会话事实，不由模型填写。

    A session fact actually read by the host, never authored by the model.
    """

    session_id: EntityId
    seq: Annotated[int, Field(ge=1)]


class MemoryEntry(MemoryFields):
    """带作用域和修订来源的独立记忆。

    Independent memory with scope and revision provenance.
    """

    memory_id: EntityId
    project_id: str | None
    revision: int
    source: Literal["user", "agent", "maintenance"]
    session_id: EntityId | None
    source_seq: int | None
    trace_sources: list[MemoryTraceSource] = Field(default_factory=list)
    created_at: str
    updated_at: str


class MemorySettings(ModelData):
    """使用和贡献分别控制，实验默认关闭。

    Independent use/contribution controls; experiments start disabled.
    """

    use: bool = True
    contribute: bool = True
    automatic: bool = True
    associations: bool = False
    auto_pages: bool = False
    recall_chars: Annotated[int, Field(ge=0)] = 6000
    recall_limit: Annotated[int, Field(ge=1)] = 8
    maintenance_requests: Annotated[int, Field(ge=1)] = 2
    maintenance_input_bytes: Annotated[int, Field(ge=4096)] = 60000


class MemoryJob(ModelData):
    """独立维护费用与状态，不改已结束 Run 的账本。

    Maintenance cost/state separate from finished runs.
    """

    job_id: EntityId
    model_id: ModelId
    status: Literal["running", "completed", "failed", "cancelled", "interrupted"]
    through_seq: int
    requests: int = 0
    usage: TokenUsage = Field(
        default_factory=lambda: TokenUsage(input_tokens=None, output_tokens=None)
    )
    message: str = ""
    started_at: str
    finished_at: str | None = None


class MemoryState(ModelData):
    """会话贡献起点与最近维护事实。

    Session contribution boundary and latest maintenance facts.
    """

    settings: MemorySettings = Field(default_factory=MemorySettings)
    processed_seq: int
    pending_seq: int | None = None
    pending_offset: int = 0
    job: MemoryJob | None = None
    used_ids: list[EntityId] = Field(default_factory=list)


class MemoryParams(ModelData):
    """当前项目内管理记忆。

    Manage memory within the current project.
    """

    session_id: EntityId


class MemoryQuery(ModelData):
    """词法与结构检索，可按需查询历史条目。

    Lexical/structured retrieval with optional historical entries.
    """

    query: str = ""
    category: str | None = None
    subject: str | None = None
    include_disabled: bool = False
    cursor: EntityId | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 20


class ListMemoryParams(MemoryParams, MemoryQuery):
    """桌面记忆检索。

    Desktop memory lookup.
    """


class SaveMemoryParams(MemoryParams):
    """显式保存知识，可更新已知条目。

    Explicit knowledge save or update.
    """

    memory_id: EntityId | None = None
    fields: MemoryFields


class ForgetMemoryParams(MemoryParams):
    """删除条目正文而不删除聊天。

    Delete entry content, not conversation history.
    """

    memory_id: EntityId


class ConfigureMemoryParams(MemoryParams):
    """保存会话的使用、贡献和实验选项。

    Save session use, contribution and experiment settings.
    """

    settings: MemorySettings


class MaintainMemoryParams(MemoryParams):
    """手动整理可显式选择旧范围，默认仅处理增量。

    Manual maintenance can explicitly select old history.
    """

    after_seq: Annotated[int, Field(ge=0)] | None = None
    source_ids: list[EntityId] = Field(default_factory=list)
    title: str = ""


class MemoryPage(ModelData):
    """管理页与检索结果，不隐藏局部读取失败。

    Management/retrieval results with local read failures.
    """

    entries: list[MemoryEntry]
    next_cursor: EntityId | None
    unavailable_count: int = 0
    state: MemoryState
    totals: UsageSummary = Field(default_factory=UsageSummary)


class MemoryMutation(ModelData):
    """后台候选只表达内容更新，不伪造来源。

    Maintenance candidates express edits, never forged provenance.
    """

    memory_id: EntityId | None = None
    fields: MemoryFields


class MemoryExtraction(ModelData):
    """一次维护结果可以为空。

    A maintenance batch may legitimately be empty.
    """

    entries: list[MemoryMutation] = Field(default_factory=list)
