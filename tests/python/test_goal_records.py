"""Goal / 工作图的持久边界检查，不调用模型或项目程序。

Durability checks for goals and work graphs without model calls or project execution.
"""

import json
from uuid import uuid4

import pytest

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.errors import AgentError
from my_agent.goals.journal import GoalJournal
from my_agent.goals.ledger import check_budget, usage
from my_agent.goals.state import states, views
from my_agent.goals.types import GoalBudget, GoalControl, GoalCreated, GoalCriterion, GoalSettled
from my_agent.models.types import ModelTurn, TokenUsage, ToolCall, ToolResult
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.projection import entries
from my_agent.sessions.reading import SessionReader
from my_agent.sessions.store import SessionLog, SessionStore
from my_agent.sessions.types import (
    AssistantCommitted,
    ProgressSynced,
    RequestStarted,
    RunAccepted,
    RunFinished,
    SessionCreated,
    ToolCompleted,
    ToolStarted,
)
from my_agent.storage import Storage
from my_agent.tasks.store import TaskStore
from my_agent.tasks.types import CreateTaskParams, TaskFields, UpdateTaskParams
from my_agent.workflow.types import (
    CriterionResult,
    EvidenceRef,
    HumanQuestion,
    WorkItem,
    WorkReport,
)


@pytest.fixture
def records(tmp_path):
    """以真实单写者与隔离任务日志复用生产存储。

    Use production storage with a real writer lock and isolated task journals.
    """
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    with storage.writer():
        storage.initialize()
        tasks = TaskStore(storage)
        task = tasks.create(
            CreateTaskParams(
                operation_id=str(uuid4()),
                project_id=str(uuid4()),
                model_id="glm-5.3-flash",
                fields=TaskFields(title="Task", goal="Build a page"),
            )
        )
        sessions = SessionStore(storage)
        log = SessionLog(task.initial_session_id, [])
        sessions.append(
            log,
            SessionCreated(
                project_id=task.project_id,
                model_id=task.initial_model_id,
                task_id=task.task_id,
                initial_mode="normal",
            ),
            None,
        )
        yield sessions, log, tasks, task


def make_goal(journal, log):
    """保存固定用户条件，并显式开始局部目标。

    Save fixed user criteria and explicitly activate a local goal.
    """
    goal = GoalCreated(
        goal_id=str(uuid4()),
        objective="Implement and report the page",
        criteria=[GoalCriterion(criterion_id="page", description="Report observed results")],
        budget=GoalBudget(max_requests=2, max_tools=2, max_active_seconds=30),
    )
    journal.create(log, goal)
    journal.control(
        log,
        GoalControl(
            goal_id=goal.goal_id, operation_id=str(uuid4()), expected_revision=1, action="resume"
        ),
    )
    return goal


def start_run(sessions, log, task, goal=None, *, role="work"):
    """保存真实格式的接纳与请求开始，以源任务版本关联。

    Save accepted and request-start facts tied to the source task revision.
    """
    run_id, message_id = str(uuid4()), str(uuid4())
    time_limit = None
    if goal:
        current = states(log.facts)[goal.goal_id]
        used = usage(log.facts, goal.goal_id)
        if current.budget.max_active_seconds is not None:
            remaining = (
                current.budget.max_active_seconds - used.active_seconds - used.reserved_seconds
            )
            configured = DEFAULTS["run"]["max_seconds"]
            # 不限 Run 仍遵守本用例显式 Goal 预算。 An unlimited Run keeps the explicit Goal budget.
            time_limit = remaining if configured is None else min(float(configured), remaining)
    sessions.append(
        log,
        RunAccepted(
            operation_id=str(uuid4()),
            prompt="Work within the request",
            limits=RunLimits.model_validate(DEFAULTS["run"]),
            requested_limits=None,
            mode="normal",
            goal_id=goal.goal_id if goal else None,
            goal_role=role if goal else None,
            active_time_limit_seconds=time_limit,
        ),
        run_id,
    )
    sessions.append(
        log,
        RequestStarted(message_id=message_id, task_id=task.task_id, task_revision=task.revision),
        run_id,
    )
    return run_id, message_id


def commit_turn(sessions, log, run_id, message_id, *, call=None, text="Observed result"):
    """提交完整模型结果，原生工具配对与生产历史一致。

    Commit complete model results with production-compatible native tool pairing.
    """
    native = {"role": "assistant", "content": text}
    if call is not None:
        native["tool_calls"] = [
            {
                "id": call.tool_call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                },
            }
        ]
    return sessions.append(
        log,
        AssistantCommitted(
            message_id=message_id,
            turn=ModelTurn(
                text=text,
                tool_calls=[call] if call else [],
                native=native,
                usage=TokenUsage(input_tokens=10, output_tokens=3),
            ),
        ),
        run_id,
    )


