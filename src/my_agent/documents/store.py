"""应用数据根中的未保存草稿。

Unsaved drafts in the application data root.
"""

from pydantic import ValidationError

from my_agent.changes.store import identity
from my_agent.documents.types import DocumentDraft, DraftPage
from my_agent.errors import AgentError
from my_agent.storage import Storage, utc_now, write_document


class DocumentStore:
    """单写者保存每个会话草稿，不在项目落元数据。

    Single-writer draft storage outside projects.
    """

    def __init__(self, storage: Storage) -> None:
        """绑定已选择数据根。

        Bind the chosen data root.
        """
        self.storage = storage
        self.root = storage.root / "documents"

    def load(self, session_id: str) -> DraftPage:
        """保留损坏文件并返回明确错误。

        Preserve damaged files and report explicit errors.
        """
        path = self.root / (identity(session_id) + ".json")
        if path.resolve() != path:
            raise AgentError("DOCUMENT_STORAGE_INVALID", "草稿存储路径包含链接。")
        try:
            page = DraftPage.model_validate_json(path.read_bytes())
            if any(draft.session_id != session_id for draft in page.drafts):
                raise AgentError("DOCUMENT_DRAFT_DAMAGED", "草稿归属错误，原文件已保留。")
            return page
        except FileNotFoundError:
            return DraftPage(drafts=[])
        except ValidationError as exc:
            raise AgentError("DOCUMENT_DRAFT_DAMAGED", "草稿文件损坏，原文件已保留。") from exc
        except OSError as exc:
            raise AgentError("DOCUMENT_DRAFT_UNAVAILABLE", "无法读取草稿。") from exc

    def save(self, draft: DocumentDraft) -> DraftPage:
        """原子保存草稿；内容等于基线时移除草稿。

        Atomically persist drafts; remove buffers equal to their base.
        """
        self.storage.require_writer()
        page = self.load(draft.session_id)
        drafts = [item for item in page.drafts if item.path != draft.path]
        if draft.content != draft.base_content:
            drafts.append(draft.model_copy(update={"updated_at": utc_now()}))
        result = DraftPage(drafts=drafts)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AgentError("DOCUMENT_DRAFT_SAVE_FAILED", "无法创建草稿目录。") from exc
        write_document(self.root / (identity(draft.session_id) + ".json"), result)
        return result
