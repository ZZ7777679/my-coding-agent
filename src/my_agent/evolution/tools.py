"""模型提出改进，采用仍走项目已配置策略。

Model proposals follow the project's adoption settings.
"""

import json
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

from my_agent.errors import AgentError
from my_agent.evolution.service import EvolutionService
from my_agent.evolution.types import (
    CreateEvolutionCandidate,
    EvolutionControl,
    EvolutionJobControl,
    EvolutionScope,
    EvolutionSource,
    EvolutionTarget,
    GenerateEvolutionCandidate,
    SaveEvolutionFeedback,
)
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor


class FeedbackArgs(ModelData):
    """模型只能记录当前会话的反馈。

    Models can record feedback only for the current session.
    """

    text: str
    kind: Literal["problem", "success", "instruction"] = "problem"
    target: EvolutionTarget | None = None


class ProposalArgs(ModelData):
    """候选正文不自带基线或采用状态。

    Proposed content carries no invented baseline or adoption state.
    """

    target: EvolutionTarget
    title: str
    rationale: str
    after: str


class ReviewArgs(ModelData):
    """按当前工作范围发起或查看独立复盘，不暂停原任务。

    Start or inspect an independent contextual review without pausing the source task.
    """

    action: Literal["start", "status", "stop"] = "start"
    scope: Literal["session", "task", "project"] = "session"
    instruction: str = ""
    job_id: str | None = None


class EvolutionTools:
    """能力按需发现，不把复盘流程变成每轮前置条件。

    Discoverable learning tools never become a per-turn prerequisite.
    """

    def __init__(
        self, context: ToolContext, delegate: ToolExecutor, service: EvolutionService
    ) -> None:
        """绑定原会话和真实资源服务。

        Bind the source session and actual resource services.
        """
        self.context, self.delegate, self.service = context, delegate, service

    def is_mutating(self, name: str) -> bool:
        """候选可能按已保存设置采用，Plan 仅保存草稿。

        A proposal may follow saved adoption settings; Plan only creates drafts.
        """
        if name in {"record_feedback", "propose_improvement", "review_experience"}:
            return False
        return self.delegate.is_mutating(name)

    def definitions(self) -> list[JsonObject]:
        """描述真实副作用与项目范围。

        Describe actual effects and project scope.
        """
        result = self.delegate.definitions()
        for name, model, description in (
            (
                "review_experience",
                ReviewArgs,
                "Start a read-only improvement investigation for the current session, task or "
                "project when relevant to the user's request. Uses the independent improvement "
                "budget and selectively reads evidence; does not pause the original task, apply "
                "changes or create a formal session. Return is acceptance, not completion. "
                "Use action=status/stop with job_id to read findings/coverage or cancel. "
                "The user can continue in the Experience and Improvements page.",
            ),
            (
                "record_feedback",
                FeedbackArgs,
                "Record a specific user correction or observed success/failure for later review. "
                "Do not record guesses as facts. Optional target identifies the resource. "
                "This does not stop the current task; automatic review follows project settings.",
            ),
            (
                "propose_improvement",
                ProposalArgs,
                "Propose a complete replacement for an explicit project rule, memory/preference, "
                "Skill, tool note, workstyle or code file. The host reads the actual baseline. "
                "Adoption follows project settings; code is never auto-applied. "
                "Plan mode saves drafts only. This is optional, not a completion requirement.",
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
        """记录来源，不接受模型伪造成功或修改原 Goal 状态。

        Capture provenance without accepting fabricated success or changing the source Goal.
        """
        if call.name not in {"record_feedback", "propose_improvement", "review_experience"}:
            return await self.delegate.execute(call)
        try:
            result: JsonObject
            source = EvolutionSource(session_id=self.context.session_id, run_id=self.context.run_id)
            if call.name == "review_experience":
                review = ReviewArgs.model_validate(call.arguments)
                if review.action == "start":
                    from my_agent.sessions.projection import summarize

                    summary = summarize(await self.service.sessions._load(self.context.session_id))
                    identity = (
                        self.context.project_id
                        if review.scope == "project"
                        else summary.task_id
                        if review.scope == "task"
                        else self.context.session_id
                    )
                    if identity is None:
                        raise AgentError(
                            "INVALID_TOOL_ARGUMENTS", "此会话未归属任务，可选择 session 范围。"
                        )
                    job = await self.service.generate(
                        GenerateEvolutionCandidate(
                            project_id=self.context.project_id,
                            mode="investigate",
                            origin=EvolutionScope(kind=review.scope, identity=identity),
                            instruction=review.instruction,
                        )
                    )
                else:
                    if not review.job_id:
                        raise AgentError("INVALID_TOOL_ARGUMENTS", "查看或停止复盘需要 job_id。")
                    if review.action == "stop":
                        job = await self.service.stop(
                            EvolutionJobControl(
                                project_id=self.context.project_id,
                                job_id=review.job_id,
                            )
                        )
                    else:
                        job = await self.service.job_detail(
                            EvolutionJobControl(
                                project_id=self.context.project_id,
                                job_id=review.job_id,
                            )
                        )
                result = {
                    "job_id": job.job_id,
                    "status": job.status,
                    "message": job.message,
                    "summary": job.summary,
                    "findings": [finding.model_dump(mode="json") for finding in job.findings],
                    "coverage": job.review_input.coverage.model_dump(mode="json")
                    if job.review_input
                    else None,
                }
            elif call.name == "record_feedback":
                args = FeedbackArgs.model_validate(call.arguments)
                params = SaveEvolutionFeedback.model_validate(
                    {
                        "project_id": self.context.project_id,
                        "feedback_id": str(uuid4()),
                        **args.model_dump(),
                        "source": source.model_dump(),
                    }
                )
                # Plan 不能通过自动采用产生项目写入；仍保留用户反馈。
                # Plan cannot cause adoption through automatic review, but feedback is retained.
                params.target = None if self.context.mode == "plan" else params.target
                value = await self.service.feedback(params)
                result = {"feedback_id": value.feedback_id, "status": "saved"}
            else:
                proposal = ProposalArgs.model_validate(call.arguments)
                candidate = await self.service.create(
                    CreateEvolutionCandidate(
                        project_id=self.context.project_id,
                        **proposal.model_dump(),
                    )
                )
                candidate.sources = [source]
                candidate = await self.service.sessions.worker.call(
                    self.service.store.save, candidate
                )
                settings = await self.service.sessions.worker.call(
                    self.service.store.settings, self.context.project_id
                )
                if (
                    self.context.mode != "plan"
                    and candidate.target.kind != "code"
                    and candidate.target.kind in settings.auto_apply
                ):
                    candidate = await self.service.control(
                        EvolutionControl(
                            project_id=self.context.project_id,
                            candidate_id=candidate.candidate_id,
                            action="apply",
                        ),
                        automatic=True,
                    )
                result = {
                    "candidate_id": candidate.candidate_id,
                    "title": candidate.title,
                    "target": candidate.target.model_dump(mode="json"),
                    "status": candidate.status,
                    "message": candidate.message,
                }
            return ToolResult(
                tool_call_id=call.tool_call_id,
                is_error=False,
                content=json.dumps(result, ensure_ascii=False),
            )
        except (AgentError, ValidationError) as exc:
            code = exc.code if isinstance(exc, AgentError) else "INVALID_TOOL_ARGUMENTS"
            message = (
                exc.message if isinstance(exc, AgentError) else "改进参数不完整，请按工具定义修正。"
            )
            return ToolResult(
                tool_call_id=call.tool_call_id,
                is_error=True,
                content=json.dumps({"code": code, "message": message}, ensure_ascii=False),
            )
