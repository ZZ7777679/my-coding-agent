"""搜索与模型 Git 的隔离验证，不使用个人仓库。

Isolated search/model Git checks without personal repos."""

import asyncio
import json
import os
import shutil
import subprocess
import threading
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from my_agent.config import DEFAULTS
from my_agent.documents.types import DocumentSearchParams
from my_agent.errors import AgentError
from my_agent.local_git.service import LocalGitService
from my_agent.local_git.tools import GitTools
from my_agent.local_git.types import ConfigureGitParams, GitHistoryParams, GitProjectParams
from my_agent.models.types import ToolCall
from my_agent.runtime.settings import RunLimits
from my_agent.runtime.tools import ToolContext
from my_agent.tools.read_only import ReadTools, SearchArgs
from tests.python.test_goal_controller import app_at, create_session
from tests.python.test_tasks import ContextModel


def test_search_regex_context_paths_and_fallback(tmp_path, monkeypatch):
    """真实 rg 支持正则和路径筛选；无 rg 时字面搜索仍可用。

    Real rg supports regex/path/context; literal search survives missing rg.
    """
    assert shutil.which("rg"), "This targeted regex acceptance requires rg"
    (tmp_path / "tests").mkdir()
    (tmp_path / "代码.py").write_bytes("# 中文\r\ndef hello():\r\n    return 1\r\n".encode())
    (tmp_path / "tests/skip.py").write_text("def ignored():", encoding="utf-8")
    tools = ReadTools(tmp_path, RunLimits.model_validate(DEFAULTS["run"]), threading.Event())
    result = tools._search(
        SearchArgs(
            query=r"^def\s+\w+\(",
            regex=True,
            before=1,
            after=1,
            include_globs=["**/*.py"],
            exclude_globs=["tests/**"],
        )
    )
    assert len(result["matches"]) == 1
    match = result["matches"][0]
    assert (match["path"], match["line"]) == ("代码.py", 2)
    assert match["context_before"] == [{"line": 1, "text": "# 中文"}]
    assert match["context_after"] == [{"line": 3, "text": "    return 1"}]
    with pytest.raises(AgentError) as invalid:
        tools._search(SearchArgs(query="(", regex=True))
    assert invalid.value.code == "INVALID_TOOL_ARGUMENTS"
    monkeypatch.setattr("my_agent.tools.read_only.shutil.which", lambda _: None)
    fallback = tools._search(SearchArgs(query="hello"))
    assert fallback["backend"] == "python" and len(fallback["matches"]) == 1
    with pytest.raises(AgentError, match="rg"):
        tools._search(SearchArgs(query="hello", regex=True))
    (tmp_path / "many.txt").write_text("needle\n" + "context\n" * 50000, encoding="utf-8")
    bounded = tools._search(SearchArgs(query="needle", after=100000))
    assert bounded["matches"][0]["line"] == 1 and bounded["truncated"]
    assert len(json.dumps(bounded).encode()) < tools.limits.max_tool_bytes
    tools.stop.set()
    with pytest.raises(AgentError) as stopped:
        tools._search(SearchArgs(query="hello"))
    assert stopped.value.code == "CANCELLED"


def test_regex_search_batches_many_small_files(tmp_path, monkeypatch):
    """批量搜索保持 Windows 换行和行号，不为每个匹配文件启动进程。

    Batch small files with correct Windows newlines/line numbers, not a process per match file.
    """
    for index in range(201):
        (tmp_path / f"file-{index:03}.py").write_bytes(b"# context\r\ndef hello():\r\n    pass\r\n")
    original = subprocess.Popen
    starts = []

    def observe(*args, **kwargs):
        """仅计数真实子进程，不替换 rg 结果。 Count actual subprocesses without faking rg."""
        starts.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", observe)
    tools = ReadTools(tmp_path, RunLimits.model_validate(DEFAULTS["run"]), threading.Event())
    result = tools._search(SearchArgs(query=r"^def\s+.*:$", regex=True, before=1, limit=100))
    assert len(result["matches"]) == 100 and result["truncated"]
    assert result["matches"][0]["line"] == 2
    assert result["matches"][0]["context_before"] == [{"line": 1, "text": "# context"}]
    assert len(starts) < 20  # 批处理成本，非硬性时延门槛。 Batch cost, not a timing threshold.
    empty = tmp_path / "empty"
    empty.mkdir()
    empty_tools = ReadTools(empty, tools.limits, threading.Event())
    with pytest.raises(AgentError) as invalid:
        empty_tools._search(SearchArgs(query="(", regex=True))
    assert invalid.value.code == "INVALID_TOOL_ARGUMENTS"


