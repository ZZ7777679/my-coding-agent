"""M7 使用真实服务与隔离文件验证采用和恢复。

Validate M7 adoption/restoration through real services and isolated files.
"""

import asyncio
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from my_agent.errors import AgentError
from my_agent.evolution.types import (
    CreateEvolutionCandidate,
    EvolutionControl,
    EvolutionExperimentParams,
    EvolutionJobControl,
    EvolutionQuery,
    EvolutionRunsQuery,
    EvolutionSettings,
    EvolutionSource,
    EvolutionTarget,
    GenerateEvolutionCandidate,
    SaveEvolutionFeedback,
)
from my_agent.execution.types import ProgramCommand, RunCommandArgs, ShellCommand
from my_agent.sessions.trace import TraceParams, trace_page
from tests.python.test_goal_controller import app_at, call, create_session, turn


class ReviewModel:
    """仅返回一个候选，记录实际输入。

    Return one candidate and retain actual input.
    """

    def __init__(self):
        """初始化离线请求记录。

        Initialize offline request records.
        """
        self.requests = []

    def check_available(self):
        """不访问凭据。

        Do not access credentials.
        """

    async def complete(self, **kwargs):
        """生成项目规范修正，不伪造验证。

        Propose a rule correction without claiming tests.
        """
        self.requests.append(kwargs)
        payload = json.loads(next(m["content"] for m in kwargs["messages"] if m["role"] == "user"))
        return turn(
            text=json.dumps(
                {
                    "summary": "Keep checks focused",
                    "proposals": [
                        {
                            "finding_id": "feedback",
                            "title": "Keep checks focused",
                            "rationale": "User feedback",
                            "target": payload["directed_target"],
                            "after": "Run only checks relevant to changed behavior.\n",
                        }
                    ]
                    if payload.get("directed_target")
                    else [],
                }
            )
        )


async def check_rule_generation_restore_and_conflict(tmp_path):
    """候选采用可恢复，外部编辑不被覆盖。

    Candidates restore correctly without overwriting later edits.
    """
    model = ReviewModel()
    async with app_at(tmp_path / "data", model) as app:
        created = await create_session(app, tmp_path / "project")
        pid = created.task.project_id
        service = app.sessions.evolution
        path = tmp_path / "project" / "AGENTS.md"
        path.write_text("Old guidance\n", encoding="utf-8", newline="")
        job = await service.generate(
            GenerateEvolutionCandidate(
                project_id=pid,
                target=EvolutionTarget(kind="project_rule", identity="AGENTS.md"),
                instruction="Only relevant checks",
            )
        )
        await service.jobs[job.job_id][1]
        assert job.status == "completed"
        assert len(model.requests) == 1
        candidate = await service.control(
            EvolutionControl(
                project_id=pid,
                candidate_id=job.candidate_id,
                action="apply",
            )
        )
        assert path.read_text(encoding="utf-8") == candidate.after
        path.write_text("User edit\n", encoding="utf-8", newline="")
        with pytest.raises(AgentError, match="目标已被其他工作修改"):
            await service.control(
                EvolutionControl(
                    project_id=pid,
                    candidate_id=job.candidate_id,
                    action="revert",
                )
            )
        assert path.read_text(encoding="utf-8") == "User edit\n"
        path.write_text(candidate.after, encoding="utf-8", newline="")
        await service.control(
            EvolutionControl(
                project_id=pid,
                candidate_id=job.candidate_id,
                action="revert",
            )
        )
        assert path.read_text(encoding="utf-8") == "Old guidance\n"
        page = await service.page(EvolutionQuery(project_id=pid))
        assert page.candidates[0].status == "reverted"


