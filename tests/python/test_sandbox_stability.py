"""M6 沙箱定向实验，显式启用且仅使用隔离数据与复制运行时。

Opt-in M6 sandbox experiments with isolated data and a copied runtime.
"""

import asyncio
import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest

import my_agent.execution.sandbox_preview as preview_module
from my_agent.config import DEFAULTS
from my_agent.errors import AgentError
from my_agent.execution.sandbox import SandboxLease
from my_agent.execution.types import (
    BindEnvironmentParams,
    ProgramCommand,
    PythonEnvironment,
    RunCommandArgs,
    SandboxSettings,
    SaveEnvironmentParams,
    ShellCommand,
    StartServiceArgs,
)
from my_agent.local_git.types import (
    GitCommitParams,
    GitDiffParams,
    GitHistoryParams,
    GitPathsParams,
    GitProjectParams,
)
from my_agent.runtime.settings import RunLimits
from my_agent.runtime.tools import ToolContext
from my_agent.terminals.types import OpenTerminalParams, ReadTerminalParams, WriteTerminalParams
from tests.python.test_context_memory import KnowledgeModel
from tests.python.test_goal_controller import app_at, create_session


def ps_literal(value):
    """为测试目录构造 PowerShell 字面量。 Quote a test path as a PowerShell literal."""
    return "'" + value.replace("'", "''") + "'"


def directory_dacl(path):
    """只读保存测试目录 DACL，验证退出后临时权限恢复。

    Read a test directory DACL to verify temporary grants are restored at exit.
    """
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    api.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(pointer),
        ctypes.POINTER(pointer),
        ctypes.POINTER(pointer),
        ctypes.POINTER(pointer),
        ctypes.POINTER(pointer),
    ]
    api.GetNamedSecurityInfoW.restype = wintypes.DWORD
    api.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        pointer,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPWSTR),
        pointer,
    ]
    api.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [pointer]
    descriptor, text = pointer(), wintypes.LPWSTR()
    try:
        code = api.GetNamedSecurityInfoW(
            str(path), 1, 4, None, None, None, None, ctypes.byref(descriptor)
        )
        if code:
            raise ctypes.WinError(code)
        if not api.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, 1, 4, ctypes.byref(text), None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return text.value
    finally:
        for value in (text, descriptor):
            if value:
                kernel.LocalFree(ctypes.cast(value, pointer))


@pytest.fixture(autouse=True)
def forbid_elevation(monkeypatch):
    """实验宿主必须未提权，禁止加载启动 UAC 的 shell32。

    Require a non-elevated test host and forbid loading the UAC launch library.
    """
    if os.name != "nt":
        return
    assert not ctypes.windll.shell32.IsUserAnAdmin(), "Run this experiment without elevation"
    native = ctypes.WinDLL

    def load(name, *args, **kwargs):
        """保留原生 API，若产品试图启动 ShellExecute 则立即失败。

        Preserve native APIs but fail immediately if product code attempts ShellExecute.
        """
        assert str(name).lower() not in {"shell32", "shell32.dll"}, "Elevation is forbidden"
        return native(name, *args, **kwargs)

    monkeypatch.setattr(ctypes, "WinDLL", load)


@pytest.fixture
def sandbox_runtime():
    """只接受产物根内的既有复制运行时，不修改系统解释器。

    Accept an existing copied runtime under test artifacts, never modify system Python.
    """
    supplied = os.environ.get("MY_AGENT_TEST_SANDBOX_RUNTIME")
    if not supplied or os.name != "nt":
        pytest.skip("Explicit Windows sandbox experiment required")
    path = Path(supplied).resolve(strict=True)
    assert path.is_relative_to((Path(__file__).resolve().parents[2] / ".artifacts/tests").resolve())
    return path