def test_bad_search_patterns_allow_run_to_continue(tmp_path):
    """模式错误回到真实模型循环，允许修正后完成。

    Return malformed patterns to the real loop so a corrected call can finish.
    """
    from tests.python.test_collaboration import finish
    from tests.python.test_goal_controller import call, turn
    from tests.python.test_work_graph import WorkModel

    async def scenario():
        """使用生产工具与存储，只替换模型响应。 Use real tools/storage with model-only fixtures."""
        model = WorkModel()
        model.steps = [
            turn(call("search", query="needle", exclude_globs=["!"])),
            turn(call("search", query="needle", include_globs=["[z-a]"])),
            turn(call("search", query="needle", include_globs=["**/*.py"])),
            turn(text="Found the requested line"),
        ]
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            (tmp_path / "project/main.py").write_text("needle\n", encoding="utf-8")
            identity = created.session.session_id
            await app.sessions.start(identity, str(uuid4()), "Find needle", None)
            await finish(app, identity)
            view = await app.sessions.view(identity)
            assert view.summary.run.status == "completed"
            assert len(model.requests) == 4
            assert "INVALID_TOOL_ARGUMENTS" in json.dumps(model.requests[1]["messages"])

    asyncio.run(scenario())


@pytest.mark.skipif(os.name != "nt", reason="Windows managed Git backend")
def test_model_git_and_recoverable_switch(tmp_path, monkeypatch):
    """真实工具提交、关闭、重启、恢复及冲突，开发仓库不参与。

    Exercise real tools, restart, restoration and collisions outside the development repository.
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    async def scenario():
        """共享生产装配与 RPC，所有项目和数据归隔离目录。

        Use production composition with isolated data."""
        async with app_at(tmp_path / "data", ContextModel()) as app:
            created = await create_session(app, tmp_path / "project")
            project_id, session_id = created.session.project_id, created.session.session_id
            root = tmp_path / "project"
            context = ToolContext(
                root,
                RunLimits.model_validate(DEFAULTS["run"]),
                threading.Event(),
                project_id,
                session_id,
                str(uuid4()),
                "normal",
                None,
            )
            tools = app.sessions.tool_factory(context)

            async def call(name, **arguments):
                """调用真实已装配工具并读取事实。

                Call assembled tools and read actual results."""
                result = await tools.execute(
                    ToolCall(tool_call_id=str(uuid4()), name=name, arguments=arguments)
                )
                assert not result.is_error, result.content
                return json.loads(result.content)

            assert not (await call("git_status"))["repository"]
            assert (await call("git_init"))["repository"]
            env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
            for name, value in (
                ("user.name", "Fixture"),
                ("user.email", "fixture@example.invalid"),
            ):
                subprocess.run(
                    ["git", "-C", str(root), "config", "--local", name, value],
                    check=True,
                    capture_output=True,
                    env=env,
                )
            file = root / "代码.py"
            file.write_text("# context\ndef hello():\n    return 1\n", encoding="utf-8")
            desktop_search = await app.documents.search(
                DocumentSearchParams(session_id=session_id, query=r"^def\s+", regex=True, before=1)
            )
            assert desktop_search.matches[0].context_before[0].text == "# context"
            assert "+def hello" in (await call("git_diff", path=file.name))["text"]
            await call("git_stage", paths=[file.name])
            assert "+def hello" in (await call("git_diff", path=file.name, area="index"))["text"]
            await call("git_unstage", paths=[file.name])
            assert (await call("git_status"))["files"][0]["index_status"] == "?"
            await call("git_stage", paths=[file.name])
            commit = await call("git_commit", message="isolated commit")
            assert (await call("git_log"))["commits"][0]["commit_id"] == commit["commit_id"]

            plan = GitTools(
                replace(context, mode="plan"),
                ReadTools(root, context.limits, context.stop),
                app.local_git,
            )
            assert "git_commit" not in {item["function"]["name"] for item in plan.definitions()}
            denied = await plan.execute(
                ToolCall(tool_call_id="p", name="git_commit", arguments={"message": "no"})
            )
            assert denied.is_error and "Plan" in denied.content
            archives = []

            async def archive(text):
                """仅记录当前工具归档。

                Capture only this tool's archive."""
                archives.append(text)
                return "isolated-archive"

            file.write_text("long line\n" * 6000, encoding="utf-8")
            bounded_tools = GitTools(replace(context, archive_output=archive), tools, app.local_git)
            archived = await bounded_tools.execute(
                ToolCall(tool_call_id="d", name="git_diff", arguments={"path": file.name})
            )
            assert json.loads(archived.content)["archive_id"] == "isolated-archive"
            assert "+long line" in archives[0]
            contents = file.read_bytes()
            params = {"project_id": project_id, "enabled": False}
            off = await app.dispatch("git.configure", params)
            assert not off.enabled and off.backup_path and not (root / ".git").exists()
            assert file.read_bytes() == contents
            assert (await call("git_status"))["code"] == "GIT_DISABLED"
            blocked = await tools.execute(
                ToolCall(tool_call_id="off", name="git_init", arguments={})
            )
            assert blocked.is_error and "GIT_DISABLED" in blocked.content
            restarted = LocalGitService(app.environments, app.worker)
            assert not (await restarted.settings(GitProjectParams(project_id=project_id))).enabled
            # 新仓库不能被恢复操作吞并，先保留两者再交还用户。
            # Restoring must never merge into a newly created repository.
            (root / ".git").mkdir()
            with pytest.raises(AgentError) as conflict:
                await restarted.configure(ConfigureGitParams(project_id=project_id, enabled=True))
            assert conflict.value.code == "GIT_BACKUP_CONFLICT"
            assert Path(off.backup_path).exists() and (root / ".git").exists()
            (
                root / ".git"
            ).rmdir()  # 仅移除本测试刚创建的空目录。 Only the empty fixture directory.
            await restarted.configure(ConfigureGitParams(project_id=project_id, enabled=True))
            history = await restarted.history(GitHistoryParams(project_id=project_id))
            assert history.commits[0].commit_id == commit["commit_id"]
            assert file.read_bytes() == contents
            # 子项目关闭只保存开关，绝不移动上层 .git。
            # Disabling a nested project must leave parent metadata intact.
            child = await create_session(app, root / "nested")
            before = (root / ".git/HEAD").read_bytes()
            child_off = await restarted.configure(
                ConfigureGitParams(project_id=child.session.project_id, enabled=False)
            )
            assert child_off.backup_path is None and (root / ".git/HEAD").read_bytes() == before
            await restarted.close()

    asyncio.run(scenario())


def test_pointer_metadata_move_and_failed_copy_preserves_source(tmp_path, monkeypatch):
    """工作树指针只移动自身；移动失败不删除原文件。

    Move only pointer files; preserve sources on failure."""
    from my_agent.local_git.settings import GitSettingsStore

    source = tmp_path / ".git"
    target = tmp_path / "backup/metadata"
    source.write_text("gitdir: ../shared/worktrees/demo\n", encoding="utf-8")
    GitSettingsStore._move(source, target)
    assert not source.exists() and target.read_text() == "gitdir: ../shared/worktrees/demo\n"
    GitSettingsStore._move(target, source)

    def fail(*args):
        """模拟移动不可用，不执行副作用。

        Simulate unavailable movement without side effects."""
        raise PermissionError("fixture")

    monkeypatch.setattr("my_agent.local_git.settings.shutil.move", fail)
    with pytest.raises(AgentError) as error:
        GitSettingsStore._move(source, target)
    assert error.value.code == "GIT_BACKUP_FAILED" and source.exists()