async def check_builtin_skill_copy_and_memory_restore(tmp_path):
    """内置内容保持原样；新偏好恢复后可以再次采用。

    Preserve bundled Skills and allow reapplying restored new preferences.
    """
    async with app_at(tmp_path / "data", ReviewModel()) as app:
        created = await create_session(app, tmp_path / "project")
        pid = created.task.project_id
        service = app.sessions.evolution
        catalog = await service.catalog(pid)
        builtin = next(
            item for item in catalog.items if item.target.identity.startswith("builtin:")
        )
        resource = await service.resources.read(pid, builtin.target)
        assert resource.content is None
        assert resource.reference_content
        candidate = await service.create(
            CreateEvolutionCandidate(
                project_id=pid,
                target=builtin.target,
                title="Copy method",
                after=resource.reference_content + "\nUse a short summary.\n",
            )
        )
        adopted = await service.control(
            EvolutionControl(
                project_id=pid,
                candidate_id=candidate.candidate_id,
                action="apply",
            )
        )
        assert adopted.target.identity.startswith("user:")
        await service.control(
            EvolutionControl(
                project_id=pid,
                candidate_id=candidate.candidate_id,
                action="revert",
            )
        )
        read_back = await service.resources.read(pid, builtin.target)
        assert read_back.content is None
        assert read_back.reference_content == resource.reference_content
        memory = await service.create(
            CreateEvolutionCandidate(
                project_id=pid,
                target=EvolutionTarget(kind="preference", identity="", scope="user"),
                title="Concise summaries",
                after=json.dumps({"title": "Concise", "content": "Keep summaries concise."}),
            )
        )
        for action in ("apply", "revert", "apply"):
            memory = await service.control(
                EvolutionControl(
                    project_id=pid,
                    candidate_id=memory.candidate_id,
                    action=action,
                )
            )
        entry = service.resources.memory.read(memory.target.identity, pid)
        assert entry.category == "preference" and entry.scope == "user"


async def check_diagnostics_do_not_persist_exception_secrets(tmp_path):
    """保存异常位置与原因码，不保存异常中的秘密。

    Save locations/causes without exception secrets.
    """
    async with app_at(tmp_path / "data", ReviewModel()) as app:
        created = await create_session(app, tmp_path / "project")
        try:
            try:
                raise ValueError("Gateway refused credentials: token=private-value-never-log-this")
            except ValueError as exc:
                raise AgentError(
                    "MODEL_FAILED", "连接失败。", cause_code="CONNECT", phase="connect"
                ) from exc
        except AgentError as exc:
            identity = await app.worker.call(
                app.sessions.diagnostics.record,
                exc.code,
                exc.message,
                component="model",
                exception=exc,
                project_id=created.task.project_id,
            )
        content = (app.storage.root / "logs" / "diagnostics" / f"{identity}.json").read_text(
            encoding="utf-8"
        )
        assert "private-value-never-log-this" not in content
        assert "Gateway refused credentials" in content
        assert "ValueError" in content and '"phase": "connect"' in content
        feedback = await app.dispatch(
            "evolution.feedback",
            {
                "project_id": created.task.project_id,
                "feedback_id": str(uuid4()),
                "text": "Connection failed",
            },
        )
        assert feedback.text == "Connection failed"
        assert not app.sessions.evolution.jobs


def test_evolution_resource_roundtrip(tmp_path):
    """验证采用、恢复及外部改动保留。 Verify adoption, restoration and conflict preservation."""
    asyncio.run(check_rule_generation_restore_and_conflict(tmp_path))


def test_evolution_skill_and_memory(tmp_path):
    """验证内置副本与偏好恢复。 Verify bundled copies and preference restoration."""
    asyncio.run(check_builtin_skill_copy_and_memory_restore(tmp_path))


def test_evolution_diagnostics(tmp_path):
    """验证异常来源且不保存秘密。 Verify exception provenance without secret persistence."""
    asyncio.run(check_diagnostics_do_not_persist_exception_secrets(tmp_path))


