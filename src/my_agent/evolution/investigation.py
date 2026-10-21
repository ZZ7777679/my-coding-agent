"""用现有运行循环调查证据和资源，形成多个独立候选。

Investigate evidence/resources through the existing loop and produce independent candidates.
"""

import asyncio
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from uuid import uuid4

from pydantic import Field, ValidationError

from my_agent.errors import AgentError
from my_agent.evolution.investigation_evidence import InvestigationEvidence
from my_agent.evolution.scopes import scope_sources
from my_agent.evolution.types import (
    DiagnosticEvent,
    EvolutionCandidate,
    EvolutionControl,
    EvolutionCoverage,
    EvolutionFinding,
    EvolutionInput,
    EvolutionJob,
    EvolutionMaterial,
    EvolutionResource,
    EvolutionTarget,
    GenerateEvolutionCandidate,
)
from my_agent.memory.types import MemoryFields
from my_agent.models.failures import ModelResponseError
from my_agent.models.types import JsonObject, ModelData, ModelProgress, ToolCall, ToolResult
from my_agent.runtime.loop import run_loop
from my_agent.sessions.types import (
    AssistantCommitted,
    Fact,
    FactData,
    RequestStarted,
    ToolStarted,
)
from my_agent.storage import read_document, utc_now
from my_agent.tools.read_only import ReadTools

if TYPE_CHECKING:
    from my_agent.evolution.service import EvolutionService


class IndexArgs(ModelData):
    """搜索目录并分页；查询不扩大证据选择。 Search/page the index without expanding selection."""

    query: str = ""
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1)] = 30
    failed_only: bool = False


class ReadEvidenceArgs(ModelData):
    """读取已选事实的正文页。 Read a body page from a selected fact."""

    session_id: str
    seq: Annotated[int, Field(ge=1)]
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1)] = 8000


class ResourceArgs(ModelData):
    """按明确资源身份阅读，全文基线由宿主保留。 Read resources while the host retains baselines."""

    target: EvolutionTarget
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1)] = 8000


class Proposal(ModelData):
    """模型建议只含正文与关联，不含采用权限。

    Proposed content/linkage confers no adoption authority.
    """

    finding_id: str
    title: str
    rationale: str
    target: EvolutionTarget
    after: str


class InvestigationResult(ModelData):
    """允许无问题或无修改的结论。 Allow findings without edits, including no-change conclusions."""

    summary: str
    findings: list[EvolutionFinding] = Field(default_factory=list)
    proposals: list[Proposal] = Field(default_factory=list)


