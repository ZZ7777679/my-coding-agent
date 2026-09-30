"""Windows 实际进程所有权和输出验证。

Real Windows process ownership and output checks."""

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from my_agent.execution.windows import WindowsProcess
from my_agent.processes import probe_environment


def test_program_tools_json_commands_and_service(tmp_path, monkeypatch):
    """经实际工具入口执行 JSON 包装命令和服务，并区分输入与内部错误。

    Execute JSON-wrapped commands and services; distinguish input errors from internal failures.
    """
    import asyncio
    import socket
    import threading
    from uuid import uuid4

    import pytest
    from pydantic import ValidationError

    from my_agent.changes.store import ChangeStore
    from my_agent.config import DEFAULTS, resolve_data_dir
    from my_agent.execution.environments import EnvironmentStore
    from my_agent.execution.service import ProgramService
    from my_agent.execution.store import ProgramStore
    from my_agent.execution.types import ProgramView, ProjectExecution, RunCommandArgs
    from my_agent.models.types import ToolCall
    from my_agent.projects import ProjectService
    from my_agent.runtime.settings import RunLimits
    from my_agent.runtime.tools import ToolContext
    from my_agent.storage import Storage, write_document
    from my_agent.tools.files import FileCoordinator, FileTools
    from my_agent.tools.programs import ProjectTools
    from my_agent.worker import BusinessWorker

    # 隔离进程的 PATH 优先当前测试解释器，不更改机器环境。
    # Prefer this test interpreter in the child PATH without changing machine settings.
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"])
    root = tmp_path / "project"
    root.mkdir()
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    worker = BusinessWorker()
    envs = EnvironmentStore(storage)
    service = ProgramService(envs, ProgramStore(storage), worker)

    async def scenario():
        """只启动隔离项目中的短命令与环回服务，最后清理实际进程。

        Run short commands and a loopback service in isolation, cleaning up owned processes.
        """
        project = ProjectService(storage).open(path=str(root)).active_project
        assert project
        assert not envs.path.exists()
        context = ToolContext(
            root,
            RunLimits.model_validate(DEFAULTS["run"]),
            threading.Event(),
            project.project_id,
            str(uuid4()),
            str(uuid4()),
            "normal",
            None,
        )
        tools = ProjectTools(
            context, FileTools(context, ChangeStore(storage), worker, FileCoordinator()), service
        )
        command = {
            "kind": "program",
            "program": "node",
            "arguments": ["-e", "console.log('harness exec works,', 1+1)"],
        }
        cases = [
            (command, "harness exec works, 2"),
            (json.dumps(command), "harness exec works, 2"),
            (json.dumps(command, sort_keys=True), "harness exec works, 2"),
            (
                json.dumps(
                    {"kind": "powershell", "script": "Write-Output 'harness exec works, ${(6*7)}'"}
                ),
                "harness exec works, ${(6*7)}",
            ),
            (json.dumps({"kind": "powershell", "script": "Get-Location"}), "Path"),
            (json.dumps({"kind": "powershell", "script": "(Get-Location).Path"}), str(root)),
        ]
        try:
            environment = await tools.execute(
                ToolCall(tool_call_id=str(uuid4()), name="execution_environment", arguments={})
            )
            assert not environment.is_error
            assert "trusted" not in json.loads(environment.content)["binding"]
            python_probe = await tools.execute(
                ToolCall(tool_call_id=str(uuid4()), name="inspect_python", arguments={})
            )
            assert not python_probe.is_error, python_probe.content
            inspected = json.loads(python_probe.content)
            assert inspected["code"] == "PYTHON_READY"
            assert inspected["version"] == sys.version.split()[0]
            assert Path(inspected["interpreter"]).resolve() == Path(sys.executable).resolve()
            for command_input, expected in cases:
                call = ToolCall(
                    tool_call_id=str(uuid4()),
                    name="run_command",
                    arguments={"command": command_input},
                )
                result = await tools.execute(call)
                assert not result.is_error, result.content
                view = ProgramView.model_validate_json(result.content)
                assert view.summary.exit_code == 0 and view.summary.pid is not None
                assert view.summary.cwd == str(root)
                assert expected in "".join(
                    chunk.text for chunk in view.output if chunk.stream == "stdout"
                )
                assert call.arguments["command"] == command_input

            assert not envs.path.exists()
            # 旧配置里的 false 只作为兼容数据读取，不再阻断服务或要求重新保存设置。
            # A legacy false flag must not block services or require resaving settings.
            write_document(
                envs.path,
                envs.read().model_copy(
                    update={
                        "bindings": [
                            ProjectExecution(
                                project_id=project.project_id,
                                environment_id=None,
                                mode="direct",
                                trusted=False,
                            )
                        ]
                    }
                ),
            )
            with socket.socket() as port_socket:
                port_socket.bind(("127.0.0.1", 0))
                port = port_socket.getsockname()[1]
            result = await tools.execute(
                ToolCall(
                    tool_call_id=str(uuid4()),
                    name="start_service",
                    arguments={
                        "command": json.dumps(
                            {
                                "kind": "program",
                                "program": sys.executable,
                                "arguments": [
                                    "-m",
                                    "http.server",
                                    str(port),
                                    "--bind",
                                    "127.0.0.1",
                                ],
                            }
                        ),
                        "ready_url": f"http://127.0.0.1:{port}/",
                    },
                )
            )
            assert not result.is_error, result.content
            ready = ProgramView.model_validate_json(result.content)
            assert ready.summary.status == "ready" and ready.summary.http_status == 200
            for name in ("read_program", "stop_program"):
                result = await tools.execute(
                    ToolCall(
                        tool_call_id=str(uuid4()),
                        name=name,
                        arguments={"program_id": ready.summary.program_id},
                    )
                )
                assert not result.is_error, result.content
            assert ProgramView.model_validate_json(result.content).summary.status == "stopped"

            invalid = await tools.execute(
                ToolCall(
                    tool_call_id=str(uuid4()),
                    name="run_command",
                    arguments={"command": json.dumps({"kind": "powershell"})},
                )
            )
            failure = json.loads(invalid.content)
            assert invalid.is_error and failure["code"] == "INVALID_TOOL_ARGUMENTS"
            assert "command.ShellCommand.script" in failure["message"]
            assert "Field required" in failure["message"]

            async def broken_service(*args):
                """模拟参数解析之后的内部失败，不能再归因到模型输入。

                Simulate an internal failure after argument parsing, not a model-input error.
                """
                RunCommandArgs.model_validate({"command": {}})

            monkeypatch.setattr(service, "run", broken_service)
            with pytest.raises(ValidationError):
                await tools.execute(
                    ToolCall(
                        tool_call_id=str(uuid4()),
                        name="run_command",
                        arguments={"command": command},
                    )
                )
        finally:
            await service.close()

    with storage.writer():
        try:
            asyncio.run(scenario())
        finally:
            worker.close()


