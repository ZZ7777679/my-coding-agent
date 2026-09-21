"""简单的记忆与任务决定工具。

Simple memory and task-decision tools.
"""

import json
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from my_agent.collaboration.tools import text_page
from my_agent.errors import AgentError
from my_agent.identifiers import EntityId
from my_agent.memory.service import MemoryService
from my_agent.memory.types import MemoryFields, MemoryQuery
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor
from my_agent.sessions.projection import summarize
from my_agent.tasks.store import TaskStore
from my_agent.workflow.types import EventRef, SharedDecision


class SaveMemoryArgs(ModelData):
    """知识正文与可选更新身份。

    Knowledge content and optional update identity.
    """

    fields: MemoryFields
    memory_id: EntityId | None = None


class ReadMemoryArgs(ModelData):
    """按 ID 和字符偏移展开正文。

    Expand content by ID and character offset.
    """

    memory_id: EntityId
    offset: int = 0


class ForgetMemoryArgs(ModelData):
    """只删除明确条目。

    Delete one identified entry.
    """

    memory_id: EntityId


class ReadTaskArgs(ModelData):
    """分页读取当前任务共同事实。 Page current shared task facts."""

    offset: int = 0


class MemoryTools:
    """知识写入只改应用元数据，Plan 同样可用。

    Knowledge edits only affect app metadata, including in Plan mode.
    """

    def __init__(
        self, context: ToolContext, delegate: ToolExecutor, service: MemoryService, tasks: TaskStore
    ) -> None:
        """绑定宿主身份与服务。

        Bind host identity and services.
        """
        self.context, self.delegate, self.service, self.tasks = context, delegate, service, tasks

    def is_mutating(self, name: str) -> bool:
        """知识操作不是项目文件写入。

        Knowledge operations do not write project files.
        """
        return False if name in self.names else self.delegate.is_mutating(name)

    names = {
        "search_memory",
        "read_memory",
        "save_memory",
        "forget_memory",
        "publish_task_decision",
        "read_task",
    }

    def definitions(self) -> list[JsonObject]:
        """按内容提供记忆操作，不要求评分或证明表。

        Expose content operations without scores or proof forms.
        """
        result = self.delegate.definitions()
        for name, model, description in (
            (
                "read_task",
                ReadTaskArgs,
                "Read current shared task facts, members and decisions. Use next_offset for more.",
            ),
            (
                "search_memory",
                MemoryQuery,
                (
                    "Search current project and user memories. Use literal "
                    "query/subject/category or empty query to browse. No model request. "
                    "Results are fallible stored notes; read the body and current evidence "
                    "before relying on a claim. include_disabled also finds stale/old entries."
                ),
            ),
            (
                "read_memory",
                ReadMemoryArgs,
                "Read one memory and its status/provenance by id; pass next_offset as offset "
                "to continue a long body. A stored claim is not current tool verification.",
            ),
            (
                "save_memory",
                SaveMemoryArgs,
                (
                    "Persist reusable knowledge. Project scope by default; user scope "
                    "only for explicit cross-project preference. User current "
                    "instructions override memories. Do not save temporary task status; "
                    "publish_task_decision handles task-local decisions. Respect current "
                    "contribution setting except explicit user saves. Correct a known entry "
                    "using its memory_id; set fields.enabled=false to stop using a disproved "
                    "or obsolete claim without deleting its record. Do not save transient "
                    "runtime capabilities or unverified assistant guesses as project facts."
                ),
            ),
            (
                "forget_memory",
                ForgetMemoryArgs,
                (
                    "Forget an identified memory when requested. Deletes memory content, "
                    "not original chat; does not rebuild summaries."
                ),
            ),
            (
                "publish_task_decision",
                SharedDecision,
                (
                    "Share a task-local user-confirmed decision immediately with peer "
                    "sessions. Mark your own suggestion as proposal. Never overwrites "
                    "user-maintained task fields and never promotes it to global memory. "
                    "Use for explicit task-wide corrections, not every message."
                ),
            ),
        ):
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
        """真实保存后返回内容或引用；读取故障仅影响相应条目。

        Return persisted content/references; reads fail locally.
        """
        if call.name not in self.names:
            return await self.delegate.execute(call)
        try:
            sid = self.context.session_id
            if call.name == "read_task":
                read_task = ReadTaskArgs.model_validate(call.arguments)
                log = await self.service.sessions._load(sid)
                task_id = summarize(log).task_id
                if task_id is None:
                    raise AgentError("INVALID_TOOL_ARGUMENTS", "此会话尚未归属任务。")
                task = await self.service.sessions.worker.call(self.tasks.get, task_id)
                content = text_page(
                    {"task_id": task_id, "revision": task.revision},
                    "content",
                    task.model_dump_json(),
                    read_task.offset,
                    self.context.limits.max_tool_bytes,
                )
            elif call.name == "search_memory":
                query = MemoryQuery.model_validate(call.arguments)
                page = await self.service.page(sid, query)
                data: JsonObject = {
                    "entries": [
                        {
                            "memory_id": item.memory_id,
                            "title": item.title,
                            "category": item.category,
                            "scope": item.scope,
                            "enabled": item.enabled,
                            "stale": item.stale,
                            "source": item.source,
                        }
                        for item in page.entries
                    ],
                    "next_cursor": page.next_cursor,
                    "unavailable_count": page.unavailable_count,
                    "contribute": page.state.settings.contribute,
                    "use": page.state.settings.use,
                }
                while (
                    len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
                    > self.context.limits.max_tool_bytes
                    and len(page.entries) > 1
                ):
                    query = query.model_copy(update={"limit": max(1, query.limit // 2)})
                    page = await self.service.page(sid, query)
                    data["entries"] = [
                        {"memory_id": item.memory_id, "title": item.title} for item in page.entries
                    ]
                    data["next_cursor"] = page.next_cursor
                content = json.dumps(data, ensure_ascii=False)
            elif call.name == "read_memory":
                read = ReadMemoryArgs.model_validate(call.arguments)
                if read.offset < 0:
                    raise AgentError("INVALID_TOOL_ARGUMENTS", "offset 不能小于 0。")
                entry = await self.service.sessions.worker.call(
                    self.service.store.read, read.memory_id, self.context.project_id
                )
                content = text_page(
                    {
                        "memory_id": entry.memory_id,
                        "title": entry.title,
                        "source": entry.source,
                        "revision": entry.revision,
                        "scope": entry.scope,
                        "enabled": entry.enabled,
                        "stale": entry.stale,
                        "pinned": entry.pinned,
                        "updated_at": entry.updated_at,
                        "source_session_id": entry.session_id,
                        "source_through_seq": entry.source_seq,
                    },
                    "content",
                    entry.content,
                    read.offset,
                    self.context.limits.max_tool_bytes,
                )
            elif call.name == "save_memory":
                save = SaveMemoryArgs.model_validate(call.arguments)
                log = await self.service.sessions._load(sid)
                entry = await self.service.sessions.worker.call(
                    self.service.store.save,
                    self.context.project_id,
                    save.fields,
                    identity=save.memory_id,
                    source="agent",
                    session_id=sid,
                    source_seq=len(log.facts),
                )
                content = json.dumps(
                    {
                        "memory_id": entry.memory_id,
                        "title": entry.title,
                        "scope": entry.scope,
                        "saved": True,
                    },
                    ensure_ascii=False,
                )
            elif call.name == "forget_memory":
                forget = ForgetMemoryArgs.model_validate(call.arguments)
                await self.service.forget(sid, forget.memory_id)
                content = json.dumps({"memory_id": forget.memory_id, "forgotten": True})
            else:
                decision = SharedDecision.model_validate(call.arguments)
                log = await self.service.sessions._load(sid)
                task_id = summarize(log).task_id
                if task_id is None:
                    raise AgentError(
                        "INVALID_TOOL_ARGUMENTS", "此会话尚未归属任务，可先由用户选择任务。"
                    )
                source = EventRef(session_id=sid, run_id=self.context.run_id, seq=len(log.facts))
                operation = str(
                    uuid5(
                        NAMESPACE_URL, f"decision:{sid}:{self.context.run_id}:{call.tool_call_id}"
                    )
                )
                task = await self.service.sessions.worker.call(
                    self.tasks.record_decision, task_id, decision, source, operation
                )
                content = json.dumps(
                    {
                        "task_id": task_id,
                        "revision": task.revision,
                        "decision": decision.model_dump(),
                    },
                    ensure_ascii=False,
                )
            return ToolResult(tool_call_id=call.tool_call_id, content=content, is_error=False)
        except ValidationError:
            error = {"code": "INVALID_TOOL_ARGUMENTS", "message": "请按该工具定义提供参数。"}
        except AgentError as exc:
            error = {"code": exc.code, "message": exc.message}
        return ToolResult(
            tool_call_id=call.tool_call_id,
            content=json.dumps(error, ensure_ascii=False),
            is_error=True,
        )
