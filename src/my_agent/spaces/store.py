"""合作空间在应用数据根单文件保存。

Persist each collaboration space under the application data root.
"""

import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from my_agent.errors import AgentError
from my_agent.identifiers import EntityId
from my_agent.spaces.types import SaveSpaceParams, SpaceRecord, SpaceView
from my_agent.storage import MAX_DOCUMENT_BYTES, Storage, read_document, utc_now, write_document
from my_agent.tasks.types import TaskView


class SpaceStore:
    """复用单写者与原子替换，读取不创建空间。

    Reuse the single writer and atomic files; reads create nothing.
    """

    def __init__(self, storage: Storage) -> None:
        """绑定数据根，不向项目落数据。

        Bind the data root without writing into projects.
        """
        self.storage = storage
        self.root = storage.root / "spaces"

    def path(self, task_id: str) -> Path:
        """验证任务身份和真实存储位置。

        Validate the task identity and actual storage location.
        """
        try:
            TypeAdapter(EntityId).validate_python(task_id, strict=True)
        except ValidationError as exc:
            raise AgentError("SPACE_NOT_FOUND", "空间任务标识不正确。") from exc
        path = self.root / f"{task_id}.json"
        if path.resolve() != path:
            raise AgentError("SPACE_STORAGE_INVALID", "空间存储路径含有不支持的链接。")
        return path

    def get(self, task_id: str) -> SpaceRecord | None:
        """缺失返回空；损坏和访问故障保留原文件。

        Return absent state; preserve corrupt or inaccessible files.
        """
        path = self.path(task_id)
        try:
            # stat 区分真正缺失与访问故障；不将读取错误当作旧任务。
            # Stat separates absence from access failures; failures are not legacy state.
            path.stat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise AgentError("SPACE_UNAVAILABLE", "无法读取空间记录，原文件已保留。") from exc
        try:
            record = read_document(path, SpaceRecord)
            if record.view.task_id != task_id:
                raise AgentError("SPACE_DAMAGED", "空间记录身份不一致，原文件已保留。")
            return record
        except AgentError as exc:
            if exc.code == "DATA_INVALID":
                raise AgentError(
                    "SPACE_DAMAGED", "空间记录损坏或版本不支持，原文件已保留。"
                ) from exc
            if exc.code == "DATA_UNAVAILABLE":
                raise AgentError("SPACE_UNAVAILABLE", "无法读取空间记录，原文件已保留。") from exc
            raise

    def _write(self, record: SpaceRecord) -> SpaceRecord:
        """保存成功后发布新版本；不宣称跨文件事务。

        Publish only durable revisions, without cross-file transactions.
        """
        self.storage.require_writer()
        path = self.path(record.view.task_id)
        content = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        if len(content.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise AgentError("SPACE_CAPACITY", "空间记录超过存储容量，原文件已保留。")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_document(path, record)
        except OSError as exc:
            raise AgentError("SPACE_SAVE_FAILED", "无法保存空间记录，原文件已保留。") from exc
        return record

    def save_config(self, task: TaskView, params: SaveSpaceParams) -> SpaceRecord:
        """只改配置，保留所有当前和历史会话绑定。

        Update configuration while preserving all session bindings.
        """
        current = self.get(params.task_id)
        revision = current.view.revision if current is not None else None
        if params.expected_revision != revision:
            raise AgentError("SPACE_VERSION_CONFLICT", "空间已变化，请重新载入后合并修改。")
        if current is None:
            now = utc_now()
            return self._write(
                SpaceRecord(
                    view=SpaceView(
                        task_id=task.task_id,
                        project_id=task.project_id,
                        revision=1,
                        config=params.config,
                        created_at=now,
                        updated_at=now,
                    )
                )
            )
        if current.view.project_id != task.project_id:
            raise AgentError("SPACE_PROJECT_MISMATCH", "空间与任务项目归属不一致。")
        if current.view.config == params.config:
            return current
        return self.save(
            current.model_copy(
                update={"view": current.view.model_copy(update={"config": params.config})}
            )
        )

    def save(self, record: SpaceRecord) -> SpaceRecord:
        """业务线程内推进版本并原子保存恢复状态。

        Advance revision and atomically save recovery state on the worker.
        """
        view = record.view.model_copy(
            update={"revision": record.view.revision + 1, "updated_at": utc_now()}
        )
        return self._write(record.model_copy(update={"view": view}))
