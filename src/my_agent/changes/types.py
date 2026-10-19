"""差异的公开数据契约。 Public file-change contracts."""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.models.types import ModelData
from my_agent.sessions.types import SessionId


class ChangeSummary(ModelData):
    """一次写入的来源与结果，准备状态不等于成功。

    Provenance and outcome; prepared is not success."""

    change_id: SessionId
    session_id: SessionId
    run_id: SessionId
    project_id: str
    tool_call_id: str
    path: str
    operation: Literal["create", "edit", "delete", "move", "create_directory", "delete_directory"]
    destination: str | None = None
    source: Literal["agent", "user", "restore"] = "agent"
    status: Literal["prepared", "applied", "failed"]
    created_at: str
    before_sha256: str | None
    after_sha256: str
    error: str | None = None


class ChangeRecord(ModelData):
    """同一原子元数据文件保存版本与两端原始字节。

    Atomically persist metadata and both byte images."""

    schema_version: Literal[1] = 1
    summary: ChangeSummary
    before_base64: str | None
    after_base64: str
    directory_manifest: dict[str, str] | None = None


class ListChangesParams(ModelData):
    """会话内分页，不接受文件系统路径。 Page by session without filesystem path input."""

    session_id: SessionId
    cursor: SessionId | None
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    scope: Literal["session", "task"] = "session"
    path: str | None = None


class GetChangeParams(ModelData):
    """按成果身份与字符游标读取差异。 Read a change by identity and character cursor."""

    session_id: SessionId
    change_id: SessionId
    offset: Annotated[int, Field(ge=0)] = 0


class ChangePage(ModelData):
    """差异元数据页，损坏记录明确计数。 Metadata page with explicit unreadable-record count."""

    changes: list[ChangeSummary]
    next_cursor: SessionId | None
    unavailable_count: int
    coverage: str = "文件工具及编辑器保存的修改；未记录的外部或 shell 写入来源未知。"


class ChangeView(ModelData):
    """历史修改的有界 diff；不代表当前磁盘内容。 Bounded historical diff, not live disk contents."""

    summary: ChangeSummary
    diff: str
    next_offset: int | None
