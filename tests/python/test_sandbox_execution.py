"""M6 原生沙箱实机验证；显式指定隔离运行时才运行。

M6 native sandbox checks run only with an explicitly supplied isolated runtime.
"""

import asyncio
import os
import shutil
import socket
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from my_agent.config import DEFAULTS
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
from my_agent.runtime.settings import RunLimits
from my_agent.runtime.tools import ToolContext
from my_agent.terminals.types import OpenTerminalParams, ReadTerminalParams, WriteTerminalParams
from tests.python.test_context_memory import KnowledgeModel
from tests.python.test_goal_controller import app_at, create_session


def test_optional_sandbox_recovery_io_failure_does_not_block_direct_mode(tmp_path, monkeypatch):
    """旧沙箱清理的 I/O 故障可见，但不阻断启动及直接执行环境。

    Surface orphan cleanup I/O errors without blocking startup or direct execution selection.
    """

    def unavailable(directory):
        """模拟系统拒绝旧临时目录，不实际修改权限。 Simulate an inaccessible orphan directory."""
        raise PermissionError(directory)

    monkeypatch.setattr(SandboxLease, "recover", unavailable)

    async def scenario():
        """通过真实初始化和环境查询验证边界。 Exercise production initialization and selection."""
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            created = await create_session(app, tmp_path / "project")
            project_id = created.session.project_id
            catalog = await app.worker.call(app.environments.catalog, project_id)
            assert catalog.sandbox_issue and catalog.binding.mode == "direct"
            view, _, _ = await app.worker.call(app.environments.selected, project_id)
            assert view.execution.mode == "direct" and app.initialized

    asyncio.run(scenario())


def test_native_sandbox_shells_without_network(tmp_path):
    """用同一无网络主体运行 PowerShell 和 Node，不重复 HTTP 授权。

    Run PowerShell and Node under one offline identity without repeating HTTP authorization.
    """
    if not os.environ.get("MY_AGENT_TEST_SANDBOX_RUNTIME"):
        pytest.skip("Explicit native sandbox acceptance required")
    node = shutil.which("node.exe")
    if node is None:
        pytest.skip("Node executable unavailable for this compatibility check")
    runtime = tmp_path / "node-runtime"
    runtime.mkdir()
    shutil.copy2(node, runtime / "node.exe")

    async def scenario():
        """使用复制的 Node 与系统 PowerShell，确认内写外拒及子进程。

        Use copied Node and system PowerShell to check writes, denied outside access and children.
        """
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            session = (await create_session(app, tmp_path / "project")).session
            root = tmp_path / "project"
            catalog = await app.worker.call(app.environments.catalog, session.project_id)
            await app.worker.call(
                app.environments.bind,
                BindEnvironmentParams(
                    project_id=session.project_id,
                    environment_id=None,
                    expected_revision=catalog.revision,
                    mode="sandbox",
                    sandbox=SandboxSettings(network="blocked", read_paths=[str(runtime)]),
                ),
            )
            context = ToolContext(
                root,
                RunLimits.model_validate(DEFAULTS["run"]),
                threading.Event(),
                session.project_id,
                session.session_id,
                str(uuid4()),
                "normal",
                None,
            )
            ps = await app.programs.run(
                context,
                RunCommandArgs(
                    command=ShellCommand(
                        kind="powershell",
                        script="Set-Content -LiteralPath ps.txt -Value PS_OK; Write-Output PS_OK",
                    )
                ),
            )
            assert ps.summary.exit_code == 0 and ps.summary.mode == "sandbox", ps
            assert "PS_OK" in (root / "ps.txt").read_text()
            script = (
                "const fs=require('node:fs');"
                "fs.writeFileSync('node.txt','NODE_OK');"
                "try{fs.writeFileSync('../outside.txt','bad');process.exitCode=1;}"
                "catch(e){console.log('DENIED');}"
                "require('node:child_process').execFileSync(process.execPath,"
                "['-e','console.log(123)'],{stdio:'inherit'});"
            )
            result = await app.programs.run(
                context,
                RunCommandArgs(
                    command=ProgramCommand(
                        kind="program", program=str(runtime / "node.exe"), arguments=["-e", script]
                    )
                ),
            )
            assert result.summary.exit_code == 0 and result.summary.mode == "sandbox", result
            assert (root / "node.txt").read_text() == "NODE_OK"
            assert not (tmp_path / "outside.txt").exists()
            assert "DENIED" in str(result.output) and "123" in str(result.output)
            terminal = await app.terminals.open(
                OpenTerminalParams(
                    project_id=session.project_id,
                    session_id=session.session_id,
                    command=ProgramCommand(
                        kind="program", program="powershell.exe", arguments=["-NoProfile"]
                    ),
                )
            )
            await app.terminals.write(
                WriteTerminalParams(
                    terminal_id=terminal.summary.terminal_id,
                    text="Set-Content -LiteralPath terminal.txt -Value TERMINAL_PS_OK; exit\r\n",
                )
            )
            await asyncio.wait_for(
                app.terminals.owned[terminal.summary.terminal_id].done.wait(), 10
            )
            terminal = await app.terminals.read(
                ReadTerminalParams(terminal_id=terminal.summary.terminal_id)
            )
            assert terminal.summary.exit_code == 0 and terminal.summary.mode == "sandbox", terminal
            assert "TERMINAL_PS_OK" in (root / "terminal.txt").read_text()
        assert list((tmp_path / "data/sandbox-leases").glob("*.json")) == []

    asyncio.run(scenario())


