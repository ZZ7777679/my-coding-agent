"""在线发现和安装的定向检查，不调用模型。

Focused skill discovery/import checks without models.
"""

import asyncio
import io
import json
import os
import zipfile
from pathlib import Path

import httpx
import pytest

from my_agent.errors import AgentError
from my_agent.skills.online import github_source, skillhub_source
from tests.python.test_goal_controller import app_at, create_session
from tests.support.online_skill_fixture import BODY, archive_bytes, catalog_response


async def finished(app):
    """等待本次后台操作，失败状态留给断言。

    Await one background operation and retain failures.
    """
    await asyncio.wait_for(asyncio.shield(app.online_skills.task), 180)
    return await app.dispatch("skills.online.status", {})


def test_online_skill_snapshot_install_project_and_restart(tmp_path):
    """经过真实 RPC 安装同一快照并恢复来源。

    Install a snapshot through real RPC and restore provenance.
    """

    async def scenario():
        """只替换网站响应，不替换存储与安装。

        Substitute website responses, not storage or installation.
        """
        async with app_at(tmp_path / "data", None) as app:
            app.online_skills.transport = httpx.MockTransport(catalog_response)
            await app.dispatch("skills.online.search", {"query": "sample"})
            results = await finished(app)
            assert results.status == "ready" and results.hits[0].source == "fixture/repo"
            await app.dispatch("skills.online.inspect", {"source": results.hits[0].url})
            preview = (await finished(app)).preview
            assert preview.origin.revision == "1" * 40 and preview.total == 2
            params = {"preview_id": preview.preview_id, "path": "skills/demo"}
            document = await app.dispatch("skills.online.read", params)
            assert document.content == BODY and document.file_count == 3
            assert not (tmp_path / "data" / "skills").exists()
            await app.dispatch("skills.online.install", params)
            installed = await finished(app)
            assert installed.status == "installed", installed
            assert installed.installed.origin.directory == "skills/demo"
            folder = Path(installed.installed.resource_base)
            assert (folder / "assets/pixel.bin").read_bytes() == b"\x00\xff\x80"
            (folder / "SKILL.md").write_text(BODY + "Local change.", encoding="utf-8")
            await app.dispatch("skills.online.install", params)
            duplicate = await finished(app)
            assert duplicate.error_code == "SKILL_EXISTS"
            assert (folder / "SKILL.md").read_text(encoding="utf-8").endswith("Local change.")
            created = await create_session(app, tmp_path / "project")
            # 项目导入复用已安装资源，附属文件与来源也保留。
            # Importing the installed resource preserves assets and provenance.
            await app.dispatch(
                "skills.save",
                {
                    "project_id": created.task.project_id,
                    "scope": "project",
                    "name": "sample-skill",
                    "content": "",
                    "import_directory": str(folder),
                },
            )
            catalog = await app.dispatch("skills.list", {"project_id": created.task.project_id})
            project = next(i for i in catalog.items if i.source == "project")
            assert project.origin.repository == "fixture/repo"
            log = await app.sessions._load(created.session.session_id)
            await app.dispatch(
                "skills.select",
                {
                    "project_id": created.task.project_id,
                    "session_id": log.session_id,
                    "selected": [project.skill_id],
                },
            )
            text, _ = await app.worker.call(app.sessions.skills.materials, log)
            assert "Local change." in text
        assert not list((tmp_path / "data/skill-downloads").iterdir())
        async with app_at(tmp_path / "data", None) as restored:
            catalog = await restored.dispatch("skills.list", {})
            assert next(i for i in catalog.items if i.name == "sample-skill").origin.ref == "HEAD"

    asyncio.run(scenario())


