"""技能覆盖、引用与请求材料。 Skill precedence, references and request materials."""

import asyncio
from pathlib import Path

import pytest

from my_agent.context.store import ContextStore
from my_agent.context.types import HistoryParams
from my_agent.errors import AgentError
from my_agent.skills.types import SkillReadParams
from my_agent.workflow.methods import load_method
from tests.python.test_goal_controller import app_at, create_session


def test_skill_selection_refresh_and_project_rules(tmp_path):
    """使用真实 RPC 与存储验证资源更新。 Verify resource changes through real RPC and storage."""

    async def scenario():
        """隔离应用不访问模型。 An isolated app never calls a model."""
        async with app_at(tmp_path / "data", None) as app:
            library = await app.dispatch("skills.list", {})
            assert library.project_directory == "" and len(library.items) == 9
            created = await create_session(app, tmp_path / "project")
            sid, pid = created.session.session_id, created.task.project_id
            params = {"project_id": pid, "session_id": sid}
            body = "---\nname: plan\ndescription: custom --- method\n---\nUse short plans."
            catalog = await app.dispatch("skills.save", {**params, "name": "plan", "content": body})
            assert (
                next(i for i in catalog.items if i.skill_id == "builtin:plan").shadowed_by
                == "user:plan"
            )
            await app.dispatch("skills.select", {**params, "selected": ["user:plan"]})
            (tmp_path / "project" / "AGENTS.md").write_text("Use local tools.", encoding="utf-8")
            log = await app.sessions._load(sid)
            text, materials = await app.worker.call(app.sessions.skills.materials, log)
            assert "Use local tools." in text and "Use short plans." in text
            old = next(m for m in materials if m.source_id == "user:plan")
            repeat = (await app.worker.call(app.sessions.skills.materials, log))[1]
            assert (
                next(m for m in repeat if m.source_id == "user:plan").read_arguments
                == old.read_arguments
            )
            assert (
                len([m for m in materials if m.kind == "skill" and m.source_id == "user:plan"]) == 1
            )
            await app.dispatch(
                "skills.save",
                {
                    **params,
                    "name": "plan",
                    "content": body.replace("short", "clear"),
                    "overwrite": True,
                },
            )
            text, _ = await app.worker.call(app.sessions.skills.materials, log)
            assert "Use clear plans." in text and "Use short plans." not in text
            archive = await app.worker.call(
                ContextStore(app.sessions.store).history,
                log,
                HistoryParams(session_id=sid, **old.read_arguments),
            )
            assert "Use short plans." in archive.items[0].text
            doc = await app.worker.call(
                app.sessions.skills.read, SkillReadParams(**params, skill_id="user:plan")
            )
            assert "clear" in doc.content
            await app.dispatch(
                "skills.enable", {**params, "skill_id": "user:plan", "enabled": False}
            )
            text, _ = await app.worker.call(app.sessions.skills.materials, log)
            assert "Use clear plans." not in text
            settings = app.sessions.store.path(sid).with_name("skills.json")
            settings.write_text("{invalid", encoding="utf-8")
            text, _ = await app.worker.call(app.sessions.skills.materials, log)
            assert "Use local tools." in text and "DATA_INVALID" in text
            assert settings.read_text(encoding="utf-8") == "{invalid"
            # 项目导入是一份独立副本，附属资源随正文一起复制。
            # Project imports are independent copies and include the skill's assets.
            reference = app.sessions.skills.root / "plan" / "references" / "note.md"
            reference.parent.mkdir()
            reference.write_text("reference text", encoding="utf-8")
            imported = await app.dispatch(
                "skills.save",
                {
                    "project_id": pid,
                    "name": "plan",
                    "content": "",
                    "scope": "project",
                    "import_directory": str(reference.parent.parent),
                },
            )
            assert any(i.source == "project" and i.name == "plan" for i in imported.items)
            copied = tmp_path / "project/.agents/skills/plan/references/note.md"
            assert copied.read_text(encoding="utf-8") == "reference text"
            assert all(i.source != "project" for i in (await app.dispatch("skills.list", {})).items)

            (tmp_path / "project").rename(tmp_path / "project-moved")
            with pytest.raises(AgentError, match="项目目录已失效"):
                await app.dispatch(
                    "skills.save",
                    {
                        "project_id": pid,
                        "name": "plan",
                        "content": body,
                        "scope": "project",
                    },
                )
            assert not (tmp_path / "project").exists()

    asyncio.run(scenario())


