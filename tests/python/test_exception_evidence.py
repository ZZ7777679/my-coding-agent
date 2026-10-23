"""统一异常、工具失败接续和选择性诊断材料的定向验收。

Target unified exceptions, continuation after tool failures and selective diagnostic evidence.
"""

import asyncio
import json
import os
import runpy
import sys
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError
from my_agent.evolution import diagnostics
from my_agent.evolution.types import (
    EvolutionControl,
    EvolutionExperimentParams,
    EvolutionSource,
    GenerateEvolutionCandidate,
)
from my_agent.execution.types import ProgramCommand, RunCommandArgs
from my_agent.models.native_search import NativeSearchClient
from my_agent.models.types import ModelProgress
from my_agent.rpc.application import RpcApplication
from my_agent.rpc.dto import CredentialInfo
from my_agent.rpc.server import serve
from my_agent.sessions.trace import trace_items
from my_agent.sessions.types import RunFinished
from my_agent.storage import Storage
from tests.python.test_evolution import ReviewModel
from tests.python.test_goal_controller import app_at, call, create_session, turn
from tests.python.test_rpc import frame


def test_diagnostic_causes_redaction_and_storage_degradation(tmp_path, monkeypatch):
    """真实原因仅记录一次；不可写诊断仍返回原业务失败。

    Record real causes once; unwritable diagnostics preserve the original business failure.
    """

    async def scenario():
        """核对原记录、RPC 回读与已知秘密。 Check stored records, RPC reads and known secrets."""
        async with app_at(tmp_path / "data", ReviewModel()) as app:
            store = app.sessions.diagnostics
            store.secrets = ("isolated-key-value",)
            try:
                try:
                    raise ValueError(
                        "Missing response for tool abc; token=hidden-token isolated-key-value"
                    )
                except ValueError as cause:
                    raise AgentError(
                        "MODEL_PROTOCOL",
                        "Tool reply absent",
                        details={
                            "Authorization": "hidden-header",
                            "http_status": 400,
                        },
                    ) from cause
            except AgentError as cause:
                error = await app.worker.call(
                    store.capture, cause, component="model", operation="complete"
                )
            again = await app.worker.call(store.capture, error, component="runtime")
            assert again.diagnostic_id == error.diagnostic_id
            event = await app.dispatch(
                "evolution.diagnostic", {"diagnostic_id": error.diagnostic_id}
            )
            assert [c.type for c in event.causes] == ["AgentError", "ValueError"]
            assert "Missing response for tool abc" in event.causes[1].message
            assert event.causes[1].parent == 0 and event.causes[1].frames
            assert event.details["http_status"] == 400
            assert len(list(store.root.glob("*.json"))) == 1
            raw = event.model_dump_json()
            assert all(
                s not in raw for s in ["hidden-token", "hidden-header", "isolated-key-value"]
            )

            def deny(*args):
                """只拒绝本次诊断落盘。 Reject only this diagnostic write."""
                raise PermissionError("isolated directory unavailable")

            monkeypatch.setattr(diagnostics, "write_document", deny)
            missing = await app.worker.call(
                store.capture, RuntimeError("original defect"), component="tool"
            )
            assert "original defect" in missing.message and missing.diagnostic_id is None
            assert "DIAGNOSTIC_WRITE_FAILED" in missing.diagnostic_issue
            assert "isolated directory unavailable" in missing.diagnostic_issue

    asyncio.run(scenario())


