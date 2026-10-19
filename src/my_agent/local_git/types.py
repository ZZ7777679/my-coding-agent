"""本地 Git 工作台的严格公开契约。

Strict public contracts for local Git."""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.models.types import ModelData

GitPath = Annotated[str, Field(min_length=1, max_length=4096, pattern=r"^[^\x00]*$")]


class GitProjectParams(ModelData):
    """已登记项目身份。

    Registered project identity."""

    project_id: str


class GitDiffParams(GitProjectParams):
    """明确查看工作区或暂存区的一个路径。

    Read one worktree or index path diff."""

    path: GitPath
    area: Literal["worktree", "index"] = "worktree"


class ConfigureGitParams(GitProjectParams):
    """用户切换 Git；关闭移走自身元数据，开启恢复。

    Toggle Git with recoverable metadata relocation."""

    enabled: bool


class GitSettings(GitProjectParams):
    """开关与实际备份事实，不探测上层仓库。

    Switch and actual backup facts, without parent discovery."""

    enabled: bool = True
    backup_path: str | None = None
    project_metadata_present: bool = False


class GitPathsParams(GitProjectParams):
    """按明确文件操作，不能以空路径列表提交全部。

    Operate on explicit paths only.
    """

    paths: Annotated[list[GitPath], Field(min_length=1)]


class GitCommitParams(GitProjectParams):
    """用户明确提交现有暂存区，不自动 stage 或设置身份。

    Commit existing index without staging.
    """

    message: Annotated[str, Field(min_length=1, max_length=64000, pattern=r"\S")]


class GitHistoryParams(GitProjectParams):
    """本地历史的可调查询大小。

    Adjustable local-history query size."""

    limit: Annotated[int, Field(ge=1, le=1000)] = 30


class GitFileStatus(ModelData):
    """Git 的工作区与暂存区双列状态。

    Git's separate worktree and index status columns.
    """

    path: str
    index_status: str
    worktree_status: str
    original_path: str | None = None


class GitStatus(ModelData):
    """工具可用性与仓库事实，不需要 remote。

    Availability and repository facts without remote.
    """

    project_id: str
    available: bool
    repository: bool
    repository_root: str | None = None
    project_repository: bool = False
    branch: str | None
    files: list[GitFileStatus]
    code: str | None = None
    message: str | None = None


class GitDiff(ModelData):
    """作为纯文本显示的当前本地差异。

    Current local diff displayed as plain text."""

    project_id: str
    path: str
    area: Literal["worktree", "index"]
    text: str
    truncated: bool


class GitCommit(ModelData):
    """本地提交身份与简要历史，不公开 Git 配置。

    Local commit identity and concise history.
    """

    commit_id: str
    subject: str
    author: str
    authored_at: str


class GitHistory(ModelData):
    """本地提交列表。

    Local commit list."""

    project_id: str
    commits: list[GitCommit]


class GitCommitResult(ModelData):
    """提交完成后的真实 HEAD 与命令输出。

    Actual HEAD and output after commit."""

    project_id: str
    commit_id: str
    output: str
