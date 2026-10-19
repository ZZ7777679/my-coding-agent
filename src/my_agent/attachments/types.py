"""
附件身份与分块上传契约，不保存内联图片到对话。
Attachment identities and chunk uploads without inline images in chat
logs.
"""

from typing import Literal

from pydantic import Field

from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData


class Attachment(ModelData):
    """
    文件快照或图片元信息，字节单独保存。
    File snapshot or image metadata with separately stored bytes.
    """

    attachment_id: EntityId
    session_id: EntityId
    kind: Literal["image", "text"]
    name: str
    mime: str
    purpose: str = ""
    origin: Literal["file", "selection", "upload"] = "file"
    source_path: str | None = None
    draft: bool = False
    start_line: int | None = None
    end_line: int | None = None
    size_bytes: int
    created_at: str


class AttachmentParams(ModelData):
    """按所属会话读取一个附件。 Read an attachment within its owning session."""

    session_id: EntityId
    attachment_id: EntityId
    offset: int = Field(default=0, ge=0)


class ImageChunk(ModelData):
    """
    分块经过原协议大小边界，完成才用于请求。
    Chunk within the existing protocol frame boundary; use only
    completed
    uploads.
    """

    session_id: EntityId
    attachment_id: EntityId | None = None
    name: str
    mime: Literal["image/png", "image/jpeg", "image/webp", "image/gif"]
    data: str
    final: bool
    purpose: str = ""


class AttachmentUpload(ModelData):
    """
    上传进度不表示模型已经看图。
    Upload progress never means the model has inspected the image.
    """

    attachment_id: EntityId
    complete: bool
    attachment: Attachment | None = None


class ImportAttachment(ModelData):
    """
    显式选择文件，或从编辑器提交未保存选区。
    Explicit file selection or an unsaved editor selection.
    """

    session_id: EntityId
    path: str
    content: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    draft: bool = False
    purpose: str = ""


class AttachmentView(ModelData):
    """
    查看保存的文本或图片，只有显式预览返回图片数据。
    View saved text or images; image data is returned only for explicit
    preview.
    """

    attachment: Attachment
    text: str | None = None
    image_url: str | None = None
    image_data: str | None = None
    next_offset: int | None = None


class AttachmentPage(ModelData):
    """原生选择器返回的已保存材料，取消返回空集合。

    Saved materials returned by the native picker; cancellation returns an empty collection.
    """

    attachments: list[Attachment]
