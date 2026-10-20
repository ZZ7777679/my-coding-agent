"""明确解析项目命令与已有环境，不安装依赖。

Resolve project commands without installing dependencies."""

import base64
from pathlib import Path

from my_agent.errors import AgentError
from my_agent.execution.environments import executable, execution_environment
from my_agent.execution.types import Command, EnvironmentView
from my_agent.tools.policy import relative_path


def working_directory(root: Path, value: str) -> Path:
    """接受项目内的相对或绝对 cwd，仍核对真实目录归属。

    Accept relative or absolute cwd while checking canonical project containment."""
    try:
        base = root.resolve(strict=True)
        selected = Path(value)
        target = (
            selected if selected.is_absolute() else base.joinpath(*relative_path(value).parts)
        ).resolve(strict=True)
        if not target.is_dir() or not target.is_relative_to(base):
            raise OSError
        return target
    except (OSError, RuntimeError, ValueError) as exc:
        raise AgentError("PROGRAM_CWD_INVALID", "命令工作目录不存在或已超出项目范围。") from exc


def powershell_location(cwd: Path, sandboxed: bool) -> str:
    """设置真实项目位置；沙箱拒绝卷根元数据时仅用项目 PSDrive 兼容。

    Select the real project; use a project PSDrive only when sandbox volume metadata is denied.
    """
    literal = str(cwd).replace("'", "''")
    location = (
        "Set-Location -LiteralPath 'Microsoft.PowerShell.Core\\FileSystem::"
        + literal
        + "' -ErrorAction Stop\n"
    )
    if not sandboxed:
        return location
    # PSDrive 映射不修改原生 cwd 或系统权限；ProviderPath 仍为实际项目绝对路径。
    # The PSDrive changes neither native cwd nor permissions; ProviderPath remains the real path.
    return (
        "try {\n" + location + "} catch [System.UnauthorizedAccessException] {\n"
        "New-PSDrive -Name MyAgentProject -PSProvider FileSystem -Root '"
        + literal
        + "' -Scope Global -ErrorAction Stop | Out-Null\n"
        "Set-Location -LiteralPath 'MyAgentProject:\\' -ErrorAction Stop\n}\n"
    )


def command_line(
    command: Command, view: EnvironmentView, cwd: Path, *, interactive: bool = False
) -> tuple[list[str], dict[str, str]]:
    """解析实际 exe / argv，Conda 显式使用 prefix，uv 不隐式同步。

    Resolve actual argv, use the selected Conda prefix, and never implicitly run uv sync.
    """
    env = execution_environment(view)
    sandboxed = view.execution is not None and view.execution.mode == "sandbox"
    if command.kind == "powershell":
        # EncodedCommand 只处理转义；是否隔离由随后选定的执行后端决定。
        # EncodedCommand handles quoting only; the selected launch backend supplies isolation.
        script = (
            "$ErrorActionPreference = 'Stop'\n"
            + powershell_location(cwd, sandboxed)
            + "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
            "$OutputEncoding = [Console]::OutputEncoding\n"
            "$global:LASTEXITCODE = 0\n"
            ". {\n"
            + command.script
            # 先结束输出管线，避免 exit 丢弃 Get-Location 等对象的延迟格式化。
            # Finish the output pipeline before exit so deferred object formatting is flushed.
            + "\n} | Out-Default\nif ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }\n"
        )
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        argv = [
            executable("powershell.exe", env, cwd),
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded,
        ]
    else:
        name = command.program
        arguments = list(command.arguments)
        if name.casefold() in {"python", "python.exe", "python3", "pip", "pip.exe", "pip3"}:
            if view.record.definition.kind != "system":
                if view.interpreter is None:
                    raise AgentError("ENVIRONMENT_NO_PYTHON", "所选环境没有可用的 Python 解释器。")
                if name.casefold().startswith("pip"):
                    arguments = ["-m", "pip", *arguments]
                name = view.interpreter
        elif name.casefold() in {"uv", "uv.exe", "conda", "conda.exe"}:
            if view.launcher and name.casefold().split(".")[0] == view.record.definition.kind:
                name = view.launcher
        argv = [executable(name, env, cwd), *arguments]
        if (
            interactive
            and sandboxed
            and Path(argv[0]).name.casefold() in {"powershell.exe", "pwsh.exe"}
            and all(
                value.casefold() in {"-nologo", "-noprofile", "-noexit", "-sta", "-mta"}
                for value in arguments
            )
        ):
            # 仅补普通交互启动，不改写用户明确提供的 -Command/-File/其他启动参数。
            # Initialize plain interactive shells only; preserve explicit scripts and other options.
            if not any(value.casefold() == "-noexit" for value in arguments):
                argv.append("-NoExit")
            argv.extend(
                [
                    "-EncodedCommand",
                    base64.b64encode(powershell_location(cwd, True).encode("utf-16le")).decode(
                        "ascii"
                    ),
                ]
            )
    if view.record.definition.kind == "conda":
        if not view.launcher or not view.prefix:
            raise AgentError("ENVIRONMENT_UNAVAILABLE", "Conda 入口或 prefix 已失效。")
        argv = [view.launcher, "run", "--prefix", view.prefix, "--no-capture-output", *argv]
    return argv, env
