"""组合现有流程、团队图和 Skill；不增加执行运行时。

Compose existing workflows, team graphs and Skills without another execution runtime.
"""

import re
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid5

from my_agent.errors import AgentError
from my_agent.spaces.types import SpaceConfig
from my_agent.storage import Storage, read_document, utc_now, write_document
from my_agent.workflow.style_types import (
    CaptureWorkStyle,
    WorkStyle,
    WorkStyleCatalog,
    WorkStyleDefault,
)

if TYPE_CHECKING:
    from my_agent.tasks.types import TaskView


class WorkStyleStore:
    """单写者保存组合与项目默认；任务保存独立副本。

    Single-writer storage for composites and project defaults; tasks retain independent copies.
    """

    def __init__(self, storage: Storage) -> None:
        """只定位数据根，不写项目目录。 Locate app data without touching projects."""
        self.storage = storage
        self.root = storage.root / "workstyles"

    def path(self, style_id: str) -> Path:
        """UUID 身份定位模板。 Locate templates by UUID identity."""
        return self.root / (str(UUID(style_id)) + ".json")

    def default_path(self, project_id: str) -> Path:
        """项目设置与可分享模板分开保存。

        Keep project settings separate from shareable templates.
        """
        return self.root / "projects" / (str(UUID(project_id)) + ".json")

    def selected(self, project_id: str) -> str | None:
        """没有项目设置即没有组合默认，不改变旧流程。

        Missing settings do not alter existing workflow defaults.
        """
        path = self.default_path(project_id)
        return read_document(path, WorkStyleDefault).style_id if path.exists() else None

    def load(self, style_id: str) -> WorkStyle:
        """读取定义；损坏内容保持原样。 Read definitions without replacing corrupt contents."""
        return read_document(self.path(style_id), WorkStyle)

    def catalog(self, project_id: str | None = None) -> WorkStyleCatalog:
        """逐项列出可读模板及问题，不加载任何会话。

        List templates and local issues without sessions.
        """
        result = WorkStyleCatalog()
        for path in self.root.glob("*.json"):
            try:
                result.styles.append(read_document(path, WorkStyle))
            except AgentError as exc:
                result.issues.append(path.stem + ": " + exc.message)
        if project_id:
            result.default_style_id = self.selected(project_id)
        return result

    @staticmethod
    def portable(style: WorkStyle, project_root: Path | None = None) -> WorkStyle:
        """去除运行事实和已知项目绝对路径，保留方法与逻辑关系。

        Strip execution facts and known project paths while retaining methods and relationships.
        """
        result = style.model_copy(deep=True)
        for item in result.team.initial_work_items:
            item.status, item.claim_status = "planned", "assigned" if item.owner_member_id else None
            item.run_id, item.result = None, None
            item.evidence, item.feedback_from = [], []
        if project_root:
            # 只改明确的当前项目根，不猜测或删除普通文案。
            # Replace only the known project root, never guess paths in ordinary prose.
            value = result.model_dump(mode="json")

            def relative(node: object) -> object:
                """递归转换已知路径前缀，结构仍由契约解析。

                Replace known path prefixes while retaining the schema.
                """
                if isinstance(node, str):
                    for prefix in {str(project_root), project_root.as_posix()}:
                        node = re.sub(re.escape(prefix) + r"""(?=$|[/\\\s"',;)])""", ".", node)
                    return node
                if isinstance(node, list):
                    return [relative(item) for item in node]
                if isinstance(node, dict):
                    return {key: relative(item) for key, item in node.items()}
                return node

            result = WorkStyle.model_validate(relative(value))
        return result

    def save(self, style: WorkStyle) -> WorkStyle:
        """保存蓝图不反向更新任务快照。 Save a blueprint without updating existing tasks."""
        self.storage.require_writer()
        result = self.portable(style)
        result.updated_at = utc_now()
        self.root.mkdir(parents=True, exist_ok=True)
        write_document(self.path(result.style_id), result)
        return result

    def set_default(self, params: WorkStyleDefault) -> WorkStyleCatalog:
        """只保存未来默认，不执行或重建已有任务。

        Persist a future default without running/rebuilding tasks.
        """
        self.storage.require_writer()
        if params.style_id:
            self.load(params.style_id)
        path = self.default_path(params.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_document(path, params)
        return self.catalog(params.project_id)

    @staticmethod
    def instantiate(style: WorkStyle, task_id: str) -> WorkStyle:
        """为任务生成稳定的新成员身份，不携带旧绑定或执行结果。

        Generate task-specific stable member identities without bindings or execution results.
        """
        result = WorkStyleStore.portable(style)
        identities = {
            member.member_id: str(uuid5(UUID(task_id), "member:" + member.member_id))
            for member in result.team.members
        }
        for member in result.team.members:
            member.member_id = identities[member.member_id]
        for edge in result.team.edges:
            edge.edge_id = str(uuid5(UUID(task_id), "edge:" + edge.edge_id))
            edge.source_member_id = identities[edge.source_member_id]
            edge.target_member_id = identities[edge.target_member_id]
        result.team.receiver_member_id = identities.get(result.team.receiver_member_id or "")
        for item in result.team.initial_work_items:
            item.owner_member_id = identities.get(item.owner_member_id or "")
        return result

    def capture(self, task: "TaskView", params: CaptureWorkStyle, root: Path) -> WorkStyle:
        """从当前定义生成组合，不保存进度或其他成员聊天。

        Capture definitions without progress or peer history.
        """
        from my_agent.spaces.store import SpaceStore
        from my_agent.spaces.work_graph import work_items

        record = SpaceStore(self.storage).get(task.task_id)
        team = record.view.config.model_copy(deep=True) if record else SpaceConfig()
        team.initial_work_items = (
            work_items(task, record.view) if record else task.work.planned_items
        )
        chosen = list(
            dict.fromkeys(
                [*(task.workstyle.skill_ids if task.workstyle else []), *params.skill_ids]
            )
        )
        style = WorkStyle(
            style_id=params.style_id,
            name=params.name,
            description=params.description,
            workflow=task.workflow.template if task.workflow else None,
            team=team,
            skill_ids=chosen,
        )
        return self.portable(style, root)
