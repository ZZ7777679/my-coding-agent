"""回退使用公开状态与内部快照分离的契约。

Public rollback states are separate from stored snapshots.
"""

import json
from importlib.resources import files
from typing import Annotated, Literal

from pydantic import Field

from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData

_DEFAULTS = json.loads(files("my_agent").joinpath("defaults.json").read_text(encoding="utf-8"))[
    "rollback"
]


class RollbackSettings(ModelData):
    """只限制检查点覆盖范围，不限制编码任务。 Bound checkpoint coverage, never coding execution."""

    enabled: bool = _DEFAULTS["enabled"]
    max_file_bytes: Annotated[int, Field(ge=1)] = _DEFAULTS["max_file_bytes"]
    max_total_bytes: Annotated[int, Field(ge=1)] = _DEFAULTS["max_total_bytes"]


class FileCheckpointSummary(ModelData):
    """检查点来源与覆盖事实，不向模型暴露内容摘要键。 Checkpoint provenance and actual coverage."""

    checkpoint_id: EntityId
    session_id: EntityId
    project_id: str
    run_id: EntityId | None
    before_seq: int
    title: str
    kind: Literal["request", "restore"] = "request"
    status: Literal["capturing", "ready", "partial", "failed"]
    created_at: str
    finished_at: str | None = None
    changed_files: int = 0
    issues: list[str] = Field(default_factory=list)


class FileSnapshot(ModelData):
    """内部内容地址仅用于存储去重，不是模型编辑门槛。

    Internal addresses deduplicate storage only.
    """

    files: dict[str, str] = Field(default_factory=dict)
    omitted: list[str] = Field(default_factory=list)
    discovery_complete: bool = True
    # None 表示旧快照未记录忽略范围；空列表才表示没有忽略入口。
    # None denotes legacy unknown coverage; an empty list means no excluded roots.
    excluded_paths: list[str] | None = None


class FileCheckpoint(ModelData):
    """保存请求前后原始字节引用。 Store before/after references to original file bytes."""

    summary: FileCheckpointSummary
    before: FileSnapshot
    after: FileSnapshot | None = None


class CheckpointParams(ModelData):
    """读取所选会话的代码起点。 Read code starting points for a selected session."""

    session_id: EntityId


class CheckpointPage(ModelData):
    """列出可恢复点和局部不可读记录。 List restore points and unreadable entries."""

    checkpoints: list[FileCheckpointSummary]
    unavailable_count: int = 0


class PreviewCheckpointParams(CheckpointParams):
    """预览回到所选请求之前的代码变化。 Preview code changes back to a selected request."""

    checkpoint_id: EntityId


class RestoreCheckpointParams(PreviewCheckpointParams):
    """明确指定恢复方式和文件，不自动执行新的模型请求。

    Restore without automatically running a new prompt.
    """

    mode: Literal["code", "conversation"] = "code"
    paths: list[str] | None = None
    include_observed: bool = False
    operation_id: EntityId


class RestoreFile(ModelData):
    """单文件真实预览／结果；未知写入来源不能伪造成 Agent 修改。

    Per-file preview/result with honest provenance.
    """

    path: str
    source: Literal["agent", "observed", "other_session"]
    status: Literal["ready", "unchanged", "conflict", "restored", "failed", "skipped"]
    message: str = ""
    diff: str = ""


class RestorePreview(ModelData):
    """恢复范围、提示与来源。 Restore scope, limitations and provenance."""

    checkpoint: FileCheckpointSummary
    files: list[RestoreFile]
    issues: list[str] = Field(default_factory=list)


class RestoreResult(ModelData):
    """逐文件结果与反向检查点，对话未成功回退时如实显示。 Per-file outcomes and undo checkpoint."""

    files: list[RestoreFile]
    undo_checkpoint_id: EntityId
    rewound: bool
    prompt: str = ""
    message: str


class RestoreReceipt(ModelData):
    """先保存操作身份及逐文件结果，中断后不盲目重放。

    Journal identity and outcomes without blind replay.
    """

    params: RestoreCheckpointParams
    result: RestoreResult
    completed: bool = False


class ConversationRestored(ModelData):
    """追加回退事实，旧分支完整保留供 Trace 查看。

    Append rewind facts while retaining old branches.
    """

    kind: Literal["session.restored"] = "session.restored"
    operation_id: EntityId
    checkpoint_id: EntityId
    before_seq: int | None = None
    paths: list[str] = Field(default_factory=list)
    message: str
