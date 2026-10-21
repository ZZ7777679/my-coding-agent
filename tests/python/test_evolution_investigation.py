"""真实服务、隔离跨项目证据与离线模型的调查主链。

Investigation through real services, isolated cross-project evidence and an offline model.
"""

import asyncio
import json
from uuid import uuid4

import pytest

from my_agent.errors import AgentError
from my_agent.evolution.types import (
    EvolutionControl,
    EvolutionJobControl,
    EvolutionSettings,
    EvolutionSource,
    GenerateEvolutionCandidate,
    SaveEvolutionFeedback,
)
from my_agent.sessions.trace import TraceParams, trace_page
from tests.python.test_evolution import ReviewModel
from tests.python.test_goal_controller import app_at, call, create_session, turn


class InvestigatingModel(ReviewModel):
    """根据实际工具结果调查，返回两个不同资源的改进建议。

    Investigate actual tool results and propose improvements for two distinct resources.
    """

    def __init__(self, blocked=False, direct_file_only=False, hold_proposal=False):
        """可暂停首请求，覆盖活动输入去重。

        Optionally pause the first request to verify active-input deduplication.
        """
        super().__init__()
        self.stages = {}
        self.results = {}
        self.direct_file_only = direct_file_only
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.source_read, self.proposal_release = asyncio.Event(), asyncio.Event()
        if not blocked:
            self.release.set()
        if not hold_proposal:
            self.proposal_release.set()

    async def complete(self, **kwargs):
        """在调查中读取真实目录、资源定义及长事件后段。

        Read actual indexes, resource definitions and later spans of a long event.
        """
        if not kwargs["messages"][0]["content"].startswith("Investigate selected"):
            return turn(text="Recorded source observation")
        self.requests.append(kwargs)
        self.started.set()
        await self.release.wait()
        sid = kwargs["session_id"]
        stage = self.stages.get(sid, 0)
        self.stages[sid] = stage + 1
        if stage == 0:
            calls = [
                call("index_review_evidence", query="BODY_TARGET", limit=100),
                call(
                    "read_review_resource",
                    target={"kind": "tool_guidance", "identity": "read_file"},
                ),
            ]
            if not self.direct_file_only:
                calls.append(
                    call(
                        "read_review_resource",
                        target={"kind": "code", "identity": "agent_core.py"},
                    )
                )
            return turn(*calls)
        outputs = [
            json.loads(message["content"])
            for message in kwargs["messages"]
            if message["role"] == "tool"
        ]
        if stage == 1:
            index = next(output for output in outputs if "matched_count" in output)
            row = next(
                item
                for item in index["items"]
                if item["kind"] == "run.accepted" and "BODY_TARGET" in item["title"]
            )
            resource = next(
                json.loads(output["text"])
                for output in outputs
                if output.get("target", {}).get("kind") == "tool_guidance"
            )
            definition = json.loads(resource["reference_content"])["function"]
            assert definition["name"] == "read_file"
            assert "start_line" in definition["parameters"]["properties"]
            assert "lines" in definition["parameters"]["properties"]
            self.results[sid] = {"row": row, "schema": definition}
            return turn(
                call(
                    "read_review_evidence",
                    session_id=row["session_id"],
                    seq=row["seq"],
                    offset=12000,
                    limit=8000,
                ),
                call("read_file", path="agent_core.py"),
            )
        evidence = next(output for output in outputs if output.get("offset") == 12000)
        assert "BODY_TAIL_MARKER" in evidence["text"]
        source_file = next(output for output in outputs if output.get("path") == "agent_core.py")
        assert "value = 1" in json.dumps(source_file)
        self.source_read.set()
        await self.proposal_release.wait()
        row = self.results[sid]["row"]
        source = {"session_id": row["session_id"], "seq": row["seq"], "scope": "event"}
        self.results[sid]["body"] = evidence["text"]
        findings = [
            {
                "finding_id": "usage",
                "title": "Use the actual read arguments",
                "explanation": "The selected correction and actual schema agree.",
                "category": "tool_usage",
                "targets": [{"kind": "tool_guidance", "identity": "read_file"}],
                "sources": [source],
            },
            {
                "finding_id": "implementation",
                "title": "Correct the implementation value",
                "explanation": "The selected observation relates to the inspected source.",
                "category": "implementation",
                "targets": [{"kind": "code", "identity": "agent_core.py"}],
                "sources": [source],
            },
        ]
        return turn(
            text=json.dumps(
                {
                    "summary": "Two independent findings; no validation claimed.",
                    "findings": findings,
                    "proposals": [
                        {
                            "finding_id": "usage",
                            "title": "Read guidance",
                            "rationale": "Use the inspected parameter schema.",
                            "target": {"kind": "tool_guidance", "identity": "read_file"},
                            "after": "Use start_line and lines for focused reads.",
                        },
                        {
                            "finding_id": "implementation",
                            "title": "Implementation correction",
                            "rationale": "Update the inspected target source independently.",
                            "target": {"kind": "code", "identity": "agent_core.py"},
                            "after": "value = 2\n",
                        },
                    ],
                }
            )
        )


