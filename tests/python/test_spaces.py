"""M5 空间服务的隔离持久化与既有协作验证，不调用外网模型。

Isolated M5 space persistence and existing collaboration checks without live models.
"""

import asyncio
from uuid import uuid4

from my_agent.errors import AgentError
from my_agent.sessions.types import RequestStarted
from tests.python.test_collaboration import finish
from tests.python.test_goal_controller import app_at, create_session
from tests.python.test_tasks import ContextModel


def team():
    """构造两个完整成员，连线保持可选。 Build two full members with optional relationships."""
    implementer, reviewer = str(uuid4()), str(uuid4())
    return {
        "organisation": "peer",
        "receiver_member_id": implementer,
        "members": [
            {
                "member_id": implementer,
                "name": "Implementation",
                "role": "Implementer",
                "scope": "Build the requested page",
                "model_id": "glm-5.3-flash",
                "position": {"x": -25.5, "y": 80},
            },
            {
                "member_id": reviewer,
                "name": "Review",
                "role": "Reviewer",
                "scope": "Review the existing page",
                "model_id": "deepseek-v4.1-flash",
                "position": {"x": 420, "y": 180.5},
            },
        ],
        "edges": [],
    }


async def save_team(app, task_id, config):
    """使用正式 RPC 保存草稿，不绕过协议。 Save a draft through the production RPC boundary."""
    result = await app.dispatch(
        "spaces.save", {"task_id": task_id, "expected_revision": None, "config": config}
    )
    assert result.space is not None
    return result.space


def test_draft_and_legacy_task_restore_without_creating_sessions(tmp_path):
    """旧任务不自动迁移，草稿与布局保存不创建会话或执行模型。

    Do not migrate legacy tasks or create sessions/model requests when saving a draft and layout.
    """

    async def scenario():
        """真实存储重启并核对原任务、会话和项目内容。

        Restart actual storage and preserve the original task, session and project contents.
        """
        model = ContextModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            task_id = created.task.task_id
            task_path = app.tasks.store.path(task_id)
            task_before = task_path.read_bytes()
            sessions_root = tmp_path / "data" / "sessions"
            before = set(sessions_root.iterdir())
            missing = await app.dispatch("spaces.get", {"task_id": task_id})
            assert missing.space is None
            assert not (tmp_path / "data" / "spaces" / f"{task_id}.json").exists()
            config = team()
            source, target = [member["member_id"] for member in config["members"]]
            config["edges"] = [
                {
                    "edge_id": str(uuid4()),
                    "source_member_id": source,
                    "target_member_id": target,
                    "kind": "delegate",
                    "label": "Implement and return feedback",
                },
                {
                    "edge_id": str(uuid4()),
                    "source_member_id": target,
                    "target_member_id": source,
                    "kind": "feedback",
                    "label": "Review feedback",
                },
            ]
            saved = await save_team(app, task_id, config)
            stored_config = saved.config
            config["members"][0]["name"] = "Unsaved local member draft"
            saved = (
                await app.dispatch(
                    "spaces.layout",
                    {
                        "task_id": task_id,
                        "layout": {
                            "graph_open": False,
                            "viewport": {"x": -120, "y": 48.5, "zoom": 0.75},
                        },
                    },
                )
            ).space
            assert saved.config == stored_config
            assert not saved.layout.graph_open
            assert saved.layout.viewport.zoom == 0.75
            assert all(binding.session_id is None for binding in saved.bindings)
            assert set(sessions_root.iterdir()) == before
            assert task_path.read_bytes() == task_before
            assert not model.inputs and not app.sessions.active_runs
            assert list((tmp_path / "project").iterdir()) == []
        async with app_at(tmp_path / "data", model) as app:
            restored = (await app.dispatch("spaces.get", {"task_id": task_id})).space
            assert restored == saved
            assert set(sessions_root.iterdir()) == before
            assert task_path.read_bytes() == task_before
            assert not model.inputs and not app.sessions.active_runs

    asyncio.run(scenario())


def test_partial_start_persists_and_reuses_created_sessions_after_restart(tmp_path, monkeypatch):
    """会话已写入但组建未完成时保留部分结果，重启后显式接续不重复创建。

    Preserve partial assembly after a session write; reuse it on explicit restart continuation.
    """

    async def scenario():
        """只在真实会话创建后的边界注入一次失败。

        Inject a single failure after the actual session creation boundary.
        """
        model = ContextModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            task_id = created.task.task_id
            await save_team(app, task_id, team())
            original = app.sessions.create

            async def fail_after_create(*args, **kwargs):
                """保留真正写好的会话，模拟后续调用未返回成功。

                Keep the real saved session and simulate a missing successful return.
                """
                result = await original(*args, **kwargs)
                if kwargs.get("role") == "Reviewer":
                    raise AgentError("SESSION_SAVE_FAILED", "Simulated post-save failure")
                return result

            with monkeypatch.context() as patch:
                patch.setattr(app.sessions, "create", fail_after_create)
                partial = (await app.dispatch("spaces.start", {"task_id": task_id})).space
            assert partial is not None
            assert len([item for item in partial.bindings if item.session_id]) == 1
            assert any(item.error for item in partial.bindings)
            sessions_root = tmp_path / "data" / "sessions"
            session_ids = {item.name for item in sessions_root.iterdir()}
            assert len(session_ids) == 3
            assert not model.inputs and not app.sessions.active_runs
        async with app_at(tmp_path / "data", model) as app:
            restored = (await app.dispatch("spaces.get", {"task_id": task_id})).space
            assert restored == partial
            complete = (await app.dispatch("spaces.start", {"task_id": task_id})).space
            assert complete is not None and complete.error is None
            assert all(item.session_id and item.error is None for item in complete.bindings)
            assert {item.name for item in sessions_root.iterdir()} == session_ids
            identities = [item.session_id for item in complete.bindings]
            selected_id = identities[0]
            await app.sessions.select_model(selected_id, str(uuid4()), "deepseek-v4.1-flash")
            skill_params = {"project_id": created.task.project_id, "session_id": selected_id}
            await app.dispatch("skills.select", {**skill_params, "selected": ["builtin:plan"]})
            graph_config = complete.config.model_dump(mode="json")
            graph_config["members"][0]["position"] = {"x": 66, "y": 77}
            await app.dispatch(
                "spaces.save",
                {
                    "task_id": task_id,
                    "expected_revision": complete.revision,
                    "config": graph_config,
                },
            )
            repeated = (await app.dispatch("spaces.start", {"task_id": task_id})).space
            assert [item.session_id for item in repeated.bindings] == identities
            assert (await app.sessions.view(selected_id)).summary.model_id == "deepseek-v4.1-flash"
            assert (await app.dispatch("skills.list", skill_params)).selected == ["builtin:plan"]
            assert {item.name for item in sessions_root.iterdir()} == session_ids
            assert not model.inputs and not app.sessions.active_runs

    asyncio.run(scenario())


