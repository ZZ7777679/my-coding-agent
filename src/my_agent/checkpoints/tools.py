"""模型按需调用同一检查点服务。 On-demand model tools share the checkpoint service."""

from uuid import uuid4

from pydantic import BaseModel, ValidationError

from my_agent.checkpoints.service import RollbackService
from my_agent.checkpoints.types import (
    CheckpointParams,
    PreviewCheckpointParams,
    RestoreCheckpointParams,
)
from my_agent.errors import AgentError
from my_agent.models.types import JsonObject, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor
from my_agent.tools.arguments import argument_message
from my_agent.tools.read_only import encode

TOOLS: dict[str, tuple[type[BaseModel], str]] = {
    "list_checkpoints": (
        CheckpointParams,
        "List request-level code checkpoints and coverage; Git is not required.",
    ),
    "preview_restore": (
        PreviewCheckpointParams,
        "Preview reversing code since a completed request, preserving later disjoint edits.",
    ),
    "restore_checkpoint": (
        RestoreCheckpointParams,
        "Restore code only when requested by the user. Does not rewind conversation or touch Git "
        "index. Unknown-author changes require explicit include_observed; inspect preview first.",
    ),
}


class RollbackTools:
    """只恢复代码；对话重新开始保留桌面入口。

    Expose code restore; conversational rewind stays in the UI.
    """

    def __init__(
        self, context: ToolContext, delegate: ToolExecutor, service: RollbackService
    ) -> None:
        """注入当前运行归属和共用服务。 Inject current run ownership and the shared service."""
        self.context, self.delegate, self.service = context, delegate, service

    def definitions(self) -> list[JsonObject]:
        """模型不传会话身份；Plan 不提供恢复写入。

        Bind session identity and omit mutation in Plan.
        """
        result = self.delegate.definitions()
        for name, (model, description) in TOOLS.items():
            if name == "restore_checkpoint" and self.context.mode == "plan":
                continue
            schema = model.model_json_schema()
            for field in ("session_id", "operation_id", "mode"):
                schema["properties"].pop(field, None)
                if field in schema.get("required", []):
                    schema["required"].remove(field)
            result.append(
                {
                    "type": "function",
                    "function": {"name": name, "description": description, "parameters": schema},
                }
            )
        return result

    def is_mutating(self, name: str) -> bool:
        """恢复为文件副作用，查询只读。 Restoration mutates files; queries are read-only."""
        return name == "restore_checkpoint" if name in TOOLS else self.delegate.is_mutating(name)

    async def execute(self, call: ToolCall) -> ToolResult:
        """复用桌面服务，恢复不自动重新执行原请求。

        Reuse desktop behavior without replaying the old request.
        """
        if call.name not in TOOLS:
            return await self.delegate.execute(call)
        try:
            if any(k in call.arguments for k in ("session_id", "mode", "operation_id")):
                raise AgentError("INVALID_TOOL_ARGUMENTS", "会话、模式和操作身份由宿主提供。")
            values = {**call.arguments, "session_id": self.context.session_id}
            result: BaseModel
            if call.name == "list_checkpoints":
                args = CheckpointParams.model_validate(values)
                result = await self.service.sessions.worker.call(
                    self.service.store.page, args.session_id
                )
            elif call.name == "preview_restore":
                result = await self.service.preview(
                    PreviewCheckpointParams.model_validate(values), self.context.run_id
                )
            else:
                if self.context.mode == "plan":
                    raise AgentError("INVALID_TOOL_ARGUMENTS", "Plan 模式不执行代码恢复。")
                result = await self.service.restore(
                    RestoreCheckpointParams.model_validate(
                        {**values, "mode": "code", "operation_id": str(uuid4())}
                    ),
                    self.context.run_id,
                )
            return ToolResult(
                tool_call_id=call.tool_call_id,
                content=encode(result.model_dump(mode="json")),
                is_error=False,
            )
        except ValidationError as exc:
            return ToolResult(
                tool_call_id=call.tool_call_id,
                content=encode(
                    {"code": "INVALID_TOOL_ARGUMENTS", "message": argument_message(exc)}
                ),
                is_error=True,
            )
        except AgentError as exc:
            return ToolResult(
                tool_call_id=call.tool_call_id,
                content=encode({"code": exc.code, "message": exc.message}),
                is_error=True,
            )