def reference(fact, kind="assistant", expectation="observed"):
    """构造已发生事实引用，不使用虚构路径或成果。

    Reference an existing fact without inventing paths or artifacts.
    """
    return EvidenceRef(
        session_id=fact.session_id,
        run_id=fact.run_id,
        seq=fact.seq,
        kind=kind,
        expectation=expectation,
    )


def finish(sessions, log, run_id, report=None, *, status="completed", elapsed=1.5):
    """保存终态与实际报告，供 Goal / 任务各自幂等投影。

    Persist terminal facts and reports for idempotent goal and task projection.
    """
    return sessions.append(
        log,
        RunFinished(status=status, code=None, message=None, elapsed_seconds=elapsed, report=report),
        run_id,
    )


def sync_report(sessions, log, tasks, result):
    """先同步真实报告，再保存确认；不把步骤伪装成跨文件事务。

    Synchronize the real report before acknowledging it, without claiming a transaction.
    """
    target = tasks.record_report(log.session_id, result.seq)
    sessions.append(
        log,
        ProgressSynced(
            result_seq=result.seq,
            task_id=target.task_id if target else None,
            task_revision=target.revision if target else None,
        ),
        None,
    )


@pytest.mark.parametrize("terminal", ["completed", "cancelled"])
def test_ended_goal_is_history_for_followup_and_after_reload(records, terminal):
    """终态目标只作历史，新请求与工具配对保留，重载不重写原日志。

    Ended goals become history while preserving new requests, tool pairs and durable facts.
    """
    sessions, log, tasks, task = records
    journal = GoalJournal(sessions)
    goal = make_goal(journal, log)
    run_id, message_id = start_run(sessions, log, task, goal)
    call = ToolCall(tool_call_id="observed", name="list_files", arguments={})
    commit_turn(sessions, log, run_id, message_id, call=call)
    sessions.append(log, ToolStarted(call=call), run_id)
    if terminal == "cancelled":
        journal.control(
            log,
            GoalControl(
                goal_id=goal.goal_id,
                operation_id=str(uuid4()),
                expected_revision=states(log.facts)[goal.goal_id].revision,
                action="cancel",
            ),
        )
    sessions.append(
        log,
        ToolCompleted(
            result=ToolResult(tool_call_id=call.tool_call_id, content="[]", is_error=False)
        ),
        run_id,
    )
    report = WorkReport(summary="Observed the existing files", outcome="complete")
    end = finish(sessions, log, run_id, report)
    sync_report(sessions, log, tasks, end)
    journal.settle(log, GoalSettled(goal_id=goal.goal_id, result_seq=end.seq))
    chat, message = start_run(sessions, log, task)
    commit_turn(sessions, log, chat, message, text="Answer only the new question")
    finish(sessions, log, chat)
    original = sessions.path(log.session_id).read_bytes()
    restored = sessions.load(log.session_id)
    context, complete = restored.context()
    assert complete
    assert f"Historical local goal ({terminal})" in context[0]["content"]
    assert goal.objective in context[0]["content"]
    assert f"Historical work request for a {terminal} goal" in context[1]["content"]
    assert context[2]["role"] == "assistant" and context[3]["role"] == "tool"
    assert context[-2] == {"role": "user", "content": "Work within the request"}
    assert context[-1]["content"] == "Answer only the new question"
    page, _ = entries(restored, None)
    historical = [item for item in page if item.goal_result is not None]
    assert len(historical) == 1
    assert historical[0].goal_result.status == terminal
    assert historical[0].goal_result.last_report == report
    assert SessionReader(sessions).view(log.session_id, None, str(uuid4())).entries == page
    assert sessions.path(log.session_id).read_bytes() == original


def test_budget_edit_survives_settlement_but_not_another_control(records):
    """暂停后的结算不拦预算保存，另一用户控制仍阻止旧版本覆盖。

    A pause settlement permits budget saving, while another user control rejects stale edits.
    """
    sessions, log, _, task = records
    journal = GoalJournal(sessions)
    goal = make_goal(journal, log)
    run_id, _ = start_run(sessions, log, task, goal)
    journal.control(
        log,
        GoalControl(
            goal_id=goal.goal_id, operation_id=str(uuid4()), expected_revision=2, action="pause"
        ),
    )
    result = finish(sessions, log, run_id, status="cancelled")
    journal.settle(log, GoalSettled(goal_id=goal.goal_id, result_seq=result.seq))
    control = GoalControl(
        goal_id=goal.goal_id,
        operation_id=str(uuid4()),
        expected_revision=3,
        action="budget",
        budget=GoalBudget(max_requests=4),
    )
    journal.control(log, control)
    with pytest.raises(AgentError) as conflict:
        journal.control(log, control.model_copy(update={"operation_id": str(uuid4())}))
    assert conflict.value.code == "GOAL_VERSION_CONFLICT"
    saved = states(sessions.load(log.session_id).facts)[goal.goal_id]
    assert saved.status == "paused" and saved.budget.max_requests == 4
    assert usage(log.facts, goal.goal_id).requests == 1


