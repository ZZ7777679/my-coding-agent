"""团队草稿与成员工作归属复用原会话和任务服务。

Team drafts and member work ownership reuse existing sessions and tasks.
"""

import json
from typing import Literal
from uuid import UUID, uuid5

from pydantic import ValidationError

from my_agent.errors import AgentError
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor
from my_agent.spaces.team_service import SpaceTeamService
from my_agent.spaces.team_types import SaveTeamDraftArgs, UpdateSpaceWorkParams
from my_agent.spaces.types import SpaceParams
from my_agent.tools.arguments import argument_message
from my_agent.tools.read_only import encode
from my_agent.workflow.types import WorkId


class ManageSpaceWorkArgs(ModelData):
    """模型只提供工作和动作；任务、成员、Run 来源由宿主注入。

    The model supplies work and action; the host injects task, member and run provenance.
    """

    work_id: WorkId
    action: Literal["claim", "release", "result"]
    result: str | None = None
    status: Literal["planned", "in_progress", "completed", "waiting"] | None = None


class SpaceTeamTools:
    """装配已存在的工具，不建立生成模型循环。

    Wrap existing tools without another model-generation loop.
    """

    def __init__(
        self, context: ToolContext, delegate: ToolExecutor, service: SpaceTeamService
    ) -> None:
        """保留真实 Run 来源与生成服务。

        Retain actual run provenance and the generation service.
        """
        self.context, self.delegate, self.service = context, delegate, service

    def definitions(self) -> list[JsonObject]:
        """提供元数据工作入口，生成草稿仍仅限已登记 Plan 请求。

        Offer metadata work actions while drafts remain limited to requested plan generation.
        """
        result = self.delegate.definitions()
        result.append(
            {
                "type": "function",
                "function": {
                    "name": "manage_space_work",
                    "description": (
                        "Claim, release or report a result for an existing team work_id. "
                        "Use work IDs from shared task context; result action needs result text. "
                        "Optional status records planned/in_progress/completed/waiting. Claim "
                        "when switching nodes to load its stage Skills on the next model request. "
                        "Report feedback in result, then revisit a feedback target only when "
                        "the user authorized that work. Missing metadata does not block execution. "
                        "The host supplies your task, current bound member and real run IDs. "
                        "This updates optional app metadata only, including in Plan; it does "
                        "not write project files or grant project execution permissions. "
                        "Sessions without a current team binding get correctable feedback."
                    ),
                    "parameters": ManageSpaceWorkArgs.model_json_schema(),
                },
            }
        )
        if self.context.mode == "plan" and self.service.generation_for(
            self.context.session_id, self.context.run_id
        ):
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": "save_team_draft",
                        "description": (
                            "Save a complete editable team draft for the requested goal. "
                            "This saves app metadata only: it does not create sessions, adopt "
                            "the draft, execute project work or start Goals. Use UUID member/edge "
                            "IDs and only the two supported models. Skills are optional existing "
                            "skill IDs. Include roles/scopes and a receiver appropriate to "
                            "central/hierarchical/peer organisation. Initial work items are "
                            "optional; do not invent machine commands or paths."
                        ),
                        "parameters": SaveTeamDraftArgs.model_json_schema(),
                    },
                }
            )
        return result

    def is_mutating(self, name: str) -> bool:
        """草稿仅写应用元数据，Plan 可用。

        Drafts write app metadata and remain available in Plan.
        """
        return (
            False
            if name in {"save_team_draft", "manage_space_work"}
            else self.delegate.is_mutating(name)
        )

    async def _manage_work(self, call: ToolCall) -> ToolResult:
        """从真实会话和当前空间绑定解析来源，沿已有任务版本保存。

        Resolve real sessions and current bindings, then save through existing task revisions.
        """
        args = ManageSpaceWorkArgs.model_validate(call.arguments)
        if args.action == "result" and args.result is None:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "报告结果需要 result 文本。")
        session = await self.service.sessions.view(self.context.session_id)
        task_id = session.summary.task_id
        if task_id is None or session.summary.project_id != self.context.project_id:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "当前会话不属于合作任务。")
        stored = await self.service.spaces.get(SpaceParams(task_id=task_id))
        space = stored.space
        if space is None:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "当前任务没有合作空间。")
        members = {member.member_id for member in space.config.members}
        bindings = [
            binding
            for binding in space.bindings
            if binding.session_id == self.context.session_id and binding.member_id in members
        ]
        if len(bindings) != 1:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "当前会话没有唯一的有效合作成员绑定。")
        member_id = bindings[0].member_id
        task = await self.service.update_work(
            UpdateSpaceWorkParams(
                task_id=task_id,
                operation_id=str(
                    uuid5(UUID(self.context.run_id), f"space-work:{call.tool_call_id}")
                ),
                work_id=args.work_id,
                member_id=member_id,
                action=args.action,
                run_id=self.context.run_id,
                result=args.result,
                status=args.status,
            )
        )
        assignment = next(item for item in task.work.assignments if item.work_id == args.work_id)
        return ToolResult(
            tool_call_id=call.tool_call_id,
            content=encode(
                {
                    "task_id": task_id,
                    "member_id": member_id,
                    "run_id": self.context.run_id,
                    "revision": task.revision,
                    "assignment": assignment.model_dump(mode="json"),
                }
            ),
            is_error=False,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """完整严格校验后保存，不回显失败原参数。

        Strictly validate complete arguments before saving without echoing failures.
        """
        if call.name not in {"save_team_draft", "manage_space_work"}:
            return await self.delegate.execute(call)
        try:
            if self.context.stop.is_set():
                raise AgentError("CANCELLED", "生成运行已停止。")
            if call.name == "manage_space_work":
                return await self._manage_work(call)
            if self.context.mode != "plan":
                raise AgentError("SPACE_DRAFT_NOT_REQUESTED", "仅团队生成 Plan 可保存此草稿。")
            args = SaveTeamDraftArgs.model_validate(call.arguments)
            generation = await self.service.save_generated(
                self.context.session_id, self.context.run_id, args
            )
            return ToolResult(
                tool_call_id=call.tool_call_id,
                content=json.dumps(
                    {
                        "saved": True,
                        "task_id": generation.params.task_id,
                        "run_id": generation.run_id,
                        "member_count": len(args.config.members),
                        "requires_user_start": True,
                    },
                    ensure_ascii=False,
                ),
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
            if call.name == "manage_space_work":
                if exc.code not in {
                    "INVALID_TOOL_ARGUMENTS",
                    "SPACE_NOT_FOUND",
                    "SPACE_MEMBER_NOT_FOUND",
                    "SPACE_WORK_NOT_FOUND",
                    "SPACE_WORK_CLAIMED",
                    "OPERATION_CONFLICT",
                }:
                    raise
                return ToolResult(
                    tool_call_id=call.tool_call_id,
                    content=encode({"code": "INVALID_TOOL_ARGUMENTS", "message": exc.message}),
                    is_error=True,
                )
            if exc.code != "SPACE_DRAFT_NOT_REQUESTED":
                # 真正保存故障与取消交回原 Run 终止路径，不能当参数反馈吞掉。
                # Real saving failures and cancellation use the existing run termination path.
                raise
            return ToolResult(
                tool_call_id=call.tool_call_id,
                content=exc.code + " · " + exc.message,
                is_error=True,
            )
