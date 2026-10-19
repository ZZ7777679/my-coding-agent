"""编辑器与文件工作台公开契约。

Public editor and file workbench contracts.
"""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.changes.types import ChangeSummary
from my_agent.models.types import ModelData
from my_agent.sessions.types import SessionId
from my_agent.tools.file_types import EditFileArgs
from my_agent.tools.read_only import SearchArgs


class DocumentSessionParams(ModelData):
    """以会话定位项目与草稿。

    Locate projects and drafts by session.
    """

    session_id: SessionId


class DocumentParams(DocumentSessionParams):
    """指定文件而不自动扫描项目外内容。

    Select a file without scanning outside the project.
    """

    path: Annotated[str, Field(min_length=1, max_length=4096)]


class DocumentListParams(DocumentSessionParams):
    """有界文件发现与快速打开查询。

    Bounded file discovery and quick-open filtering.
    """

    directory: str = "."
    query: str = ""
    limit: Annotated[int, Field(ge=1, le=1000)] = 500


class DocumentListing(ModelData):
    """发现得到的文件和目录，明确截断。

    Discovered files and directories with explicit truncation.
    """

    files: list[str]
    directories: list[str]
    truncated: bool
    skipped: int


class DocumentSearchParams(SearchArgs):
    """与模型共享的项目文本搜索。

    Project text search shared with model tools.
    """

    session_id: SessionId


class DocumentContextLine(ModelData):
    """带行号的搜索上下文。 Numbered search context."""

    line: int
    text: str


class DocumentMatch(ModelData):
    """匹配位置与当前文本。

    A match location and current line text.
    """

    path: str
    line: int
    text: str
    context_before: list[DocumentContextLine] = Field(default_factory=list)
    context_after: list[DocumentContextLine] = Field(default_factory=list)


class DocumentSearchResult(ModelData):
    """搜索命中与不可读数量。

    Search matches and unreadable counts.
    """

    matches: list[DocumentMatch]
    truncated: bool
    skipped: int
    backend: str


class DocumentView(ModelData):
    """完整可编辑文本及其读取事实。

    Complete editable text with read facts.
    """

    path: str
    content: str
    encoding: str
    newline: str
    read_at: str
    change_id: str | None = None


class SaveDocumentParams(DocumentParams):
    """保存时核对编辑器实际基线正文。

    Check the actual editor base text when saving.
    """

    base_content: str
    content: str


class DocumentDraft(SaveDocumentParams):
    """保存未写入项目的缓冲与恢复基线。

    Persist an unsaved buffer and its recovery baseline.
    """

    updated_at: str = ""


class DraftPage(ModelData):
    """会话的可恢复草稿。

    Recoverable drafts for a session.
    """

    drafts: list[DocumentDraft]


class DocumentOperationParams(DocumentParams):
    """明确选定文件操作与目的地。

    An explicitly selected file operation and destination.
    """

    operation: Literal["create_file", "create_directory", "move", "delete"]
    destination: str | None = None
    content: str = ""
    recursive: bool = False


class OperationItem(ModelData):
    """每个文件的实际成功或失败。

    Actual success or failure for one file.
    """

    path: str
    status: Literal["applied", "failed"]
    change_id: str | None = None
    code: str | None = None
    message: str | None = None


class OperationResult(ModelData):
    """保留部分成功与未执行项数量。

    Preserve partial success and unattempted counts.
    """

    items: list[OperationItem]
    partial: bool
    unattempted: int = 0


class PatchDocumentsParams(DocumentSessionParams):
    """多文件精确补丁。

    Exact patches across multiple files.
    """

    edits: Annotated[list[EditFileArgs], Field(min_length=1, max_length=100)]


class DocumentChangeParams(DocumentSessionParams):
    """只选择一个历史修改。

    Select one historical change.
    """

    change_id: SessionId


class DocumentDiff(ModelData):
    """历史两端与当前磁盘分别呈现。

    Present historical snapshots and current disk separately.
    """

    summary: ChangeSummary
    before: str
    after: str
    current: str
    current_exists: bool
    restorable: bool
    message: str | None = None
