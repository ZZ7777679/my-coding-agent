"""空间群聊与团队模板的单写者保存。

Single-writer persistence for space chat and team templates.
"""

import json
from collections.abc import Mapping
from pathlib import Path

from my_agent.errors import AgentError
from my_agent.models.types import ModelData
from my_agent.spaces.store import SpaceStore
from my_agent.spaces.team_types import (
    SpaceChatMessage,
    SpaceChatRecord,
    SpaceChatView,
    SpaceRound,
    TeamGeneration,
    TeamTemplate,
)
from my_agent.storage import MAX_DOCUMENT_BYTES, read_document, write_document


class SpaceTeamStore:
    """保存关联而非第二套日志，沿用原子替换。

    Store associations rather than duplicate logs using atomic replacement.
    """

    def __init__(self, spaces: SpaceStore) -> None:
        """复用已选数据根与写者。 Reuse the selected data root and writer."""
        self.spaces = spaces
        self.root = spaces.root
        self.cached_chats: dict[str, SpaceChatRecord] = {}

    def chat(self, task_id: str) -> SpaceChatRecord:
        """缺失返回未写入的空快照，故障保留原文件。

        Return an unsaved empty snapshot on absence; preserve failures.
        """
        path = self.spaces.path(task_id).with_name(f"{task_id}.chat.json")
        if task_id in self.cached_chats:
            return self.cached_chats[task_id].model_copy(deep=True)
        try:
            path.stat()
        except FileNotFoundError:
            record = SpaceChatRecord(view=SpaceChatView(task_id=task_id))
        except OSError as exc:
            raise AgentError("SPACE_CHAT_UNAVAILABLE", "无法读取群聊记录。") from exc
        else:
            record = read_document(path, SpaceChatRecord)
        if record.view.task_id != task_id:
            raise AgentError("SPACE_CHAT_DAMAGED", "群聊身份不一致，原文件已保留。")
        # 旧快照只读保留，分项更新覆盖相同身份；中断后从已落盘事实恢复。
        # Keep legacy snapshots; per-item records override identical IDs after interruption.
        root = self.root / f"{task_id}.chat"
        messages = {item.message_id: item for item in record.view.messages}
        rounds = {item.round_id: item for item in record.view.rounds}
        generations = {item.params.operation_id: item for item in record.view.generations}
        try:
            for item_path in sorted((root / "messages").glob("*.json")):
                message = read_document(item_path, SpaceChatMessage)
                messages[message.message_id] = message
            for item_path in sorted((root / "rounds").glob("*.json")):
                round_item = read_document(item_path, SpaceRound)
                rounds[round_item.round_id] = round_item
            for item_path in sorted((root / "generations").glob("*.json")):
                generation = read_document(item_path, TeamGeneration)
                generations[generation.params.operation_id] = generation
        except OSError as exc:
            raise AgentError("SPACE_CHAT_UNAVAILABLE", "无法读取群聊分页记录。") from exc
        record.view.messages = sorted(
            messages.values(), key=lambda item: (item.created_at, item.message_id)
        )
        record.view.rounds = sorted(
            rounds.values(), key=lambda item: (item.created_at, item.round_id)
        )
        record.view.generations = sorted(generations.values(), key=lambda item: item.created_at)
        self.cached_chats[task_id] = record.model_copy(deep=True)
        return record

    def save_chat(self, record: SpaceChatRecord) -> SpaceChatRecord:
        """保存真实关联，公开输出每次由会话重新投影。

        Save actual references; project public output from sessions each time.
        """
        clean = record.model_copy(update={"view": record.view.model_copy(update={"outputs": []})})
        task_id = record.view.task_id
        previous = self.chat(task_id)
        root = self.root / f"{task_id}.chat"
        self.spaces.storage.require_writer()
        try:
            self._save_entries(
                root / "messages",
                {m.message_id: m for m in clean.view.messages},
                {m.message_id: m for m in previous.view.messages},
            )
            self._save_entries(
                root / "rounds",
                {r.round_id: r for r in clean.view.rounds},
                {r.round_id: r for r in previous.view.rounds},
            )
            self._save_entries(
                root / "generations",
                {g.params.operation_id: g for g in clean.view.generations},
                {g.params.operation_id: g for g in previous.view.generations},
            )
        except (AgentError, OSError) as exc:
            self.cached_chats.pop(task_id, None)
            if isinstance(exc, AgentError):
                raise
            raise AgentError("SPACE_SAVE_FAILED", "群聊记录保存失败，已落盘记录保留。") from exc
        self.cached_chats[task_id] = clean.model_copy(deep=True)
        return clean

    def _save_entries(
        self, root: Path, entries: Mapping[str, ModelData], old: Mapping[str, ModelData]
    ) -> None:
        """仅原子替换变化记录，不给全部历史设置统一容量。

        Atomically replace changed records without a total history capacity gate.
        """
        for identity, item in entries.items():
            if old.get(identity) == item:
                continue
            root.mkdir(parents=True, exist_ok=True)
            write_document(root / f"{identity}.json", item)

    def _write(self, path: Path, value: SpaceChatRecord | TeamTemplate) -> None:
        """复用存储容量和单写者，不宣称跨文件事务。

        Reuse storage capacity and writer without cross-file transactions.
        """
        self.spaces.storage.require_writer()
        if (
            len(
                (
                    json.dumps(value.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")
            )
            > MAX_DOCUMENT_BYTES
        ):
            raise AgentError("SPACE_CAPACITY", "空间记录超过存储容量，原文件已保留。")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_document(path, value)
        except OSError as exc:
            raise AgentError("SPACE_SAVE_FAILED", "空间保存失败，原文件已保留。") from exc

    def template(self, template_id: str) -> TeamTemplate:
        """严格读取模板，不创建缺失文件。

        Strictly read a template without creating missing files.
        """
        path = self.spaces.path(template_id).with_name(f"{template_id}.template.json")
        value = read_document(path, TeamTemplate)
        if value.template_id != template_id:
            raise AgentError("SPACE_TEMPLATE_DAMAGED", "模板身份不一致。")
        return value

    def templates(self) -> list[TeamTemplate]:
        """读取模板目录，损坏条目明确返回错误。

        Read the catalog and report corrupt entries explicitly.
        """
        try:
            paths = sorted(self.root.glob("*.template.json"))
        except OSError as exc:
            raise AgentError("SPACE_TEMPLATE_UNAVAILABLE", "无法读取团队模板目录。") from exc
        return [self.template(path.name.removesuffix(".template.json")) for path in paths]

    def save_template(self, template: TeamTemplate) -> TeamTemplate:
        """保存用户配置快照，不解析自由说明中的路径或命令。

        Save the user's snapshot without interpreting paths or commands in prose.
        """
        path = self.spaces.path(template.template_id).with_name(
            f"{template.template_id}.template.json"
        )
        self._write(path, template)
        return template