def test_native_sandbox_command_terminal_and_service(tmp_path):
    """使用生产服务验证文件边界、进程、HTTP 和终端清理，不修改系统环境。

    Verify production execution, file boundaries, HTTP and terminal cleanup using copied runtime.
    """
    supplied = os.environ.get("MY_AGENT_TEST_SANDBOX_RUNTIME")
    if not supplied:
        pytest.skip("Explicit copied runtime required for native sandbox check")
    runtime = Path(supplied).resolve(strict=True)
    artifacts = Path(__file__).resolve().parents[2] / ".artifacts/tests"
    assert runtime.is_relative_to(artifacts.resolve())

    async def scenario():
        """同一设置覆盖三种执行入口。 Use the same settings for three execution entry points."""
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            created = await create_session(app, tmp_path / "project")
            session = created.session
            root = tmp_path / "project"
            outside = tmp_path / "outside.txt"
            catalog = await app.worker.call(app.environments.catalog, session.project_id)
            catalog = await app.worker.call(
                app.environments.save,
                SaveEnvironmentParams(
                    project_id=session.project_id,
                    environment_id=None,
                    expected_revision=catalog.revision,
                    name="Isolated Python copy",
                    definition=PythonEnvironment(
                        kind="python", scope="absolute", interpreter=str(runtime / "python.exe")
                    ),
                ),
            )
            await app.worker.call(
                app.environments.bind,
                BindEnvironmentParams(
                    project_id=session.project_id,
                    environment_id=catalog.environments[0].record.environment_id,
                    expected_revision=catalog.revision,
                    mode="sandbox",
                    sandbox=SandboxSettings(network="enabled"),
                ),
            )
            context = ToolContext(
                root,
                RunLimits.model_validate(DEFAULTS["run"]),
                threading.Event(),
                session.project_id,
                session.session_id,
                str(uuid4()),
                "normal",
                None,
            )
            (root / "probe.py").write_text(
                "from pathlib import Path\nimport subprocess,sys\n"
                "Path('inside.txt').write_text('inside')\n"
                f"try: Path({str(outside)!r}).write_text('outside')\n"
                "except PermissionError: print('DENIED', flush=True)\n"
                "subprocess.run([sys.executable,'-c','print(123)'],check=True)\n",
                encoding="utf-8",
            )
            result = await app.programs.run(
                context,
                RunCommandArgs(
                    command=ProgramCommand(
                        kind="program", program="python", arguments=["probe.py"]
                    ),
                ),
            )
            assert result.summary.mode == "sandbox" and result.summary.exit_code == 0
            assert (root / "inside.txt").read_text() == "inside" and not outside.exists()
            assert "DENIED" in str(result.output) and "123" in str(result.output)
            terminal = await app.terminals.open(
                OpenTerminalParams(
                    project_id=session.project_id,
                    session_id=session.session_id,
                    command=ProgramCommand(
                        kind="program", program="cmd.exe", arguments=["/d", "/q"]
                    ),
                )
            )
            await app.terminals.write(
                WriteTerminalParams(
                    terminal_id=terminal.summary.terminal_id,
                    text="echo TERMINAL_OK\r\nexit\r\n",
                )
            )
            await asyncio.wait_for(
                app.terminals.owned[terminal.summary.terminal_id].done.wait(), 10
            )
            terminal = await app.terminals.read(
                ReadTerminalParams(terminal_id=terminal.summary.terminal_id)
            )
            assert terminal.summary.mode == "sandbox" and terminal.summary.exit_code == 0
            assert "TERMINAL_OK" in str(terminal.output)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            service = await app.programs.start_service(
                context,
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
                    ready_url=f"http://127.0.0.1:{port}",
                    ready_timeout_seconds=10,
                ),
            )
            assert service.summary.status == "ready" and service.summary.mode == "sandbox"
            await app.programs.stop(service.summary.program_id)
        assert list((tmp_path / "data/sandbox-leases").glob("*.json")) == []

    asyncio.run(scenario())