def test_online_cancel_failure_and_archive_boundary(tmp_path):
    """取消不会留下任务或半成品，错误网站不妨碍本地资源。

    Cancellation leaves no partial install or blocked library.
    """

    async def scenario():
        """在真实后台任务上检查取消和受影响边界。

        Exercise real background jobs and their affected boundaries.
        """
        async with app_at(tmp_path / "data", None) as app:
            local_ids = {i.skill_id for i in (await app.dispatch("skills.list", {})).items}
            app.online_skills.transport = httpx.MockTransport(catalog_response)
            start = await app.dispatch("skills.online.search", {"query": "slow"})
            # 覆盖首次调度前的取消，不能留下未 awaited 协程。
            # Cover cancellation before the first coroutine step.
            state = await app.dispatch("skills.online.cancel", {"operation_id": start.operation_id})
            assert state.status == "cancelled"
            start = await app.dispatch("skills.online.search", {"query": "slow"})
            await asyncio.sleep(0.03)
            await app.dispatch("skills.online.cancel", {"operation_id": "old-job"})
            assert app.online_skills.status().status == "running"
            state = await app.dispatch("skills.online.cancel", {"operation_id": start.operation_id})
            assert state.status == "cancelled"
            app.online_skills.transport = httpx.MockTransport(lambda r: httpx.Response(403))
            await app.dispatch("skills.online.search", {"query": "anything"})
            assert (await finished(app)).error_code == "SKILL_SOURCE_LIMITED"
            assert {i.skill_id for i in (await app.dispatch("skills.list", {})).items} == local_ids
            app.online_skills.transport = httpx.MockTransport(
                lambda r: httpx.Response(200, content=archive_bytes(escape=True))
            )
            await app.dispatch("skills.online.inspect", {"source": "fixture/repo"})
            preview = (await finished(app)).preview
            await app.dispatch(
                "skills.online.install", {"preview_id": preview.preview_id, "path": "skills/demo"}
            )
            assert (await finished(app)).error_code == "SKILL_ARCHIVE_PATH"
            assert not (tmp_path / "data/skills/sample-skill").exists()
            assert not list(tmp_path.rglob("escaped.txt"))
            with pytest.raises(AgentError, match="预览已"):
                await app.dispatch(
                    "skills.online.install", {"preview_id": "old", "path": "skills/demo"}
                )
        assert not list((tmp_path / "data/skill-downloads").iterdir())

    asyncio.run(scenario())
    assert github_source("https://github.com/owner/repo/tree/main/skills/test") == (
        "owner/repo",
        "main",
        "skills/test",
    )
    assert github_source("https://www.skills.sh/owner/repo/test") == ("owner/repo", "HEAD", "")
    with pytest.raises(AgentError, match="外部网站发布"):
        github_source("https://www.skills.sh/site/example.com/test")


@pytest.mark.parametrize("plain", [False, True])
def test_skillhub_native_preview_and_project_import(tmp_path, plain):
    """原生 ZIP 的标准与无头正文均能按预览快照导入项目并恢复。

    Import both standard and headerless SkillHub ZIPs from the exact preview snapshot.
    """
    slug = "react-native-maps"
    body = (
        "# React Native Maps\n\n## Description\nReact Native mapping components and utilities\n"
        if plain
        else "---\nname: react-native-maps\ndescription: Map components\n---\nUse the map.\n"
    )
    packed = io.BytesIO()
    with zipfile.ZipFile(packed, "w") as archive:
        archive.writestr("SKILL.md", body)
        archive.writestr("references/example.md", "Keep the map.\n")

    def response(request):
        """替换公开 HTTP，不替换真实的扫描、预览和写入。

        Stub only public HTTP while retaining real scan, preview, and installation.
        """
        assert request.url.host == "api.skillhub.cn"
        assert "authorization" not in request.headers
        if request.url.path == f"/api/v1/skills/{slug}":
            return httpx.Response(
                200,
                json={
                    "skill": {"slug": slug, "displayName": "React Native Maps", "summary": ""},
                    "latestVersion": {"version": "1.0.0"},
                },
            )
        assert request.url.path == "/api/v1/download"
        assert request.url.params.get("slug") == slug
        assert request.url.params.get("version") == "1.0.0"
        return httpx.Response(200, content=packed.getvalue())

    async def scenario():
        """在隔离数据根中走完整 RPC。 Exercise full RPC in an isolated data root."""
        async with app_at(tmp_path / "data", None) as app:
            app.online_skills.transport = httpx.MockTransport(response)
            created = await create_session(app, tmp_path / "project")
            await app.dispatch(
                "skills.online.inspect",
                {"source": f"https://skillhub.cn/skills/user_922b1001/{slug}"},
            )
            state = await finished(app)
            assert state.status == "ready" and state.preview.total == 1, state
            preview = state.preview
            assert preview.origin.repository == f"skillhub.cn/{slug}"
            assert preview.origin.ref == "1.0.0"
            assert preview.skills[0].path == ""
            params = {"preview_id": preview.preview_id, "path": ""}
            document = await app.dispatch("skills.online.read", params)
            assert document.file_count == 2
            assert body in document.content
            if plain:
                assert document.content.startswith('---\nname: "react-native-maps"\n')
                assert "React Native mapping components and utilities" in document.content
            await app.dispatch(
                "skills.online.install",
                {**params, "scope": "project", "project_id": created.task.project_id},
            )
            installed = await finished(app)
            assert installed.status == "installed", installed
            folder = Path(installed.installed.resource_base)
            assert (folder / "SKILL.md").read_text(encoding="utf-8") == document.content
            assert (folder / "references/example.md").read_text(encoding="utf-8") == (
                "Keep the map.\n"
            )
            assert installed.installed.origin.repository == f"skillhub.cn/{slug}"
        async with app_at(tmp_path / "data", None) as restored:
            catalog = await restored.dispatch(
                "skills.list", {"project_id": created.task.project_id}
            )
            assert any(i.source == "project" and i.name == slug for i in catalog.items)

    asyncio.run(scenario())
    assert skillhub_source(f"https://skillhub.cn/skills/user_922b1001/{slug}") == slug
    assert skillhub_source(f"https://skillhub.cn/skills/{slug}") == slug
    assert skillhub_source("https://github.com/owner/repo") is None


