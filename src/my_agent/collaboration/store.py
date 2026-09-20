"""协作记录逐文件原子保存，不把跨文件写入描述为事务。

Persist collaboration records atomically per file, without cross-file transactions.
"""

from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pydantic import TypeAdapter

from my_agent.collaboration.types import CollaborationLink, CollaborationRequest
from my_agent.errors import AgentError
from my_agent.identifiers import EntityId
from my_agent.storage import Storage, read_document, write_document


class CollaborationStore:
    """共享业务写者下的约定 / 请求仓库；读取不会初始化目录。

    Agreements and requests under the shared writer; reads never initialize directories.
    """

    def __init__(self, storage: Storage) -> None:
        """绑定应用数据根。 Bind the application data root."""
        self.storage = storage
        self.root = storage.root / "collaboration"

    def _path(self, group: str, identity: str) -> Path:
        """校验记录身份后定位文件。 Resolve a file after validating its identity."""
        TypeAdapter(EntityId).validate_python(identity)
        return self.root / group / f"{identity}.json"

    def link(self, source: str, target: str) -> CollaborationLink | None:
        """读取定向约定，缺失与损坏分别处理。 Distinguish absent and corrupt agreements."""
        path = self._path("links", str(uuid5(NAMESPACE_URL, source + ":" + target)))
        return read_document(path, CollaborationLink) if path.exists() else None

    def links(self, session_id: str) -> list[CollaborationLink]:
        """返回与本会话有关的双方约定。 Return agreements involving this session."""
        result = []
        for path in sorted((self.root / "links").glob("*.json")):
            item = read_document(path, CollaborationLink)
            if session_id in {item.source_session_id, item.target_session_id}:
                result.append(item)
        return result

    def save_link(self, value: CollaborationLink) -> None:
        """保存用户约定，不唤醒模型。 Save a user agreement without waking models."""
        self.storage.require_writer()
        identity = str(
            uuid5(NAMESPACE_URL, value.source_session_id + ":" + value.target_session_id)
        )
        path = self._path("links", identity)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_document(path, value)

    def request(self, request_id: str) -> CollaborationRequest:
        """读取明确请求，缺失时报业务错误。 Read an exact request or report its absence."""
        path = self._path("requests", request_id)
        if not path.exists():
            raise AgentError("COLLABORATION_NOT_FOUND", "协作请求不存在。")
        return read_document(path, CollaborationRequest)

    def requests(self) -> list[CollaborationRequest]:
        """读取持久请求供调度与分页；损坏不冒充空队列。

        Load durable requests for dispatch and paging without hiding corruption.
        """
        return [
            read_document(path, CollaborationRequest)
            for path in sorted((self.root / "requests").glob("*.json"))
        ]

    def save(self, value: CollaborationRequest) -> None:
        """原子保存请求当前事实。 Atomically save the current request facts."""
        self.storage.require_writer()
        path = self._path("requests", value.request_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_document(path, value)
