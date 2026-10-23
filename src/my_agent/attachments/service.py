"""
在现有请求组装边界加载附件；历史图片按需回读。
Load attachments at the existing request boundary; reread historical
images on demand.
"""

import base64
import binascii
import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import JsonValue

from my_agent.attachments.types import (
    Attachment,
    AttachmentParams,
    AttachmentUpload,
    AttachmentView,
    ImageChunk,
    ImportAttachment,
)
from my_agent.errors import AgentError
from my_agent.models.types import JsonObject
from my_agent.runtime.context import ContextMaterial, PreparedWindow, describe_material
from my_agent.sessions.types import RunAccepted, RunInputApplied, RunInputQueued
from my_agent.storage import read_document, utc_now, write_document

if TYPE_CHECKING:
    from my_agent.sessions.service import ActiveRun, SessionService


class AttachmentService:
    """
    复用会话存储与单写者，附件不复制到日志。
    Reuse session storage and its single writer without copying bytes
    into
    logs.
    """

    def __init__(self, sessions: "SessionService") -> None:
        """
        会话服务通过装配注入，避免领域层循环导入。
        Inject sessions at composition to avoid a domain import cycle.
        """
        self.sessions = sessions
        self.directory = sessions.store.storage.root / "attachments"
        self.uploads: dict[str, tuple[str, str, str]] = {}
        self.pending: dict[str, list[str]] = {}

    def _path(self, session_id: str, attachment_id: str, suffix: str) -> Path:
        """
        身份来自
        DTO 或宿主，检查实际附件目录。
        IDs come from DTOs or the host; check the real attachment
        directory.
        """
        directory = self.directory / session_id
        if not directory.resolve().is_relative_to(self.directory.resolve()):
            raise AgentError("ATTACHMENT_INVALID", "附件路径无效。")
        return directory / (attachment_id + suffix)

    def _save(self, item: Attachment, data: bytes) -> Attachment:
        """
        保存不可变材料后登记身份，不改项目。
        Save immutable material before registering its identity, without
        project writes.
        """
        self.sessions.store.storage.require_writer()
        path = self._path(item.session_id, item.attachment_id, ".bin")
        path.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with path.open("xb") as stream:
                created = True
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            write_document(self._path(item.session_id, item.attachment_id, ".json"), item)
        except OSError as exc:
            if created:
                path.unlink(missing_ok=True)
            raise AgentError("ATTACHMENT_SAVE_FAILED", "附件保存失败。") from exc
        except AgentError:
            if created:
                path.unlink(missing_ok=True)
            raise
        return item

    async def import_file(self, params: ImportAttachment) -> Attachment:
        """
        发送前固定所选文件或草稿的实际内容。
        Snapshot selected file or draft content before sending.
        """
        view = await self.sessions.view(params.session_id)
        root = await self.sessions.validate_project(view.summary.project_id)
        path = Path(params.path)
        path = (path if path.is_absolute() else root / path).resolve()
        if params.content is not None:
            content = params.content
            data = content.encode("utf-8")
            kind: Literal["text", "image"] = "text"
            mime: str = "text/plain"
        else:
            try:
                data = await self.sessions.worker.call(path.read_bytes)
            except FileNotFoundError as exc:
                raise AgentError("FILE_NOT_FOUND", "所选附件不存在，请修正路径后重试。") from exc
            except OSError as exc:
                raise AgentError("FILE_UNAVAILABLE", "无法读取所选附件。") from exc
            detected = self.image_mime(data)
            mime = detected or "text/plain"
            kind = "image" if detected else "text"
            if not detected:
                try:
                    content = data.decode("utf-8-sig")
                except UnicodeError as exc:
                    raise AgentError(
                        "ATTACHMENT_FORMAT", "请选择 UTF-8 文本或 PNG/JPEG/WebP/GIF 图片。"
                    ) from exc
                if params.start_line:
                    content = "\n".join(
                        content.splitlines()[params.start_line - 1 : params.end_line]
                    )
                data = content.encode("utf-8")
                mime = "text/plain"
        item = Attachment(
            attachment_id=str(uuid4()),
            session_id=params.session_id,
            kind=kind,
            name=path.name,
            mime=mime,
            purpose=params.purpose,
            origin="selection" if params.content is not None else "file",
            source_path=str(path),
            draft=params.draft,
            start_line=params.start_line,
            end_line=params.end_line,
            size_bytes=len(data),
            created_at=utc_now(),
        )
        return await self.sessions.worker.call(self._save, item, data)

    @staticmethod
    def image_mime(data: bytes) -> str | None:
        """
        按格式签名识别图片，不靠扩展名声明能力。
        Recognize image signatures instead of trusting extensions.
        """
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return "image/webp"
        return None

    async def chunk(self, params: ImageChunk) -> AttachmentUpload:
        """
        逐块保存，最终验证图片签名并生成可引用材料。
        Save chunks, then validate the signature and register readable
        material.
        """
        await self.sessions.view(params.session_id)
        identity = params.attachment_id or str(uuid4())
        owner = self.uploads.get(identity)
        if owner is not None and owner != (params.session_id, params.name, params.mime):
            raise AgentError("ATTACHMENT_INVALID", "上传身份与材料不一致。")
        if params.attachment_id is not None and owner is None:
            raise AgentError(
                "ATTACHMENT_UPLOAD_EXPIRED", "上传已经结束或应用已重启，请重新添加图片。"
            )
        try:
            data = base64.b64decode(params.data, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise AgentError("ATTACHMENT_FORMAT", "图片分块编码无效。") from exc

        def append() -> Attachment | None:
            """
            上传到应用数据根，不将
            Base64 放入业务日志。
            Upload to the data root, never base64 into business logs.
            """
            self.sessions.store.storage.require_writer()
            path = self._path(params.session_id, identity, ".upload")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("ab" if owner else "xb") as stream:
                stream.write(data)
            if not params.final:
                return None
            original = path.read_bytes()
            try:
                if self.image_mime(original) != params.mime:
                    raise AgentError("ATTACHMENT_FORMAT", "图片内容与声明格式不一致。")
                item = Attachment(
                    attachment_id=identity,
                    session_id=params.session_id,
                    kind="image",
                    name=params.name,
                    mime=params.mime,
                    purpose=params.purpose,
                    origin="upload",
                    size_bytes=len(original),
                    created_at=utc_now(),
                )
                self._save(item, original)
                return item
            finally:
                path.unlink()

        self.uploads[identity] = (params.session_id, params.name, params.mime)
        try:
            item = await self.sessions.worker.call(append)
        except (AgentError, OSError):
            await self.sessions.worker.call(
                self._path(params.session_id, identity, ".upload").unlink, missing_ok=True
            )
            self.uploads.pop(identity, None)
            raise
        if item is not None:
            self.uploads.pop(identity, None)
        return AttachmentUpload(attachment_id=identity, complete=item is not None, attachment=item)

    async def close(self) -> None:
        """清理本进程未完成的上传，保留已保存材料。

        Clean this process's incomplete uploads while retaining registered materials.
        """
        for identity, (session_id, _, _) in tuple(self.uploads.items()):
            path = self._path(session_id, identity, ".upload")
            await self.sessions.worker.call(path.unlink, missing_ok=True)
        self.uploads.clear()
        self.pending.clear()

    def _read(self, params: AttachmentParams) -> tuple[Attachment, bytes]:
        """
        精确读取所属材料，不扫描其他会话。
        Read the precise owned material without scanning peer sessions.
        """
        item = read_document(
            self._path(params.session_id, params.attachment_id, ".json"), Attachment
        )
        if item.session_id != params.session_id or item.attachment_id != params.attachment_id:
            raise AgentError("ATTACHMENT_INVALID", "附件身份与来源不一致。")
        try:
            return item, self._path(params.session_id, params.attachment_id, ".bin").read_bytes()
        except OSError as exc:
            raise AgentError("ATTACHMENT_UNAVAILABLE", "附件字节缺失或无法读取。") from exc

    async def read(self, params: AttachmentParams) -> AttachmentView:
        """分页预览快照，文本按字符、图片按字节偏移。

        Page snapshot previews using character offsets for text and byte offsets for images.
        """
        await self.sessions.view(params.session_id)
        item, data = await self.sessions.worker.call(self._read, params)
        # 预览按帧分页，不限制提交给模型的原始图片或文件大小。
        # Page previews within frames without limiting original request material size.
        page_size = 48_000
        if item.kind == "text":
            text = data.decode("utf-8")
            end = params.offset + page_size
            return AttachmentView(
                attachment=item,
                text=text[params.offset : end],
                next_offset=end if end < len(text) else None,
            )
        end = params.offset + page_size
        encoded = base64.b64encode(data[params.offset : end]).decode("ascii")
        next_offset = end if end < len(data) else None
        return AttachmentView(
            attachment=item,
            image_data=encoded,
            image_url="data:" + item.mime + ";base64," + encoded
            if params.offset == 0 and next_offset is None
            else None,
            next_offset=next_offset,
        )

    async def prepare(self, active: "ActiveRun", prepared: PreparedWindow) -> PreparedWindow:
        """
        原图仅用于当前
        Run 或显式回读；历史保留引用。
        Use images for the current run or explicit rereads, retaining
        historical references.
        """
        accepted = next(
            (
                f.data
                for f in reversed(active.log.facts)
                if f.run_id == active.run_id and isinstance(f.data, RunAccepted)
            ),
            None,
        )
        ids = list(accepted.attachment_ids if accepted else [])
        for fact in active.log.facts:
            if fact.run_id == active.run_id and isinstance(fact.data, RunInputApplied):
                queued = active.log.facts[fact.data.input_seq - 1].data
                if isinstance(queued, RunInputQueued):
                    ids.extend(i for i in queued.attachment_ids if i not in ids)
        ids.extend(i for i in self.pending.get(active.run_id, []) if i not in ids)
        if not ids:
            return prepared
        parts: list[JsonValue] = []
        materials: list[ContextMaterial] = []
        for identity in ids:
            item, data = await self.sessions.worker.call(
                self._read,
                AttachmentParams(session_id=active.log.session_id, attachment_id=identity),
            )
            description = (
                f"Attachment {identity}: {item.name}; purpose={item.purpose}; "
                f"source={item.source_path or 'pasted image'}; "
                f"{'unsaved draft' if item.draft else 'snapshot'}"
            )
            if item.kind == "image":
                parts.extend(
                    [
                        {"type": "text", "text": description},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:"
                                + item.mime
                                + ";base64,"
                                + base64.b64encode(data).decode("ascii")
                            },
                        },
                    ]
                )
            else:
                parts.append({"type": "text", "text": description + "\n" + data.decode("utf-8")})
            materials.append(
                describe_material(
                    kind="attachment",
                    title=item.name,
                    form="image" if item.kind == "image" else "snapshot",
                    reason="当前输入或显式回读材料；图片 token 未知，以响应 usage 为准",
                    text=description
                    if item.kind == "image"
                    else description + "\n" + data.decode("utf-8"),
                    source_id=identity,
                    read_tool="read_attachment",
                    read_arguments={"attachment_id": identity},
                )
            )
        messages: list[JsonObject] = [*prepared.messages, {"role": "user", "content": parts}]
        return PreparedWindow(messages, [*prepared.materials, *materials], None)