def test_goal_answer_failure_and_cumulative_budget(records):
    """HITL 精确答复、普通问答不接续失败目标，跨 Run 预算不清零。

    Require exact answers, keep failed goals stopped during chat, and retain cumulative budgets.
    """
    sessions, log, tasks, task = records
    journal = GoalJournal(sessions)
    goal = make_goal(journal, log)
    size = len(log.facts)
    journal.create(log, goal)
    assert len(log.facts) == size
    with pytest.raises(AgentError) as conflict:
        journal.create(log, goal.model_copy(update={"objective": "smaller target"}))
    assert conflict.value.code == "OPERATION_CONFLICT"
    run_id, message_id = start_run(sessions, log, task, goal)
    call = ToolCall(tool_call_id="check", name="run_command", arguments={})
    commit_turn(sessions, log, run_id, message_id, call=call)
    sessions.append(log, ToolStarted(call=call), run_id)
    observed = sessions.append(
        log,
        ToolCompleted(
            result=ToolResult(
                tool_call_id="check",
                is_error=False,
                content=json.dumps(
                    {
                        "summary": {
                            "kind": "command",
                            "status": "exited",
                            "exit_code": 7,
                        }
                    }
                ),
            )
        ),
        run_id,
    )
    # 执行结果保留原始退出码；报告不再增加第二套“成功证据”判定。
    # Keep the actual exit code without a second report-time success classifier.
    assert json.loads(observed.data.result.content)["summary"]["exit_code"] == 7
    question = HumanQuestion(
        question_id=str(uuid4()),
        question="Repair this failure?",
        impact="The check ran but did not pass",
        options=["Report only", "Repair"],
    )
    report = WorkReport(
        summary="The command returned 7; no repair started",
        outcome="wait",
        criteria=[
            CriterionResult(
                criterion_id="page",
                status="needs_user",
                explanation="Await the requested decision",
                evidence=[reference(observed, "tool_result")],
            )
        ],
        question=question,
    )
    end = finish(sessions, log, run_id, report)
    with pytest.raises(AgentError) as unsynced:
        journal.settle(log, GoalSettled(goal_id=goal.goal_id, result_seq=end.seq))
    assert unsynced.value.code == "GOAL_PROGRESS_PENDING"
    sync_report(sessions, log, tasks, end)
    journal.settle(log, GoalSettled(goal_id=goal.goal_id, result_seq=end.seq))
    state = states(log.facts)[goal.goal_id]
    assert state.status == "waiting"
    assert state.definition.objective == goal.objective
    for action, fields, expected in (
        ("resume", {}, "GOAL_NEEDS_ANSWER"),
        ("answer", {"question_id": str(uuid4()), "answer": "yes"}, "GOAL_QUESTION_MISMATCH"),
    ):
        with pytest.raises(AgentError) as rejected:
            journal.control(
                log,
                GoalControl(
                    goal_id=goal.goal_id,
                    operation_id=str(uuid4()),
                    expected_revision=state.revision,
                    action=action,
                    **fields,
                ),
            )
        assert rejected.value.code == expected
    chat, msg = start_run(sessions, log, task)
    commit_turn(sessions, log, chat, msg, text="Answer an unrelated question")
    finish(sessions, log, chat)
    assert states(log.facts)[goal.goal_id].status == "waiting"
    answer = GoalControl(
        goal_id=goal.goal_id,
        operation_id=str(uuid4()),
        expected_revision=state.revision,
        action="answer",
        question_id=question.question_id,
        answer="Report only",
    )
    journal.control(log, answer)
    journal.control(log, answer)
    run2, msg2 = start_run(sessions, log, task, goal)
    # 实际调用失败，没有完整 assistant；不能借普通问题重启原目标。
    # A failed request has no assistant commit; ordinary chat must not restart the goal.
    end2 = finish(sessions, log, run2, status="failed", elapsed=2.0)
    journal.settle(log, GoalSettled(goal_id=goal.goal_id, result_seq=end2.seq))
    chat2, msg3 = start_run(sessions, log, task)
    commit_turn(sessions, log, chat2, msg3)
    finish(sessions, log, chat2)
    assert states(log.facts)[goal.goal_id].status == "failed"
    consumed = usage(log.facts, goal.goal_id)
    assert (consumed.requests, consumed.tools, consumed.active_seconds) == (2, 1, 3.5)
    assert consumed.input_tokens is None
    with pytest.raises(AgentError) as exhausted:
        check_budget(goal.budget, consumed, requests=1)
    assert exhausted.value.code == "BUDGET_GOAL_REQUESTS"
    current = states(log.facts)[goal.goal_id]
    journal.control(
        log,
        GoalControl(
            goal_id=goal.goal_id,
            operation_id=str(uuid4()),
            expected_revision=current.revision,
            action="budget",
            budget=GoalBudget(max_requests=4),
        ),
    )
    assert usage(log.facts, goal.goal_id) == consumed
    journal.control(
        log,
        GoalControl(
            goal_id=goal.goal_id,
            operation_id=str(uuid4()),
            expected_revision=states(log.facts)[goal.goal_id].revision,
            action="resume",
        ),
    )
    run3, msg4 = start_run(sessions, log, task, goal)
    answer_fact = commit_turn(
        sessions, log, run3, msg4, text="Reported the observed failure as requested"
    )
    met = CriterionResult(
        criterion_id="page",
        status="met",
        explanation="Report delivered",
        evidence=[reference(answer_fact)],
    )
    final = finish(
        sessions,
        log,
        run3,
        WorkReport(
            summary="Observed result reported",
            outcome="complete",
            criteria=[met.model_copy(update={"criterion_id": "model-label", "evidence": []})],
        ),
    )
    sync_report(sessions, log, tasks, final)
    journal.settle(log, GoalSettled(goal_id=goal.goal_id, result_seq=final.seq))
    assert views(sessions.load(log.session_id).facts)[0].status == "completed"
    assert states(log.facts)[goal.goal_id].definition.criteria == goal.criteria
    assert tasks.get(task.task_id).fields.status == "active"