@pytest.mark.skipif(
    os.environ.get("MY_AGENT_TEST_SKILL_ONLINE") != "1", reason="explicit public network check"
)
def test_skillhub_public_live(tmp_path):
    """两种真实公开 SkillHub ZIP 均能预览并导入隔离项目。

    Preview and import both real SkillHub archive formats into an isolated project.
    """

    async def scenario():
        """只使用公开 API 与临时数据，不调用模型或个人资源库。

        Use only the public API and temporary data, without models or personal storage.
        """
        report = []
        async with app_at(tmp_path / "data", None) as app:
            created = await create_session(app, tmp_path / "project")
            for slug in ("find-skill-skillhub", "react-native-maps"):
                await app.dispatch(
                    "skills.online.inspect",
                    {"source": f"https://skillhub.cn/skills/{slug}"},
                )
                state = await finished(app)
                assert state.status == "ready" and state.preview.total == 1, state
                preview = state.preview
                candidate = preview.skills[0]
                document = await app.dispatch(
                    "skills.online.read",
                    {"preview_id": preview.preview_id, "path": candidate.path},
                )
                assert candidate.name == slug and document.content.startswith("---\n")
                await app.dispatch(
                    "skills.online.install",
                    {
                        "preview_id": preview.preview_id,
                        "path": candidate.path,
                        "scope": "project",
                        "project_id": created.task.project_id,
                    },
                )
                installed = await finished(app)
                assert installed.status == "installed", installed
                folder = Path(installed.installed.resource_base)
                assert (folder / "SKILL.md").read_text(encoding="utf-8") == document.content
                report.append(
                    {
                        "slug": slug,
                        "version": preview.origin.ref,
                        "description": candidate.description,
                        "file_count": document.file_count,
                        "project_imported": folder.exists(),
                    }
                )
            (tmp_path / "report.json").write_text(
                json.dumps({"results": report, "model_requests": 0}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        async with app_at(tmp_path / "data", None) as restored:
            catalog = await restored.dispatch(
                "skills.list", {"project_id": created.task.project_id}
            )
            assert {"find-skill-skillhub", "react-native-maps"} <= {
                i.name for i in catalog.items if i.source == "project"
            }

    asyncio.run(scenario())


@pytest.mark.skipif(
    os.environ.get("MY_AGENT_TEST_SKILL_ONLINE") != "1", reason="explicit public network check"
)
def test_online_skill_public_live(tmp_path):
    """公开网站真实搜索、项目导入和重启恢复；不使用登录或模型。

    Live public search, project import and restart without credentials.
    """

    async def scenario():
        """生产 HTTP 和 RPC，仅数据根隔离。

        Use production HTTP/RPC with an isolated data root.
        """
        async with app_at(tmp_path / "data", None) as app:
            await app.dispatch("skills.online.search", {"query": "react", "limit": 3})
            searched = await finished(app)
            assert searched.status == "ready" and searched.hits, searched
            hit = searched.hits[0]
            await app.dispatch("skills.online.inspect", {"source": hit.source})
            prepared = await finished(app)
            assert prepared.status == "ready" and prepared.preview, prepared
            selected = next(s for s in prepared.preview.skills if s.name == hit.name)
            await app.dispatch(
                "skills.online.install",
                {
                    "preview_id": prepared.preview.preview_id,
                    "path": selected.path,
                },
            )
            installed = await finished(app)
            assert installed.status == "installed", installed
            folder = Path(installed.installed.resource_base)
            assert (folder / "SKILL.md").exists() and selected.file_count > 1
            created = await create_session(app, tmp_path / "project")
            await app.dispatch(
                "skills.save",
                {
                    "project_id": created.task.project_id,
                    "scope": "project",
                    "name": selected.name,
                    "content": "",
                    "import_directory": str(folder),
                },
            )
            project_catalog = await app.dispatch(
                "skills.list", {"project_id": created.task.project_id}
            )
            project_skill = next(
                item
                for item in project_catalog.items
                if item.source == "project" and item.name == selected.name
            )
            project_folder = Path(project_skill.resource_base)
            assert (project_folder / "SKILL.md").read_bytes() == (folder / "SKILL.md").read_bytes()
            assert len([p for p in project_folder.rglob("*") if p.is_file()]) >= selected.file_count
            (tmp_path / "report.json").write_text(
                json.dumps(
                    {
                        "search": searched.model_dump(),
                        "preview": prepared.preview.model_dump(),
                        "installed": installed.installed.model_dump(),
                        "project_skill": project_skill.model_dump(),
                        "file_count": len([p for p in folder.rglob("*") if p.is_file()]),
                        "model_requests": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        async with app_at(tmp_path / "data", None) as restored:
            catalog = await restored.dispatch(
                "skills.list", {"project_id": created.task.project_id}
            )
            assert any(
                item.source == "project" and item.name == selected.name for item in catalog.items
            )

    asyncio.run(scenario())