@pytest.mark.parametrize("shell", [False, True])
def test_code_experiment_and_standalone_recovery(tmp_path, shell):
    """验证真实代码比较与独立恢复脚本。

    Verify actual code comparison and independent recovery.
    """

    async def scenario():
        """原项目在实验期间保持不变。

        Leave the original unchanged throughout experimentation.
        """
        async with app_at(tmp_path / "data", ReviewModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service, pid = app.sessions.evolution, created.task.project_id
            source = tmp_path / "project" / "answer.py"
            source.write_text("value = 1\n", encoding="utf-8", newline="")
            candidate = await service.create(
                CreateEvolutionCandidate(
                    project_id=pid,
                    target=EvolutionTarget(kind="code", identity="answer.py"),
                    title="Correct answer",
                    after="value = 2\n",
                )
            )
            job = await service.experiment(
                EvolutionExperimentParams(
                    project_id=pid,
                    candidate_id=candidate.candidate_id,
                    command=RunCommandArgs(
                        command=ShellCommand(
                            kind="powershell",
                            script="& '"
                            + sys.executable.replace("'", "''")
                            + "' -c 'import answer; assert answer.value == 2'",
                        )
                        if shell
                        else ProgramCommand(
                            kind="program",
                            program=sys.executable,
                            arguments=["-c", "import answer; assert answer.value == 2"],
                        )
                    ),
                )
            )
            await service.jobs[job.job_id][1]
            assert job.status == "completed", job.message
            assert [p.summary.exit_code for p in job.programs] == [1, 0]
            page = await service.page(EvolutionQuery(project_id=pid))
            assert page.jobs[0].details_available and not page.jobs[0].programs
            detail = await service.job_detail(
                EvolutionJobControl(project_id=pid, job_id=job.job_id)
            )
            assert len(detail.programs) == 2
            assert source.read_text(encoding="utf-8") == "value = 1\n"
            candidate = await service.control(
                EvolutionControl(
                    project_id=pid,
                    candidate_id=candidate.candidate_id,
                    action="apply",
                )
            )
            assert source.read_text(encoding="utf-8") == "value = 2\n"
            # 独立脚本不导入 my_agent；模拟业务源码无法正常启动时恢复。
            # Run without importing my_agent, as when edited application sources cannot boot.
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    sys.executable,
                    str(Path(candidate.recovery_directory) / "restore.py"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stderr
            assert source.read_text(encoding="utf-8") == "value = 1\n"
            recovered = service.store.candidate(pid, candidate.candidate_id)
            assert recovered.status == "reverted"

    asyncio.run(scenario())


def test_evolution_plan_guidance_and_cancellation(tmp_path):
    """验证 Plan 仅提案、说明进入真实请求及即时取消持久化。

    Verify Plan-only proposals, actual guidance assembly and immediate cancellation.
    """

    async def scenario():
        """使用真实工具装配，不产生网络请求。

        Exercise actual tool composition without network calls.
        """
        model = ReviewModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            service, pid = app.sessions.evolution, created.task.project_id
            await app.worker.call(
                service.store.configure,
                EvolutionSettings(project_id=pid, auto_apply=["project_rule"]),
            )
            files = await service.resources.file_tools(pid, str(uuid4()))
            executor = app.sessions.tool_factory(replace(files.context, mode="plan"))
            result = await executor.execute(
                call(
                    "propose_improvement",
                    target={"kind": "project_rule", "identity": "AGENTS.md"},
                    title="Plan proposal",
                    rationale="Explicit requested change",
                    after="Planned rule",
                )
            )
            assert not result.is_error
            assert json.loads(result.content)["status"] == "draft"
            assert "before" not in json.loads(result.content)
            assert not (tmp_path / "project" / "AGENTS.md").exists()
            candidate = await service.create(
                CreateEvolutionCandidate(
                    project_id=pid,
                    target=EvolutionTarget(kind="tool_guidance", identity="read_file"),
                    title="Explain reading",
                    after="M7-GUIDANCE: use start_line for a targeted excerpt.",
                )
            )
            await service.control(
                EvolutionControl(
                    project_id=pid,
                    candidate_id=candidate.candidate_id,
                    action="apply",
                )
            )
            sid = created.session.session_id
            await app.sessions.start(sid, str(uuid4()), "Hello", None, "plan")
            await app.sessions.active_for(sid).task
            assert "M7-GUIDANCE" in json.dumps(model.requests[-1]["messages"])
            job = await service.generate(
                GenerateEvolutionCandidate(
                    project_id=pid,
                    target=EvolutionTarget(kind="project_rule", identity="AGENTS.md"),
                )
            )
            stopped = await service.stop(EvolutionJobControl(project_id=pid, job_id=job.job_id))
            assert stopped.status == "cancelled" and job.job_id not in service.jobs
            assert service.store.job(pid, job.job_id).status == "cancelled"

    asyncio.run(scenario())


def test_review_evidence_matches_request_and_persisted_snapshot(tmp_path):
    """实际运行的工具配对、去重、范围、预算和快照与模型输入一致。

    Verify paired real-run traces, deduplication, scope, budget and persisted model input.
    """

    class EvidenceModel(ReviewModel):
        """源会话使用真实读文件工具，复盘仅替换模型回复。

        Use actual file reading in source runs and stub only review replies.
        """

        async def complete(self, **kwargs):
            """将业务读取与独立复盘分开记录。

            Record source reads separately from the independent review.
            """
            if kwargs["messages"][0]["content"].startswith("Investigate selected"):
                return await super().complete(**kwargs)
            if kwargs["messages"][-1]["role"] == "tool":
                return turn(text="Read completed.")
            prompt = next(
                item["content"] for item in reversed(kwargs["messages"]) if item["role"] == "user"
            )
            count = 45 if prompt == "EXCLUDED_RUN" else 1
            return turn(*(call("read_file", path="sample.txt") for _ in range(count)))

    async def scenario():
        """使用隔离目录及实际 RPC 装配，不请求网络。

        Use isolated storage and actual RPC composition without networking.
        """
        model = EvidenceModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            pid, sid = created.task.project_id, created.session.session_id
            service = app.sessions.evolution
            (tmp_path / "project" / "sample.txt").write_text("sample content", encoding="utf-8")
            started = await app.sessions.start(sid, str(uuid4()), "SELECTED_RUN", None, "plan")
            await app.sessions.active_for(sid).task
            run_id = started.run.run_id
            await app.sessions.start(sid, str(uuid4()), "EXCLUDED_RUN", None, "plan")
            await app.sessions.active_for(sid).task
            log = await app.sessions._load(sid)
            rows = trace_page(log, TraceParams(session_id=sid, run_id=run_id))
            assert any("SELECTED_RUN" in item.title for item in rows.items)
            tool = next(item for item in rows.items if item.tool_name == "read_file")
            source = EvolutionSource(session_id=sid, run_id=run_id)
            diagnostic = service.diagnostics.record(
                "SAMPLE_WARNING",
                "Inspect read strategy",
                component="sample",
                project_id=pid,
                source=source,
            )
            saved = await service.feedback(
                SaveEvolutionFeedback(
                    project_id=pid,
                    feedback_id=str(uuid4()),
                    text="Keep reads focused",
                    sources=[source],
                )
            )
            params = GenerateEvolutionCandidate(
                project_id=pid,
                target=EvolutionTarget(kind="project_rule", identity="AGENTS.md"),
                feedback_ids=[saved.feedback_id],
                instruction="Explain file reading.",
                sources=[
                    source,
                    EvolutionSource(session_id=sid, run_id=run_id, seq=tool.seq),
                    EvolutionSource(diagnostic_id=diagnostic),
                ],
            )
            preview = await app.dispatch("evolution.preview", params.model_dump(mode="json"))
            assert not model.requests
            materials = preview.model_dump_json()
            assert "SELECTED_RUN" in materials and "EXCLUDED_RUN" not in materials
            assert "SAMPLE_WARNING" in materials
            selected_tools = [
                m for m in preview.materials if m.source.seq == tool.seq and m.kind == "trace"
            ]
            assert selected_tools == []
            assert preview.coverage.read == 0
            assert any(e.representative.seq == tool.seq for e in preview.screening)
            catalog = await service.runs(
                EvolutionRunsQuery(
                    project_id=pid,
                    session_id=sid,
                    limit=1,
                )
            )
            assert catalog.total_runs == 2 and catalog.runs[0].event_count > 40
            earlier = await service.runs(
                EvolutionRunsQuery(
                    project_id=pid,
                    session_id=sid,
                    limit=1,
                    before_seq=catalog.before_seq,
                )
            )
            assert earlier.runs[0].run_id == run_id
            searched = await service.runs(
                EvolutionRunsQuery(
                    project_id=pid,
                    session_id=sid,
                    query="SELECTED_RUN",
                )
            )
            assert searched.matched_runs == 1 and searched.runs[0].run_id == run_id
            single = await service.preview(
                params.model_copy(
                    update={
                        "feedback_ids": [],
                        "sources": [
                            EvolutionSource(
                                scope="event",
                                session_id=sid,
                                seq=tool.seq,
                                through_seq=catalog.through_seq,
                            )
                        ],
                    }
                )
            )
            assert single.trace_count == 1 and single.selections[0].event_count == 1
            assert single.selections[0].source.scope == "event"
            # 冻结目录水位后新增一轮，不应混入“整个会话”的已选快照。
            # A new run after selection must not enter the frozen whole-session range.
            long_prompt = "LATE_RUN " + "x" * 26000 + "END_OF_LONG_SELECTION"
            await app.sessions.start(sid, str(uuid4()), long_prompt, None, "plan")
            await app.sessions.active_for(sid).task
            whole = await service.preview(
                params.model_copy(
                    update={
                        "feedback_ids": [],
                        "sources": [
                            EvolutionSource(
                                scope="session",
                                session_id=sid,
                                through_seq=catalog.through_seq,
                            )
                        ],
                    }
                )
            )
            assert whole.trace_count == catalog.total_events
            assert whole.selections[0].source.scope == "session"
            assert "LATE_RUN" not in whole.model_dump_json()
            assert preview.trace_count < whole.trace_count
            latest = await service.runs(EvolutionRunsQuery(project_id=pid, session_id=sid))
            await app.dispatch("evolution.configure", {"project_id": pid, "input_chars": None})
            long_selection = await service.preview(
                params.model_copy(
                    update={
                        "feedback_ids": [],
                        "sources": [
                            EvolutionSource(
                                scope="event",
                                session_id=sid,
                                seq=latest.runs[0].seq,
                                through_seq=latest.through_seq,
                            )
                        ],
                    }
                )
            )
            assert not long_selection.materials[0].truncated
            assert long_selection.input_chars is None
            assert "END_OF_LONG_SELECTION" not in long_selection.materials[0].content
            assert long_selection.coverage.read == 0
            job = await service.generate(params)
            await service.jobs[job.job_id][1]
            assert job.status == "completed"
            sent = json.loads(
                next(m["content"] for m in model.requests[-1]["messages"] if m["role"] == "user")
            )
            persisted = service.store.job(pid, job.job_id)
            assert sent["input"]["materials"] == [
                m.model_dump(mode="json") for m in persisted.review_input.materials
            ]
            assert sent["input"]["trace_count"] == persisted.review_input.trace_count
            assert service.store.candidate(pid, job.candidate_id).review_job_id == job.job_id
            page = await service.page(EvolutionQuery(project_id=pid))
            assert page.jobs[0].details_available and page.jobs[0].review_input is None
            await app.worker.call(
                service.store.configure,
                EvolutionSettings(
                    project_id=pid,
                    input_chars=10,
                ),
            )
            short = await service.preview(params)
            assert short.included_chars == 10 and short.omitted_materials > 0
            assert short.materials[0].truncated
            assert service.store.job(pid, job.job_id).review_input == persisted.review_input

    asyncio.run(scenario())
