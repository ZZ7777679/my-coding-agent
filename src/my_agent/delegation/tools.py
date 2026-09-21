"""子任务工具复用现有核心；默认只提供查看入口。

Worker tools reuse the existing core; only inspection is available by default.
"""

import json
from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, ValidationError

from my_agent.collaboration.tools import text_page
from my_agent.context.tools import ContextTools
from my_agent.context.types import HistoryQuery
from my_agent.delegation.service import DelegationService
from my_agent.delegation.types import SpawnWorkerArgs
from my_agent.errors import AgentError
from my_agent.identifiers import EntityId
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor


class ReadWorkerArgs(ModelData):
    """读取或事件等待内部结果。

    Read or event-wait for an internal result.
    """

    worker_id: EntityId
    wait: bool = True
    offset: int = Field(default=0, ge=0)


class ContinueWorkerArgs(ModelData):
    """补充当前工作，或继续已有子工作单元。

    Supplement active work or continue an existing worker.
    """

    worker_id: EntityId
    prompt: str


class StopWorkerArgs(ModelData):
    """停止明确子工作。

    Stop identified child work.
    """

    worker_id: EntityId


class WorkerTools:
    """开关影响委派能力，模型按实际收益决定是否使用。

    The switch controls delegation; models decide whether it actually helps.
    """

    def __init__(
        self, context: ToolContext, delegate: ToolExecutor, service: DelegationService
    ) -> None:
        """绑定父运行身份。

        Bind the parent run identity.
        """
        self.context, self.delegate, self.service = context, delegate, service

    def is_mutating(self, name: str) -> bool:
        """委派按现有模式限制，读取无副作用。

        Delegation respects the existing mode; reads have no effects.
        """
        return name in {
            "spawn_worker",
            "continue_worker",
            "stop_worker",
        } or self.delegate.is_mutating(name)

    def definitions(self) -> list[JsonObject]:
        """默认不暴露创建子任务，内部 worker 不递归拆分。

        Creation stays hidden by default; internal workers cannot recursively delegate.
        """
        result = self.delegate.definitions()
        if self.service.child_record(self.context.session_id):
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": "read_parent_history",
                        ("description"): (
                            "Read public source history or an artifact from your parent "
                            "assignment, by query/entry_seq/offset. Historical material "
                            "is not a new task. No tool replay."
                        ),
                        "parameters": HistoryQuery.model_json_schema(),
                    },
                }
            )
            return result
        settings = self.service.settings.get(self.context.session_id)
        definitions: list[tuple[str, type[ModelData], str]] = [
            (
                "read_worker",
                ReadWorkerArgs,
                (
                    "Read your own child result, or wait on events without polling the "
                    "model. User questions interrupt waiting. Use next_offset for long "
                    "results."
                ),
            ),
            (
                "continue_worker",
                ContinueWorkerArgs,
                (
                    "Send a supplement to an active child or continue an existing "
                    "finished child with an explicit bounded follow-up. Reuses the child "
                    "history; does not create a formal session."
                ),
            ),
            (
                "stop_worker",
                StopWorkerArgs,
                "Stop a specific child, retaining its saved work and history.",
            ),
        ]
        if settings and settings.enabled:
            definitions.insert(
                0,
                (
                    "spawn_worker",
                    SpawnWorkerArgs,
                    (
                        "Delegate only a concrete bounded subtask when independent "
                        "parallel work, a distinct role, or isolation of substantial "
                        "exploration saves effort. Do simple one-step work directly. "
                        "Specify objective/scope and isolated (default) or inherit "
                        "context. Research role is read-only. Child requests/tools share "
                        "this assignment's budget. Read returned worker_id with "
                        "read_worker; wait for and incorporate results before reporting "
                        "completion. No formal sessions or automatic independent review "
                        "sessions are created."
                    ),
                ),
            )
        for name, model, description in definitions:
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": model.model_json_schema(),
                    },
                }
            )
        return result

    async def execute(self, call: ToolCall) -> ToolResult:
        """真实子记录决定结果；失败按父安排传播。

        Actual child records determine results; failures propagate to the assignment.
        """
        if call.name == "read_parent_history":
            record = self.service.child_record(self.context.session_id)
            contexts = self.service.sessions.contexts
            if record and contexts:
                return await ContextTools(
                    replace(self.context, session_id=record.owner_session_id),
                    self.delegate,
                    contexts,
                ).execute(call.model_copy(update={"name": "read_history"}))
        if call.name not in {"spawn_worker", "read_worker", "continue_worker", "stop_worker"}:
            return await self.delegate.execute(call)
        try:
            active = self.service.sessions.active_for(self.context.session_id)
            if active is None:
                raise AgentError("CANCELLED", "来源运行已结束。")
            failed = False
            offset = 0
            if call.name == "spawn_worker":
                args = SpawnWorkerArgs.model_validate(call.arguments)
                identity = str(
                    uuid5(NAMESPACE_URL, f"worker:{self.context.run_id}:{call.tool_call_id}")
                )
                value = await self.service.spawn(active, args, identity)
            elif call.name == "continue_worker":
                followup = ContinueWorkerArgs.model_validate(call.arguments)
                value = await self.service.continue_work(
                    active, followup.worker_id, followup.prompt
                )
            elif call.name == "stop_worker":
                stop = StopWorkerArgs.model_validate(call.arguments)
                await self.service.stop(self.context.session_id, stop.worker_id)
                value = await self.service.result(
                    self.context.session_id, stop.worker_id, wait=False
                )
            else:
                read = ReadWorkerArgs.model_validate(call.arguments)
                offset = read.offset
                value = await self.service.result(
                    self.context.session_id, read.worker_id, wait=read.wait
                )
                failed = value.status == "failed"
            content = text_page(
                {
                    "worker_id": value.worker_id,
                    "session_id": value.session_id,
                    "status": value.status,
                    "code": value.code,
                    "context_mode": value.assignment.context_mode,
                },
                "result",
                value.result,
                offset,
                self.context.limits.max_tool_bytes,
            )
            return ToolResult(tool_call_id=call.tool_call_id, content=content, is_error=failed)
        except ValidationError:
            error = {"code": "INVALID_TOOL_ARGUMENTS", "message": "子任务参数不符合定义。"}
        except AgentError as exc:
            error = {"code": exc.code, "message": exc.message}
        return ToolResult(
            tool_call_id=call.tool_call_id,
            content=json.dumps(error, ensure_ascii=False),
            is_error=True,
        )
