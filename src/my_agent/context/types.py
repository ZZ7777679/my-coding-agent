"""上下文设置、摘要与公开状态。

Context settings, checkpoints and public state.
"""

import json
from importlib.resources import files
from typing import Annotated, Literal

from pydantic import Field, model_validator

from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData, ModelId, TokenUsage
from my_agent.runtime.context import ContextManifest

_DEFAULTS = json.loads(files("my_agent").joinpath("defaults.json").read_text(encoding="utf-8"))[
    "compaction"
]


class UsageSummary(ModelData):
    """已报告 token 与未知用量分别计数。

    Separate reported tokens from unknown usage.
    """

    requests: int = 0
    reported_input_tokens: int = 0
    reported_output_tokens: int = 0
    unknown_jobs: int = 0
    unavailable_jobs: int = 0


class ContextSettings(ModelData):
    """绝对 token 整理预算；与模型容量及生成额度分别管理。

    Absolute token policy, separate from model capacity and generation allowance.
    """

    automatic: bool = True
    auto_trigger_tokens: Annotated[int, Field(ge=1)] = _DEFAULTS["auto_trigger_tokens"]
    keep_recent_tokens: Annotated[int, Field(ge=0)] = _DEFAULTS["keep_recent_tokens"]
    tool_result_preview_tokens: Annotated[int, Field(ge=0)] = _DEFAULTS[
        "tool_result_preview_tokens"
    ]
    summary_target_tokens: Annotated[int, Field(ge=1)] = _DEFAULTS["summary_target_tokens"]
    summary_output_tokens: Annotated[int, Field(ge=1)] | None = None


class Checkpoint(ModelData):
    """完整保存的派生摘要，原始事件保持原样。

    Durable derived summary; raw events stay intact.
    """

    checkpoint_id: EntityId
    parent_id: EntityId | None
    through_seq: int
    text: str
    model_id: ModelId
    created_at: str
    usage: TokenUsage


class ContextJob(ModelData):
    """辅助整理的真实状态和累计用量。

    Actual maintenance state and cumulative usage.
    """

    job_id: EntityId
    run_id: EntityId | None
    status: Literal[
        "preparing", "receiving", "ready", "adopted", "failed", "cancelled", "interrupted"
    ]
    model_id: ModelId
    requests: int = 0
    usage: TokenUsage = Field(
        default_factory=lambda: TokenUsage(input_tokens=None, output_tokens=None)
    )
    message: str = ""
    started_at: str
    finished_at: str | None = None
    output_token_limit: int | None = None
    finish_reason: str | None = None
    history_before_bytes: int | None = None
    history_after_bytes: int | None = None
    compression_applied: bool | None = None
    mode: Literal["manual", "automatic"] = "manual"
    outcome: Literal["summary", "trimmed", "nothing", "not_smaller"] | None = None
    history_before_tokens: int | None = None
    history_after_tokens: int | None = None
    retained_tokens: int | None = None
    through_seq: int = 0
    policy: ContextSettings | None = None


class ToolPreview(ModelData):
    """只保存已采用预览的来源和预算，不复制正文。

    Store adopted preview provenance and budget, not another body.
    """

    seq: int
    tokens: int


class ContextState(ModelData):
    """会话级设置与摘要链，不保存另一份聊天。

    Session settings and checkpoint chain, not another chat.
    """

    schema_version: Literal[3] = 3
    settings: ContextSettings = Field(default_factory=ContextSettings)
    checkpoints: list[Checkpoint] = Field(default_factory=list)
    job: ContextJob | None = None
    previews: list[ToolPreview] = Field(default_factory=list)
    migrated_from_bytes: bool = False

    @model_validator(mode="before")
    @classmethod
    def upgrade_output_default(cls, value: object) -> object:
        """迁移旧字节策略，保留自动开关和明确设置的生成预算。

        Migrate byte policies, retaining automatic selection and explicit output overrides.
        """
        if isinstance(value, dict) and value and value.get("schema_version", 1) in (1, 2):
            upgraded = {**value, "schema_version": 3, "migrated_from_bytes": True}
            settings = value.get("settings")
            if isinstance(settings, dict):
                settings = dict(settings)
                for key in (
                    "prepare_ratio",
                    "target_ratio",
                    "recent_ratio",
                    "old_tool_preview_chars",
                ):
                    settings.pop(key, None)
                if "schema_version" not in value and settings.get("summary_output_tokens") == 2048:
                    settings["summary_output_tokens"] = None
                upgraded["settings"] = settings
            return upgraded
        return value


class ContextParams(ModelData):
    """定位本会话的窗口。

    Identify a session window.
    """

    session_id: EntityId


class ConfigureContextParams(ContextParams):
    """保存后续请求采用的整理设置。

    Save compaction settings for subsequent requests.
    """

    settings: ContextSettings


class ContextTokens(ModelData):
    """单次主请求的实际输入用量与独立的模型目录窗口。

    Reported input for one main request, alongside the separate catalog window.
    """

    model_id: ModelId
    window_tokens: int | None
    window_source: str
    input_tokens: int | None = None
    status: Literal["reported", "not_measured", "not_reported", "model_changed", "compacted"] = (
        "not_measured"
    )


class ContextRequest(ModelData):
    """最近请求的固定材料事实，后续设置不会改写。

    Fixed facts for the latest request, unaffected by later settings.
    """

    message_id: EntityId
    model_id: ModelId | None
    at: str
    manifest: ContextManifest


class ContextView(ContextParams):
    """输入区的 token 观察、字节处理量与整理事实。

    Token observations, byte processing sizes and compaction facts for the composer.
    """

    settings: ContextSettings
    tokens: ContextTokens
    checkpoint: Checkpoint | None
    job: ContextJob | None
    raw_bytes: int
    window_bytes: int
    limit_bytes: int
    measurement: Literal["history_bytes"] = "history_bytes"
    history_through_seq: int
    totals: UsageSummary = Field(default_factory=UsageSummary)
    last_request: ContextRequest | None = None
    estimated_history_tokens: int = 0
    estimated_input_tokens: int | None = None
    estimate_basis: str = "历史本地估计；尚无系统与工具计量"
    trigger_tokens: int = 0
    migrated_from_bytes: bool = False


class HistoryQuery(ModelData):
    """按来源、关键词和偏移读历史，所有偏移均为字符。

    Read history by source, query and character offset.
    """

    query: str = ""
    include_lookup_results: bool = False
    artifact_id: EntityId | None = None
    after_seq: Annotated[int, Field(ge=0)] = 0
    through_seq: Annotated[int, Field(ge=1)] | None = None
    entry_seq: Annotated[int, Field(ge=1)] | None = None
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    max_chars: Annotated[int, Field(ge=1, le=32000)] = 8000


class HistoryParams(HistoryQuery, ContextParams):
    """桌面读取指定会话的历史。

    Read a selected session's history from the desktop.
    """


class HistoryItem(ModelData):
    """公开材料片段，保留原序号和续读位置。

    Public fragment with original sequence and continuation.
    """

    seq: int
    kind: str
    text: str
    offset: int
    next_offset: int | None
    total_chars: int
    tool_name: str | None = None
    tool_call_id: str | None = None
    call_seq: int | None = None
    result_seq: int | None = None


class HistoryPage(ModelData):
    """可直接展开的材料索引及匹配数。

    Expandable material index and match count.
    """

    items: list[HistoryItem]
    next_after_seq: int | None
    matches: int
    match_unit: Literal["records", "occurrences"] = "records"
    through_seq: int
    complete: bool
