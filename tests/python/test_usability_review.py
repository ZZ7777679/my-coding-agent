"""复核调研中的开关持久化与搜索诊断，使用隔离服务。

Verify persisted delegation settings and search evidence using isolated services.
"""

import asyncio
import json
from uuid import uuid4

import pytest

from my_agent.delegation.types import WorkerSettings
from my_agent.errors import AgentError
from my_agent.memory.types import MemoryFields, MemoryQuery
from my_agent.models.native_search import search_result
from tests.python.test_delegation import WorkerModel, setup
from tests.python.test_goal_controller import app_at, call, turn


def test_disabled_worker_reports_setting_and_preserves_switch_after_restart(tmp_path):
    """未开启是可修正状态，开启后重启不会复位或自行启动工作。

    Disabled delegation is recoverable; enabling survives restart without starting work.
    """

    class Model(WorkerModel):
        """故意调用未开启能力以验证真实工具反馈。 Call disabled delegation deliberately."""

        async def complete(self, **kwargs):
            """第二次请求能读到具体原因而非被终止。 Observe the reason in the following request."""
            self.requests.append(kwargs)
            if len(self.requests) == 1:
                return turn(call("spawn_worker", objective="Read docs"))
            value = json.loads(kwargs["messages"][-1]["content"])
            assert value["code"] == "WORKERS_DISABLED"
            assert "Agent" in value["remediation"]
            return turn(text="The switch is off; no worker was started.")

    async def scenario():
        """保存真实设置并重新装配服务。 Persist settings and reconstruct the service."""
        model = Model()
        async with app_at(tmp_path / "data", model) as app:
            await setup(app, model, tmp_path / "project")
            sid = model.owner
            await app.sessions.start(sid, str(uuid4()), "Try delegation", None)
            await asyncio.wait_for(asyncio.shield(app.sessions.active_for(sid).task), 8)
            assert (await app.sessions.view(sid)).summary.run.status == "completed"
            assert not (await app.sessions.delegations.page(sid)).workers
            await app.sessions.delegations.configure(
                sid, WorkerSettings(enabled=True, concurrency=5)
            )
        async with app_at(tmp_path / "data", model) as app:
            page = await app.sessions.delegations.page(sid)
            assert page.settings == WorkerSettings(enabled=True, concurrency=5)
            assert not page.workers and not app.sessions.active_runs

    asyncio.run(scenario())


@pytest.mark.parametrize("failed", [False, True])
def test_native_search_keeps_observed_failure_without_claiming_cause(failed):
    """空结果协议与服务明确拒绝分别保留证据，不保存正文／凭据。

    Distinguish absent result blocks from explicit provider errors without storing prose/secrets.
    """
    content = (
        [
            {
                "type": "web_search_tool_result",
                "content": {
                    "type": "web_search_tool_result_error",
                    "error_code": "max_uses_exceeded",
                },
            }
        ]
        if failed
        else [{"type": "text", "text": "private response not for diagnostics"}]
    )
    with pytest.raises(AgentError) as caught:
        search_result(
            {"id": "test-response", "stop_reason": "end_turn", "content": content},
            "docs",
            "deepseek-flash",
        )
    error = caught.value
    assert error.phase == "response_body"
    assert error.details["model_id"] == "deepseek-flash"
    assert "web_fetch" in error.remediation
    assert "private response" not in str(error.details)
    if failed:
        assert error.cause_code == "max_uses_exceeded"
    else:
        assert error.cause_code is None
        assert error.details["block_types"] == ["text"]
        assert error.details["search_uses"] == 0


def test_old_capability_claims_remain_searchable_without_automatic_injection(tmp_path):
    """旧模型能力自述不污染请求，用户选择和正常知识仍可召回。

    Keep historical claims searchable while preserving explicit choices and ordinary recall.
    """

    class Model(WorkerModel):
        """只记录实际组装材料。 Record the actual assembled request."""

        async def complete(self, **kwargs):
            """不派发额外工具。 Return without dispatching further tools."""
            self.requests.append(kwargs)
            return turn(text="Use current tool evidence.")

    async def scenario():
        """通过真实存储、检索和请求链验证，不改个人记录。

        Verify real storage, retrieval and request assembly without personal data.
        """
        model = Model()
        async with app_at(tmp_path / "data", model) as app:
            created = await setup(app, model, tmp_path / "project")
            sid = model.owner
            memory = app.sessions.memory
            pid = created.session.project_id
            historical = memory.store.save(
                pid,
                MemoryFields(
                    title="Token tools", content="obsolete-token-claim", category="capabilities"
                ),
                source="maintenance",
            )
            for content, category, source, pinned in [
                ("user-token-choice", "capabilities", "user", False),
                ("pinned-token-choice", "capabilities", "agent", True),
                ("normal-token-knowledge", "fact", "maintenance", False),
            ]:
                memory.store.save(
                    pid,
                    MemoryFields(
                        title="Token tools", content=content, category=category, pinned=pinned
                    ),
                    source=source,
                )
            await app.sessions.start(sid, str(uuid4()), "Token tools", None)
            await asyncio.wait_for(asyncio.shield(app.sessions.active_for(sid).task), 8)
            material = json.dumps(model.requests[-1]["messages"])
            assert "obsolete-token-claim" not in material
            for value in ("user-token-choice", "pinned-token-choice", "normal-token-knowledge"):
                assert value in material
            page = await memory.page(sid, MemoryQuery(query="Token"))
            assert historical.memory_id in {entry.memory_id for entry in page.entries}
            assert list(page.recall_notes) == [historical.memory_id]
            assert memory.store.read(historical.memory_id, pid).enabled

    asyncio.run(scenario())