def test_rebinding_retains_history_provenance_and_collaboration_without_graph_edges(tmp_path):
    """换绑保留稳定成员和旧执行来源；未画边成员仍可通过既有服务互访。

    Keep stable members and old run provenance on rebinding; unlinked graph nodes can access peers.
    """

    async def scenario():
        """用离线回合核对当前职责及换绑后的材料，不调用真实模型。

        Check current duties and post-rebinding materials with offline turns, never live models.
        """
        model = ContextModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            task_id = created.task.task_id
            draft = await save_team(app, task_id, team())
            started = (await app.dispatch("spaces.start", {"task_id": task_id})).space
            assert started is not None
            source, peer = started.bindings
            old_id, peer_id = source.session_id, peer.session_id
            assert old_id and peer_id
            assert not started.config.edges and not model.inputs
            config = started.config.model_dump(mode="json")
            config["members"][0]["role"] = "Updated implementation duties"
            updated = (
                await app.dispatch(
                    "spaces.save",
                    {
                        "task_id": task_id,
                        "expected_revision": started.revision,
                        "config": config,
                    },
                )
            ).space
            await app.sessions.start(old_id, str(uuid4()), "Saved implementation result", None)
            await finish(app, old_id)
            assert "Updated implementation duties" in model.inputs[0][0]["content"]
            request = next(
                fact.data
                for fact in app.sessions.store.load(old_id).facts
                if isinstance(fact.data, RequestStarted)
            )
            materials = [item for item in request.context.materials if item.kind == "space"]
            assert len(materials) == 1
            assert materials[0].source_id == task_id and materials[0].revision == updated.revision
            prior = await app.sessions.view(old_id)
            history = await app.dispatch(
                "collaboration.history",
                {"source_session_id": peer_id, "target_session_id": old_id},
            )
            assert history.summary.run.run_id == prior.summary.run.run_id
            assert any(getattr(entry, "text", None) == "known" for entry in history.entries)
            old_path = tmp_path / "data" / "sessions" / old_id / "events.jsonl"
            old_bytes = old_path.read_bytes()
            params = {
                "task_id": task_id,
                "member_id": source.member_id,
                "session_id": None,
                "operation_id": str(uuid4()),
            }
            replaced = (await app.dispatch("spaces.bind", params)).space
            binding = next(item for item in replaced.bindings if item.member_id == source.member_id)
            new_id = binding.session_id
            assert new_id and new_id != old_id
            assert binding.session_ids == [old_id, new_id]
            assert replaced.config.members == updated.config.members
            assert replaced.config.members[0].member_id == draft.config.members[0].member_id
            again = (await app.dispatch("spaces.bind", params)).space
            assert (
                next(item for item in again.bindings if item.member_id == source.member_id)
                == binding
            )
            assert old_path.read_bytes() == old_bytes
            assert (await app.sessions.view(old_id)).summary.run.run_id == prior.summary.run.run_id
            accessible = await app.dispatch(
                "collaboration.history",
                {"source_session_id": peer_id, "target_session_id": new_id},
            )
            assert accessible.summary.session_id == new_id
            assert len(model.inputs) == 1
            await app.sessions.start(old_id, str(uuid4()), "Continue the old conversation", None)
            await finish(app, old_id)
            assert '"current_member"' not in model.inputs[-1][0]["content"]
            old_requests = [
                fact.data
                for fact in app.sessions.store.load(old_id).facts
                if isinstance(fact.data, RequestStarted)
            ]
            assert not any(item.kind == "space" for item in old_requests[-1].context.materials)
            assert old_path.read_bytes().startswith(old_bytes)
            old_bytes = old_path.read_bytes()
        async with app_at(tmp_path / "data", model) as app:
            restored = (await app.dispatch("spaces.get", {"task_id": task_id})).space
            restored_binding = next(
                item for item in restored.bindings if item.member_id == source.member_id
            )
            assert restored_binding == binding
            restored_history = await app.dispatch(
                "collaboration.history",
                {"source_session_id": peer_id, "target_session_id": old_id},
            )
            assert any(
                getattr(entry, "run_id", None) == prior.summary.run.run_id
                for entry in restored_history.entries
            )
            assert old_path.read_bytes() == old_bytes
            assert len(model.inputs) == 2 and not app.sessions.active_runs

    asyncio.run(scenario())