async def bind_project(app, root, runtime, settings):
    """通过生产入口登记环境，返回一次运行归属。 Register through production environment APIs."""
    session = (await create_session(app, root)).session
    catalog = await app.worker.call(app.environments.catalog, session.project_id)
    catalog = await app.worker.call(
        app.environments.save,
        SaveEnvironmentParams(
            project_id=session.project_id,
            environment_id=None,
            expected_revision=catalog.revision,
            name="Isolated experiment",
            definition=PythonEnvironment(
                kind="python",
                scope="absolute",
                interpreter=str(runtime / "python.exe"),
            ),
        ),
    )
    environment_id = catalog.environments[-1].record.environment_id
    await app.worker.call(
        app.environments.bind,
        BindEnvironmentParams(
            project_id=session.project_id,
            environment_id=environment_id,
            expected_revision=catalog.revision,
            mode="sandbox",
            sandbox=settings,
        ),
    )
    return ToolContext(
        root,
        RunLimits.model_validate(DEFAULTS["run"]),
        threading.Event(),
        session.project_id,
        session.session_id,
        str(uuid4()),
        "normal",
        None,
    )


async def run_python(app, context, code, timeout=None):
    """运行真实沙箱 Python 命令，不调用模型。 Run a real sandboxed command without a model."""
    return await app.programs.run(
        context,
        RunCommandArgs(
            command=ProgramCommand(kind="program", program="python", arguments=["-c", code]),
            timeout_seconds=timeout,
        ),
    )