def test_bundled_resources_legacy_methods_and_complete_copy(tmp_path):
    """验证真实预装资源、兼容身份、按需正文与完整附属资源复制。

    Check real bundled resources, legacy IDs, lazy bodies and complete copies.
    """

    async def scenario():
        """实际 RPC / 存储，隔离项目且不访问网络或模型。

        Use real RPC/storage with an isolated project and no network or model.
        """
        async with app_at(tmp_path / "data", None) as app:
            created = await create_session(app, tmp_path / "project")
            params = {
                "project_id": created.task.project_id,
                "session_id": created.session.session_id,
            }
            catalog = await app.dispatch("skills.list", params)
            assert not catalog.issues
            methods = {"discuss", "plan", "implement", "diagnose", "review", "handoff"}
            expected = methods | {
                "frontend-design",
                "vercel-react-best-practices",
                "vercel-composition-patterns",
            }
            assert {i.name for i in catalog.items if i.source == "builtin"} == expected
            for item in catalog.items:
                doc = await app.dispatch("skills.read", {**params, "skill_id": item.skill_id})
                base = Path(item.resource_base)
                assert doc.content == (base / "SKILL.md").read_text(encoding="utf-8")
                assert item.origin and item.origin.revision
                assert item.origin.revision in (base / "SOURCE.md").read_text(encoding="utf-8")
                assert (base / "LICENSE.txt").is_file()
                if item.name in methods:
                    method = load_method(item.name)
                    assert method.text == doc.content and method.version == item.version
                    assert method.version != "1"

            log = await app.sessions._load(created.session.session_id)
            text, materials = await app.worker.call(app.sessions.skills.materials, log)
            assert "builtin:frontend-design" in text  # 短目录 / Short catalog entry.
            assert not any(m.source_id == "builtin:frontend-design" for m in materials)

            # 两类复制均需保留上游规则和来源，不能只写一份正文。
            # Both copy destinations must retain upstream rules and provenance.
            item = next(i for i in catalog.items if i.name == "vercel-react-best-practices")
            source = Path(item.resource_base)
            for scope in ("user", "project"):
                result = await app.dispatch(
                    "skills.save",
                    {
                        **params,
                        "name": item.name,
                        "content": "",
                        "scope": scope,
                        "import_directory": str(source),
                    },
                )
                copied = next(i for i in result.items if i.name == item.name and i.source == scope)
                assert copied.origin == item.origin
                target = Path(copied.resource_base)
                for resource in source.rglob("*"):
                    if resource.is_file():
                        assert (
                            target / resource.relative_to(source)
                        ).read_bytes() == resource.read_bytes()
            selected = copied.skill_id
            await app.dispatch("skills.select", {**params, "selected": [selected]})
            _, materials = await app.worker.call(app.sessions.skills.materials, log)
            assert len([m for m in materials if m.source_id == selected]) == 1
            assert not any(m.source_id == item.skill_id for m in materials)

            # 旧默认阶段不能绕过新复制的用户版本，也不能重复加载两个正文。
            # Old default stages must honor overrides without loading both bodies.
            await app.dispatch(
                "skills.save",
                {
                    **params,
                    "name": "discuss",
                    "content": "---\nname: discuss\ndescription: local discussion\n"
                    "---\nLocal method.",
                },
            )
            _, materials = await app.worker.call(app.sessions.skills.materials, log, "discuss")
            assert len([m for m in materials if m.source_id == "user:discuss"]) == 1
            assert not any(m.source_id == "builtin:discuss" for m in materials)

    asyncio.run(scenario())
