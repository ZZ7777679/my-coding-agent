"""提交工作结果和可选事实引用，不另发摘要模型请求。

Report work with optional fact references without an extra summarization model call.
"""

import json
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from my_agent.errors import AgentError
from my_agent.goals.state import states
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor
from my_agent.sessions.store import SessionLog
from my_agent.sessions.types import AssistantCommitted, RunAccepted, ToolCompleted, ToolStarted
from my_agent.tools.policy import checkpoint
from my_agent.worker import BusinessWorker
from my_agent.workflow.types import CriterionResult, WorkItem, WorkReport


class GoalReportArgs(WorkReport):
    """Goal 结果控制续跑，逐项状态与引用仅作可选说明。

    Goal outcomes control continuation; criterion details and references are optional context.
    """

    outcome: Literal["continue", "complete", "wait"]
    criteria: list[CriterionResult] = Field(
        default_factory=list,
        description=(
            "Optional per-criterion progress. Use the original criterion_id when available. "
            "Report met, unmet or not_checked honestly. References are optional; copy known "
            "_evidence values rather than inventing them. "
            "A simple report needs only summary/outcome."
        ),
    )
    work_items: list[WorkItem] = Field(
        default_factory=list,
        description=(
            "Optional work breakdown, not the Goal's acceptance results. "
            "For a simple task, omit this field."
        ),
    )


class RequestReportArgs(WorkReport):
    """普通请求的 schema 只给出可用结果，不暴露 Goal 专用操作。

    Advertise only outcomes available to ordinary requests, excluding Goal-only actions.
    """

    outcome: Literal["return", "wait"]


def argument_error_message(error: ValidationError, model: type[ModelData]) -> str:
    """只显示已知字段与错误类别，不回显参数值或原始校验异常。

    Show known fields and error categories without echoing argument values or raw exceptions.
    """
    issues = error.errors(include_input=False, include_context=False, include_url=False)
    fields = sorted(
        {
            str(issue["loc"][0])
            for issue in issues
            if issue["loc"] and issue["loc"][0] in model.model_fields
        }
    )
    if fields:
        return "工作信息参数校验失败，请检查字段：" + "、".join(fields) + "。已有执行结果保留。"
    return "工作报告存在重复身份，或 wait / question 不一致。已有执行结果保留。"


class WorkStatusArgs(ModelData):
    """按事实游标读取来源索引，不接受任意其他会话身份。

    Page the source index by fact cursor without arbitrary cross-session identities.
    """

    before_seq: Annotated[int, Field(ge=1)] | None = None
    limit: Annotated[int, Field(ge=1)] = 20


