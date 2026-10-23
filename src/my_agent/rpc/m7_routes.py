"""自进化的短控制接口。

Short evolution control endpoints.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel

from my_agent.errors import AgentError
from my_agent.evolution.types import (
    CompareEvolutionCandidate,
    CreateEvolutionCandidate,
    DiagnosticQuery,
    EvolutionCandidateParams,
    EvolutionControl,
    EvolutionExperimentParams,
    EvolutionJobControl,
    EvolutionQuery,
    EvolutionResourceQuery,
    EvolutionRunsQuery,
    EvolutionSettings,
    GenerateEvolutionCandidate,
    SaveEvolutionCandidate,
    SaveEvolutionFeedback,
)

if TYPE_CHECKING:
    from my_agent.rpc.application import RpcApplication

M7_METHODS = (
    "evolution.diagnostic",
    "evolution.list",
    "evolution.catalog",
    "evolution.configure",
    "evolution.feedback",
    "evolution.resource",
    "evolution.generate",
    "evolution.candidate",
    "evolution.create",
    "evolution.edit",
    "evolution.compare",
    "evolution.control",
    "evolution.stop",
    "evolution.experiment",
    "evolution.job",
    "evolution.preview",
    "evolution.runs",
)


async def dispatch_m7(app: "RpcApplication", method: str, params: dict[str, object]) -> BaseModel:
    """边界解析一次，业务复用共享服务。

    Parse at the boundary and reuse shared business services.
    """
    service = app.sessions.evolution
    if service is None:
        raise AgentError("EVOLUTION_UNAVAILABLE", "自进化服务未装配。")
    if method == "evolution.diagnostic":
        query = DiagnosticQuery.model_validate(params)
        return await app.worker.call(service.diagnostics.read, query.diagnostic_id)
    if method in {"evolution.list", "evolution.catalog"}:
        query = EvolutionQuery.model_validate(params)
        return (
            await service.page(query)
            if method == "evolution.list"
            else await service.catalog(query.project_id)
        )
    if method == "evolution.configure":
        settings = EvolutionSettings.model_validate(params)
        await app.sessions.validate_project(settings.project_id)
        if "code" in settings.auto_apply:
            raise AgentError(
                "INVALID_SETTINGS", "本版代码采用使用明确的采用入口，不支持后台自动换版。"
            )
        return await app.worker.call(service.store.configure, settings)
    if method == "evolution.feedback":
        return await service.feedback(SaveEvolutionFeedback.model_validate(params))
    if method == "evolution.resource":
        resource = EvolutionResourceQuery.model_validate(params)
        return await service.resources.read(resource.project_id, resource.target)
    if method == "evolution.generate":
        return await service.generate(GenerateEvolutionCandidate.model_validate(params))
    if method == "evolution.preview":
        return await service.preview(GenerateEvolutionCandidate.model_validate(params))
    if method == "evolution.runs":
        return await service.runs(EvolutionRunsQuery.model_validate(params))
    if method == "evolution.create":
        return await service.create(CreateEvolutionCandidate.model_validate(params))
    if method == "evolution.edit":
        return await service.edit(SaveEvolutionCandidate.model_validate(params))
    if method == "evolution.compare":
        return await service.compare(CompareEvolutionCandidate.model_validate(params))
    if method == "evolution.control":
        return await service.control(EvolutionControl.model_validate(params))
    if method == "evolution.stop":
        return await service.stop(EvolutionJobControl.model_validate(params))
    if method == "evolution.experiment":
        return await service.experiment(EvolutionExperimentParams.model_validate(params))
    if method == "evolution.job":
        return await service.job_detail(EvolutionJobControl.model_validate(params))
    candidate = EvolutionCandidateParams.model_validate(params)
    await app.sessions.validate_project(candidate.project_id)
    return await app.worker.call(
        service.store.candidate, candidate.project_id, candidate.candidate_id
    )
