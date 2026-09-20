"""环境登记、项目默认与执行的公开契约。

Public environment, binding and execution contracts."""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.identifiers import EntityId as SessionId
from my_agent.models.types import ModelData

LocalPath = Annotated[str, Field(min_length=1, max_length=4096, pattern=r"^[^\x00]*$")]


class SystemEnvironment(ModelData):
    """用户显式选择已有本机工具，不虚构 Python 绑定。

    Explicit existing system-tool selection."""

    kind: Literal["system"]


class PythonEnvironment(ModelData):
    """已有解释器，项目相对路径在启动时解析。

    Existing interpreter with launch-time project paths."""

    kind: Literal["python"]
    scope: Literal["absolute", "project"]
    interpreter: LocalPath


class CondaEnvironment(ModelData):
    """Conda 安装入口和明确 prefix，不默认使用 base。

    Explicit Conda launcher and environment prefix."""

    kind: Literal["conda"]
    scope: Literal["absolute", "project"]
    launcher: LocalPath
    prefix: LocalPath


class UvEnvironment(ModelData):
    """登记 uv 与已有解释器，普通运行不自动同步依赖。

    Register uv and an existing interpreter."""

    kind: Literal["uv"]
    scope: Literal["absolute", "project"]
    launcher: LocalPath
    interpreter: LocalPath


# 每个分支的 kind 是互斥 Literal，普通联合即可生成标准 JSON Schema。
# Disjoint literal kinds preserve strict unions without OpenAPI-only discriminator metadata.
EnvironmentDefinition = SystemEnvironment | PythonEnvironment | CondaEnvironment | UvEnvironment


class ExecutionSettings(ModelData):
    """新启动程序采用的可调预算；持续服务不套用命令寿命。

    Adjustable launch budgets; retained services have no command-lifetime timeout.
    """

    command_timeout_seconds: Annotated[int, Field(ge=1)]
    service_ready_timeout_seconds: Annotated[int, Field(ge=1)]
    cleanup_timeout_seconds: Annotated[int, Field(ge=1)]
    probe_timeout_seconds: Annotated[int, Field(ge=1)]
    max_output_bytes: Annotated[int, Field(ge=1024)]


class EnvironmentProbe(ModelData):
    """显式探测结果及其实际路径来源。

    Explicit probe evidence with its actual path context."""

    checked_at: str
    project_id: str | None
    code: str
    message: str
    interpreter: str | None
    version: str | None
    launcher_version: str | None


class EnvironmentRecord(ModelData):
    """仅保存用户环境引用，不保存进程变量或凭据。

    Persist environment references, not env secrets."""

    environment_id: SessionId
    name: Annotated[str, Field(min_length=1, max_length=256, pattern=r"\S")]
    definition: EnvironmentDefinition
    probe: EnvironmentProbe | None = None


class ProjectExecution(ModelData):
    """项目唯一默认环境和后续执行方式。

    A project's default environment and future execution policy."""

    project_id: str
    environment_id: SessionId | None
    trusted: bool = Field(
        default=True,
        deprecated=True,
        description="Legacy compatibility field; not an execution gate. Use the selected mode.",
    )
    mode: Literal["direct", "sandbox"]


class EnvironmentView(ModelData):
    """登记事实与当前路径可用性，未经探测不冒充版本已验证。

    Registration and live path availability, without claiming unperformed probes.
    """

    record: EnvironmentRecord
    available: bool
    issue: str | None
    interpreter: str | None
    launcher: str | None
    prefix: str | None


class EnvironmentCatalog(ModelData):
    """设置页的可公开环境与当前项目绑定。

    Public environment settings and current project binding."""

    revision: Annotated[int, Field(ge=0)]
    environments: list[EnvironmentView]
    binding: ProjectExecution | None
    settings: ExecutionSettings


class EnvironmentProjectParams(ModelData):
    """可选项目用于解析相对环境。

    Optional project context for relative environments."""

    project_id: str | None


class SaveEnvironmentParams(EnvironmentProjectParams):
    """显式导入或修改引用，以版本防止覆盖较新设置。

    Import references with revision checks."""

    environment_id: SessionId | None
    expected_revision: Annotated[int, Field(ge=0)]
    name: Annotated[str, Field(min_length=1, max_length=256, pattern=r"\S")]
    definition: EnvironmentDefinition


class EnvironmentParams(EnvironmentProjectParams):
    """指定已登记环境，不接受任意待执行命令。

    Identify a registered environment, not a command."""

    environment_id: SessionId


