"""将候选关联限制为实际读过的材料，不扩大为整次调查。

Associate candidates with actually read material, not an entire investigation.
"""

from my_agent.evolution.types import (
    EvolutionFinding,
    EvolutionInput,
    EvolutionResourceReference,
    EvolutionSource,
)


def candidate_sources(
    prepared: EvolutionInput | None,
    findings: list[EvolutionFinding],
    finding_id: str,
    *,
    sole_proposal: bool = False,
    inherit_unlinked: bool = True,
) -> tuple[list[EvolutionSource], list[EvolutionResourceReference]]:
    """用发现中的关联选择宿主阅读事实；单一发现可沿用唯一调查的来源。

    Resolve finding links to host read facts; a single finding can inherit its investigation.
    """
    if prepared is None:
        return [], []
    finding = next((f for f in findings if f.finding_id == finding_id), None)
    sole = inherit_unlinked and (
        (len(findings) == 1 and finding is not None) or (not findings and sole_proposal)
    )
    linked = finding.sources if finding else []
    targets = [*finding.resources, *finding.targets] if finding else []
    sources: dict[str, EvolutionSource] = {}
    resources: dict[str, EvolutionResourceReference] = {}
    for material in prepared.materials:
        if not material.content:
            continue
        actual = material.source
        if material.kind in {"trace", "diagnostic", "improvement"} and (
            (sole and not linked) or any(source_matches(ref, actual) for ref in linked)
        ):
            sources[actual.model_dump_json()] = actual
        resource = material.resource
        if resource and (
            (sole and not (finding and finding.resources))
            or any(
                ref.identity == resource.target.identity and ref.scope == resource.target.scope
                for ref in targets
            )
        ):
            resources[resource.target.model_dump_json()] = resource
    if prepared.resource and prepared.resource.content and sole:
        resource = EvolutionResourceReference(
            target=prepared.resource.target, version=prepared.resource.version
        )
        resources[resource.target.model_dump_json()] = resource
    return list(sources.values()), list(resources.values())


def source_matches(reference: EvolutionSource, actual: EvolutionSource) -> bool:
    """关联仅缩小实际材料，不把猜测的序号变成来源事实。

    Links select existing material without turning guessed references into evidence.
    """
    if reference.candidate_id:
        return reference.candidate_id == actual.candidate_id
    if reference.diagnostic_id:
        return reference.diagnostic_id == actual.diagnostic_id
    if not reference.session_id or reference.session_id != actual.session_id:
        return False
    if reference.seq is not None:
        return reference.seq == actual.seq
    if reference.run_id:
        return reference.run_id == actual.run_id
    return reference.scope == "session"
