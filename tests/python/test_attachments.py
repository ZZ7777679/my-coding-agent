"""附件的分页和失败清理；不发模型请求。

Attachment paging and failed-upload cleanup without model requests.
"""

import asyncio
import base64

import pytest

from my_agent.attachments.types import AttachmentParams, ImageChunk, ImportAttachment
from my_agent.errors import AgentError
from tests.python.test_goal_controller import app_at, create_session
from tests.python.test_tasks import ContextModel


def test_attachment_pages_and_failed_upload_cleanup(tmp_path):
    """完整拼接大材料，失败上传不留下半成品。

    Reassemble large material and remove partial bytes after failed uploads.
    """

    async def scenario():
        """使用隔离数据根与实际服务，仅验证传输与落盘。

        Exercise actual transport and persistence services in an isolated data root.
        """
        async with app_at(tmp_path / "data", ContextModel()) as app:
            created = await create_session(app, tmp_path / "project")
            session_id = created.session.session_id
            # 此处验证分页字节，不将格式签名检查冒称为像素解码。
            # Check paged bytes without claiming signature detection decodes pixels.
            image = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 400
            uploaded = await app.attachments.chunk(
                ImageChunk(
                    session_id=session_id,
                    name="paging.png",
                    mime="image/png",
                    data=base64.b64encode(image).decode("ascii"),
                    final=True,
                )
            )
            encoded = ""
            offset = 0
            pages = 0
            while True:
                page = await app.attachments.read(
                    AttachmentParams(
                        session_id=session_id, attachment_id=uploaded.attachment_id, offset=offset
                    )
                )
                encoded += page.image_data
                pages += 1
                if page.next_offset is None:
                    break
                offset = page.next_offset
            assert pages > 1 and base64.b64decode(encoded, validate=True) == image
            content = "中文\n" * 40_001
            text = await app.attachments.import_file(
                ImportAttachment(
                    session_id=session_id, path="draft.txt", content=content, draft=True
                )
            )
            reconstructed = ""
            offset = 0
            while True:
                page = await app.attachments.read(
                    AttachmentParams(
                        session_id=session_id, attachment_id=text.attachment_id, offset=offset
                    )
                )
                reconstructed += page.text
                if page.next_offset is None:
                    break
                offset = page.next_offset
            assert reconstructed == content and text.draft and text.origin == "selection"

            partial = await app.attachments.chunk(
                ImageChunk(
                    session_id=session_id,
                    name="bad.png",
                    mime="image/png",
                    data=base64.b64encode(b"not an image").decode("ascii"),
                    final=False,
                )
            )
            with pytest.raises(AgentError) as failure:
                await app.attachments.chunk(
                    ImageChunk(
                        session_id=session_id,
                        attachment_id=partial.attachment_id,
                        name="bad.png",
                        mime="image/png",
                        data="",
                        final=True,
                    )
                )
            assert failure.value.code == "ATTACHMENT_FORMAT"
            directory = app.attachments.directory / session_id
            assert not list(directory.glob(partial.attachment_id + ".*"))
            assert partial.attachment_id not in app.attachments.uploads
            assert (directory / (uploaded.attachment_id + ".bin")).read_bytes() == image

    asyncio.run(scenario())