class WorkflowTools:
    """包裹既有工具并保存本次终结报告；持久化由 Run 结束路径负责。

    Wrap existing tools and hold a terminal report, persisted by the run-finalization path.
    """

    def __init__(
        self, context: ToolContext, delegate: ToolExecutor, log: SessionLog, worker: BusinessWorker
    ) -> None:
        """绑定当前 Run 的事实和工具，不创建新会话或 Goal。

        Bind current-run facts and tools without creating sessions or goals.
        """
        self.context, self.delegate, self.log, self.worker = context, delegate, log, worker
        self.report: WorkReport | None = None
        accepted = next(
            (
                fact.data
                for fact in log.facts
                if fact.run_id == context.run_id and isinstance(fact.data, RunAccepted)
            ),
            None,
        )
        self.answer_only = accepted is not None and accepted.goal_role == "question"
        self.report_model = (
            GoalReportArgs
            if accepted is not None and accepted.goal_role == "work"
            else RequestReportArgs
        )

    def is_mutating(self, name: str) -> bool:
        """报告改变应用进度，不属于项目文件写入；Plan 可保存方案。

        Reports update app progress, not project files; Plan can save in-app plans.
        """
        return name == "report_work" or self.delegate.is_mutating(name)

    def finished(self) -> bool:
        """完整报告意味着当前工作单元结束，不代表 Task 或 Goal 自动完成。

        A complete report ends this work unit, not automatically its task or goal.
        """
        return self.report is not None

    def request_reference(self) -> str:
        """提供本次已接纳请求的准确引用，不把控制器工作当作用户决定。

        Supply the accepted request's exact reference, excluding controller-generated goal work.
        """
        for fact in self.log.facts:
            if fact.run_id != self.context.run_id or not isinstance(fact.data, RunAccepted):
                continue
            if fact.data.goal_role == "work":
                return ""
            reference = {
                "session_id": fact.session_id,
                "run_id": fact.run_id,
                "seq": fact.seq,
                "kind": "user",
            }
            return (
                "\nCurrent accepted request reference (attributes the request, not proof of "
                "a successful check or additional permissions; collaboration remains scoped):\n"
                + json.dumps(reference)
            )
        return ""

    def definitions(self) -> list[JsonObject]:
        """暴露事实索引及可核对报告；所有项目能力仍来自既有装配。

        Expose an evidence index and checkable reports while preserving existing project tools.
        """
        result = self.delegate.definitions()
        outcomes = (
            "For this Goal work run, use continue, complete or wait with a specific user question. "
            "Judge completion against the user's original objective. "
            "Optional next_work_id selects ready work from this goal's reported scope; "
            "otherwise the host selects ready work or continues the original goal. "
            if self.report_model is GoalReportArgs
            else "For this request use return, or wait with a specific user question. "
            "Do not pick up unrelated task backlog. "
        )
        for name, model, description in (
            (
                "read_work_status",
                WorkStatusArgs,
                "Read this session's durable evidence references and current goal definition. "
                "References are optional; when citing one, copy its session_id, run_id and seq. "
                "This is a paged index (default limit=20); pass returned before_seq to get older "
                "references. Tool content is already in history. Do not load the whole index "
                "just to answer a question about context or report progress.",
            ),
            (
                "report_work",
                self.report_model,
                "End this work unit with summary and outcome. Criteria, work items, next_action "
                "and evidence references are optional progress information, not prerequisites. "
                "When adding references copy known _evidence values; never guess seq numbers. "
                "Call this last: later tools in the same response will not execute. "
                + outcomes
                + "Select a bundled method per work item when "
                "useful: discuss, plan, implement, diagnose, review or handoff. "
                "Observed failed checks are valid observations, never succeeded evidence. "
                "Report failure first; repair only if already included in the user's scope. "
                "This report does not change the user's objective, decisions or permissions.",
            ),
        ):
            if self.answer_only and name == "report_work":
                continue
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

    def _status(self, before_seq: int | None, limit: int) -> JsonObject:
        """返回有界来源索引；不复制 provider 原生字段或伪造执行结果。

        Return a bounded evidence index without native provider state or invented results.
        """
        snapshot = list(self.log.facts)
        accepted = next(
            (
                fact.data
                for fact in snapshot
                if fact.run_id == self.context.run_id and isinstance(fact.data, RunAccepted)
            ),
            None,
        )
        goal = states(snapshot).get(accepted.goal_id or "") if accepted else None
        result: JsonObject = {
            "current_work_id": accepted.work_id if accepted else None,
            "goal": {
                "definition": goal.definition.model_dump(mode="json"),
                "status": goal.status,
                "budget": goal.budget.model_dump(mode="json"),
            }
            if goal
            else None,
            "evidence": [],
            "before_seq": None,
        }
        evidence: list[JsonObject] = []
        for fact in reversed(snapshot):
            if fact.run_id is None or (before_seq is not None and fact.seq >= before_seq):
                continue
            data = fact.data
            item: JsonObject = {
                "session_id": fact.session_id,
                "run_id": fact.run_id,
                "seq": fact.seq,
            }
            if isinstance(data, ToolCompleted):
                started = next(
                    (
                        prior.data.call
                        for prior in reversed(snapshot[: fact.seq - 1])
                        if isinstance(prior.data, ToolStarted)
                        and prior.run_id == fact.run_id
                        and prior.data.call.tool_call_id == data.result.tool_call_id
                    ),
                    None,
                )
                item.update(
                    kind="tool_result",
                    tool_call_id=data.result.tool_call_id,
                    tool_name=started.name if started else None,
                    is_error=data.result.is_error,
                )
            elif isinstance(data, AssistantCommitted) and data.turn.text.strip():
                item.update(kind="assistant", message_id=data.message_id)
            elif isinstance(data, RunAccepted) and data.goal_role != "work":
                item.update(kind="user", operation_id=data.operation_id)
            else:
                continue
            if len(evidence) >= limit:
                result["before_seq"] = evidence[-1]["seq"]
                break
            candidate: JsonObject = {**result, "evidence": [*evidence, item]}
            if (
                len(json.dumps(candidate, ensure_ascii=False).encode("utf-8"))
                > self.context.limits.max_tool_bytes
            ):
                if not evidence:
                    raise AgentError(
                        "TOOL_OUTPUT_LIMIT", "Goal 定义超过工具输出预算，请调整工具预算。"
                    )
                result["before_seq"] = evidence[-1]["seq"]
                break
            evidence.append(item)
        result["evidence"] = [item for item in evidence]
        return result

    async def execute(self, call: ToolCall) -> ToolResult:
        """按公开 schema 保存报告，不以证据表或工作图完整性阻断收尾。

        Accept schema-valid reports without evidence-table or work-graph completion gates.
        """
        if call.name not in {"read_work_status", "report_work"}:
            return await self.delegate.execute(call)
        argument_model = WorkStatusArgs if call.name == "read_work_status" else self.report_model
        try:
            checkpoint(self.context.stop)
            if call.name == "read_work_status":
                args = WorkStatusArgs.model_validate(call.arguments)
                data = await self.worker.call(self._status, args.before_seq, args.limit)
            else:
                if self.answer_only:
                    raise AgentError(
                        "GOAL_INPUT_READ_ONLY", "本次仅回答插话，不更改工作报告或 Goal。"
                    )
                report = self.report_model.model_validate(call.arguments)
                self.report = report
                data = {
                    "accepted_for_run_end": True,
                    "outcome": report.outcome,
                }
            content = json.dumps(data, ensure_ascii=False)
            if len(content.encode("utf-8")) > self.context.limits.max_tool_bytes:
                raise AgentError("TOOL_OUTPUT_LIMIT", "工作信息超过本次工具输出预算。")
            return ToolResult(
                tool_call_id=call.tool_call_id,
                is_error=False,
                content=content,
            )
        except ValidationError as exc:
            code, message = "INVALID_TOOL_ARGUMENTS", argument_error_message(exc, argument_model)
        except AgentError as exc:
            if exc.code == "CANCELLED":
                raise
            code, message = exc.code, exc.message
        return ToolResult(
            tool_call_id=call.tool_call_id,
            is_error=True,
            content=json.dumps({"code": code, "message": message}, ensure_ascii=False),
        )
