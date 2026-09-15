"""CLI 适配层，与桌面 RPC 共用配置、诊断和项目服务。

CLI adapter sharing configuration, diagnostics and project services with desktop RPC.
"""

import io
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated

import typer
from pydantic import BaseModel

from my_agent import __version__
from my_agent.config import load_config, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.diagnostics import diagnose
from my_agent.errors import AgentError
from my_agent.projects import ProjectService
from my_agent.rpc.server import read_parent_credential
from my_agent.rpc.server import serve as run_server
from my_agent.storage import Storage

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
config_app = typer.Typer(no_args_is_help=True)
projects_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(projects_app, name="projects")


def entrypoint() -> None:
    """统一终端输出为 UTF-8 后启动命令分发。

    Set terminal streams to UTF-8 before dispatching CLI commands.
    """

    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    app()


@dataclass(frozen=True)
class Options:
    """保存一次 CLI 调用的数据根与模型覆盖参数。

    Hold data-root and model overrides for one CLI invocation.
    """

    data_dir: str | None
    model: str | None


def options(ctx: typer.Context) -> Options:
    """读取已初始化的 CLI 参数；缺少装配时明确失败。

    Read initialized CLI options, failing explicitly if setup was skipped.
    """

    if not isinstance(ctx.obj, Options):
        raise RuntimeError("CLI options were not initialized")
    return ctx.obj


def show_version(value: bool) -> None:
    """处理提前退出的版本选项，不初始化业务存储。

    Handle the eager version option without initializing application storage.
    """

    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    data_dir: Annotated[str | None, typer.Option("--data-dir")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    version: bool = typer.Option(False, "--version", callback=show_version, is_eager=True),
) -> None:
    """My Coding Agent 本地工程入口，提供配置、项目与诊断命令。

    Local My Coding Agent entry point for configuration, projects and diagnostics.
    """
    ctx.obj = Options(data_dir, model)


@contextmanager
def report_errors(as_json: bool) -> Iterator[None]:
    """把业务错误转为脱敏输出和非零退出码，JSON 模式保持单个对象。

    Render public errors with a nonzero exit code and a single object in JSON mode.
    """

    try:
        yield
    except AgentError as exc:
        if as_json:
            typer.echo(
                json.dumps(
                    {
                        "error": {
                            "code": exc.code,
                            "message": exc.message,
                            "remediation": exc.remediation,
                        }
                    },
                    ensure_ascii=False,
                )
            )
        else:
            typer.echo(exc.code + ": " + exc.message, err=True)
        raise typer.Exit(1) from None


def output(value: BaseModel, as_json: bool) -> None:
    """输出公开 DTO；JSON 模式使用紧凑格式。

    Print a public DTO, using compact output in JSON mode.
    """

    typer.echo(value.model_dump_json(indent=None if as_json else 2))


@config_app.command("show")
def config_show(
    ctx: typer.Context,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """只读查看当前模型配置与凭据来源，不显示密钥。

    Inspect model configuration and credential metadata without revealing secrets.
    """

    with report_errors(as_json):
        args = options(ctx)
        config = load_config(resolve_data_dir(args.data_dir), args.model)
        output(config.public(resolve_credential().info), as_json)


@projects_app.command("list")
def projects_list(
    ctx: typer.Context,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """只读列出最近项目，并标明目录当前是否可用。

    List recent projects read-only, including their current availability.
    """

    with report_errors(as_json):
        storage = Storage(resolve_data_dir(options(ctx).data_dir))
        storage.validate_metadata()
        output(ProjectService(storage).view(), as_json)


@projects_app.command("open")
def projects_open(
    ctx: typer.Context,
    root: Annotated[str | None, typer.Option("--root")] = None,
    project_id: Annotated[str | None, typer.Option("--id")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """按路径或已有标识登记项目；成功持久化后返回当前选择。

    Open a project by path or ID and return the selection after persistence succeeds.
    """

    with report_errors(as_json):
        storage = Storage(resolve_data_dir(options(ctx).data_dir))
        with storage.writer():
            output(ProjectService(storage).open(path=root, project_id=project_id), as_json)


@app.command()
def doctor(
    ctx: typer.Context,
    dev: Annotated[bool, typer.Option("--dev")] = False,
    network: Annotated[bool, typer.Option("--network")] = False,
    write_probe: Annotated[bool, typer.Option("--write-probe")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """默认只做本机只读诊断；额外探测需显式启用。

    Run local read-only diagnostics; additional probes require explicit flags.
    """

    args = options(ctx)
    report = diagnose(
        args.data_dir, model=args.model, dev=dev, network=network, write_probe=write_probe
    )
    output(report, as_json)
    if any(check.blocking for check in report.checks):
        raise typer.Exit(1)


@app.command()
def serve(
    ctx: typer.Context,
    parent_credential: Annotated[bool, typer.Option("--parent-credential", hidden=True)] = False,
) -> None:
    """在标准输入输出上运行 JSONL RPC，连接关闭后释放资源。

    Serve JSONL RPC over standard streams and release resources when the connection closes.
    """
    with report_errors(False):
        credential = (
            read_parent_credential(sys.stdin.buffer) if parent_credential else resolve_credential()
        )
        try:
            run_server(
                resolve_data_dir(options(ctx).data_dir),
                sys.stdin.buffer,
                sys.stdout.buffer,
                credential,
                model=options(ctx).model,
            )
        except BrokenPipeError:
            return