async def prepare_investigation(
    service: "EvolutionService", params: GenerateEvolutionCandidate
) -> tuple[EvolutionInput, InvestigationEvidence]:
    """冻结明确来源；首包为目录，原始正文通过调查工具读取。

    Freeze explicit sources and start with an index; tools read bodies on demand.
    """
    await service.sessions.validate_project(params.project_id)
    worker = service.sessions.worker
    settings = await worker.call(service.store.settings, params.project_id)
    sources = list(params.sources)
    # 接续使用原来冻结的范围，不因项目后续新增会话而悄悄扩大。
    # Continuations retain frozen selections instead of importing new project sessions.
    if not params.review_job_id:
        sources.extend(await scope_sources(service.sessions, params.project_id, params.origin))
    materials: list[EvolutionMaterial] = []
    previous = None
    if params.review_job_id:
        previous = await worker.call(service.store.job, params.project_id, params.review_job_id)
        if previous.status == "running":
            raise AgentError("EVOLUTION_REVIEW_RUNNING", "调查仍在进行，可先查看进度。")
        if previous.review_input:
            sources.extend(s.source for s in previous.review_input.selections)
            materials.extend(previous.review_input.materials)
    for identity in dict.fromkeys(params.feedback_ids):
        feedback = await worker.call(service.store.read_feedback, params.project_id, identity)
        sources.extend([feedback.source, *feedback.sources])
        materials.append(
            EvolutionMaterial(
                kind="feedback",
                title=f"反馈 · {feedback.created_at}",
                source=feedback.source,
                content=feedback.text,
                total_chars=len(feedback.text),
            )
        )
    seen_diagnostics: set[str] = set()
    for source in sources:
        if source.diagnostic_id and source.diagnostic_id not in seen_diagnostics:
            event = await worker.call(
                read_document,
                service.diagnostics.root / f"{source.diagnostic_id}.json",
                DiagnosticEvent,
            )
            content = event.model_dump_json(indent=2)
            materials.append(
                EvolutionMaterial(
                    kind="diagnostic",
                    title=f"{event.component} · {event.code}",
                    source=event.source.model_copy(update={"diagnostic_id": event.diagnostic_id}),
                    content=content,
                    total_chars=len(content),
                )
            )
            seen_diagnostics.add(source.diagnostic_id)
    evidence = await InvestigationEvidence.build(service.sessions, sources)
    await evidence.screen(params.instruction)
    initial = await evidence.index()
    index_text = json.dumps(initial, ensure_ascii=False)
    materials = [m for m in materials if m.kind != "index"]
    materials.append(
        EvolutionMaterial(
            kind="index",
            title="本地筛选索引（线索与摘录；正文按需读取）",
            content=index_text,
            total_chars=len(index_text),
        )
    )
    result = EvolutionInput(
        resource=await service.resources.read(params.project_id, params.target)
        if params.target
        else None,
        instruction=params.instruction,
        input_chars=settings.input_chars,
        prepared_at=utc_now(),
        selections=evidence.selections,
        trace_count=evidence.selected_count,
        coverage=EvolutionCoverage(
            selected=evidence.selected_count, unread=evidence.selected_count
        ),
        screening=evidence.episodes[:30],
        episode_count=len(evidence.episodes),
    )
    remaining = settings.input_chars
    for material in materials:
        if remaining is not None and remaining <= 0:
            result.omitted_materials += 1
            continue
        content = material.content[:remaining]
        result.materials.append(
            material.model_copy(
                update={
                    "content": content,
                    "truncated": material.truncated or len(content) < len(material.content),
                }
            )
        )
        result.included_chars += len(content)
        if remaining is not None:
            remaining -= len(content)
    evidence.restore(result.materials)
    result.coverage = evidence_coverage(evidence)
    return result, evidence


def evidence_coverage(evidence: InvestigationEvidence) -> EvolutionCoverage:
    """将内部阅读统计映射为公开计量，不猜测未读内容。

    Map actual reading statistics to public counts without guessing unread content.
    """
    values = evidence.coverage()
    return EvolutionCoverage(
        selected=evidence.selected_count,
        read=int(str(values["read_count"])),
        complete=int(str(values["fully_read_count"])),
        unread=int(str(values["unread_count"])),
    )


class SnapshotReads(ReadTools):
    """保留同一次文件读取的完整基线，不以提案时的新内容替代。

    Keep the full baseline from the exact file read, never a later proposal-time version.
    """

    def _read(self, name: str) -> tuple[str, bytes, str]:
        """捕获原读取返回值，沿用编码、换行和取消行为。

        Capture original read results while retaining encoding, newline and cancellation behavior.
        """
        value = super()._read(name)
        self.baselines[self.policy.target(name)] = value[0]
        return value

    def __init__(self, original: ReadTools) -> None:
        """复用既有读取配置，缓存仅存活于本次调查。

        Reuse read settings with a cache scoped to this investigation.
        """
        super().__init__(original.policy.root, original.limits, original.stop)
        self.baselines: dict[Path, str] = {}


