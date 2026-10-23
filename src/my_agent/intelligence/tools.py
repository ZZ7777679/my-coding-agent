"""共享语言与图片工具，使用既有运行和结果通道。

Shared language and image tools through existing runs and results.
"""

from pydantic import Field, ValidationError

from my_agent.attachments.service import AttachmentService
from my_agent.attachments.types import AttachmentParams, ImportAttachment
from my_agent.errors import AgentError
from my_agent.intelligence.service import IntelligenceService
from my_agent.intelligence.types import LanguageQuery
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor, failed_tool_result
from my_agent.tools.read_only import encode


class ReadAttachmentArgs(ModelData):
    """读取已保存输入材料。

    Read saved input materials.
    """

    attachment_id: str
    offset: int = Field(default=0, ge=0)


class ViewImageArgs(ModelData):
    """显式读取图片及用途；保存不等于理解。

    Read an explicit image and purpose; saving does not mean understanding.
    """

    path: str
    purpose: str = ""


class IntelligenceTools:
    """查询不拦截正常编码，图片经下一请求真实发送。

    Queries never gate normal coding; images are sent in the next actual request.
    """

    def __init__(
        self,
        context: ToolContext,
        delegate: ToolExecutor,
        service: IntelligenceService,
        attachments: AttachmentService,
    ) -> None:
        """注入共享服务与受信运行身份。

        Inject shared services and trusted run identity.
        """
        self.context, self.delegate, self.service, self.attachments = (
            context,
            delegate,
            service,
            attachments,
        )

    def definitions(self) -> list[JsonObject]:
        """仅提供实际能力；重命名编辑通过文件工具应用。

        Expose real capabilities; apply rename edits through file tools.
        """
        query = LanguageQuery.model_json_schema()
        query["properties"].pop("project_id")
        query["required"].remove("project_id")
        definitions: list[JsonObject] = [
            {
                "type": "function",
                "function": {
                    "name": "code_insight",
                    "description": (
                        "Query LSP definition/references/symbols/hover/diagnostics/"
                        "completion/rename. Positions are zero-based UTF-16. Rename returns edits "
                        "and target snapshots; apply authorized edits with file tools. "
                        "Optional services do not block coding."
                    ),
                    "parameters": query,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_attachment",
                    "description": (
                        "Read a saved text or image attachment. Reading an image sends its "
                        "original bytes to the next model request; do not claim visual "
                        "inspection before that request."
                    ),
                    "parameters": ReadAttachmentArgs.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "view_image",
                    "description": (
                        "Read an explicit image file (including a browser screenshot artifact). "
                        "Its bytes are included in the next model request; saving a screenshot "
                        "alone is not visual inspection."
                    ),
                    "parameters": ViewImageArgs.model_json_schema(),
                },
            },
        ]
        return [*self.delegate.definitions(), *definitions]

    def is_mutating(self, name: str) -> bool:
        """查询本身不修改项目。

        Queries themselves do not modify the project.
        """
        return (
            False
            if name in {"code_insight", "read_attachment", "view_image"}
            else self.delegate.is_mutating(name)
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """完整参数在边界解析，返回真实查询或读取结果。

        Parse complete arguments at the boundary and return actual results.
        """
        if call.name not in {"code_insight", "read_attachment", "view_image"}:
            return await self.delegate.execute(call)
        try:
            if call.name == "code_insight":
                result = await self.service.query(
                    LanguageQuery.model_validate(
                        {**call.arguments, "project_id": self.context.project_id}
                    )
                )
                content = result.model_dump(mode="json")
            else:
                if call.name == "view_image":
                    args = ViewImageArgs.model_validate(call.arguments)
                    item = await self.attachments.import_file(
                        ImportAttachment(
                            session_id=self.context.session_id, path=args.path, purpose=args.purpose
                        )
                    )
                    identity = item.attachment_id
                else:
                    args_read = ReadAttachmentArgs.model_validate(call.arguments)
                    identity = args_read.attachment_id
                view = await self.attachments.read(
                    AttachmentParams(
                        session_id=self.context.session_id,
                        attachment_id=identity,
                        offset=args_read.offset if call.name == "read_attachment" else 0,
                    )
                )
                content = {
                    "attachment": view.attachment.model_dump(mode="json"),
                    "text": view.text,
                    "next_offset": view.next_offset if view.attachment.kind == "text" else None,
                    "image_next_request": view.attachment.kind == "image",
                }
                if view.attachment.kind == "image":
                    pending = self.attachments.pending.setdefault(self.context.run_id, [])
                    if identity not in pending:
                        pending.append(identity)
            return ToolResult(
                tool_call_id=call.tool_call_id, content=encode(content), is_error=False
            )
        except ValidationError:
            return ToolResult(
                tool_call_id=call.tool_call_id,
                content=encode(
                    {"code": "INVALID_TOOL_ARGUMENTS", "message": "请按工具 schema 提供完整参数。"}
                ),
                is_error=True,
            )
        except AgentError as exc:
            if call.name == "code_insight" and exc.code in {
                "LSP_UNAVAILABLE",
                "LSP_DISCONNECTED",
                "LSP_REQUEST_FAILED",
                "LSP_TIMEOUT",
            }:
                # 真正连接或执行故障停止原 Run；可选服务缺失仍作为可修正反馈。
                # Actual connection or execution failure stops the run; absence remains feedback.
                raise
            return failed_tool_result(call, exc)
