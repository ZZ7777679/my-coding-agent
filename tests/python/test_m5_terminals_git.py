"""隔离项目真实 ConPTY 与无 remote Git 验证。 Real ConPTY and no-remote Git in isolated projects."""

import asyncio
import os
import subprocess
import sys
import threading
import time
from uuid import uuid4

import pytest

from my_agent.config import DEFAULTS
from my_agent.errors import AgentError
from my_agent.execution.types import ProgramCommand
from my_agent.local_git.service import LocalGitService
from my_agent.local_git.types import (
    GitCommitParams,
    GitDiffParams,
    GitHistoryParams,
    GitPathsParams,
    GitProjectParams,
)
from my_agent.models.types import ToolCall
from my_agent.runtime.settings import RunLimits
from my_agent.runtime.tools import ToolContext
from my_agent.terminals.service import TerminalService
from my_agent.terminals.tools import TerminalTools
from my_agent.terminals.types import (
    OpenTerminalParams,
    ReadTerminalParams,
    ResizeTerminalParams,
    TerminalControlParams,
    TerminalParams,
    TerminalView,
    WriteTerminalParams,
)
from my_agent.tools.read_only import ReadTools
from tests.python.test_execution import process_handle
from tests.python.test_goal_controller import app_at, create_session
from tests.python.test_tasks import ContextModel


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY")
def test_real_terminal_unicode_takeover_interrupt_children(tmp_path):
    """中文输入、真实中断、接管互斥、子树退出与历史恢复。

    Verify Unicode input, interruption, exclusive takeover, child cleanup and history recovery.
    """

    async def scenario():
        """不调用模型，使用已登记的隔离项目与真实输入程序。

        Use an isolated registered project and real input program without model calls.
        """
        async with app_at(tmp_path / "data", ContextModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service = TerminalService(app.environments, app.storage, app.worker)
            project_id, session_id = created.session.project_id, created.session.session_id
            root = tmp_path / "project"
            child_pid = root / "child.pid"
            script = (
                "import pathlib,subprocess,sys,time; "
                "print('READY',flush=True); line=input(); print('ECHO:'+line,flush=True); "
                "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); "
                "pathlib.Path('child.pid').write_text(str(p.pid)); "
                "print('CHILD',flush=True); time.sleep(60)"
            )
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
            tools = TerminalTools(context, ReadTools(root, context.limits, context.stop), service)
            try:
                opened = await service.open(
                    OpenTerminalParams(
                        project_id=project_id,
                        session_id=session_id,
                        command=ProgramCommand(
                            kind="program", program=sys.executable, arguments=["-u", "-c", script]
                        ),
                    )
                )
                identity = opened.summary.terminal_id
                params = TerminalParams(terminal_id=identity)

                async def output_contains(expected):
                    """限定验证等待，只消费本终端实际输出。

                    Bound waiting for this terminal's real output.
                    """
                    deadline = time.monotonic() + 12
                    while time.monotonic() < deadline:
                        view = await service.read(ReadTerminalParams(terminal_id=identity))
                        if expected in "".join(chunk.text for chunk in view.output):
                            return view
                        assert view.summary.status == "running", view.summary
                        await asyncio.sleep(0.03)
                    raise AssertionError(f"Expected terminal output: {expected}")

                await output_contains("READY")
                resized = await service.resize(
                    ResizeTerminalParams(terminal_id=identity, cols=77, rows=19)
                )
                assert (resized.summary.cols, resized.summary.rows) == (77, 19)
                await service.control(
                    TerminalControlParams(
                        terminal_id=identity, controller="member", session_id=session_id
                    )
                )
                with pytest.raises(AgentError) as blocked:
                    await service.write(WriteTerminalParams(terminal_id=identity, text="wrong\r"))
                assert blocked.value.code == "TERMINAL_MEMBER_CONTROL"
                await service.control(
                    TerminalControlParams(terminal_id=identity, controller="user")
                )
                member_denied = await tools.execute(
                    ToolCall(
                        tool_call_id=str(uuid4()),
                        name="write_terminal",
                        arguments={"terminal_id": identity, "text": "wrong\r"},
                    )
                )
                assert member_denied.is_error and "TERMINAL_USER_CONTROL" in member_denied.content
                await service.write(
                    WriteTerminalParams(terminal_id=identity, text="中文持续输入\r")
                )
                await output_contains("ECHO:中文持续输入")
                await output_contains("CHILD")
                kernel, handle = process_handle(int(child_pid.read_text()))
                try:
                    await service.interrupt(params)
                    # Python sleep 接收真实 Ctrl+C 后退出；退出仍清理其孩子。
                    # Real Ctrl+C interrupts Python sleep; root exit still reaps descendants.
                    deadline = time.monotonic() + 12
                    while time.monotonic() < deadline:
                        view = await service.read(ReadTerminalParams(terminal_id=identity))
                        if view.summary.status != "running":
                            break
                        await asyncio.sleep(0.03)
                    assert view.summary.status == "exited", view.summary
                    assert view.summary.exit_code is not None
                    assert kernel.WaitForSingleObject(handle, 5000) == 0
                finally:
                    kernel.CloseHandle(handle)
                # 等监视器完成最终保存；展示终态早于落盘完成，不能据此改历史。
                # Wait for the monitor's final save, not merely the displayed exit state.
                owned = service.owned.get(identity)
                if owned is not None:
                    await owned.done.wait()
                record = service.store.load(identity)
                record.summary.status = "running"
                record.summary.pid = os.getpid()
                service.store.save(record)
                reopened = TerminalService(app.environments, app.storage, app.worker)
                recovered = await reopened.read(ReadTerminalParams(terminal_id=identity))
                assert recovered.summary.status == "interrupted" and not reopened.owned
                await reopened.close()
                agent_started = await tools.execute(
                    ToolCall(
                        tool_call_id=str(uuid4()),
                        name="start_terminal",
                        arguments={
                            "command": {
                                "kind": "program",
                                "program": sys.executable,
                                "arguments": [
                                    "-u",
                                    "-c",
                                    "print('AGENT_READY',flush=True); "
                                    "print('AGENT_ECHO:'+input(),flush=True)",
                                ],
                            }
                        },
                    )
                )
                assert not agent_started.is_error, agent_started.content
                agent_view = TerminalView.model_validate_json(agent_started.content)
                identity = agent_view.summary.terminal_id
                assert agent_view.summary.controller == "member"
                await output_contains("AGENT_READY")
                agent_wrote = await tools.execute(
                    ToolCall(
                        tool_call_id=str(uuid4()),
                        name="write_terminal",
                        arguments={"terminal_id": identity, "text": "成员中文输入\r"},
                    )
                )
                assert not agent_wrote.is_error, agent_wrote.content
                await output_contains("AGENT_ECHO:成员中文输入")
                owned = service.owned.get(identity)
                if owned is not None:
                    await owned.done.wait()
                assert (
                    await service.read(ReadTerminalParams(terminal_id=identity))
                ).summary.exit_code == 0
                cmd = await service.open(
                    OpenTerminalParams(
                        project_id=project_id,
                        command=ProgramCommand(
                            kind="program", program="cmd.exe", arguments=["/D", "/Q"]
                        ),
                    )
                )
                identity = cmd.summary.terminal_id
                await service.write(
                    WriteTerminalParams(terminal_id=identity, text="echo CMD_REA^DY\r\nexit\r\n")
                )
                await output_contains("CMD_READY")
                owned = service.owned.get(identity)
                if owned is not None:
                    await owned.done.wait()
                assert (
                    await service.read(ReadTerminalParams(terminal_id=identity))
                ).summary.exit_code == 0
            finally:
                await service.close()

    asyncio.run(scenario())


@pytest.mark.skipif(os.name != "nt", reason="Windows execution backend")
def test_local_git_without_remote_worktree_index_commit_history(tmp_path, monkeypatch):
    """无 remote 完成初始化、中文差异、暂存 / 取消、提交及历史。

    Initialize, diff Unicode paths, stage/unstage, commit and read history without any remote.
    """

    # 产物位于开发仓库内，阻止 Git 搜索到开发仓库，避免测试提交污染它。
    # Artifacts live inside the development checkout; prevent discovery of its parent repository.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    async def scenario():
        """只为隔离仓库设置本地测试身份，不接触用户全局配置。

        Configure identity only in the isolated fixture, never in global user settings.
        """
        async with app_at(tmp_path / "data", ContextModel()) as app:
            created = await create_session(app, tmp_path / "project")
            service = LocalGitService(app.environments, app.worker)
            project_id = created.session.project_id
            root = tmp_path / "project"
            params = GitProjectParams(project_id=project_id)
            try:
                initial = await service.status(params)
                assert initial.available and not initial.repository
                assert not (root / ".git").exists()
                assert (await service.init(params)).repository
                env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
                for name, value in (
                    ("user.name", "M5 Fixture"),
                    ("user.email", "m5@example.invalid"),
                ):
                    subprocess.run(
                        ["git", "-C", str(root), "config", "--local", name, value],
                        check=True,
                        capture_output=True,
                        env=env,
                    )
                file = root / "中文 空格.txt"
                file.write_text("第一行\n", encoding="utf-8")
                status = await service.status(params)
                assert any(f.path == file.name and f.index_status == "?" for f in status.files)
                assert (
                    "第一行"
                    in (
                        await service.diff(GitDiffParams(project_id=project_id, path=file.name))
                    ).text
                )
                paths = GitPathsParams(project_id=project_id, paths=[file.name])
                staged = await service.stage(paths)
                assert any(f.path == file.name and f.index_status == "A" for f in staged.files)
                assert (
                    "+第一行"
                    in (
                        await service.diff(
                            GitDiffParams(project_id=project_id, path=file.name, area="index")
                        )
                    ).text
                )
                unstaged = await service.unstage(paths)
                assert file.read_text(encoding="utf-8") == "第一行\n"
                assert any(f.path == file.name and f.index_status == "?" for f in unstaged.files)
                await service.stage(paths)
                committed = await service.commit(
                    GitCommitParams(project_id=project_id, message="本地首个提交")
                )
                history = await service.history(GitHistoryParams(project_id=project_id))
                assert history.commits[0].commit_id == committed.commit_id
                assert history.commits[0].subject == "本地首个提交"
                file.write_text("第二行\n", encoding="utf-8")
                changed = await service.status(params)
                assert any(f.path == file.name and f.worktree_status == "M" for f in changed.files)
                await service.stage(paths)
                await service.unstage(paths)
                assert file.read_text(encoding="utf-8") == "第二行\n"
                remote = subprocess.run(
                    ["git", "-C", str(root), "remote"],
                    check=True,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                assert remote.stdout == ""
                # 子目录仍可使用上层仓库，状态/暂存路径必须相对子项目，独立 init 不改父索引。
                # Parent repos remain usable; paths stay local; explicit init preserves the parent.
                nested = await create_session(app, root / "nested_project")
                nested_root = root / "nested_project"
                nested_id = nested.session.project_id
                nested_params = GitProjectParams(project_id=nested_id)
                (nested_root / "inside.txt").write_text("nested only\n", encoding="utf-8")
                parent = await service.status(nested_params)
                assert parent.repository and not parent.project_repository
                assert parent.repository_root is not None
                assert root.samefile(parent.repository_root)
                assert [item.path for item in parent.files] == ["inside.txt"]
                assert (
                    "+nested only"
                    in (
                        await service.diff(GitDiffParams(project_id=nested_id, path="inside.txt"))
                    ).text
                )
                nested_paths = GitPathsParams(project_id=nested_id, paths=["inside.txt"])
                await service.stage(nested_paths)
                assert [item.path for item in (await service.status(nested_params)).files] == [
                    "inside.txt"
                ]
                await service.unstage(nested_paths)
                parent_index = (root / ".git/index").read_bytes()
                independent = await service.init(nested_params)
                assert independent.repository and independent.project_repository
                assert nested_root.samefile(independent.repository_root)
                assert (root / ".git/index").read_bytes() == parent_index
                assert not service.processes
            finally:
                await service.close()

    asyncio.run(scenario())