def test_cwd_accepts_absolute_project_path_without_escape(tmp_path):
    """项目绝对路径可复用，真实项目外目录仍拒绝。

    Reuse absolute project paths while rejecting directories outside the canonical project.
    """
    import pytest

    from my_agent.errors import AgentError
    from my_agent.execution.commands import working_directory

    project = tmp_path / "项目 空格"
    child = project / "src"
    child.mkdir(parents=True)
    sibling = tmp_path / "项目 空格-other"
    sibling.mkdir()
    assert working_directory(project, ".") == project.resolve()
    assert working_directory(project, str(project)) == project.resolve()
    assert working_directory(project, str(child)) == child.resolve()
    for outside in (tmp_path, sibling):
        with pytest.raises(AgentError) as failed:
            working_directory(project, str(outside))
        assert failed.value.code == "PROGRAM_CWD_INVALID"


def test_project_environment_commands_and_service_lifecycle(tmp_path, monkeypatch):
    """验证项目绑定、实际结果、取消与服务保留 / 退出。

    Verify bindings, actual results, cancellation and retained-service cleanup.
    """
    import asyncio
    import socket
    import threading
    from uuid import uuid4

    import pytest

    from my_agent.config import DEFAULTS, resolve_data_dir
    from my_agent.errors import AgentError
    from my_agent.execution.environments import EnvironmentStore
    from my_agent.execution.service import ProgramService
    from my_agent.execution.store import ProgramStore
    from my_agent.execution.types import (
        BindEnvironmentParams,
        EnvironmentParams,
        GetProgramParams,
        ProgramCommand,
        PythonEnvironment,
        RunCommandArgs,
        SaveEnvironmentParams,
        ShellCommand,
        StartServiceArgs,
    )
    from my_agent.projects import ProjectService
    from my_agent.runtime.settings import RunLimits
    from my_agent.runtime.tools import ToolContext
    from my_agent.storage import Storage
    from my_agent.worker import BusinessWorker

    root = tmp_path / "项目 空格"
    root.mkdir()
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    worker = BusinessWorker()
    envs = EnvironmentStore(storage)
    service = ProgramService(envs, ProgramStore(storage), worker)
    monkeypatch.setenv("OPENCODE_API_KEY", "test-only-credential")

    async def scenario():
        """全部执行位于隔离项目，结束时清理本场景所有进程。

        Execute only in the isolated project and clean up every owned process.
        """
        project = ProjectService(storage).open(path=str(root)).active_project
        assert project
        context = ToolContext(
            root,
            RunLimits.model_validate(DEFAULTS["run"]),
            threading.Event(),
            project.project_id,
            str(uuid4()),
            str(uuid4()),
            "normal",
            None,
        )
        catalog = envs.save(
            SaveEnvironmentParams(
                project_id=project.project_id,
                expected_revision=0,
                environment_id=None,
                name="Existing Python",
                definition=PythonEnvironment(
                    kind="python", scope="absolute", interpreter=sys.executable
                ),
            )
        )
        identifier = catalog.environments[0].record.environment_id
        assert catalog.environments[0].record.probe is None
        command = RunCommandArgs(
            command=ProgramCommand(
                kind="program",
                program="python",
                arguments=[
                    "-c",
                    "import os,sys; print('code-result',os.getenv('OPENCODE_API_KEY')); "
                    "sys.exit(7)",
                ],
            )
        )
        assert envs.selected(project.project_id)[0].record.definition.kind == "system"
        catalog = envs.bind(
            BindEnvironmentParams(
                project_id=project.project_id,
                environment_id=identifier,
                trusted=True,
                mode="direct",
                expected_revision=catalog.revision,
            )
        )
        catalog = await service.probe(
            EnvironmentParams(project_id=project.project_id, environment_id=identifier)
        )
        assert catalog.environments[0].record.probe.code == "ENVIRONMENT_READY"
        assert catalog.environments[0].record.probe.version == sys.version.split()[0]
        view = await service.run(context, command)
        assert view.summary.status == "exited" and view.summary.exit_code == 7
        assert "code-result None" in "".join(item.text for item in view.output)
        shell = await service.run(
            context,
            RunCommandArgs(
                command=ShellCommand(kind="powershell", script="Write-Output '中文 shell'; exit 3")
            ),
        )
        assert shell.summary.exit_code == 3 and "中文 shell" in "".join(
            v.text for v in shell.output
        )

        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            port = port_socket.getsockname()[1]
        args = StartServiceArgs(
            command=ProgramCommand(
                kind="program",
                program="python",
                arguments=["-m", "http.server", str(port), "--bind", "127.0.0.1"],
            ),
            ready_url=f"http://127.0.0.1:{port}/",
            ready_timeout_seconds=5,
        )
        ready = await service.start_service(context, args)
        assert ready.summary.status == "ready" and ready.summary.http_status == 200
        assert ready.summary.retained
        await service.finish_run(context.run_id)
        assert (
            await service.get(GetProgramParams(program_id=ready.summary.program_id))
        ).summary.retained
        # 第二次启动同端口必须失败，不能把第一次服务当成自己的就绪结果。
        # A second launch on this port must fail without claiming or killing the first service.
        with pytest.raises(AgentError) as collision:
            await service.start_service(context, args)
        assert collision.value.code == "SERVICE_PORT_IN_USE"
        assert not service.owned[ready.summary.program_id].done.is_set()

        sleeper = RunCommandArgs(
            command=ProgramCommand(
                kind="program", program="python", arguments=["-c", "import time; time.sleep(30)"]
            ),
            timeout_seconds=1,
        )
        with pytest.raises(AgentError) as timed_out:
            await service.run(context, sleeper)
        assert timed_out.value.code == "PROGRAM_TIMEOUT"
        cancel = asyncio.create_task(
            service.run(context, sleeper.model_copy(update={"timeout_seconds": 30}))
        )
        for _ in range(100):
            if any(p.record.summary.kind == "command" for p in service.owned.values()):
                break
            await asyncio.sleep(0.02)
        cancel.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancel
        assert all(p.record.summary.kind == "service" for p in service.owned.values())
        await service.close()
        stopped = service.store.load(ready.summary.program_id)
        assert stopped.summary.status == "stopped"
        # 历史 PID 即使碰巧是仍存活进程也不能接管；这里只标记未知结果。
        # Historical PIDs never confer ownership, even when they still refer to a live process.
        stopped.summary.status = "ready"
        stopped.summary.pid = __import__("os").getpid()
        service.store.save(stopped)
        reopened = ProgramService(EnvironmentStore(storage), ProgramStore(storage), worker)
        await reopened.recover()
        assert (
            await reopened.get(GetProgramParams(program_id=stopped.summary.program_id))
        ).summary.status == "interrupted"
        await reopened.close()

    with storage.writer():
        try:
            asyncio.run(scenario())
        finally:
            asyncio.run(service.close())
            worker.close()


