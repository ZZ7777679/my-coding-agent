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


def command_line(
    command: Command, view: EnvironmentView, cwd: Path
) -> tuple[list[str], dict[str, str]]:
    """解析实际 exe / argv，Conda 显式使用 prefix，uv 不隐式同步。

    Resolve actual argv, use the selected Conda prefix, and never implicitly run uv sync.
    """
    env = execution_environment(view)
    if command.kind == "powershell":
        # EncodedCommand 避免跨 shell 转义；仍是显式、未隔离的任意脚本执行。
        # EncodedCommand avoids cross-shell quoting; this remains explicit unrestricted execution.
        script = (
            "$ErrorActionPreference = 'Stop'\n"
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
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
    if view.record.definition.kind == "conda":
        if not view.launcher or not view.prefix:
            raise AgentError("ENVIRONMENT_UNAVAILABLE", "Conda 入口或 prefix 已失效。")
        argv = [view.launcher, "run", "--prefix", view.prefix, "--no-capture-output", *argv]
    return argv, env