async def source_project(app, root):
    """创建超过索引首屏的真实业务轨迹，保留一个长事件。

    Create actual business traces beyond one index page, including a long event.
    """
    created = await create_session(app, root)
    sid = created.session.session_id
    long_prompt = "BODY_TARGET " + "x" * 16000 + " BODY_TAIL_MARKER"
    for prompt in [long_prompt, *(f"FILLER_{index}" for index in range(9))]:
        await app.sessions.start(sid, str(uuid4()), prompt, None, "plan")
        await app.sessions.active_for(sid).task
    log = await app.sessions._load(sid)
    assert len(trace_page(log, TraceParams(session_id=sid, limit=100)).items) > 30
    return created, EvolutionSource(session_id=sid, scope="session", through_seq=log.facts[-1].seq)


def test_investigation_cross_project_multiple_findings_and_independent_candidates(tmp_path):
    """业务项目证据可改进另一源码项目，各候选单独采用。

    Business-project evidence can improve another source project through independent candidates.
    """

    async def scenario():
        """核对真实读取、持久快照和实际写入归属。

        Check actual reads, persisted snapshots and the destination of real writes.
        """
        model = InvestigatingModel()
        async with app_at(tmp_path / "data", model) as app:
            source, reference = await source_project(app, tmp_path / "business")
            target = await create_session(app, tmp_path / "harness")
            pid, service = target.task.project_id, app.sessions.evolution
            (tmp_path / "business" / "agent_core.py").write_text("business\n", encoding="utf-8")
            code = tmp_path / "harness" / "agent_core.py"
            code.write_text("value = 1\n", encoding="utf-8", newline="")
            job = await service.generate(
                GenerateEvolutionCandidate(project_id=pid, sources=[reference])
            )
            await service.jobs[job.job_id][1]
            detail = await service.job_detail(
                EvolutionJobControl(project_id=pid, job_id=job.job_id)
            )
            assert detail.status == "completed", detail.message
            assert len(detail.findings) == len(detail.candidate_ids) == 2
            assert detail.requests == 3
            assert detail.review_input.coverage.read == 1
            assert detail.review_input.coverage.complete == 0
            assert detail.review_input.coverage.unread > 30
            trace = next(m for m in detail.review_input.materials if m.kind == "trace")
            assert trace.offset == 12000 and "BODY_TAIL_MARKER" in trace.content
            assert trace.source.session_id == source.session.session_id
            resources = [m.content for m in detail.review_input.materials if m.kind == "resource"]
            assert any("start_line" in text and "parameters" in text for text in resources)
            candidates = [service.store.candidate(pid, cid) for cid in detail.candidate_ids]
            guidance = next(c for c in candidates if c.target.kind == "tool_guidance")
            implementation = next(c for c in candidates if c.target.kind == "code")
            assert {c.finding_id for c in candidates} == {"usage", "implementation"}
            assert guidance.before is None and implementation.before == "value = 1\n"
            await service.control(
                EvolutionControl(project_id=pid, candidate_id=guidance.candidate_id, action="apply")
            )
            assert service.store.candidate(pid, implementation.candidate_id).status == "draft"
            assert code.read_text(encoding="utf-8") == "value = 1\n"
            await service.control(
                EvolutionControl(
                    project_id=pid, candidate_id=implementation.candidate_id, action="apply"
                )
            )
            assert code.read_text(encoding="utf-8") == "value = 2\n"
            assert (tmp_path / "business" / "agent_core.py").read_text() == "business\n"
            assert not service.resources.guidance(source.task.project_id)

    asyncio.run(scenario())


