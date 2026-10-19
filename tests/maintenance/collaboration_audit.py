"""协作审查的隔离观察器，不把缺陷断言成健康行为。

Observe collaboration review cases without treating known defects as acceptance criteria.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from my_agent.errors import AgentError
from my_agent.sessions.types import RunAccepted, ToolCompleted
from my_agent.spaces.team_types import SpaceChatMessage
from tests.python.test_collaboration import finish, pair
from tests.python.test_goal_controller import app_at, call, create_session, definition, turn
from tests.python.test_spaces import save_team, team
from tests.python.test_work_graph import WorkModel, wait_goal


async def observe_errors(root: Path) -> list[dict[str, object]]:
    """通过真实工具调用观察未安排协作对 Run 与 Goal 的影响。

    Observe unarranged peer calls through real tools and Run/Goal controllers.
    """
    results: list[dict[str, object]] = []
    for use_goal in (False, True):
        case = root / ("goal" if use_goal else "run")
        case.mkdir()
        model = WorkModel()
        async with app_at(case / "data", model) as app:
            source, target = await pair(app, case / "project")
            model.steps = [
                turn(call("request_collaboration", target_session_id=target, objective="Review")),
                turn(text="No agreement: report the issue and finish this request"),
            ]
            if use_goal:
                await app.sessions.goals.create(source, definition(max_requests=2))
                await wait_goal(app, source)
            else:
                await app.sessions.start(source, str(uuid4()), "Ask the reviewer", None)
                await finish(app, source)
            view = await app.sessions.view(source)
            log = await app.worker.call(app.sessions.store.load, source)
            outputs = [
                json.loads(fact.data.result.content)
                for fact in log.facts
                if isinstance(fact.data, ToolCompleted)
            ]
            results.append(
                {
                    "scenario": "unarranged_peer_goal" if use_goal else "unarranged_peer_run",
                    "model_calls": len(model.requests),
                    "run_status": view.summary.run.status,
                    "run_code": view.summary.run.code,
                    "goal_status": (await app.sessions.goals.list(source))[-1].status
                    if use_goal
                    else None,
                    "tool_outputs": outputs,
                }
            )
    return results


async def observe_graph(root: Path) -> dict[str, object]:
    """核对生成节点删除、长输入及群聊存储容量；不调用真实模型。

    Inspect generated-node removal, long input and chat capacity without live models.
    """
    case = root / "graph"
    case.mkdir()
    model = WorkModel()
    async with app_at(case / "data", model) as app:
        created = await create_session(app, case / "project")
        task_id = created.task.task_id
        config = team()
        owner = config["members"][0]["member_id"]
        config["initial_work_items"] = [
            {
                "work_id": "generated-item",
                "title": "Generated item",
                "scope": "Review this item",
                "status": "planned",
                "method": "review",
                "stage_id": "review",
            }
        ]
        await save_team(app, task_id, config)
        graph = await app.dispatch("spaces.work_graph", {"task_id": task_id})
        removed = await app.dispatch(
            "spaces.work_graph_save",
            {
                "task_id": task_id,
                "operation_id": str(uuid4()),
                "expected_revision": graph.task.revision,
                "items": [],
            },
        )
        await app.dispatch(
            "spaces.work_graph_save",
            {
                "task_id": task_id,
                "operation_id": str(uuid4()),
                "expected_revision": removed.task.revision,
                "items": config["initial_work_items"],
            },
        )
        await app.dispatch("spaces.start", {"task_id": task_id})
        space = (await app.dispatch("spaces.get", {"task_id": task_id})).space
        session_id = next(b.session_id for b in space.bindings if b.member_id == owner)
        before = await app.worker.call(app.tasks.store.get, task_id)
        error: dict[str, object] | None = None
        try:
            await app.dispatch(
                "spaces.work_graph_start",
                {
                    "task_id": task_id,
                    "operation_id": str(uuid4()),
                    "work_ids": ["generated-item"],
                    "member_id": owner,
                    "instruction": "x" * 16000,
                },
            )
        except ValidationError as exc:
            error = {
                "type": type(exc).__name__,
                "details": exc.errors(include_input=False, include_url=False),
            }
        except AgentError as exc:
            error = {"code": exc.code, "message": exc.message}
        await finish(app, session_id)
        after = await app.worker.call(app.tasks.store.get, task_id)
        review_item = config["initial_work_items"][0]
        model.steps = [
            turn(
                call(
                    "report_work",
                    summary="Review needs a second pass",
                    outcome="continue",
                    next_action="Continue the same read-only review",
                    work_items=[review_item],
                )
            ),
            turn(call("report_work", summary="Review finished", outcome="complete")),
        ]
        await app.dispatch(
            "spaces.work_graph_start",
            {
                "task_id": task_id,
                "operation_id": str(uuid4()),
                "work_ids": ["generated-item"],
                "member_id": owner,
                "continuous": True,
            },
        )
        await wait_goal(app, session_id)
        log = await app.worker.call(app.sessions.store.load, session_id)
        review_modes = [fact.data.mode for fact in log.facts if isinstance(fact.data, RunAccepted)]
        record = await app.worker.call(app.team.store.chat, task_id)
        for index in range(100):
            record.view.messages.append(
                SpaceChatMessage(
                    message_id=str(uuid4()),
                    content="\u5ba1" * 15000,
                    mode="normal",
                    target_member_ids=[owner],
                    created_at=f"2026-10-19T00:00:{index % 60:02d}Z",
                )
            )
        capacity_error = None
        try:
            await app.worker.call(app.team.store.save_chat, record)
        except AgentError as exc:
            capacity_error = {"code": exc.code, "message": exc.message}
        return {
            "scenario": "graph_edit_and_limits",
            "items_before_remove": [item.work_id for item in graph.items],
            "saved_planned_items": [item.work_id for item in removed.task.work.planned_items],
            "items_after_remove": [item.work_id for item in removed.items],
            "long_instruction_chars": 16000,
            "start_error": error,
            "stage_before": before.workflow.session_stages.get(session_id),
            "stage_after": after.workflow.session_stages.get(session_id),
            "review_continuation_modes": review_modes,
            "fake_model_calls_including_review": len(model.requests),
            "capacity_message_count": len(record.view.messages),
            "capacity_error": capacity_error,
        }


async def main() -> None:
    """所有测试数据和报告写入独立产物目录。

    Keep all scenario data and the report under an isolated artifact directory.
    """
    artifacts = Path(__file__).resolve().parents[2] / ".artifacts" / "tests"
    artifacts.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="collaboration-audit-", dir=artifacts))
    results: list[object] = await observe_errors(root)
    results.append(await observe_graph(root))
    report = root / "report.json"
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
