"""轨迹配对、分页与公开字段。 Trace pairing, paging and public fields."""

from uuid import uuid4

import pytest

from my_agent.config import load_config
from my_agent.context.types import ContextJob, ContextState
from my_agent.models.failures import ModelResponseError
from my_agent.models.types import TokenUsage, ToolResult
from my_agent.sessions.store import SessionLog
from my_agent.sessions.tool_presentation import tool_caption
from my_agent.sessions.trace import TraceDetailParams, TraceParams, trace_detail, trace_page
from my_agent.sessions.types import (
    AssistantCommitted,
    Fact,
    RequestStarted,
    RunFinished,
    ToolCompleted,
    ToolStarted,
)
from my_agent.storage import write_document
from tests.python.test_goal_controller import app_at, call, create_session, turn


@pytest.mark.parametrize(
    "command, expected",
    [
        (
            {"kind": "program", "program": "python", "arguments": ["app.py", "--port", "8000"]},
            "运行 · python app.py --port 8000",
        ),
        (
            {"kind": "powershell", "script": "Get-Location\nGet-Date"},
            "运行 · PowerShell · Get-Location Get-Date",
        ),
        (
            '{"kind":"program","program":"cmd.exe","arguments":["/c","dir"]}',
            "运行 · cmd.exe /c dir",
        ),
    ],
)
def test_tool_summary_reads_nested_and_legacy_commands(command, expected):
    """程序摘要读取真实嵌套参数，保留原调用不变。

    Present nested/legacy command targets without changing the original call.
    """
    item = call("run_command", command=command)
    original = item.model_dump_json()
    assert tool_caption(item) == expected
    assert item.model_dump_json() == original


def test_trace_pairs_across_pages_and_does_not_expose_native(tmp_path):
    """相邻请求之外仍正确配对，原生私有字段不泄漏。

    Pair nonadjacent calls and exclude native data."""
    sid, run, message = (str(uuid4()) for _ in range(3))
    tool = call("read_file", path="hello.txt")
    reply = turn(text="done")
    reply.native["private_sentinel"] = "never expose"
    data = [
        RequestStarted(message_id=message),
        ToolStarted(call=tool),
        AssistantCommitted(message_id=message, turn=reply),
        ToolCompleted(
            result=ToolResult(tool_call_id=tool.tool_call_id, content="hello", is_error=False)
        ),
    ]
    log = SessionLog(
        sid,
        [
            Fact(session_id=sid, run_id=run, seq=i + 1, at=f"2026-09-21T00:00:0{i}Z", data=value)
            for i, value in enumerate(data)
        ],
    )
    page = trace_page(log, TraceParams(session_id=sid, limit=1))
    assert page.items[0].seq == 3
    earlier = trace_page(log, TraceParams(session_id=sid, before_seq=page.before_seq, limit=1))
    assert earlier.items[0].status == "completed"
    assert earlier.items[0].duration_ms == 2000
    detail = trace_detail(log, TraceDetailParams(session_id=sid, seq=2))
    assert "hello" in detail.text and "read_file" in detail.text
    assert (
        "private_sentinel" not in trace_detail(log, TraceDetailParams(session_id=sid, seq=3)).text
    )
    assert trace_page(log, TraceParams(session_id=sid, errors_only=True)).items == []
    watched = trace_page(log, TraceParams(session_id=sid, limit=1, watch_seqs=[2]))
    assert watched.items[0].seq == 3 and watched.updates[0].status == "completed"
    result_detail = trace_detail(log, TraceDetailParams(session_id=sid, seq=2, part="result"))
    assert result_detail.text == "hello"
    from my_agent.sessions.projection import entries

    page_entries, _ = entries(log, None, selected_seqs={4})
    assert page_entries[0].text == "读取 · hello.txt"
    assert page_entries[0].call is None  # 不为摘要重复携带完整参数 / no duplicated arguments.
    state = ContextState(
        job=ContextJob(
            job_id=str(uuid4()),
            run_id=None,
            status="preparing",
            model_id="glm-5.3-flash",
            started_at="2026-09-22T00:00:00Z",
        )
    )
    write_document(tmp_path / "context.json", state)
    jobs = trace_page(log, TraceParams(session_id=sid), tmp_path).jobs
    assert jobs[0]["status"] == "preparing" and jobs[0]["requests"] == 0


