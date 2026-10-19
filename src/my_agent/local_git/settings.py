"""项目 Git 开关和可恢复元数据移动。

Project Git switch and recoverable metadata relocation."""

import os
import shutil
from pathlib import Path

from my_agent.errors import AgentError
from my_agent.execution.environments import EnvironmentStore
from my_agent.local_git.types import GitSettings
from my_agent.models.types import ModelData
from my_agent.storage import read_document, write_document


class GitPreference(ModelData):
    """只持久化用户开关，其余状态来自文件。

    Persist only the switch; derive filesystem facts."""

    enabled: bool = True


class GitSettingsStore:
    """只移动选定项目自身的 .git，保留工作文件和上层仓库。

    Relocate only the selected project's .git; preserve work files and parent repositories.
    """

    def __init__(self, environments: EnvironmentStore) -> None:
        """复用受控项目登记及数据根。

        Reuse registered projects and the application data root."""
        self.environments = environments
        self.storage = environments.storage

    def _paths(self, project_id: str) -> tuple[Path, Path, Path]:
        """先解析登记项目，再核实固定备份目录。

        Resolve registration before checking backup containment."""
        root = self.environments.project_root(project_id)
        if Path(project_id).name != project_id or project_id in {".", ".."}:
            raise AgentError("GIT_SETTINGS_INVALID", "项目身份不能用于 Git 备份目录。")
        base = self.storage.root.resolve() / "git-backups" / project_id
        if not base.resolve().is_relative_to(self.storage.root.resolve()):
            raise AgentError("GIT_BACKUP_PATH_INVALID", "Git 备份目录已指向应用数据根之外。")
        return root / ".git", base / "metadata", base / "settings.json"

    def read(self, project_id: str) -> GitSettings:
        """旧项目默认启用；已有备份也能揭示中断后的关闭状态。

        Default on; backups expose interrupted moves."""
        source, backup, path = self._paths(project_id)
        preference = read_document(path, GitPreference) if path.exists() else GitPreference()
        saved = os.path.lexists(backup)
        return GitSettings(
            project_id=project_id,
            enabled=preference.enabled and not saved,
            backup_path=str(backup) if saved else None,
            project_metadata_present=os.path.lexists(source),
        )

    @staticmethod
    def _move(source: Path, target: Path) -> None:
        """移动前核实真实范围，不覆盖任何现有目标。

        Check actual bounds before moving; never overwrite."""
        if os.path.lexists(target):
            raise AgentError(
                "GIT_BACKUP_CONFLICT", "项目 .git 与备份同时存在；已保留两者，请先整理冲突。"
            )
        # .git 文件可作为 worktree 指针移动；绝不移动它指向的共享目录。
        # Move a worktree pointer file itself, never its shared metadata target.
        if (
            source.is_symlink()
            or source.is_junction()
            or source.resolve().parent != source.parent.resolve()
        ):
            raise AgentError(
                "GIT_METADATA_LINK", ".git 是链接目录，请先在项目中处理；未移动其目标。"
            )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
        except OSError as exc:
            raise AgentError(
                "GIT_BACKUP_FAILED",
                "Git 元数据移动未完成；已保留现有内容，请检查项目和备份位置后接续。",
            ) from exc

    def configure(self, project_id: str, enabled: bool) -> GitSettings:
        """先记录关闭意图再移动；开启只在恢复成功后保存。

        Persist off before moving; on after restoration."""
        self.storage.require_writer()
        source, backup, path = self._paths(project_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AgentError("GIT_BACKUP_FAILED", "无法创建 Git 设置与备份目录。") from exc
        if enabled:
            if os.path.lexists(backup):
                self._move(backup, source)
            write_document(path, GitPreference(enabled=True))
        else:
            write_document(path, GitPreference(enabled=False))
            if os.path.lexists(source):
                self._move(source, backup)
        return self.read(project_id)
