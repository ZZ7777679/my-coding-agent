"""把技能引用接入既有工具链。 Add skill references to the existing tool chain."""

import json

from pydantic import ValidationError

from my_agent.errors import AgentError
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor
from my_agent.skills.service import SkillService
from my_agent.skills.types import SelectSkillsParams, SkillParams, SkillReadParams


class LoadSkillArgs(ModelData):
    """使用目录中的准确身份。 Use the exact catalog identity."""

    skill_id: str
    reason: str = ""


class SkillTools:
    """选择技能后由下一请求的上下文装配提供正文。

    Select a skill whose body is supplied by the next request assembly.
    """

    def __init__(self, context: ToolContext, delegate: ToolExecutor, service: SkillService) -> None:
        """绑定当前会话与资源服务。 Bind session and resource service."""
        self.context, self.delegate, self.service = context, delegate, service

    def is_mutating(self, name: str) -> bool:
        """加载方法不编辑项目文件。 Loading a method does not edit project files."""
        return False if name == "load_skill" else self.delegate.is_mutating(name)

    def definitions(self) -> list[JsonObject]:
        """只发布一个按需加载入口。 Advertise one on-demand loading entry."""
        return [
            *self.delegate.definitions(),
            {
                "type": "function",
                "function": {
                    "name": "load_skill",
                    "description": "Load a skill by exact catalog ID. Its current "
                    "body and resource base enter the next request and survive compaction. "
                    "Do not reload an already active skill. Scripts use normal command tools.",
                    "parameters": LoadSkillArgs.model_json_schema(),
                },
            },
        ]

    async def execute(self, call: ToolCall) -> ToolResult:
        """持久化引用，不再复制正文。 Persist references without duplicating bodies."""
        if call.name != "load_skill":
            return await self.delegate.execute(call)
        try:
            args = LoadSkillArgs.model_validate(call.arguments)
            params = SkillParams(
                project_id=self.context.project_id, session_id=self.context.session_id
            )
            worker = self.service.sessions.worker
            document = await worker.call(
                self.service.read, SkillReadParams(**params.model_dump(), skill_id=args.skill_id)
            )
            catalog = await worker.call(self.service.catalog, params)
            await worker.call(
                self.service.select,
                SelectSkillsParams(
                    **params.model_dump(),
                    selected=list(dict.fromkeys([*catalog.selected, args.skill_id])),
                ),
            )
            content = {
                "skill_id": args.skill_id,
                "resource_base": document.item.resource_base,
                "version": document.item.version,
                "body_in_next_request": True,
                "reason": args.reason or "模型按需加载",
            }
            return ToolResult(
                tool_call_id=call.tool_call_id,
                content=json.dumps(content, ensure_ascii=False),
                is_error=False,
            )
        except ValidationError:
            error = {"code": "INVALID_TOOL_ARGUMENTS", "message": "请提供目录中的 skill_id。"}
        except AgentError as exc:
            error = {
                "code": "INVALID_TOOL_ARGUMENTS"
                if exc.code in {"SKILL_NOT_FOUND", "SKILL_INVALID", "INVALID_TOOL_ARGUMENTS"}
                else exc.code,
                "message": exc.message,
            }
        return ToolResult(
            tool_call_id=call.tool_call_id,
            content=json.dumps(error, ensure_ascii=False),
            is_error=True,
        )
