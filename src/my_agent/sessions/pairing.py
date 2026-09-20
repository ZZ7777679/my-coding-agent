"""从原始事实辨别未配对工具，调用身份始终附带运行与回合。

Identify unpaired tools from facts, qualifying call identity by run and turn.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from my_agent.models.types import ToolCall
from my_agent.sessions.recovery_types import SessionRecovered
from my_agent.sessions.types import (
    AssistantCommitted,
    Fact,
    ToolCompleted,
    ToolSkipped,
    ToolStarted,
)


@dataclass
class PendingTool:
    """模型已提交但没有完整结果的调用及其实际开始事实。

    A committed model call without a complete result and its actual start fact, if any.
    """

    run_id: str
    turn_seq: int
    call: ToolCall
    started_seq: int | None = None


def pending_tools(facts: Sequence[Fact]) -> list[PendingTool]:
    """保留原调用顺序；历史中重用的工具 ID 不互相覆盖。

    Preserve call order without conflating reused tool IDs from different historical turns.
    """
    pending: dict[tuple[str, str], PendingTool] = {}
    for fact in facts:
        data = fact.data
        if fact.run_id is None:
            continue
        if isinstance(data, AssistantCommitted):
            for call in data.turn.tool_calls:
                pending[(fact.run_id, call.tool_call_id)] = PendingTool(fact.run_id, fact.seq, call)
        elif isinstance(data, ToolStarted):
            item = pending.get((fact.run_id, data.call.tool_call_id))
            if item:
                item.started_seq = fact.seq
        elif isinstance(data, (ToolCompleted, ToolSkipped)):
            pending.pop((fact.run_id, data.result.tool_call_id), None)
        elif isinstance(data, SessionRecovered):
            for recovered in data.items:
                pending.pop((fact.run_id, recovered.tool_call_id), None)
    return list(pending.values())
