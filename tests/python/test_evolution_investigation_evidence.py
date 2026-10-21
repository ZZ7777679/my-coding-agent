"""调查按身份分页读取所选事实，覆盖统计不把索引当正文。

Investigations page selected facts by identity without counting indexes as body evidence.
"""

import asyncio
from uuid import uuid4

import pytest

from my_agent.config import DEFAULTS
from my_agent.errors import AgentError
from my_agent.evolution.investigation_evidence import InvestigationEvidence
from my_agent.evolution.types import EvolutionSource
from my_agent.models.types import ToolCall, ToolResult
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.store import SessionLog
from my_agent.sessions.trace import TraceDetailParams, trace_detail
from my_agent.sessions.types import (
    Fact,
    RunAccepted,
    RunFinished,
    SessionCreated,
    ToolCompleted,
    ToolStarted,
)
from my_agent.worker import BusinessWorker


class SelectedSessions:
    """只提供隔离日志，不能访问个人会话。

    Supply isolated logs without access to personal sessions.
    """

    def __init__(self, logs):
        self.worker = BusinessWorker()
        self.logs = {log.session_id: log for log in logs}

    async def _load(self, session_id):
        return self.logs[session_id]


def make_log(project_id, *, long=False):
    """构造含可配对工具与晚期失败的真实公开事实。

    Build real public facts with pairable tools and a later failure.
    """
    sid, run = str(uuid4()), str(uuid4())
    first = ToolCall(tool_call_id="first", name="read_file", arguments={"path": "large.txt"})
    last = ToolCall(tool_call_id="last", name="edit_file", arguments={"path": "late-needle.py"})
    values = [
        SessionCreated(project_id=project_id, model_id="glm-5.3-flash"),
        RunAccepted(
            operation_id=str(uuid4()),
            prompt="Inspect this project",
            limits=RunLimits.model_validate(DEFAULTS["run"]),
            requested_limits=None,
        ),
        ToolStarted(call=first),
        ToolCompleted(
            result=ToolResult(
                tool_call_id="first", content="x" * (60000 if long else 20), is_error=False
            )
        ),
        ToolStarted(call=last),
        ToolCompleted(
            result=ToolResult(tool_call_id="last", content="late failure", is_error=True)
        ),
        RunFinished(status="failed", code="TOOL_FAILED", message="tool failure"),
    ]
    return SessionLog(
        sid,
        [
            Fact(
                session_id=sid,
                run_id=None if i == 0 else run,
                seq=i + 1,
                at=f"2026-10-20T00:00:0{i}Z",
                data=value,
            )
            for i, value in enumerate(values)
        ],
    )


async def check_cross_project_index_and_incremental_read():
    """大正文不挤掉后续事件，跨项目身份与正文增量读取保持真实。

    Large bodies cannot displace later events; project identities and incremental reads stay real.
    """
    first, other = make_log("original-project", long=True), make_log("other-project")
    sessions = SelectedSessions([first, other])
    try:
        investigation = await InvestigationEvidence.build(
            sessions,
            [
                EvolutionSource(session_id=first.session_id, scope="session"),
                EvolutionSource(session_id=other.session_id, scope="session"),
                EvolutionSource(
                    session_id=first.session_id, run_id=first.facts[1].run_id, scope="run"
                ),
            ],
        )
        # 先读取目录不读取正文，晚期目标不会受旧48K材料拼接预算影响。
        # Indexing reads no body; later targets cannot be lost to the former 48K budget.
        assert investigation.selected_count == 10
        assert investigation.materials == []
        page = await investigation.index("late-needle", limit=1, failed_only=True)
        assert page["matched_count"] == 2
        assert page["next_offset"] == 1
        assert page["coverage"]["read_count"] == 0
        following = await investigation.index("late-needle", offset=1, limit=1, failed_only=True)
        assert following["next_offset"] is None
        assert {page["items"][0]["project_id"], following["items"][0]["project_id"]} == {
            "original-project",
            "other-project",
        }
        assert all(source.through_seq == 7 for source in investigation.sources)
        assert len(investigation.selections) == 3

        tail = await investigation.read(first.session_id, 3, offset=30000, limit=10000)
        assert tail["offset"] == 30000 and tail["next_offset"] == 40000
        assert tail["coverage"]["partially_read_count"] == 1
        assert tail["coverage"]["read_chars"] == 10000
        await investigation.read(first.session_id, 3, offset=35000, limit=10000)
        assert investigation.coverage()["read_chars"] == 15000
        saved = investigation.materials
        assert saved[0].offset == 30000
        resumed = await InvestigationEvidence.build(sessions, investigation.sources)
        resumed.restore(saved)
        resumed.restore(saved)
        assert resumed.coverage() == investigation.coverage()
        assert resumed.materials[0].content == saved[0].content
        assert resumed.materials[0].offset == 30000
        wrong_cutoff = saved[0].model_copy(
            update={"source": saved[0].source.model_copy(update={"through_seq": 99})}
        )
        resumed.restore([wrong_cutoff])
        assert resumed.coverage()["read_chars"] == 15000
        await resumed.read(first.session_id, 3, limit=1000)
        assert resumed.coverage()["read_chars"] == 16000
        assert resumed.selected_count == investigation.selected_count
        whole = await investigation.read(first.session_id, 3, limit=100000)
        expected = ""
        offset = 0
        while True:
            detail = trace_detail(
                first, TraceDetailParams(session_id=first.session_id, seq=3, offset=offset)
            )
            expected += detail.text
            if detail.next_offset is None:
                break
            offset = detail.next_offset
        assert whole["text"] == expected
        assert whole["next_offset"] is None
        assert investigation.coverage()["fully_read_count"] == 1
        assert investigation.coverage()["read_chars"] == len(expected)
        assert len(investigation.materials) == 1
        assert investigation.materials[0].content == expected
        assert not investigation.materials[0].truncated
        assert (await investigation.index("TOOL_FAILED"))["matched_count"] == 2
    finally:
        sessions.worker.close()