def test_investigation_preserves_baseline_read_by_file_tool(tmp_path):
    """源码调查读取后的人工作业不被生成结束时的新基线掩盖。

    User changes after source inspection cannot be hidden behind a newly captured final baseline.
    """

    async def scenario():
        """在真实读取与提案之间编辑文件，采用必须保留后到修改。

        Edit between the actual read and proposal; adoption must preserve the intervening edit.
        """
        model = InvestigatingModel(direct_file_only=True, hold_proposal=True)
        async with app_at(tmp_path / "data", model) as app:
            source, reference = await source_project(app, tmp_path / "business")
            pid, service = source.task.project_id, app.sessions.evolution
            code = tmp_path / "business" / "agent_core.py"
            code.write_text("value = 1\n", encoding="utf-8", newline="")
            job = await service.generate(
                GenerateEvolutionCandidate(project_id=pid, sources=[reference])
            )
            try:
                await asyncio.wait_for(model.source_read.wait(), 3)
                code.write_text("value = 7  # User edit\n", encoding="utf-8", newline="")
            finally:
                model.proposal_release.set()
            await service.jobs[job.job_id][1]
            detail = service.store.job(pid, job.job_id)
            assert detail.status == "completed", detail.message
            implementation = next(
                candidate
                for identity in detail.candidate_ids
                if (candidate := service.store.candidate(pid, identity)).target.kind == "code"
            )
            assert implementation.before == "value = 1\n"
            with pytest.raises(AgentError, match="目标已被其他工作修改"):
                await service.control(
                    EvolutionControl(
                        project_id=pid, candidate_id=implementation.candidate_id, action="apply"
                    )
                )
            assert code.read_text(encoding="utf-8") == "value = 7  # User edit\n"

    asyncio.run(scenario())


def test_investigation_only_deduplicates_active_input_and_links_feedback(tmp_path):
    """仅调查不保存提案，活动输入及反馈重试保留同一作业身份。

    Investigation-only saves no proposals; active input and feedback retries retain job identities.
    """

    async def scenario():
        """冻结模型首请求，显式验证活动去重和反馈接纳结果。

        Pause the first model request to verify deduplication and accepted feedback results.
        """
        model = InvestigatingModel(blocked=True)
        async with app_at(tmp_path / "data", model) as app:
            source, reference = await source_project(app, tmp_path / "business")
            pid, service = source.task.project_id, app.sessions.evolution
            (tmp_path / "business" / "agent_core.py").write_text(
                "value = 1\n", encoding="utf-8", newline=""
            )
            params = GenerateEvolutionCandidate(
                project_id=pid, mode="investigate", sources=[reference]
            )
            job = await service.generate(params)
            await asyncio.wait_for(model.started.wait(), 3)
            same = await service.generate(params)
            assert same.job_id == job.job_id and len(service.jobs) == 1
            model.release.set()
            await service.jobs[job.job_id][1]
            detail = service.store.job(pid, job.job_id)
            assert detail.status == "completed", detail.message
            assert len(detail.findings) == 2 and not detail.candidate_ids
            assert not list(
                service.store.path(pid, "candidates", str(uuid4())).parent.glob("*.json")
            )
            await app.worker.call(
                service.store.configure, EvolutionSettings(project_id=pid, automatic_review=True)
            )
            feedback_params = SaveEvolutionFeedback(
                project_id=pid,
                feedback_id=str(uuid4()),
                text="Inspect these observations",
                sources=[reference],
            )
            feedback = await service.feedback(feedback_params)
            assert feedback.review_job_id is not None
            repeated = await service.feedback(feedback_params)
            assert repeated.review_job_id == feedback.review_job_id
            live = service.jobs.get(feedback.review_job_id)
            if live:
                await live[1]
            reviewed = service.store.job(pid, feedback.review_job_id)
            assert reviewed.mode == "investigate" and reviewed.status == "completed"
            assert not reviewed.candidate_ids
            assert (
                service.store.read_feedback(pid, feedback.feedback_id).review_job_id
                == reviewed.job_id
            )

    asyncio.run(scenario())
