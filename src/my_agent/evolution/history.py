"""检索真实改进结果，正文与采用效果保持区别。

Search actual improvement history without equating adoption with effectiveness.
"""

from my_agent.errors import AgentError
from my_agent.evolution.store import EvolutionStore
from my_agent.evolution.types import EvolutionCandidate, EvolutionMaterial, EvolutionSource
from my_agent.models.types import JsonObject


def history_material(
    candidate: EvolutionCandidate, offset: int = 0, limit: int | None = None
) -> EvolutionMaterial:
    """记录实际读取的候选版本及比较身份，不复制原始 Trace。

    Record the candidate revision and comparison actually read, without duplicating its traces.
    """
    current = [c for c in candidate.comparisons if c.content_revision == candidate.content_revision]
    comparison = current[-1] if current else None
    text = candidate.model_dump_json(indent=2)
    body = text[offset : None if limit is None else offset + limit]
    return EvolutionMaterial(
        kind="improvement",
        title=candidate.title,
        source=EvolutionSource(
            candidate_id=candidate.candidate_id,
            content_revision=candidate.content_revision,
            comparison_at=comparison.at if comparison else None,
            candidate_status=candidate.status,
        ),
        content=body,
        total_chars=len(text),
        offset=offset,
        truncated=offset > 0 or len(body) < len(text),
    )


def search_history(
    store: EvolutionStore,
    project_id: str,
    query: str = "",
    offset: int = 0,
    limit: int = 30,
    status: str | None = None,
    target: str | None = None,
    outcome: str | None = None,
) -> JsonObject:
    """在全部当前候选和实际比较中检索，分页不是总数上限。

    Search all current candidates and actual comparisons; pagination is not a total cap.
    """
    directory = store.path(project_id, "candidates", project_id).parent
    rows: list[EvolutionCandidate] = []
    issues: list[str] = []
    words = query.casefold().split()
    for path in directory.glob("*.json"):
        try:
            candidate = store.candidate(project_id, path.stem)
        except AgentError as exc:
            issues.append(path.stem + ": " + exc.code)
            continue
        comparisons = [
            c for c in candidate.comparisons if c.content_revision == candidate.content_revision
        ]
        last = comparisons[-1] if comparisons else None
        corpus = candidate.model_dump_json().casefold()
        if (
            all(word in corpus for word in words)
            and (status is None or status == candidate.status)
            and (target is None or target.casefold() in candidate.target.identity.casefold())
            and (outcome is None or outcome == (last.outcome if last else "not_checked"))
        ):
            rows.append(candidate)
    rows.sort(key=lambda c: (c.updated_at, c.candidate_id), reverse=True)
    return {
        "items": [
            {
                "candidate_id": c.candidate_id,
                "title": c.title,
                "target": c.target.model_dump(mode="json"),
                "status": c.status,
                "content_revision": c.content_revision,
                "comparisons": [r.model_dump(mode="json") for r in c.comparisons],
            }
            for c in rows[offset : offset + limit]
        ],
        "matched_count": len(rows),
        "next_offset": offset + limit if offset + limit < len(rows) else None,
        "issues": [issue for issue in issues],
        "note": "采用仅表示已修改；效果以对应正文版本的实际比较为准。正文按需读取。",
    }