def test_cross_project_index_and_incremental_read():
    """索引分页和长正文覆盖使用真实投影。

    Check index pages and long-body coverage with real projections.
    """
    asyncio.run(check_cross_project_index_and_incremental_read())


async def check_frozen_scope_and_overlap():
    """范围截止同时限制配对结果；重叠只扩大确切事件的授权。

    Cutoffs constrain paired results; overlapping selections widen only the exact authorized event.
    """
    log = make_log("source-project")
    sessions = SelectedSessions([log])
    try:
        bounded = EvolutionSource(session_id=log.session_id, scope="session", through_seq=3)
        investigation = await InvestigationEvidence.build(sessions, [bounded, bounded])
        assert investigation.selected_count == 3
        assert len(investigation.sources) == 1
        body = await investigation.read(log.session_id, 3, limit=100000)
        assert "tool.completed" not in body["text"]
        with pytest.raises(AgentError) as error:
            await investigation.read(log.session_id, 5)
        assert error.value.code == "TRACE_NOT_FOUND"
        # 后来追加的结果不会改变已经接纳的索引或正文快照。
        # Later results cannot change an already accepted index or body snapshot.
        log.facts.append(
            Fact(
                session_id=log.session_id,
                run_id=log.facts[1].run_id,
                seq=8,
                at="2026-10-20T00:00:08Z",
                data=RunFinished(status="completed", code=None, message="done"),
            )
        )
        assert (await investigation.read(log.session_id, 3, limit=100000))["text"] == body["text"]
        expanded = await InvestigationEvidence.build(
            sessions,
            [
                bounded,
                EvolutionSource(session_id=log.session_id, seq=3, scope="event", through_seq=4),
            ],
        )
        assert expanded.selected_count == 3
        complete = await expanded.read(log.session_id, 3, limit=100000)
        assert "tool.completed" in complete["text"]
        assert complete["through_seq"] == 4
        exact = await InvestigationEvidence.build(
            sessions, [EvolutionSource(session_id=log.session_id, seq=3, scope="event")]
        )
        assert (await exact.index("TOOL_FAILED"))["matched_count"] == 0
        with pytest.raises(AgentError):
            await expanded.read(log.session_id, 5)
        with pytest.raises(AgentError):
            await InvestigationEvidence.build(
                sessions,
                [
                    EvolutionSource(
                        session_id=log.session_id, seq=3, run_id=str(uuid4()), scope="event"
                    )
                ],
            )
        legacy = await InvestigationEvidence.build(
            sessions, [EvolutionSource(session_id=log.session_id)]
        )
        assert legacy.selected_count == 0 and legacy.issues
        future = await InvestigationEvidence.build(
            sessions, [EvolutionSource(session_id=log.session_id, scope="session", through_seq=99)]
        )
        assert future.sources[0].through_seq == 8
        with pytest.raises(AgentError):
            await expanded.index(offset=-1)
    finally:
        sessions.worker.close()


def test_frozen_scope_and_overlap():
    """冻结边界与重叠选择不扩大其他行。

    Check frozen boundaries and per-row overlapping selection.
    """
    asyncio.run(check_frozen_scope_and_overlap())