def test_sandbox_system_volume_project_without_ancestor_dacl(tmp_path, sandbox_runtime):
    """系统卷临时项目真实启动并清理，不要求能修改卷根 DACL。

    Launch and clean a temporary system-volume project without requiring volume-root DACL writes.
    """
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    if temporary_root.anchor.casefold() != Path(os.environ["SystemRoot"]).anchor.casefold():
        pytest.skip("User temporary directory is not on the system volume")
    report = {}
    with tempfile.TemporaryDirectory(prefix="my-agent-r2-") as temporary:
        control = Path(temporary).resolve(strict=True)
        assert control.parent == temporary_root and control.name.startswith("my-agent-r2-")
        root = control / "project"
        before = {path: directory_dacl(path) for path in (control, *control.parents)}

        async def scenario():
            """复用生产绑定、命令和关闭流程，输出留在测试产物目录。

            Reuse production bindings, commands and shutdown, retaining output in test artifacts.
            """
            async with app_at(tmp_path / "data", KnowledgeModel()) as app:
                context = await bind_project(app, root, sandbox_runtime, SandboxSettings())
                result = await run_python(
                    app,
                    context,
                    "from pathlib import Path; Path('inside.txt').write_text('R2_OK');"
                    " print('R2_OK')",
                )
                assert result.summary.exit_code == 0, result
                assert (root / "inside.txt").read_text() == "R2_OK"
                shell = await app.programs.run(
                    context,
                    RunCommandArgs(
                        command=ShellCommand(
                            kind="powershell",
                            script="(Get-Location).ProviderPath; cmd.exe /d /c cd; "
                            "Get-Content -LiteralPath inside.txt; "
                            "Set-Content -LiteralPath shell.txt -Value SHELL_R2; "
                            "cmd.exe /d /c type shell.txt",
                        )
                    ),
                )
                assert shell.summary.exit_code == 0, shell
                output = "".join(chunk.text for chunk in shell.output if chunk.stream == "stdout")
                assert output.count(str(root)) >= 2 and "R2_OK" in output, shell
                assert (root / "shell.txt").read_text().strip() == "SHELL_R2"
                terminal = await app.terminals.open(
                    OpenTerminalParams(
                        project_id=context.project_id,
                        session_id=context.session_id,
                        command=ProgramCommand(
                            kind="program",
                            program="powershell.exe",
                            arguments=["-NoLogo", "-NoProfile"],
                        ),
                    )
                )
                await app.terminals.write(
                    WriteTerminalParams(
                        terminal_id=terminal.summary.terminal_id,
                        text="(Get-Location).ProviderPath; cmd.exe /d /c cd; "
                        "Set-Content -LiteralPath terminal.txt -Value TERMINAL_R2; "
                        "cmd.exe /d /c type terminal.txt; exit\r\n",
                    )
                )
                await asyncio.wait_for(
                    app.terminals.owned[terminal.summary.terminal_id].done.wait(), 10
                )
                terminal = await app.terminals.read(
                    ReadTerminalParams(terminal_id=terminal.summary.terminal_id)
                )
                assert terminal.summary.exit_code == 0, terminal
                terminal_output = "".join(chunk.text for chunk in terminal.output)
                assert str(root) in terminal_output and "TERMINAL_R2" in terminal_output, terminal
                assert (root / "terminal.txt").read_text().strip() == "TERMINAL_R2"
                leases = list((tmp_path / "data/sandbox-leases").glob("*.json"))
                assert len(leases) == 1
                recorded = json.loads(leases[0].read_text(encoding="utf-8"))
                assert recorded["skipped_ancestors"][root.anchor] == 5
                report.update(
                    project_volume=root.anchor,
                    skipped_ancestors=recorded["skipped_ancestors"],
                    python_exit=result.summary.exit_code,
                    powershell_exit=shell.summary.exit_code,
                    terminal_exit=terminal.summary.exit_code,
                )
            assert not list((tmp_path / "data/sandbox-leases").glob("*.json"))
            assert all(directory_dacl(path) == saved for path, saved in before.items())
            report["leases_cleaned"] = True
            report["ancestor_dacls_restored"] = True

        asyncio.run(scenario())
    report["temporary_project_removed"] = not root.exists()
    (tmp_path / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def test_sandbox_required_grant_denial_reaps_failed_lease(tmp_path, sandbox_runtime, monkeypatch):
    """实际项目授权仍必须成功；拒绝后回收已创建主体和失败前记录。

    Required project grants must succeed; on denial reap the identity and write-ahead journal.
    """
    root = tmp_path / "project"
    original = SandboxLease.acl

    def deny_project(self, path, principal, permission, *, inherit=True):
        """只模拟项目授权拒绝，其他授权和清理使用真实系统 API。

        Simulate only project-grant denial; use real APIs for other grants and cleanup.
        """
        if path == root and permission == "M":
            raise AgentError("SANDBOX_ACCESS_FAILED", "Required project grant denied") from (
                ctypes.WinError(5)
            )
        return original(self, path, principal, permission, inherit=inherit)

    monkeypatch.setattr(SandboxLease, "acl", deny_project)

    async def scenario():
        """通过真实启动入口验证拒绝未被当成兼容反馈忽略。

        Verify through the launch entry point that required-grant denial cannot be ignored.
        """
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            context = await bind_project(app, root, sandbox_runtime, SandboxSettings())
            with pytest.raises(AgentError) as failed:
                await run_python(app, context, "print('MUST_NOT_START')")
            assert failed.value.code == "SANDBOX_ACCESS_FAILED"
            assert failed.value.__cause__.winerror == 5
            assert not list((tmp_path / "data/sandbox-leases").glob("*.json"))
            assert not app.programs.owned

    asyncio.run(scenario())


def test_sandbox_local_git_and_python_inspection(tmp_path, sandbox_runtime, monkeypatch):
    """普通权限下真实 Git 读写和 Python 检查，不更改系统安装或全局 Git。

    Exercise real Git reads/writes and Python inspection without elevation or global Git changes.
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)

    async def scenario():
        """沿生产服务使用项目沙箱，提交仅发生在本次隔离仓库。

        Use production services with the project sandbox, committing only in the isolated repo.
        """
        root = tmp_path / "project"
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            context = await bind_project(app, root, sandbox_runtime, SandboxSettings())
            probe = await app.programs.inspect_python(context.project_id)
            assert probe.code == "PYTHON_READY", probe
            assert Path(probe.interpreter).samefile(sandbox_runtime / "python.exe")
            git = app.sessions.local_git
            params = GitProjectParams(project_id=context.project_id)
            before = await git.status(params)
            assert before.available and not before.repository, before
            assert (await git.init(params)).repository
            config = root / ".git/config"
            with config.open("a", encoding="utf-8") as stream:
                stream.write(
                    "\n[user]\n\tname = Sandbox Fixture\n\temail = fixture@example.invalid\n"
                )
            path = root / "sample.txt"
            path.write_text("first\n", encoding="utf-8")
            paths = GitPathsParams(project_id=context.project_id, paths=[path.name])
            assert (await git.stage(paths)).files[0].index_status == "A"
            commit = await git.commit(
                GitCommitParams(project_id=context.project_id, message="Isolated sandbox commit")
            )
            history = await git.history(GitHistoryParams(project_id=context.project_id))
            assert history.commits[0].commit_id == commit.commit_id
            path.write_text("second\n", encoding="utf-8")
            diff = await git.diff(GitDiffParams(project_id=context.project_id, path=path.name))
            assert "-first" in diff.text and "+second" in diff.text
            await git.stage(paths)
            assert (await git.unstage(paths)).files[0].worktree_status == "M"
            assert not git.processes
            assert any(
                lease.directory == tmp_path / "data/sandbox-leases"
                for lease in SandboxLease.pool.values()
            )
        assert not list((tmp_path / "data/sandbox-leases").glob("*.json"))
        (tmp_path / "report.json").write_text(
            json.dumps(
                {
                    "elevated": False,
                    "python_inspection": "passed",
                    "git": ["init", "status", "stage", "commit", "history", "diff", "unstage"],
                    "cleanup": "passed",
                }
            ),
            encoding="utf-8",
        )

    asyncio.run(scenario())


def alive(pid):
    """只查询测试产生的进程，退出也包括 PID 已不存在。

    Query only experiment-owned processes; a missing PID is also an exited process.
    """
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        assert ctypes.get_last_error() == 87
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 258
    finally:
        kernel.CloseHandle(handle)


def test_sandbox_boundaries_soak_cancel_and_timeout(tmp_path, sandbox_runtime):
    """验证真实边界、连续／并发复用以及取消／超时后的可用性。

    Verify actual boundaries, serial/concurrent reuse and availability after cancellation/timeouts.
    """
    report = {"started": time.time(), "commands": 0}
    outside, readonly, writable = (tmp_path / name for name in ("outside", "read", "write"))
    for path in (outside, readonly, writable):
        path.mkdir()
        (path / "sentinel.txt").write_text("original")

    async def scenario():
        """使用真实应用服务执行实验，不启动外网或授权助手。

        Exercise production services without external networking or an authorization helper.
        """
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            settings = SandboxSettings(
                network="blocked", read_paths=[str(readonly)], write_paths=[str(writable)]
            )
            context = await bind_project(app, tmp_path / "project", sandbox_runtime, settings)
            root = context.root
            # 先创建 junction 再建立授权，覆盖继承 ACL 是否意外传播到链接目标。
            # Create the junction before grants to catch accidental ACL propagation to its target.
            subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    f"New-Item -ItemType Junction -Path {ps_literal(str(root / 'escape'))} "
                    f"-Value {ps_literal(str(outside))} | Out-Null",
                ],
                check=True,
                capture_output=True,
                timeout=10,
            )
            shutil.copy2(
                Path(__file__).parents[1] / "fixtures/sandbox_boundary.py", root / "probe.py"
            )
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                with socket.create_connection(listener.getsockname(), timeout=1):
                    accepted, _ = listener.accept()
                    accepted.close()
                (root / "config.json").write_text(
                    json.dumps(
                        {
                            "outside": str(outside),
                            "read": str(readonly),
                            "write": str(writable),
                            "port": listener.getsockname()[1],
                        }
                    ),
                    encoding="utf-8",
                )
                result = await run_python(
                    app,
                    context,
                    "import runpy,sys;sys.argv=['probe.py','config.json'];"
                    "runpy.run_path('probe.py',run_name='__main__')",
                )
                report["boundaries"] = result.model_dump(mode="json")
                assert result.summary.exit_code == 0, result
                listener.settimeout(0.2)
                with pytest.raises(TimeoutError):
                    listener.accept()
            assert (outside / "sentinel.txt").read_text() == "original"
            assert (readonly / "sentinel.txt").read_text() == "original"
            elapsed = []
            for index in range(20):
                start = time.monotonic()
                result = await run_python(app, context, f"print({index})")
                assert result.summary.exit_code == 0
                elapsed.append(time.monotonic() - start)
                report["commands"] += 1
            parallel = await asyncio.gather(
                *(
                    run_python(
                        app,
                        replace(context, run_id=str(uuid4()), session_id=str(uuid4())),
                        f"from pathlib import Path;Path('parallel-{i}.txt').write_text('{i}')",
                    )
                    for i in range(8)
                )
            )
            assert all(result.summary.exit_code == 0 for result in parallel)
            assert all((root / f"parallel-{i}.txt").read_text() == str(i) for i in range(8))
            report["commands"] += len(parallel)
            report["serial_seconds"] = elapsed
            assert len(list((tmp_path / "data/sandbox-leases").glob("*.json"))) == 1
            report["helper_launches"] = 0
            for operation in ("cancel", "timeout"):
                pidfile = root / (operation + ".json")
                code = (
                    "import subprocess,sys,time,json,os;from pathlib import Path;"
                    "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(300)']);"
                    f"Path({str(pidfile)!r}).write_text(json.dumps([os.getpid(),p.pid]));"
                    "time.sleep(300)"
                )
                task = asyncio.create_task(
                    run_python(app, context, code, 2 if operation == "timeout" else 30)
                )
                async with asyncio.timeout(10):
                    while not pidfile.exists():
                        if task.done():
                            await task
                        await asyncio.sleep(0.05)
                pids = json.loads(pidfile.read_text())
                if operation == "cancel":
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    with pytest.raises(AgentError, match="执行时限") as raised:
                        await task
                    assert raised.value.code == "PROGRAM_TIMEOUT"
                assert all(not alive(pid) for pid in pids)
                report[operation] = {"pids": pids, "exited": True}
                assert (await run_python(app, context, "print('recovered')")).summary.exit_code == 0
        assert not list((tmp_path / "data/sandbox-leases").glob("*.json"))
        report["cleaned"] = True

    try:
        asyncio.run(scenario())
    finally:
        report["seconds"] = time.time() - report["started"]
        (tmp_path / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def test_sandbox_network_multiple_projects_without_elevation(tmp_path, sandbox_runtime):
    """普通用户下运行两个项目及配置变更；HTTP 内容和独立权限均须通过。

    Run projects and configuration changes unelevated, verifying HTTP and separate file access.
    """
    report = {"started": time.time(), "http": [], "identities": [], "elevation_allowed": False}

    async def scenario():
        """生产服务连续启动两个项目，保持 HTTP 内容与文件归属可核对。

        Start two projects through production services with verifiable HTTP content and ownership.
        """
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            contexts = [
                await bind_project(
                    app,
                    tmp_path / f"project-{i}",
                    sandbox_runtime,
                    SandboxSettings(network="enabled"),
                )
                for i in range(2)
            ]
            for index, context in enumerate(contexts):
                (context.root / "index.html").write_text(f"PROJECT-{index}")
                result = await run_python(app, context, "print('start')")
                assert result.summary.exit_code == 0, result
                other = contexts[1 - index].root / "index.html"
                blocked = await run_python(
                    app, context, f"from pathlib import Path;Path({str(other)!r}).write_text('bad')"
                )
                assert blocked.summary.exit_code != 0 and "PermissionError" in str(blocked.output)
                for cycle in range(2):
                    with socket.socket() as probe:
                        probe.bind(("127.0.0.1", 0))
                        port = probe.getsockname()[1]
                    url = f"http://127.0.0.1:{port}"
                    service = await app.programs.start_service(
                        context,
                        StartServiceArgs(
                            command=ProgramCommand(
                                kind="program",
                                program="python",
                                arguments=["-m", "http.server", str(port), "--bind", "127.0.0.1"],
                            ),
                            ready_url=url,
                            ready_timeout_seconds=15,
                        ),
                    )
                    async with httpx.AsyncClient(trust_env=False) as client:
                        response = await client.get(service.summary.url)
                    assert response.status_code == 200 and response.text == f"PROJECT-{index}"
                    await app.programs.stop(service.summary.program_id)
                    with socket.socket() as probe:
                        assert probe.connect_ex(("127.0.0.1", port)) != 0
                    report["http"].append(
                        {"project": index, "cycle": cycle, "status": 200, "port_closed": True}
                    )
            leases = tmp_path / "data/sandbox-leases"
            originals = list(leases.glob("*.json"))
            assert len(originals) == 2
            context = contexts[0]
            catalog = await app.worker.call(app.environments.catalog, context.project_id)
            await app.worker.call(
                app.environments.bind,
                BindEnvironmentParams(
                    **catalog.binding.model_dump(exclude={"sandbox"}),
                    expected_revision=catalog.revision,
                    sandbox=SandboxSettings(network="enabled", authorization_timeout_seconds=90),
                ),
            )
            assert (await run_python(app, context, "print('same')")).summary.exit_code == 0
            assert set(leases.glob("*.json")) == set(originals)
            extra = tmp_path / "extra"
            extra.mkdir()
            catalog = await app.worker.call(app.environments.catalog, context.project_id)
            await app.worker.call(
                app.environments.bind,
                BindEnvironmentParams(
                    **catalog.binding.model_dump(exclude={"sandbox"}),
                    expected_revision=catalog.revision,
                    sandbox=SandboxSettings(network="enabled", read_paths=[str(extra)]),
                ),
            )
            assert (await run_python(app, context, "print('new scope')")).summary.exit_code == 0
            report["identities"] = [json.loads(path.read_text()) for path in leases.glob("*.json")]
            assert len(report["identities"]) == 3
            retained = []
            for index, item in enumerate(contexts):
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", 0))
                    port = probe.getsockname()[1]
                url = f"http://127.0.0.1:{port}"
                running = await app.programs.start_service(
                    item,
                    StartServiceArgs(
                        command=ProgramCommand(
                            kind="program",
                            program="python",
                            arguments=[
                                "-m",
                                "http.server",
                                str(port),
                                "--bind",
                                "127.0.0.1",
                            ],
                        ),
                        ready_url=url,
                        ready_timeout_seconds=15,
                    ),
                )
                retained.append((index, running.summary.url, running.summary.program_id))
            async with httpx.AsyncClient(trust_env=False) as client:
                responses = await asyncio.gather(*(client.get(url) for _, url, _ in retained))
            assert [response.text for response in responses] == ["PROJECT-0", "PROJECT-1"]
            report["simultaneous_services"] = 2
            # 放行联网主体后再创建离线主体，确认规则不是全局放行。
            # A later offline identity must remain blocked while other identities have permits.
            offline = await bind_project(
                app, tmp_path / "offline", sandbox_runtime, SandboxSettings(network="blocked")
            )
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                result = await run_python(
                    app,
                    offline,
                    "import socket;socket.create_connection("
                    f"('127.0.0.1',{listener.getsockname()[1]}),timeout=1)",
                )
                assert result.summary.exit_code != 0
                assert "TimeoutError" in str(result.output) or "PermissionError" in str(
                    result.output
                )
                report["other_identity_network_blocked"] = True
            # 留给真实 app.close 清理，验证无需逐个手动停止。
            # Leave retained services to actual app.close, without manual per-service stops.
            report["retained_pids"] = [app.programs.owned[item[2]].process.pid for item in retained]
        assert not list(leases.glob("*.json"))
        assert all(not alive(pid) for pid in report["retained_pids"])
        assert not list(leases.glob("*/bridge/bridge.exe"))
        report["cleaned"] = True

    try:
        asyncio.run(scenario())
    finally:
        report.update(seconds=time.time() - report["started"])
        (tmp_path / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def test_sandbox_preview_binary_duplex_and_shutdown(tmp_path, sandbox_runtime):
    """普通用户验证大响应、POST、协议升级和带活动连接的退出。

    Verify binary POST, protocol upgrade and active-connection shutdown unelevated.
    """
    report = {}

    def duplex(url):
        """完成真实升级及多轮双向字节交换，保留连接供退出清理。

        Upgrade and exchange bytes repeatedly, retaining the connection for shutdown verification.
        """
        connection = socket.create_connection(("127.0.0.1", urlsplit(url).port), timeout=5)
        connection.sendall(
            b"GET /duplex HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\n\r\n"
        )
        header = b""
        while not header.endswith(b"\r\n\r\n"):
            part = connection.recv(1)
            assert part
            header += part
        assert b"101" in header
        for index in range(3):
            body = bytes(range(256)) * (128 + index)
            connection.sendall(body)
            received = b""
            while len(received) < len(body):
                part = connection.recv(len(body) - len(received))
                assert part
                received += part
            assert received == body
        return connection

    async def scenario():
        """用真实 ProgramService 和 HTTP 客户端验证管道转发。

        Exercise pipe forwarding with production ProgramService and an actual HTTP client.
        """
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            context = await bind_project(
                app, tmp_path / "project", sandbox_runtime, SandboxSettings(network="enabled")
            )
            shutil.copy2(Path(__file__).parents[1] / "fixtures/sandbox_http.py", context.root)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            service = await app.programs.start_service(
                context,
                StartServiceArgs(
                    command=ProgramCommand(
                        kind="program", program="python", arguments=["sandbox_http.py", str(port)]
                    ),
                    ready_url=f"http://127.0.0.1:{port}",
                ),
            )
            url = service.summary.url
            body = bytes(range(256)) * 8192
            async with httpx.AsyncClient(trust_env=False) as client:
                assert (await client.get(url)).content == body
                assert (await client.post(url, content=body)).content == body
            report["binary_get_post_bytes"] = len(body)
            connection = await asyncio.to_thread(duplex, url)
            report["duplex_roundtrips"] = 3
            owned = app.programs.owned[service.summary.program_id]
            preview = owned.preview_task.result()
            with preview.lock:
                pids = [process.pid for process in preview.clients.values() if process]
            assert pids
        assert all(not alive(pid) for pid in pids)
        assert connection.recv(1) == b""
        connection.close()
        with socket.socket() as probe:
            probe.settimeout(1)
            assert probe.connect_ex(("127.0.0.1", urlsplit(url).port)) != 0
        report.update(relays_exited=True, preview_port_closed=True, elevation_allowed=False)

    try:
        asyncio.run(scenario())
    finally:
        (tmp_path / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def test_sandbox_preview_cancel_during_preparation(tmp_path, sandbox_runtime, monkeypatch):
    """准备转发器时取消也回收实际创建的端口与服务。

    Cancellation during preparation reaps the actual preview listener and service.
    """
    entered, release = threading.Event(), threading.Event()
    prepare = preview_module.bridge_executable

    def delayed(process, timeout):
        """建立可复现取消窗口，仍运行真正的准备过程。

        Create a deterministic cancellation window while retaining real preparation.
        """
        entered.set()
        assert release.wait(10)
        return prepare(process, timeout)

    monkeypatch.setattr(preview_module, "bridge_executable", delayed)

    async def scenario():
        """取消请求后等待完整清理，不将线程开始当作已经完成。

        Await cleanup after cancellation, rather than treating thread dispatch as completion.
        """
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            context = await bind_project(
                app, tmp_path / "project", sandbox_runtime, SandboxSettings(network="enabled")
            )
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            pending = asyncio.create_task(
                app.programs.start_service(
                    context,
                    StartServiceArgs(
                        command=ProgramCommand(
                            kind="program",
                            program="python",
                            arguments=["-m", "http.server", str(port), "--bind", "127.0.0.1"],
                        ),
                        ready_url=f"http://127.0.0.1:{port}",
                    ),
                )
            )
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                owned = next(iter(app.programs.owned.values()))
                pending.cancel()
            finally:
                release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(pending, 10)
            assert owned.done.is_set() and not app.programs.owned
            preview = owned.preview_task.result()
            assert preview.closed and not preview.clients and not alive(owned.process.pid)
            with socket.socket() as probe:
                probe.settimeout(1)
                assert probe.connect_ex(("127.0.0.1", urlsplit(preview.url).port)) != 0
        assert not list((tmp_path / "data/sandbox-leases").glob("*.json"))

    asyncio.run(scenario())


@pytest.mark.parametrize("network", ["blocked", "enabled"])
def test_sandbox_crash_and_restart(tmp_path, sandbox_runtime, network):
    """真实终止独立宿主后核对 Job 清理和租约恢复，不重放旧命令。

    Kill a disposable host and verify Job cleanup and lease recovery without replaying commands.
    """

    async def prepare():
        """使用生产环境配置生成子宿主快照。 Build the child snapshot from production settings."""
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            context = await bind_project(
                app, tmp_path / "project", sandbox_runtime, SandboxSettings(network=network)
            )
            view, _, _ = await app.worker.call(app.environments.selected, context.project_id, True)
            (tmp_path / "view.json").write_text(view.model_dump_json(), encoding="utf-8")

    asyncio.run(prepare())
    if network == "enabled":
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        (tmp_path / "port.json").write_text(json.dumps(port))
        (tmp_path / "project/index.html").write_text("CRASH-PROBE")
    with (tmp_path / "host.log").open("w", encoding="utf-8") as output:
        host = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-m", "tests.support.sandbox_crash_host", str(tmp_path)],
            stdout=output,
            stderr=output,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            deadline = time.monotonic() + 30
            while not (tmp_path / "ready.json").exists():
                assert host.poll() is None, (tmp_path / "host.log").read_text()
                assert time.monotonic() < deadline
                time.sleep(0.05)
            ready = json.loads((tmp_path / "ready.json").read_text())
            child = ready["pid"]
            assert ready["elevated"] is False
            assert alive(child)
            if network == "enabled":
                deadline = time.monotonic() + 10
                with httpx.Client(trust_env=False, timeout=1) as client:
                    while True:
                        try:
                            response = client.get(ready["url"])
                            assert response.text == "CRASH-PROBE"
                            break
                        except httpx.ConnectError:
                            assert time.monotonic() < deadline
                            time.sleep(0.05)
            host.kill()
            host.wait(timeout=10)
            deadline = time.monotonic() + 5
            while alive(child) and time.monotonic() < deadline:
                time.sleep(0.05)
            assert not alive(child)
            SandboxLease.recover(tmp_path / "leases")
            assert not list((tmp_path / "leases").glob("*.json"))
            assert not list((tmp_path / "leases").glob("*/bridge/bridge.exe"))
            (tmp_path / "report.json").write_text(
                json.dumps(
                    {
                        "host_killed": True,
                        "child_exited": True,
                        "leases_recovered": True,
                        "network": network,
                        "http_verified": network == "enabled",
                    }
                )
            )
        finally:
            if host.poll() is None:
                host.kill()
                host.wait(timeout=10)
            SandboxLease.recover(tmp_path / "leases")
