"""现场入口只展开用户选择的范围。 Expand only the selected contextual scope."""

from typing import TYPE_CHECKING

from my_agent.errors import AgentError
from my_agent.evolution.types import EvolutionScope, EvolutionSource
from my_agent.sessions.projection import summarize
from my_agent.tasks.store import TaskStore

if TYPE_CHECKING:
    from my_agent.sessions.service import SessionService


async def scope_sources(
    sessions: "SessionService", project_id: str, scope: EvolutionScope | None
) -> list[EvolutionSource]:
    """遍历范围内全部分页；后续新增记录不会混入已接纳作业。

    Expand all pages in scope; later records do not enter an accepted review.
    """
    if scope is None:
        return []
    if scope.kind == "session":
        summary = summarize(await sessions._load(scope.identity))
        if summary.project_id != project_id:
            raise AgentError("PROJECT_MISMATCH", "复盘会话不属于当前项目。")
        return [EvolutionSource(session_id=scope.identity, scope="session")]
    if scope.kind == "project":
        if scope.identity != project_id:
            raise AgentError("PROJECT_MISMATCH", "复盘范围不属于当前项目。")
    else:
        task = await sessions.worker.call(TaskStore(sessions.store.storage).get, scope.identity)
        if task.project_id != project_id:
            raise AgentError("PROJECT_MISMATCH", "复盘任务不属于当前项目。")
    sources: list[EvolutionSource] = []
    cursor = None
    while True:
        page = await sessions.list(project_id, cursor, 100)
        sources.extend(
            EvolutionSource(session_id=item.session_id, scope="session")
            for item in page.sessions
            if scope.kind == "project" or item.task_id == scope.identity
        )
        cursor = page.next_cursor
        if cursor is None:
            return sources