def wait_exit(process, seconds=5):
    """等待本测试创建的根进程结束。

    Wait for this test's root process to exit."""
    deadline = time.monotonic() + seconds
    while process.poll() is None:
        if time.monotonic() > deadline:
            raise AssertionError("Owned test process did not exit")
        time.sleep(0.01)
    return process.poll()


def test_environment_reference_failure_and_default_system_snapshot(tmp_path, monkeypatch):
    """显式绑定失效不回退；无绑定可用本机工具，后续设置不重复审批已接纳启动。

    Reject stale bindings, use system tools when unbound, and snapshot each admitted launch.
    """
    import asyncio
    import threading
    from pathlib import Path
    from uuid import uuid4

    import pytest

    from my_agent.config import DEFAULTS, resolve_data_dir
    from my_agent.errors import AgentError
    from my_agent.execution.environments import EnvironmentStore, executable
    from my_agent.execution.service import ProgramService
    from my_agent.execution.store import ProgramStore
    from my_agent.execution.types import (
        BindEnvironmentParams,
        ProgramCommand,
        PythonEnvironment,
        RunCommandArgs,
        SaveEnvironmentParams,
        SystemEnvironment,
    )
    from my_agent.projects import ProjectService
    from my_agent.runtime.settings import RunLimits
    from my_agent.runtime.tools import ToolContext
    from my_agent.storage import Storage
    from my_agent.worker import BusinessWorker

    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("CUSTOM_BUILD_HOME", "build-fixture")
    monkeypatch.setenv("OPENCODE_API_KEY", "sentinel-only")
    monkeypatch.setenv("MY_AGENT_DATA_DIR", "app-fixture")
    reference = root / "python.exe"
    reference.write_bytes(b"Not executed during import")
    monkeypatch.chdir(root)
    assert executable("python", {"PATH": str(Path(sys.executable).parent)}, root) == str(
        Path(sys.executable).resolve()
    )
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    worker = BusinessWorker()
    envs = EnvironmentStore(storage)
    with storage.writer():
        project = ProjectService(storage).open(path=str(root)).active_project
        catalog = envs.save(
            SaveEnvironmentParams(
                project_id=project.project_id,
                expected_revision=0,
                environment_id=None,
                name="Project reference",
                definition=PythonEnvironment(
                    kind="python", scope="project", interpreter="python.exe"
                ),
            )
        )
        identifier = catalog.environments[0].record.environment_id
        binding = BindEnvironmentParams(
            project_id=project.project_id,
            environment_id=identifier,
            trusted=True,
            mode="direct",
            expected_revision=catalog.revision,
        )
        envs.bind(binding)
        with pytest.raises(AgentError) as stale:
            envs.bind(binding)
        assert stale.value.code == "ENVIRONMENT_REVISION_CONFLICT"
        reference.unlink()
        with pytest.raises(AgentError) as missing:
            envs.selected(project.project_id)
        assert missing.value.code == "ENVIRONMENT_UNAVAILABLE"
        envs.bind(
            BindEnvironmentParams(
                project_id=project.project_id,
                environment_id=None,
                trusted=True,
                mode="direct",
                expected_revision=envs.read().revision,
            )
        )
        default_view, _, _ = envs.selected(project.project_id)
        assert isinstance(default_view.record.definition, SystemEnvironment)
        assert envs.catalog(project.project_id).binding.environment_id is None
        service = ProgramService(envs, ProgramStore(storage), worker)
        original_save = service.store.save

        def change_mode_after_intent(record):
            """准备落盘后切换执行方式，下次启动才采用新方式。

            Change execution mode after admission; only the next launch adopts it.
            """
            original_save(record)
            if record.summary.status == "starting":
                envs.bind(
                    binding.model_copy(
                        update={
                            "mode": "sandbox",
                            "environment_id": None,
                            "expected_revision": envs.read().revision,
                        }
                    )
                )

        monkeypatch.setattr(service.store, "save", change_mode_after_intent)
        context = ToolContext(
            root,
            RunLimits.model_validate(DEFAULTS["run"]),
            threading.Event(),
            project.project_id,
            str(uuid4()),
            str(uuid4()),
            "normal",
            None,
        )

        async def scenario():
            """已接纳启动使用快照，显式沙箱选择影响下一次启动。

            The admitted launch uses its snapshot; sandbox selection affects the next launch."""
            try:
                command = RunCommandArgs(
                    command=ProgramCommand(
                        kind="program",
                        program=sys.executable,
                        arguments=[
                            "-c",
                            "import os; assert os.getenv('CUSTOM_BUILD_HOME') == 'build-fixture'; "
                            "assert os.getenv('OPENCODE_API_KEY') is None; "
                            "assert os.getenv('MY_AGENT_DATA_DIR') is None; raise SystemExit(99)",
                        ],
                    )
                )
                result = await service.run(context, command)
                assert result.summary.status == "exited" and result.summary.exit_code == 99
                with pytest.raises(AgentError) as sandbox:
                    await service.run(context, command)
                assert sandbox.value.code == "SANDBOX_UNAVAILABLE"
                records, unavailable = service.store.records()
                assert unavailable == 0 and len(records) == 1
                assert records[0].summary.status == "exited"
            finally:
                await service.close()

        try:
            asyncio.run(scenario())
            monkeypatch.chdir(tmp_path)
            # 只删除本场景空目录；登记保留 / remove this empty fixture, preserving registration.
            root.rmdir()
            envs.bind(
                binding.model_copy(
                    update={"environment_id": None, "expected_revision": envs.read().revision}
                )
            )
            assert (
                EnvironmentStore(storage).catalog(project.project_id).binding.environment_id is None
            )
            storage_bytes = envs.path.read_bytes()
            envs.path.write_bytes(b"{")
            with pytest.raises(AgentError):
                envs.read()
            assert envs.path.read_bytes() == b"{"
            envs.path.write_bytes(storage_bytes)
        finally:
            worker.close()