class InvestigationTools:
    """只读能力适配器，复用文件工具并保存实际读取的材料。

    Read-only adapter reusing file tools and retaining the material actually read.
    """

    def __init__(
        self,
        service: "EvolutionService",
        job: EvolutionJob,
        evidence: InvestigationEvidence,
        files: "ReadTools",
    ) -> None:
        """绑定这次调查的来源与目标项目。 Bind this investigation's evidence and target project."""
        self.service, self.job, self.evidence = service, job, evidence
        self.files = SnapshotReads(files)
        self.resources: dict[str, EvolutionResource] = {}
        # 指定资源的预览就是首包基线，后续提案不能用更新后的值冒充它。
        # A directed resource preview is the initial baseline, never replaced by a later value.
        if job.review_input and job.review_input.resource:
            resource = job.review_input.resource
            self.resources[resource.target.model_dump_json()] = resource
        self.result: InvestigationResult | None = None
        self.base_materials = (
            [m for m in job.review_input.materials if m.kind not in {"trace", "resource"}]
            if job.review_input
            else []
        )
        self.materials: list[EvolutionMaterial] = (
            [m for m in job.review_input.materials if m.kind == "resource"]
            if job.review_input
            else []
        )

    def definitions(self) -> list[JsonObject]:
        """少量固定调查能力加既有文件读取。

        Expose focused investigation plus existing file reads.
        """
        result = self.files.definitions()
        for name, model, description in (
            (
                "index_review_evidence",
                IndexArgs,
                "Search ALL selected public event text and metadata, ordered by review focus, "
                "corrections and failures. Includes grouped recommendations with representatives "
                "and nearby/success contrasts. Supports failed_only and pagination. Excerpts "
                "are screening leads, not full body reads or proven causes. Empty query lists all.",
            ),
            (
                "read_review_evidence",
                ReadEvidenceArgs,
                "Read selected Trace by session_id/seq; follow next_offset for longer output.",
            ),
            (
                "list_review_resources",
                IndexArgs,
                "Search/page target rules, memory, skills, tool guidance and workstyles. "
                "Use list_files/search to find implementation source files.",
            ),
            (
                "read_review_resource",
                ResourceArgs,
                "Read a resource with its host baseline. For tool_guidance, reference_content is "
                "the actual tool schema/description, content is separately editable local advice. "
                "New resources have null content. Follow next_offset for the complete resource.",
            ),
            (
                "submit_review",
                InvestigationResult,
                "Finish by submitting findings and independent proposals. "
                "Invalid arguments are returned for correction. In investigate mode, "
                "submit findings and an empty proposals list. This records a report "
                "and does not grant adoption authority.",
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

    def is_mutating(self, name: str) -> bool:
        """调查不修改业务资源。 Investigation does not mutate business resources."""
        return False

    async def baseline(self, target: EvolutionTarget) -> EvolutionResource:
        """资源和源码阅读共享实际基线；没有读取过的新目标才读取当前值。

        Resource and source reads share actual baselines; only unread targets need a current read.
        """
        key = target.model_dump_json()
        if key in self.resources:
            return self.resources[key]
        if target.kind in {"code", "project_rule"}:
            path = (self.files.policy.root / target.identity).resolve()
            if path in self.files.baselines:
                return EvolutionResource(
                    target=target, content=self.files.baselines[path], label=target.identity
                )
        return await self.service.resources.read(self.job.project_id, target)

    async def execute(self, call: ToolCall) -> ToolResult:
        """读取结果与实际输入同步保存，参数错误交回模型修正。

        Persist actual input alongside results; return argument feedback for model correction.
        """
        try:
            value = await self._read(call)
            result = ToolResult(
                tool_call_id=call.tool_call_id,
                content=json.dumps(value, ensure_ascii=False),
                is_error=False,
            )
        except (ValidationError, AgentError) as exc:
            code = exc.code if isinstance(exc, AgentError) else "INVALID_TOOL_ARGUMENTS"
            message = (
                exc.message
                if isinstance(exc, AgentError)
                else "参数需修正："
                + "; ".join(
                    ".".join(str(part) for part in error["loc"]) + ": " + error["msg"]
                    for error in exc.errors(include_input=False, include_context=False)
                )
            )
            result = ToolResult(
                tool_call_id=call.tool_call_id,
                is_error=True,
                content=json.dumps({"code": code, "message": message}, ensure_ascii=False),
            )
        if self.job.review_input:
            prepared = self.job.review_input
            prepared.materials = [*self.base_materials, *self.evidence.materials, *self.materials]
            coverage = self.evidence.coverage()
            prepared.coverage = evidence_coverage(self.evidence)
            prepared.included_chars = sum(len(m.content) for m in prepared.materials)
            prepared.omitted_materials = int(str(coverage["omitted_count"]))
        await self.service.sessions.worker.call(self.service.store.save_job, self.job)
        return result

    async def _read(self, call: ToolCall) -> JsonObject:
        """分派只读调查，不接入命令执行或资源写入。

        Dispatch reads without commands or resource writes.
        """
        if call.name == "submit_review":
            self.result = InvestigationResult.model_validate(call.arguments)
            self.job.response_text = json.dumps(call.arguments, ensure_ascii=False, indent=2)
            return {
                "accepted": True,
                "findings": len(self.result.findings),
                "proposals": len(self.result.proposals),
            }
        if call.name == "index_review_evidence":
            args = IndexArgs.model_validate(call.arguments)
            index_result = await self.evidence.index(**args.model_dump())
            text = json.dumps(index_result, ensure_ascii=False)
            self.materials.append(
                EvolutionMaterial(
                    kind="index",
                    title=f"检索线索 · {args.query or '全部'} · offset {args.offset}",
                    content=text,
                    total_chars=len(text),
                )
            )
            return index_result
        if call.name == "read_review_evidence":
            read = ReadEvidenceArgs.model_validate(call.arguments)
            return await self.evidence.read(**read.model_dump())
        if call.name == "list_review_resources":
            args = IndexArgs.model_validate(call.arguments)
            catalog = await self.service.catalog(self.job.project_id)
            items = [
                item
                for item in catalog.items
                if args.query.casefold() in (item.label + " " + item.target.identity).casefold()
            ]
            page = items[args.offset : args.offset + args.limit]
            return {
                "items": [i.model_dump(mode="json") for i in page],
                "matched_count": len(items),
                "issues": [issue for issue in catalog.issues],
                "next_offset": args.offset + len(page)
                if args.offset + len(page) < len(items)
                else None,
            }
        if call.name == "read_review_resource":
            resource_args = ResourceArgs.model_validate(call.arguments)
            key = resource_args.target.model_dump_json()
            resource = self.resources.get(key)
            if resource is None:
                resource = await self.baseline(resource_args.target)
                self.resources[key] = resource
                self.resources[resource.target.model_dump_json()] = resource
                if (
                    resource.target.kind in {"code", "project_rule"}
                    and resource.content is not None
                ):
                    path = (self.files.policy.root / resource.target.identity).resolve()
                    self.files.baselines[path] = resource.content
            text = resource.model_dump_json()
            end = resource_args.offset + resource_args.limit
            body = text[resource_args.offset : end]
            self.materials.append(
                EvolutionMaterial(
                    kind="resource",
                    title=resource.label,
                    content=body,
                    total_chars=len(text),
                    truncated=resource_args.offset > 0 or end < len(text),
                )
            )
            return {
                "target": resource.target.model_dump(mode="json"),
                "text": body,
                "offset": resource_args.offset,
                "next_offset": end if end < len(text) else None,
                "total_chars": len(text),
            }
        if call.name in {"list_files", "read_file", "search"}:
            result = await self.files.execute(call)
            self.materials.append(
                EvolutionMaterial(
                    kind="resource",
                    title=call.name + " · " + json.dumps(call.arguments, ensure_ascii=False),
                    content=result.content,
                    total_chars=len(result.content),
                )
            )
            # 保留原工具错误结构供已有循环识别可修正错误。
            # Preserve original tool errors for existing loop recovery classification.
            value = json.loads(result.content)
            if result.is_error:
                raise AgentError(
                    str(value.get("code", "READ_FAILED")), str(value.get("message", "读取失败。"))
                )
            return value if isinstance(value, dict) else {"result": value}
        raise AgentError("INVALID_TOOL_ARGUMENTS", "调查中没有此工具。")


class InvestigationSink:
    """将共用循环事实投影到维护作业，不污染正式会话。

    Project shared-loop events into the maintenance job without polluting source sessions.
    """

    def __init__(self, service: "EvolutionService", job: EvolutionJob) -> None:
        """保存作业引用与最终完整回答。 Keep the job and final complete answer."""
        self.service, self.job, self.sequence, self.answer = service, job, 0, ""
        self.usage_known = False

    async def commit(self, data: FactData) -> Fact:
        """保存真实计数及阶段；临时 Fact 仅用于原循环的续接协议。

        Save real counts/phases; transient Facts serve only the shared continuation protocol.
        """
        self.sequence += 1
        if isinstance(data, RequestStarted):
            self.job.requests += 1
            self.job.message = f"调查模型请求 {self.job.requests}"
        elif isinstance(data, ToolStarted):
            self.job.message = f"调查 · {data.call.name}"
        elif isinstance(data, AssistantCommitted):
            self.answer = data.turn.text
            for field in ("input_tokens", "output_tokens", "cached_input_tokens"):
                current = getattr(self.job.usage, field)
                reported = getattr(data.turn.usage, field)
                setattr(
                    self.job.usage,
                    field,
                    reported
                    if not self.usage_known
                    else current + reported
                    if current is not None and reported is not None
                    else None,
                )
            self.usage_known = True
        await self.service.sessions.worker.call(self.service.store.save_job, self.job)
        return Fact(
            session_id=self.job.job_id,
            run_id=self.job.job_id,
            seq=self.sequence,
            at=utc_now(),
            data=data,
        )

    async def text(self, message_id: str, delta: str) -> None:
        """正文等完整结果后解析。 Parse text only after the complete result."""

    async def reasoning(self, message_id: str, delta: str) -> None:
        """维护思考不混入业务对话。 Keep maintenance reasoning out of business conversations."""

    async def progress(self, message_id: str, progress: ModelProgress) -> None:
        """网络瞬态不逐片写入持久化。 Avoid persistent writes for each transport update."""


async def investigate(
    service: "EvolutionService",
    job: EvolutionJob,
    params: GenerateEvolutionCandidate,
    evidence: InvestigationEvidence,
) -> None:
    """调查、生成和计量共用现有运行循环，结果按资源独立保存。

    Reuse the existing loop for investigation/proposals and save each resource candidate separately.
    """
    worker = service.sessions.worker
    stop = threading.Event()
    try:
        settings = await worker.call(service.store.settings, job.project_id)
        limits = job.budget or settings.budget
        files = await service.resources.file_tools(job.project_id, job.job_id)
        tools = InvestigationTools(service, job, evidence, files.read)
        sink = InvestigationSink(service, job)
        previous = (
            await worker.call(service.store.job, job.project_id, params.review_job_id)
            if params.review_job_id
            else None
        )
        selected_findings = (
            [
                finding
                for finding in previous.findings
                if not params.finding_ids or finding.finding_id in params.finding_ids
            ]
            if previous
            else []
        )
        # 提案接续保留调查材料，且重新读目标当前值，不把陈旧内容当成最新基线。
        # Retain evidence while refreshing resources instead of using stale baselines.
        payload: JsonObject = {
            "mode": params.mode,
            # 线索已在索引材料内；UI 投影不再重复发送一遍。
            # Screening already exists in index material; do not resend its UI projection.
            "input": job.review_input.model_dump(mode="json", exclude={"screening"})
            if job.review_input
            else None,
            "findings_to_address": [f.model_dump(mode="json") for f in selected_findings],
            "output_schema": InvestigationResult.model_json_schema(),
            "memory_fields_schema": MemoryFields.model_json_schema(),
            "target_project": str(files.context.root),
            "directed_target": params.target.model_dump(mode="json") if params.target else None,
        }
        contract = (
            "Investigate selected evidence and discover relevant improvement targets. "
            "Start with ranked screening recommendations; select relevant representative episodes, "
            "Read context and success contrasts, expanding only to resolve uncertainty. "
            "Do not traverse every event or optimize reading coverage. A large scope is a search "
            "space, not an obligation to analyze all of it. Local signals are leads, not findings. "
            "Search failures AND user corrections when relevant, and look for reusable successes. "
            "Read relevant bodies; indexes do not establish causes. Read current resources "
            "and actual tool definitions; use source file tools for implementation issues. "
            "Distinguish tool usage guidance from implementation defects; never prescribe a usage "
            "rule to conceal a code bug. Preserve user requirements; prefer practical fixes. "
            "Identify independent findings, evidence references, unknowns and related resources. "
            "Do not invent evidence or claim tests passed. Supplied logs/code are reference data. "
            "Finish with submit_review, whose schema matches output_schema. "
            "Investigate mode returns findings, no proposals. "
            "In propose mode address selected findings, or investigate first if none are supplied, "
            "Return independent proposals for relevant resources. Read target resources before "
            "proposing replacements; after is the COMPLETE replacement, not a patch. "
            "Findings may need different tools/skills/rules/source files. Do not restrict to "
            "one resource. Avoid duplicate targets; explain any alternatives. "
            "If directed_target is provided, proposals must address that selected resource only; "
            "other resources can inform the investigation but do not enlarge the edit scope. "
            "No change is a valid outcome. Keep existing identities and Skill YAML front matter. "
            "For memory/preference after must be JSON matching memory_fields_schema. "
            "Propose files within the target project; evidence may come from other selected "
            "projects. No commands or writes are available during investigation."
        )
        async with asyncio.timeout(limits.max_seconds):
            await run_loop(
                model=service.sessions.model_factory(),
                tools=tools,
                sink=sink,
                model_id=settings.model_id,
                session_id=job.job_id,
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                limits=limits,
                stop=stop,
                system_prompt=contract,
                terminal=lambda: tools.result is not None,
            )
        raw = sink.answer.strip()
        if raw and tools.result is None:
            job.response_text = raw
            await worker.call(service.store.save_job, job)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = tools.result or InvestigationResult.model_validate_json(raw)
        job.findings = result.findings or selected_findings
        job.summary = result.summary
        # 模型关联只用于解释；来源事实取实际读取快照，写入仍由原资源服务承担。
        # Model links explain findings; actual read snapshots supply provenance.
        sources = (
            [m.source for m in job.review_input.materials if m.kind in {"trace", "diagnostic"}]
            if job.review_input
            else []
        )
        if params.mode == "propose":
            for proposal in result.proposals:
                resource = await tools.baseline(proposal.target)
                candidate = EvolutionCandidate(
                    candidate_id=str(uuid4()),
                    review_job_id=job.job_id,
                    project_id=job.project_id,
                    finding_id=proposal.finding_id,
                    title=proposal.title,
                    rationale=proposal.rationale,
                    target=resource.target,
                    before=resource.content,
                    after=proposal.after,
                    feedback_ids=params.feedback_ids,
                    sources=sources,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    model_id=settings.model_id,
                )
                await worker.call(service.store.save, candidate)
                job.candidate_ids.append(candidate.candidate_id)
                job.candidate_id = job.candidate_ids[0]
                await worker.call(service.store.save_job, job)
                if candidate.target.kind in settings.auto_apply and candidate.target.kind != "code":
                    await service.control(
                        EvolutionControl(
                            project_id=job.project_id,
                            candidate_id=candidate.candidate_id,
                            action="apply",
                        ),
                        automatic=True,
                    )
        job.status = "completed"
        job.message = f"调查完成 · {len(job.findings)} 项发现 · {len(job.candidate_ids)} 个候选"
    except asyncio.CancelledError:
        stop.set()
        job.status, job.message = (
            "cancelled",
            "调查已停止；已保存的候选和采用事实保留，可逐项查看或恢复。",
        )
    except (AgentError, ValidationError, OSError, TimeoutError) as exc:
        job.status = "failed"
        job.message = (
            exc.message
            if isinstance(exc, AgentError)
            else "调查返回格式不完整，已读证据和已保存候选保留。"
            if isinstance(exc, ValidationError)
            else "调查达到运行时间预算，可在经验与改进的改进预算中调整后重试。"
            if isinstance(exc, TimeoutError)
            else "调查保存或读取失败，已有记录保留。"
        )
        if isinstance(exc, ModelResponseError):
            # 失败请求已计数；未知响应量不冒充零。
            # Failed requests are counted; absent response usage never means zero.
            job.usage.input_tokens = job.usage.output_tokens = None
        await worker.call(
            service.diagnostics.record,
            exc.code if isinstance(exc, AgentError) else "EVOLUTION_FAILED",
            job.message,
            component="evolution",
            project_id=job.project_id,
            exception=exc,
        )
    except Exception as exc:
        job.status, job.message = "failed", "调查内部错误；原任务和已保存候选保留。"
        await worker.call(
            service.diagnostics.record,
            "EVOLUTION_INTERNAL_ERROR",
            job.message,
            component="evolution",
            project_id=job.project_id,
            exception=exc,
        )
    finally:
        stop.set()
        await service.finish_job(job)
