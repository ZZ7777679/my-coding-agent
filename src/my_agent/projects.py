"""CLI 与桌面共用的项目登记与恢复服务，不修改用户项目内容。

Shared project registration and recovery for CLI and desktop, without editing projects.
"""

import os
from pathlib import Path
from uuid import uuid4

from pydantic import model_validator

from my_agent.errors import AgentError
from my_agent.rpc.dto import DTO, Identifier, ProjectSummary, ProjectsView, Text, Timestamp
from my_agent.storage import Storage, read_document, utc_now, write_document


class ProjectRecord(DTO):
    """保存路径、文件系统身份和最近打开时间，用于重启后重新验证。

    Persist paths, filesystem identity and last-open time for revalidation after restart.
    """

    project_id: Identifier
    name: Text
    path: Text
    canonical_path: Text
    identity: Text
    last_opened_at: Timestamp


class ProjectIndex(DTO):
    """保存项目记录与当前选择引用；不等同于文件系统实时状态。

    Store project records and the active reference, not live filesystem state.
    """

    schema_version: int
    last_active_project_id: Identifier | None
    projects: list[ProjectRecord]

    @model_validator(mode="after")
    def consistent_ids(self) -> "ProjectIndex":
        """拒绝重复项目标识和指向不存在记录的当前选择。

        Reject duplicate IDs and active references to nonexistent records.
        """

        ids = [p.project_id for p in self.projects]
        if len(set(ids)) != len(ids) or (
            self.last_active_project_id is not None and self.last_active_project_id not in ids
        ):
            raise ValueError("Invalid project references")
        return self


def inspect_project(path: Path, data_root: Path) -> tuple[Path, str]:
    """解析真实目录并检查可访问性、数据重叠和文件系统身份。

    Resolve the directory and check access, data-root overlap and filesystem identity.
    """

    try:
        canonical = path.resolve(strict=True)
        if not canonical.is_dir():
            raise AgentError("PROJECT_UNAVAILABLE", "选择的路径不是文件夹。")
        if canonical.is_relative_to(data_root) or data_root.is_relative_to(canonical):
            raise AgentError("PROJECT_DATA_OVERLAP", "项目目录与应用数据目录不能相同或互相包含。")
        with os.scandir(canonical) as entries:
            next(entries, None)
        stat = canonical.stat()
        return canonical, str(stat.st_dev) + ":" + str(stat.st_ino)
    except (OSError, RuntimeError) as exc:
        raise AgentError("PROJECT_UNAVAILABLE", "项目目录不存在或无法访问，请重新选择。") from exc


class ProjectService:
    """在给定存储根管理项目索引；所有写操作要求已有写入锁。

    Manage the project index under one storage root; writes require its existing lock.
    """

    def __init__(self, storage: Storage) -> None:
        """绑定存储与索引位置，不读取或创建项目记录。

        Bind storage and index location without reading or creating records.
        """

        self.storage = storage
        self.path = storage.root / "projects.json"

    def read(self) -> ProjectIndex:
        """只读加载索引；缺失返回初始结构，损坏或版本不兼容明确失败。

        Read the index; default only when absent and fail on corruption or version mismatch.
        """

        if not self.path.exists():
            return ProjectIndex(schema_version=1, last_active_project_id=None, projects=[])
        index = read_document(self.path, ProjectIndex)
        if index.schema_version != 1:
            raise AgentError("DATA_VERSION_UNSUPPORTED", "项目记录版本不受支持。")
        return index

    def initialize(self) -> None:
        """持锁初始化缺失文件，保留所有已有索引内容。

        Initialize missing files under the lock while preserving existing index content.
        """

        self.storage.require_writer()
        index = self.read()
        self.storage.initialize()
        if not self.path.exists():
            write_document(self.path, index)

    def summary(self, record: ProjectRecord) -> ProjectSummary:
        """重新验证目录身份，将失效原因作为状态返回并保留记录。

        Revalidate directory identity and report unavailability without discarding the record.
        """

        error: str | None = None
        try:
            _, identity = inspect_project(Path(record.path), self.storage.root)
            if identity != record.identity:
                error = "PROJECT_CHANGED"
        except AgentError as exc:
            error = exc.code
        return ProjectSummary(
            project_id=record.project_id,
            name=record.name,
            path=record.path,
            canonical_path=record.canonical_path,
            last_opened_at=record.last_opened_at,
            available=error is None,
            unavailable_code=error,
        )

    def view(self) -> ProjectsView:
        """返回当前项目与最近二十项摘要；列表截取不删除已保存记录。

        Return the active project and twenty recent summaries without deleting stored records.
        """

        index = self.read()
        ordered = sorted(index.projects, key=lambda item: item.last_opened_at, reverse=True)
        active = next(
            (item for item in index.projects if item.project_id == index.last_active_project_id),
            None,
        )
        return ProjectsView(
            active_project=self.summary(active) if active else None,
            recent_projects=[self.summary(item) for item in ordered[:20]],
        )

    def open(self, *, path: str | None = None, project_id: str | None = None) -> ProjectsView:
        """验证选择、复用目录身份并原子保存索引；不初始化项目 Git 或修改代码。

        Validate selection, reuse directory identity and atomically save without editing projects.
        """

        self.storage.require_writer()
        if (path is None) == (project_id is None):
            raise AgentError("INVALID_PARAMS", "必须指定项目路径或已有项目标识。")
        index = self.read()
        existing: ProjectRecord | None = None
        if project_id is not None:
            existing = next((p for p in index.projects if p.project_id == project_id), None)
            if existing is None:
                raise AgentError("PROJECT_NOT_FOUND", "找不到该项目记录。")
            path = existing.path
        # 二选一的输入与已有记录查找已保证路径存在。
        # The exclusive inputs and record lookup above guarantee a path value.
        assert path is not None
        display = Path(path).absolute()
        canonical, identity = inspect_project(display, self.storage.root)
        if existing is not None and existing.identity != identity:
            raise AgentError("PROJECT_CHANGED", "该路径的目录已被替换，请重新选择项目。")
        if existing is None:
            existing = next(
                (p for p in index.projects if p.identity == identity and self.summary(p).available),
                None,
            )
        record = ProjectRecord(
            project_id=existing.project_id if existing else str(uuid4()),
            name=display.name or str(display),
            path=str(display),
            canonical_path=str(canonical),
            identity=identity,
            last_opened_at=utc_now(),
        )
        updated = ProjectIndex(
            schema_version=1,
            last_active_project_id=record.project_id,
            projects=[p for p in index.projects if p.project_id != record.project_id] + [record],
        )
        self.storage.initialize()
        write_document(self.path, updated)
        return self.view()