def test_diagnostic_cleanup_failure_preserves_saved_evidence(tmp_path, monkeypatch):
    """旧诊断无法删除时仍能读取新诊断，辅助故障不替代业务错误。

    Failed retention cleanup preserves new evidence and the original business error.
    """
    with Storage(resolve_data_dir(str(tmp_path / "data"))).writer() as storage:
        store = diagnostics.DiagnosticStore(storage, max_records=1, secrets=("fixture-secret",))
        store.prune_every = 1
        first = store.capture(ValueError("old failure"), component="tool")
        old_path = store.root / (first.diagnostic_id + ".json")
        os.utime(old_path, (1, 1))
        unlink = Path.unlink

        def deny_old_record(path, *args, **kwargs):
            """仅模拟旧记录被占用，新记录照常原子保存。

            Simulate one locked old record while new records save atomically.
            """
            if path == old_path:
                raise PermissionError("old diagnostic is locked; fixture-secret")
            return unlink(path, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(Path, "unlink", deny_old_record)
            error = store.capture(AgentError("HTTP_ERROR", "original rejection"), component="model")
            assert error.code == "HTTP_ERROR" and error.message == "original rejection"
            assert error.diagnostic_id is not None
            assert store.read(error.diagnostic_id).message == "original rejection"
            assert "DIAGNOSTIC_CLEANUP_FAILED" in error.diagnostic_issue
            assert "old diagnostic is locked" in error.diagnostic_issue
            assert "fixture-secret" not in error.diagnostic_issue
            assert store.capture(error, component="runtime").diagnostic_id == error.diagnostic_id
            assert len(list(store.root.glob("*.json"))) == 2

        recovered = store.capture(RuntimeError("later failure"), component="runtime")
        assert recovered.diagnostic_id and recovered.diagnostic_issue is None
        assert store.read(recovered.diagnostic_id).message == "RuntimeError: later failure"
        assert store.issue is None and not old_path.exists()
        assert len(list(store.root.glob("*.json"))) == 1


def test_trace_diagnostic_to_verified_fix_and_memory(tmp_path):
    """从失败 Trace 按需查诊断、改候选、实际比较，再从已验证候选提炼记忆。

    Read diagnostics selectively from failed Trace, compare a fix, then derive a sourced memory.
    """

    class FixModel(ReviewModel):
        """隔离模型只决定调用顺序，文件与诊断使用真实服务。

        An isolated model controls call order; files and diagnostics use real services.
        """

        def __init__(self):
            """保存调查步骤与经验来源。 Keep investigation steps and experience sources."""
            super().__init__()
            self.stage, self.lesson, self.identity = 0, False, None

        async def complete(self, **kwargs):
            """执行真实缺陷或调查工具，不发送外部请求。

            Exercise the actual defect or investigation tools without external requests.
            """
            if not kwargs["messages"][0]["content"].startswith("Investigate selected"):
                value = runpy.run_path(str(tmp_path / "project/answer.py"))["answer"]()
                return turn(text=str(value))
            self.stage += 1
            if self.lesson:
                if self.stage == 1:
                    return turn(call("read_review_history", candidate_id=self.identity))
                return turn(
                    call(
                        "submit_review",
                        summary="Verified fixture lesson",
                        proposals=[
                            {
                                "finding_id": "lesson",
                                "title": "Fixture failure lesson",
                                "rationale": "The inspected comparison passed",
                                "target": {"kind": "memory", "identity": ""},
                                "after": json.dumps(
                                    {
                                        "title": "Fixture lesson",
                                        "content": "Verified example: answer() returns 2.",
                                    }
                                ),
                            }
                        ],
                    )
                )
            if self.stage == 1:
                prompt = str(kwargs["messages"])
                assert "read_review_diagnostic" in prompt and self.identity in prompt
                # 摘录不是原因正文。 Excerpts are not causes.
                assert '"exception_types":' not in prompt
                return turn(
                    call("read_review_diagnostic", diagnostic_id=self.identity),
                    call("read_review_resource", target={"kind": "code", "identity": "answer.py"}),
                )
            outputs = [json.loads(m["content"]) for m in kwargs["messages"] if m["role"] == "tool"]
            assert any(o.get("diagnostic_id") == self.identity for o in outputs)
            return turn(
                call(
                    "submit_review",
                    summary="Observed fixture implementation defect",
                    proposals=[
                        {
                            "finding_id": "defect",
                            "title": "Correct fixture answer",
                            "rationale": "Concrete cause inspected",
                            "target": {"kind": "code", "identity": "answer.py"},
                            "after": "def answer():\n    return 2\n",
                        }
                    ],
                )
            )

    async def scenario():
        """真实隔离命令验证前后差异，原失败与来源保持不变。

        Real isolated commands verify before/after behavior while preserving failure provenance.
        """
        model = FixModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid, pid = created.session.session_id, created.task.project_id
            source = tmp_path / "project/answer.py"
            source.write_text(
                'def answer():\n    raise ValueError("FIXTURE_CONCRETE_DEFECT")\n', encoding="utf-8"
            )
            await app.sessions.start(sid, str(uuid4()), "Run example", None)
            await app.sessions.active_for(sid).task
            view = await app.sessions.view(sid)
            assert "FIXTURE_CONCRETE_DEFECT" in view.summary.run.message
            model.identity = view.summary.run.diagnostic_id
            log = await app.sessions._load(sid)
            request = next(r for r in trace_items(log) if r.kind == "request.started")
            assert request.diagnostic_ids == [model.identity]
            service = app.sessions.evolution
            job = await service.generate(
                GenerateEvolutionCandidate(
                    project_id=pid,
                    sources=[
                        EvolutionSource(
                            session_id=sid, run_id=request.run_id, seq=request.seq, scope="event"
                        )
                    ],
                    instruction="Find and repair the isolated example error",
                )
            )
            await service.jobs[job.job_id][1]
            assert job.status == "completed", job.message
            diagnostic_materials = [m for m in job.review_input.materials if m.kind == "diagnostic"]
            assert len(diagnostic_materials) == 1
            assert diagnostic_materials[0].source.diagnostic_id == model.identity
            assert len(job.review_input.selections) == 1 and job.review_input.trace_count == 1
            candidate = service.store.candidate(pid, job.candidate_id)
            assert candidate.status == "draft" and "raise ValueError" in source.read_text()
            experiment = await service.experiment(
                EvolutionExperimentParams(
                    project_id=pid,
                    candidate_id=candidate.candidate_id,
                    command=RunCommandArgs(
                        command=ProgramCommand(
                            kind="program",
                            program=sys.executable,
                            arguments=["-c", "import answer; assert answer.answer() == 2"],
                        )
                    ),
                )
            )
            await service.jobs[experiment.job_id][1]
            assert experiment.status == "completed", experiment.message
            assert [p.summary.exit_code for p in experiment.programs] == [1, 0]
            await service.control(
                EvolutionControl(
                    project_id=pid, candidate_id=candidate.candidate_id, action="apply"
                )
            )
            await app.sessions.start(sid, str(uuid4()), "Run corrected example", None)
            await app.sessions.active_for(sid).task
            assert (await app.sessions.view(sid)).summary.run.status == "completed"
            model.lesson, model.stage, model.identity = True, 0, candidate.candidate_id
            lesson = await service.generate(
                GenerateEvolutionCandidate(
                    project_id=pid,
                    candidate_ids=[candidate.candidate_id],
                    instruction="Record the verified fixture lesson",
                )
            )
            await service.jobs[lesson.job_id][1]
            assert lesson.status == "completed", lesson.message
            adopted = await service.control(
                EvolutionControl(project_id=pid, candidate_id=lesson.candidate_id, action="apply")
            )
            memory = service.resources.memory.read(adopted.target.identity, pid)
            assert any(
                s.candidate_id == candidate.candidate_id and s.comparison_at
                for s in memory.evolution_sources
            )
            assert not memory.stale

    asyncio.run(scenario())


def test_rpc_unexpected_exception_has_concrete_cause(tmp_path, monkeypatch):
    """实际 JSONL 返回定位信息，诊断与 RPC 身份一致。

    Real JSONL returns useful causes with matching diagnostic and RPC identities.
    """
    original = RpcApplication.dispatch

    async def dispatch(self, method, params):
        """只注入一个 RPC 故障，其余使用真实装配。 Inject one RPC fault into real composition."""
        if method == "fixture.failure":
            raise KeyError("missing_tool_response")
        return await original(self, method, params)

    monkeypatch.setattr(RpcApplication, "dispatch", dispatch)
    payload = frame(
        "initialize",
        {
            "app_version": "test",
            "protocol_version": DEFAULTS["protocol_version"],
            "data_schema_version": 1,
        },
        "init",
    )
    payload += frame("fixture.failure", {}, "fault")
    output = BytesIO()
    serve(
        resolve_data_dir(str(tmp_path / "rpc")),
        BytesIO(payload),
        output,
        ResolvedCredential(
            None, CredentialInfo(env_var="OPENCODE_API_KEY", source="none", present=False)
        ),
    )
    failure = next(
        json.loads(line)
        for line in output.getvalue().splitlines()
        if json.loads(line).get("id") == "fault"
    )["error"]
    assert "missing_tool_response" in failure["message"]
    record = json.loads(
        (
            tmp_path / "rpc/logs/diagnostics" / (failure["data"]["diagnostic_id"] + ".json")
        ).read_text(encoding="utf-8")
    )
    assert record["request_id"] == "fault" and record["operation"] == "fixture.failure"
    assert record["causes"][0]["type"] == "KeyError"


def test_real_program_failure_preserves_cause_when_cleanup_also_fails(tmp_path):
    """真实 Windows 启动拒绝与清理故障分别保存，不覆盖原始原因。

    Preserve a real Windows launch rejection separately from a subsequent cleanup failure.
    """

    class ProgramModel(ReviewModel):
        """仅安排运行隔离无效程序。 Request only the isolated invalid executable."""

        async def complete(self, **kwargs):
            """由真实进程后端产生错误。 Let the real process backend produce the failure."""
            return turn(
                call(
                    "run_command",
                    command={"kind": "program", "program": "./invalid.exe", "arguments": []},
                )
            )

    async def scenario():
        """程序未执行，错误保留 OS 解释并可以继续会话。

        No program runs; preserve the OS explanation and allow subsequent conversation.
        """
        async with app_at(tmp_path / "data", ProgramModel()) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            (tmp_path / "project/invalid.exe").write_text("not an executable", encoding="utf-8")
            finish = app.sessions.finish_run

            async def fail_cleanup(run_id):
                """真实清理完成后注入独立故障。 Inject a separate failure after real cleanup."""
                await finish(run_id)
                raise RuntimeError("fixture cleanup failure")

            app.sessions.finish_run = fail_cleanup
            await app.sessions.start(
                sid, str(uuid4()), "Run isolated executable", None, mode="normal"
            )
            await app.sessions.active_for(sid).task
            view = await app.sessions.view(sid)
            assert view.summary.can_continue and not view.summary.issue
            assert view.summary.run.cause_code == "PROCESS_API_FAILED"
            assert "fixture cleanup failure" in view.summary.run.message
            store = app.sessions.diagnostics
            event = store.read(view.summary.run.diagnostic_id)
            assert event.operation == "run_command" and event.tool_call_id
            assert event.details["operation"] == "CreateProcess"
            # Windows 可按文件格式或体系结构拒绝同一无效样本，保留系统实际给出的码。
            # Windows may reject the invalid image format or architecture; preserve its actual code.
            assert event.details["winerror"] in {193, 216}
            assert event.causes[0].frames and str(event.details["winerror"]) in event.message
            records = [json.loads(p.read_text(encoding="utf-8")) for p in store.root.glob("*.json")]
            assert any(e["operation"] == "finish_run" for e in records)
            assert len(records) == 2

    asyncio.run(scenario())


def test_auxiliary_search_failure_does_not_damage_session(tmp_path, monkeypatch):
    """辅助请求进度不冒充主请求；失败后同会话与重启均能发送。

    Auxiliary progress never impersonates chat; failed sessions remain sendable after restart.
    """

    class SearchModel(ReviewModel):
        """首轮搜索，后续普通回复。 Search once and then answer normally."""

        async def complete(self, **kwargs):
            """只记录真实调用，避免重放搜索。 Count calls without replaying search."""
            self.requests.append(kwargs)
            return (
                turn(call("web_search", query="Python release notes"))
                if len(self.requests) == 1
                else turn(text="Can continue")
            )

    calls = 0

    async def search(self, query, max_uses, session_id, limits, progress):
        """复现辅助进度后搜索失败，不请求外网。 Reproduce progress then failure without network."""
        nonlocal calls
        calls += 1
        await progress(ModelProgress(phase="receiving", elapsed_ms=1))
        raise AgentError(
            "WEB_SEARCH_UNAVAILABLE", "No native result block", details={"result_blocks": 0}
        )

    monkeypatch.setattr(NativeSearchClient, "check_available", lambda self: None)
    monkeypatch.setattr(NativeSearchClient, "search", search)

    async def scenario():
        """保存失败并模拟缺失终态后接续。 Persist failure and resume a missing outcome."""
        model = SearchModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            await app.sessions.start(sid, str(uuid4()), "Search", None)
            await app.sessions.active_for(sid).task
            view = await app.sessions.view(sid)
            assert view.summary.can_continue and not view.summary.issue
            assert view.summary.run.cause_code == "WEB_SEARCH_UNAVAILABLE"
            log = await app.sessions._load(sid)
            terminal = next(f for f in reversed(log.facts) if isinstance(f.data, RunFinished))
            assert terminal.data.failed_request_id is None
            diagnostic_id = terminal.data.diagnostic_id
            assert diagnostic_id and len(list(app.sessions.diagnostics.root.glob("*.json"))) == 1
            row = next(r for r in trace_items(log) if r.tool_name == "web_search")
            assert row.diagnostic_ids == [diagnostic_id]
            files = await app.sessions.evolution.resources.file_tools(
                created.task.project_id, str(uuid4())
            )
            executor = app.sessions.tool_factory(replace(files.context, session_id=sid))
            result = await executor.execute(call("read_diagnostic", diagnostic_id=diagnostic_id))
            assert not result.is_error and "No native result block" in result.content
            await app.sessions.start(sid, str(uuid4()), "Can I continue?", None)
            await app.sessions.active_for(sid).task
            assert (await app.sessions.view(sid)).summary.run.status == "completed"
            # 隔离样本复现用户磁盘尾部：保留工具结果，缺少终态，绝不修改个人会话。
            # Reproduce the user's valid tool-result prefix only in the isolated fixture.
            path = app.sessions.store.path(sid)
            path.write_bytes(
                b"".join(
                    line + b"\n" for line in path.read_bytes().splitlines()[: terminal.seq - 1]
                )
            )
            app.sessions.last_log.issue = "SESSION_DAMAGED"
            assert (await app.sessions.view(sid)).summary.can_continue
        async with app_at(tmp_path / "data", model) as app:
            assert (await app.sessions.view(sid)).summary.can_continue
            await app.sessions.start(sid, str(uuid4()), "Continue after reopening", None)
            await app.sessions.active_for(sid).task
            assert (await app.sessions.view(sid)).summary.run.status == "completed"
            assert calls == 1

    asyncio.run(scenario())
