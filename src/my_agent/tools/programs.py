"""把执行服务接入工具协议，Plan 只允许查看。

Adapt execution to tools while keeping Plan read-only."""

import json

from pydantic import ValidationError

from my_agent.errors import AgentError
from my_agent.execution.service import ProgramService
from my_agent.execution.types import (
    GetProgramParams,
    ProgramParams,
    RunCommandArgs,
    StartServiceArgs,
)
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor
from my_agent.tools.policy import checkpoint
from my_agent.tools.read_only import encode


class NoArguments(ModelData):
    """查看当前项目执行配置时不接受路径或覆盖。

    Inspect configuration without path overrides."""


type ProgramArguments = (
    NoArguments | RunCommandArgs | StartServiceArgs | ProgramParams | GetProgramParams
)


def parse_program_arguments(call: ToolCall) -> ProgramArguments:
    """兼容 command 对象的 JSON 字符串包装，再解析实际工具参数。

    Decode a JSON-wrapped command object before parsing the tool's arguments.
    """
    models: dict[str, type[ProgramArguments]] = {
        "execution_environment": NoArguments,
        "run_command": RunCommandArgs,
        "start_service": StartServiceArgs,
        "read_program": GetProgramParams,
        "stop_program": ProgramParams,
    }
    arguments = call.arguments
    if call.name in {"run_command", "start_service"}:
        command = arguments.get("command")
        if isinstance(command, str):
            try:
                decoded = json.loads(command)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, dict):
                # 只解开对象包装，不猜 shell、不改脚本，也不改写保存的原始调用。
                # Unwrap only the object; preserve command semantics and the recorded raw call.
                arguments = {**arguments, "command": decoded}
    return models[call.name].model_validate(arguments)


def argument_failure(call: ToolCall, error: ValidationError) -> ToolResult:
    """反馈字段位置与实际类型问题，不回显命令正文或输入值。

    Report field locations and type errors without echoing command text or input values.
    """
    issues = error.errors(include_input=False, include_context=False, include_url=False)
    details = "; ".join(
        f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}" for issue in issues
    )
    message = "程序工具参数错误：" + details
    if any(issue["loc"] and issue["loc"][0] == "command" for issue in issues):
        message += (
            '。command 示例：{"kind":"powershell","script":"Get-Location"}；'
            '直接执行用 {"kind":"program","program":"node","arguments":["--version"]}。'
        )
    return ToolResult(
        tool_call_id=call.tool_call_id,
        content=encode({"code": "INVALID_TOOL_ARGUMENTS", "message": message}),
        is_error=True,
    )