def process_handle(pid):
    """打开观察句柄，避免按复用后的 PID 判断。

    Hold an observation handle independent of PID reuse."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    assert handle
    return kernel, handle


def test_native_arguments_environment_and_bounded_output(tmp_path, monkeypatch):
    """真实传递参数，白名单不继承模型 key，超量持续消费。

    Check arguments, env and output draining."""
    monkeypatch.setenv("OPENCODE_API_KEY", "test-only-credential")
    env = {**probe_environment(), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    directory = tmp_path / "中文 空格"
    directory.mkdir()
    code = (
        "import json,os,sys; print(json.dumps([sys.argv[1:],os.getcwd(),"
        "os.getenv('OPENCODE_API_KEY')],ensure_ascii=False)); sys.exit(7)"
    )
    arguments = ["a b", 'quote"value', "末尾\\", "&literal"]
    process = WindowsProcess([sys.executable, "-u", "-c", code, *arguments], directory, env, 16384)
    try:
        assert wait_exit(process) == 7
        process.finish(5)
        chunks, dropped = process.drain()
        value = json.loads(b"".join(data for stream, data in chunks if stream == "stdout"))
        assert value == [arguments, str(directory), None] and dropped == 0
    finally:
        process.close()
    noisy = WindowsProcess(
        [
            sys.executable,
            "-u",
            "-c",
            "import sys; sys.stdout.write('x'*100000); sys.stderr.write('y'*100000)",
        ],
        directory,
        env,
        1024,
    )
    try:
        assert wait_exit(noisy) == 0
        noisy.finish(5)
        chunks, dropped = noisy.drain()
        assert sum(len(data) for _, data in chunks) <= 1024 and dropped > 0
    finally:
        noisy.close()


def test_owned_tree_cleanup_and_owner_death(tmp_path):
    """主动停止和宿主异常退出均不留下自有子树。

    Reap descendants after explicit stop or owner death."""
    env = {**probe_environment(), "PYTHONUTF8": "1"}
    child_path = tmp_path / "child.txt"
    code = (
        "import subprocess,sys,pathlib,time; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(60)"
    )
    process = WindowsProcess([sys.executable, "-c", code, str(child_path)], tmp_path, env, 16384)
    try:
        deadline = time.monotonic() + 5
        while not child_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        kernel, child = process_handle(int(child_path.read_text()))
        try:
            process.terminate()
            process.finish(5)
            # TerminateJobObject 发起异步终止，内核句柄发信号可能略晚于 Job 计数归零。
            # Termination is asynchronous; wait for the observed child handle to become signalled.
            assert kernel.WaitForSingleObject(child, 5000) == 0
        finally:
            kernel.CloseHandle(child)
    finally:
        process.close()
    # 模拟后端突然退出；子进程不能继承 Job 句柄来延长生命周期。
    # Simulate abrupt backend death; children must not inherit the job handle.
    owner_code = (
        "import sys,pathlib; from my_agent.execution.windows import WindowsProcess; "
        "from my_agent.processes import probe_environment; "
        "p=WindowsProcess([sys.executable,'-c','import time; time.sleep(60)'],"
        "pathlib.Path(sys.argv[1]),probe_environment(),16384); "
        "print(p.pid,flush=True); sys.stdin.readline()"
    )
    owner = subprocess.Popen(
        [sys.executable, "-u", "-c", owner_code, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        kernel, child = process_handle(int(owner.stdout.readline()))
        try:
            owner.kill()
            owner.wait(5)
            assert kernel.WaitForSingleObject(child, 5000) == 0
        finally:
            kernel.CloseHandle(child)
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.communicate(timeout=5)