class RemoveEnvironmentParams(EnvironmentParams):
    """删除登记而不卸载环境。

    Remove a reference without uninstalling its environment."""

    expected_revision: Annotated[int, Field(ge=0)]


class BindEnvironmentParams(ProjectExecution):
    """用户保存项目默认环境与执行方式。

    Persist the user's default environment and execution mode."""

    expected_revision: Annotated[int, Field(ge=0)]


class SaveExecutionSettings(ModelData):
    """仅影响后续启动，不重新执行或热切换程序。

    Affect future launches without restarting programs."""

    expected_revision: Annotated[int, Field(ge=0)]
    settings: ExecutionSettings
    project_id: str | None


class ProgramCommand(ModelData):
    """程序和参数数组直接执行，不猜测 shell 转义。

    Execute an explicit program and argument array."""

    kind: Literal["program"]
    program: LocalPath
    arguments: list[Annotated[str, Field(max_length=64000, pattern=r"^[^\x00]*$")]] = Field(
        default_factory=list
    )


class ShellCommand(ModelData):
    """用户任务中的显式 PowerShell 脚本，与普通 argv 区分。

    Explicit PowerShell, distinct from argv."""

    kind: Literal["powershell"]
    script: Annotated[str, Field(min_length=1, max_length=64000, pattern=r"^[^\x00]*$")]


Command = ProgramCommand | ShellCommand


class RunCommandArgs(ModelData):
    """命令在项目内 cwd 运行，超时可按需要覆盖。

    Run in a project cwd with an optional timeout."""

    command: Command
    cwd: str = "."
    timeout_seconds: Annotated[int, Field(ge=1)] | None = None


class StartServiceArgs(ModelData):
    """前台启动 HTTP 预览，经响应检查后交付保留。

    Retain a foreground HTTP preview after probing."""

    command: Command
    cwd: str = "."
    ready_url: Annotated[str, Field(min_length=1, max_length=4096)]
    ready_timeout_seconds: Annotated[int, Field(ge=1)] | None = None


class ProgramSummary(ModelData):
    """实际程序身份、来源与结果，PID 仅展示而非恢复授权。

    Program identity and outcome; a saved PID is not authority to reclaim a process.
    """

    program_id: SessionId
    project_id: str
    session_id: SessionId
    run_id: SessionId
    tool_call_id: str | None = None
    environment_id: SessionId
    environment_name: str
    environment_revision: int
    kind: Literal["command", "service"]
    command: Command
    resolved_command: list[str]
    cwd: str
    mode: Literal["direct"] = "direct"
    status: Literal[
        "starting", "running", "ready", "stopping", "exited", "stopped", "failed", "interrupted"
    ]
    pid: int | None
    exit_code: int | None
    retained: bool
    created_at: str
    finished_at: str | None
    url: str | None
    http_status: int | None
    code: str | None
    message: str | None
    dropped_bytes: int = 0


class OutputChunk(ModelData):
    """按消费顺序编号的输出块，始终作为纯文本处理。

    Numbered output chunks rendered as plain text."""

    seq: int
    stream: Literal["stdout", "stderr"]
    text: str


class ProgramView(ModelData):
    """有界输出页与实际状态。

    Bounded output page and actual process state."""

    summary: ProgramSummary
    output: list[OutputChunk]
    next_seq: int
    truncated: bool


class ProgramPage(ModelData):
    """按项目或会话查询卡片，损坏记录明确计数。

    Query project/session cards with damage counts."""

    programs: list[ProgramSummary]
    next_cursor: str | None
    unavailable_count: int
    active_count: int


class ListProgramsParams(ModelData):
    """用户查询卡片范围；工具另校验会话权限。

    User query scope; tools also check session ownership."""

    project_id: str
    session_id: SessionId | None = None
    cursor: SessionId | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 20


class ProgramParams(ModelData):
    """只使用受管程序身份。

    Address a managed program by identity only."""

    program_id: SessionId


class GetProgramParams(ProgramParams):
    """从已看到的输出序号继续读取。

    Continue reading after the last observed output sequence."""

    after_seq: Annotated[int, Field(ge=0)] = 0


class ChooseEnvironmentPathParams(ModelData):
    """选择已有环境入口。 Select existing environment paths through a trusted picker."""

    kind: Literal["executable", "directory"]


class ExecutionStatus(ModelData):
    """退出前展示实际持有的工作。 Show owned work before application shutdown."""

    programs: list[ProgramSummary]
    probe_count: int