class ProjectTools:
    """组合文件与项目执行，模式限制由对应工具负责。

    Compose file and execution tools with mode checks at the responsible tool boundary.
    """

    def __init__(self, context: ToolContext, files: ToolExecutor, programs: ProgramService) -> None:
        """运行身份由宿主注入，模型不能伪造归属。

        Inject run identity from the trusted host."""
        self.context, self.files, self.programs = context, files, programs

    def is_mutating(self, name: str) -> bool:
        """执行和停止均视为副作用，不以只读命令猜测来绕过模式。

        Treat execution and stopping as mutations without guessing command intent.
        """
        return name in {"run_command", "start_service", "stop_program"} or self.files.is_mutating(
            name
        )

    def definitions(self) -> list[JsonObject]:
        """当前模式只暴露实际可用的工具接口。

        Expose real tool contracts for the current mode."""
        definitions = self.files.definitions()
        for name, model, description in (
            (
                "execution_environment",
                NoArguments,
                "Read project environment and execution mode. No installation or execution. "
                "An unbound project uses existing system tools without a separate trust switch. "
                "Import/select a Python/Conda/uv environment only when that task needs it.",
            ),
            (
                "read_program",
                GetProgramParams,
                "Read this session's managed program status and bounded output; no execution.",
            ),
            (
                "run_command",
                RunCommandArgs,
                "Run a finite command in the selected project with its configured environment. "
                'Pass command as an object, e.g. {"kind":"program","program":"node",'
                '"arguments":["--version"]} or {"kind":"powershell","script":"Get-Location"}. '
                "Python aliases use the selected interpreter. "
                "cwd may be relative or absolute but must resolve inside the selected project. "
                "For npm.cmd, batch files or pipelines use explicit kind=powershell with a script. "
                "Waits for completion. Nonzero exit is a result, not automatic repair permission. "
                "Do not execute tests unless the task needs them; do not detach child processes.",
            ),
            (
                "start_service",
                StartServiceArgs,
                "Start a foreground HTTP preview/API for the user; requires a loopback ready_url. "
                "command is the same program/powershell object accepted by run_command. "
                "cwd may be relative or absolute within the selected project. "
                "Verifies an owned listener and HTTP headers. "
                "Retained until stopped or app exit. HTTP response is not a business test.",
            ),
            (
                "stop_program",
                ProgramParams,
                "Stop a managed program owned by this session; never accepts a raw PID.",
            ),
        ):
            if self.context.mode == "plan" and self.is_mutating(name):
                continue
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": model.model_json_schema(),
                    },
                }
            )
        return definitions

    async def execute(self, call: ToolCall) -> ToolResult:
        """校验完整参数与身份，取消交给执行服务清理。

        Validate full arguments and ownership; reap cancellation."""
        if call.name not in {
            "execution_environment",
            "read_program",
            "run_command",
            "start_service",
            "stop_program",
        }:
            return await self.files.execute(call)
        try:
            checkpoint(self.context.stop)
            if self.context.mode == "plan" and self.is_mutating(call.name):
                raise AgentError("PLAN_READ_ONLY", "Plan 模式不能运行或停止程序。")
            try:
                args = parse_program_arguments(call)
            except ValidationError as exc:
                return argument_failure(call, exc)
            if isinstance(args, NoArguments):
                result: ModelData = await self.programs.worker.call(
                    self.programs.environments.catalog, self.context.project_id
                )
            elif isinstance(args, RunCommandArgs):
                result = await self.programs.run(self.context, args, call.tool_call_id)
            elif isinstance(args, StartServiceArgs):
                result = await self.programs.start_service(self.context, args, call.tool_call_id)
            else:
                options = (
                    args
                    if isinstance(args, GetProgramParams)
                    else GetProgramParams(program_id=args.program_id)
                )
                view = await self.programs.get(options)
                if (
                    view.summary.session_id != self.context.session_id
                    or view.summary.project_id != self.context.project_id
                ):
                    raise AgentError(
                        "PROGRAM_SCOPE_DENIED",
                        "当前会话不能访问其他会话的程序；用户可在项目卡片管理。",
                    )
                result = (
                    view
                    if call.name == "read_program"
                    else await self.programs.stop(options.program_id)
                )
            # 模型只需要当前环境，不把废弃的 trusted 字段变成新的操作前置条件。
            # Omit the obsolete trust field so models do not invent a setup prerequisite.
            content = (
                result.model_dump_json(exclude={"binding": {"trusted"}})
                if call.name == "execution_environment"
                else result.model_dump_json()
            )
            if len(content.encode("utf-8")) > self.context.limits.max_tool_bytes:
                # 保留状态和关联 ID，只缩减日志；完整有界日志仍在运行卡片。
                # Keep status and identity while shortening logs; the card retains the bounded tail.
                data = json.loads(content)
                if self.context.archive_output:
                    data["archive_id"] = await self.context.archive_output(content)
                    data["archive_read"] = "read_history(artifact_id=archive_id, offset=0)"
                if "output" in data:
                    while (
                        data["output"]
                        and len(encode(data).encode("utf-8")) > self.context.limits.max_tool_bytes
                    ):
                        data["output"].pop(0)
                    data["truncated"] = True
                    content = encode(data)
                if len(content.encode("utf-8")) > self.context.limits.max_tool_bytes:
                    raise AgentError(
                        "TOOL_OUTPUT_LIMIT",
                        "结果超出本次工具输出预算，请在运行卡片查看并按需调整预算。",
                    )
            return ToolResult(tool_call_id=call.tool_call_id, content=content, is_error=False)
        except AgentError as exc:
            if exc.code == "CANCELLED":
                raise
            code, message = exc.code, exc.message
        return ToolResult(
            tool_call_id=call.tool_call_id,
            content=encode({"code": code, "message": message}),
            is_error=True,
        )