def test_interruption_pairing_and_missing_time_remain_explicit(records):
    """控制穿插不破坏配对；重启不显示活跃或把离线时间伪造成已工作。

    Interleaved controls preserve pairing; restart cannot invent active work or offline duration.
    """
    sessions, log, _, task = records
    journal = GoalJournal(sessions)
    prefix = sessions.path(log.session_id).read_bytes()
    goal = make_goal(journal, log)
    run_id, message_id = start_run(sessions, log, task, goal)
    call = ToolCall(tool_call_id="read", name="list_files", arguments={})
    commit_turn(sessions, log, run_id, message_id, call=call)
    sessions.append(log, ToolStarted(call=call), run_id)
    with pytest.raises(AgentError):
        sessions.append(log, ToolStarted(call=call), run_id)
    revision = states(log.facts)[goal.goal_id].revision
    journal.control(
        log,
        GoalControl(
            goal_id=goal.goal_id,
            operation_id=str(uuid4()),
            expected_revision=revision,
            action="pause",
        ),
    )
    with pytest.raises(AgentError) as busy:
        journal.control(
            log,
            GoalControl(
                goal_id=goal.goal_id,
                operation_id=str(uuid4()),
                expected_revision=revision + 1,
                action="resume",
            ),
        )
    assert busy.value.code == "GOAL_RUN_BUSY"
    sessions.append(
        log,
        ToolCompleted(result=ToolResult(tool_call_id="read", content="[]", is_error=False)),
        run_id,
    )
    end = finish(sessions, log, run_id, status="cancelled")
    journal.settle(log, GoalSettled(goal_id=goal.goal_id, result_seq=end.seq))
    assert log.context()[1]
    journal.control(
        log,
        GoalControl(
            goal_id=goal.goal_id,
            operation_id=str(uuid4()),
            expected_revision=states(log.facts)[goal.goal_id].revision,
            action="resume",
        ),
    )
    run2, _ = start_run(sessions, log, task, goal)
    reopened = sessions.load(log.session_id)
    view = views(reopened.facts)[0]
    assert view.status == "interrupted"
    assert view.usage.uncertain_run_ids == [run2]
    assert view.usage.active_seconds == 1.5
    assert view.usage.reserved_seconds == 28.5
    live = views(log.facts, live_goals={goal.goal_id}, live_seconds={run2: 2.25})[0]
    assert live.status == "active" and live.usage.active_seconds == 3.75
    assert live.usage.reserved_seconds == 0
    assert sessions.path(log.session_id).read_bytes().startswith(prefix)
    with pytest.raises(AgentError) as unconfirmed:
        finish(sessions, reopened, run2)
    assert unconfirmed.value.code == "RUN_RESULT_UNCONFIRMED"
    interrupted = finish(sessions, reopened, run2, status="interrupted", elapsed=None)
    assert journal.pending_results(reopened, goal.goal_id) == {interrupted.seq}
    journal.settle(reopened, GoalSettled(goal_id=goal.goal_id, result_seq=interrupted.seq))
    assert states(reopened.facts)[goal.goal_id].status == "interrupted"
    assert usage(reopened.facts, goal.goal_id).uncertain_run_ids == [run2]