def test_trace_detail_pages_long_output_without_loss():
    """分段读取合并后仍是完整事实。 Detail chunks preserve the complete saved fact."""
    sid, run = str(uuid4()), str(uuid4())
    result = ToolCompleted(
        result=ToolResult(tool_call_id="orphan", content="x" * 50000, is_error=True)
    )
    log = SessionLog(
        sid, [Fact(session_id=sid, run_id=run, seq=1, at="2026-09-21T00:00:00Z", data=result)]
    )
    page = trace_page(log, TraceParams(session_id=sid, errors_only=True))
    assert page.items[0].is_error
    first = trace_detail(log, TraceDetailParams(session_id=sid, seq=1))
    text, offset = first.text, first.next_offset
    while offset is not None:
        chunk = trace_detail(log, TraceDetailParams(session_id=sid, seq=1, offset=offset))
        text += chunk.text
        offset = chunk.next_offset
    assert len(text) == first.total_chars
    assert "x" * 50000 in text


@pytest.mark.parametrize("status,is_error", [("failed", True), ("cancelled", False)])
def test_trace_terminal_request_keeps_success_and_failure_identity(status, is_error):
    """失败或取消只归属于未提交请求，已成功响应保持完成。

    Attribute failure/cancellation only to the unanswered request, preserving successful replies.
    """
    sid, run, first, pending = (str(uuid4()) for _ in range(4))
    values = [
        RequestStarted(message_id=first),
        AssistantCommitted(message_id=first, turn=turn(text="ready")),
        RequestStarted(message_id=pending),
        RunFinished(status=status, code="MODEL_OUTPUT_TRUNCATED", message="incomplete"),
    ]
    log = SessionLog(
        sid,
        [
            Fact(session_id=sid, run_id=run, seq=i + 1, at=f"2026-09-30T00:00:0{i}Z", data=d)
            for i, d in enumerate(values)
        ],
    )
    page = trace_page(log, TraceParams(session_id=sid))
    assert page.items[0].status == "completed" and not page.items[0].is_error
    failed = next(item for item in page.items if item.seq == 3)
    assert failed.request_id == pending and failed.status == status
    assert failed.is_error == is_error and failed.duration_ms == 1000
    assert (
        "MODEL_OUTPUT_TRUNCATED" in trace_detail(log, TraceDetailParams(session_id=sid, seq=3)).text
    )
    assert (
        3 in {i.seq for i in trace_page(log, TraceParams(session_id=sid, errors_only=True)).items}
    ) == is_error


@pytest.mark.parametrize("known", [True, False])
def test_failed_request_usage_survives_reopen_without_committing_turn(tmp_path, known):
    """失败计量持久化且缓存不重复计费，旧未知不伪造为零。

    Persist failed usage without a complete turn or double-counting cache hits; preserve unknown.
    """
    import asyncio

    class FailedModel:
        """只模拟失败响应，不执行任何工具。 Simulate a failed response without tools."""

        def check_available(self):
            """本地替身不需要凭据。 The local double needs no credentials."""

        async def complete(self, **kwargs):
            """交付服务端已报告的用量或未知。 Deliver reported usage or explicit unknown."""
            raise ModelResponseError(
                "MODEL_OUTPUT_TRUNCATED",
                "incomplete",
                TokenUsage(
                    input_tokens=100 if known else None,
                    output_tokens=20 if known else None,
                    cached_input_tokens=80 if known else None,
                ),
                "length",
            )

    async def scenario():
        """生产事实重开后不重复入账。 Reopen production facts without double charging."""
        async with app_at(tmp_path / "data", FailedModel()) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            limits = load_config(app.storage.location).run
            await app.sessions.start(sid, str(uuid4()), "build", limits, mode="normal")
            await app.sessions.active_for(sid).task
            view = await app.sessions.view(sid)
            assert view.summary.run.status == "failed"
            assert view.summary.run.input_tokens == (100 if known else None)
            assert view.summary.run.output_tokens == (20 if known else None)
            log = app.sessions.store.load(sid)
            request = next(f for f in log.facts if isinstance(f.data, RequestStarted))
            end = next(f for f in log.facts if isinstance(f.data, RunFinished))
            assert end.data.failed_request_id == request.data.message_id
            assert not any(isinstance(f.data, AssistantCommitted) for f in log.facts)
            row = next(
                i
                for i in trace_page(log, TraceParams(session_id=sid)).items
                if i.seq == request.seq
            )
            assert row.usage.cached_input_tokens == (80 if known else None)
            from my_agent.goals.ledger import usage

            goal_id = str(uuid4())
            goal_facts = [
                f.model_copy(update={"data": f.data.model_copy(update={"goal_id": goal_id})})
                if f.data.kind == "run.accepted"
                else f
                for f in log.facts
            ]
            assert usage(goal_facts, goal_id).input_tokens == (100 if known else None)
        async with app_at(tmp_path / "data", FailedModel()) as app:
            reopened = await app.sessions.view(sid)
            assert reopened.summary.run.requests == 1
            assert reopened.summary.run.input_tokens == (100 if known else None)

    asyncio.run(scenario())