def test_task_report_sync_keeps_history_without_proof_or_graph_gates(records, monkeypatch):
    """报告引用和图仅作进度信息，最新报告不覆盖用户字段或丢失旧版本。

    Treat references and graphs as progress, preserving user fields and every prior report.
    """
    import my_agent.tasks.store as task_module

    sessions, log, tasks, task = records
    run, message = start_run(sessions, log, task)
    observed = commit_turn(sessions, log, run, message)
    evidence = reference(observed)
    items = [
        WorkItem(
            work_id="discuss",
            title="Discuss",
            scope="Current request",
            status="completed",
            evidence=[evidence],
        ),
        WorkItem(
            work_id="implement",
            title="Implement",
            scope="Approved scope",
            status="planned",
            depends_on=["discuss"],
        ),
    ]
    bogus = evidence.model_copy(update={"seq": 999})
    report = WorkReport(
        summary="Progress with an unverified model reference",
        outcome="return",
        work_items=[items[0].model_copy(update={"evidence": [bogus]}), items[1]],
    )
    end = finish(sessions, log, run, report)
    saved = sessions.path(log.session_id).read_bytes()
    actual_write = task_module.atomic_write

    def unavailable(path, content):
        """模拟任务保存失败，运行事实保持真实。

        Fail task saving while retaining the real run facts.
        """
        raise AgentError("SAVE_FAILED", "simulated")

    monkeypatch.setattr(task_module, "atomic_write", unavailable)
    with pytest.raises(AgentError):
        tasks.record_report(log.session_id, end.seq)
    assert tasks.get(task.task_id).revision == 1
    assert sessions.path(log.session_id).read_bytes() == saved
    monkeypatch.setattr(task_module, "atomic_write", actual_write)
    synced = tasks.record_report(log.session_id, end.seq)
    assert synced is not None and synced.revision == 2
    assert tasks.record_report(log.session_id, end.seq).revision == 2
    assert synced.fields == task.fields and synced.fields.status == "active"
    assert synced.work.items[0].source.seq == end.seq
    assert synced.work.items[0].item.evidence == [bogus]
    assert sessions.path(log.session_id).read_bytes() == saved
    current = tasks.update(
        UpdateTaskParams(
            task_id=task.task_id,
            operation_id=str(uuid4()),
            expected_revision=2,
            fields=TaskFields(
                title="User correction", goal=task.fields.goal, decisions="User confirmed"
            ),
        )
    )
    # 仅共同文字改变时，旧工作基线仍可合并；用户结论保持原样。
    # Shared-text changes can merge against unchanged work while preserving user decisions.
    run2, msg2 = start_run(sessions, log, synced)
    actual2 = commit_turn(sessions, log, run2, msg2)
    updated = items[1].model_copy(update={"status": "completed", "evidence": [reference(actual2)]})
    end2 = finish(
        sessions,
        log,
        run2,
        WorkReport(summary="Implementation reported", outcome="return", work_items=[updated]),
    )
    second = tasks.record_report(log.session_id, end2.seq)
    assert second.fields == current.fields and second.revision == 4
    run3, msg3 = start_run(sessions, log, synced)
    commit_turn(sessions, log, run3, msg3)
    end3 = finish(
        sessions,
        log,
        run3,
        WorkReport(
            summary="Latest plan with incomplete dependencies",
            outcome="return",
            work_items=[
                items[0].model_copy(update={"depends_on": ["implement"]}),
                items[1].model_copy(update={"depends_on": ["discuss", "later-item"]}),
            ],
        ),
    )
    third = tasks.record_report(log.session_id, end3.seq)
    assert third.revision == 5 and third.fields == current.fields
    assert third.work.items[1].item.status == "planned"
    assert tasks.history(task.task_id)[3].view.work.items[1].item.status == "completed"
    assert tasks.get(task.task_id).work == third.work
