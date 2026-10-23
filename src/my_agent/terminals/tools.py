"""现有工具循环的交互终端适配，不额外执行模型。 Terminal adapter for the existing tool loop."""

from pydantic import ValidationError

from my_agent.errors import AgentError
from my_agent.execution.types import Command
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor, failed_tool_result
from my_agent.terminals.service import TerminalService
from my_agent.terminals.types import (
    ListTerminalsParams,
    OpenTerminalParams,
    ReadTerminalParams,
    TerminalPage,
    TerminalParams,
    TerminalView,
    WriteTerminalParams,
)
from my_agent.tools.arguments import argument_message
from my_agent.tools.policy import checkpoint
from my_agent.tools.read_only import encode


class StartTerminalArgs(ModelData):
    """模型只给命令，不自行伪造项目、成员与会话归属。

    Models supply commands without forging project/member/session ownership.
    """

    command: Command
    cwd: str = "."


class NoTerminalArgs(ModelData):
    """宿主提供当前会话范围，不接收伪造身份。

    Host supplies session scope without forged identities.
    """


class TerminalTools:
    """复用既有组合工具，控制权只由明确用户入口更改。

    Extend existing tools; input control changes only through explicit user actions.
    """

    def __init__(
        self, context: ToolContext, base: ToolExecutor, terminals: TerminalService
    ) -> None:
        """宿主注入当前会话和共享终端服务。 Inject current session and shared terminal ownership."""
        self.context, self.base, self.terminals = context, base, terminals

    def is_mutating(self, name: str) -> bool:
        """启动、输入、中断和关闭均属于副作用。 Launch/input/interrupt/close are mutations."""
        return name in {
            "start_terminal",
            "write_terminal",
            "interrupt_terminal",
            "close_terminal",
        } or self.base.is_mutating(name)

    def definitions(self) -> list[JsonObject]:
        """Plan 可读终端，但不运行或写输入。 Plan can read terminals but cannot launch/write."""
        definitions = self.base.definitions()
        for name, model, description in (
            (
                "list_terminals",
                NoTerminalArgs,
                "List terminals assigned to this session with actual state and input ownership. "
                "Read output with read_terminal; a running shell does not prove command success.",
            ),
            (
                "start_terminal",
                StartTerminalArgs,
                "Start a real Windows ConPTY program using the selected project environment. "
                "Returns terminal_id promptly; read_terminal reads and write_terminal sends input. "
                "Retained across replies/navigation until closed or app exit. "
                "Use an explicit program for interactive shells; kind=powershell runs a script. "
                "A running terminal or command prompt is not evidence of command success.",
            ),
            (
                "read_terminal",
                ReadTerminalParams,
                "Read this session's interactive terminal state and merged output after_seq. "
                "User takeover allows reading; input is blocked until explicitly returned.",
            ),
            (
                "write_terminal",
                WriteTerminalParams,
                "Send text to this session's member-controlled terminal. "
                "For a line include carriage return (\\r). Never claim control or retry after "
                "user takeover; wait for an explicit return.",
            ),
            (
                "interrupt_terminal",
                TerminalParams,
                "Send real Ctrl+C to this session's member-controlled foreground program. "
                "The shell may remain open; read actual state/output instead of assuming exit.",
            ),
            (
                "close_terminal",
                TerminalParams,
                "Close this session's member-controlled terminal and reap its owned process tree. "
                "Never accepts a raw PID or restarts a historical terminal.",
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
        """完整参数校验后交给共享终端服务，输出按工具预算分页。

        Validate complete arguments and delegate to shared terminals with bounded tool output.
        """
        models: dict[str, type[ModelData]] = {
            "list_terminals": NoTerminalArgs,
            "start_terminal": StartTerminalArgs,
            "read_terminal": ReadTerminalParams,
            "write_terminal": WriteTerminalParams,
            "interrupt_terminal": TerminalParams,
            "close_terminal": TerminalParams,
        }
        if call.name not in models:
            return await self.base.execute(call)
        try:
            checkpoint(self.context.stop)
            if self.context.mode == "plan" and self.is_mutating(call.name):
                raise AgentError("PLAN_READ_ONLY", "Plan 模式不能操作终端输入或生命周期。")
            try:
                args = models[call.name].model_validate(call.arguments)
            except ValidationError as exc:
                return ToolResult(
                    tool_call_id=call.tool_call_id,
                    is_error=True,
                    content=encode(
                        {"code": "INVALID_TOOL_ARGUMENTS", "message": argument_message(exc)}
                    ),
                )
            result: TerminalView | TerminalPage
            if isinstance(args, NoTerminalArgs):
                page = await self.terminals.list(
                    ListTerminalsParams(project_id=self.context.project_id)
                )
                items = [s for s in page.terminals if s.session_id == self.context.session_id]
                result = page.model_copy(
                    update={
                        "terminals": items,
                        "active_count": sum(
                            s.status in {"running", "starting", "stopping"} for s in items
                        ),
                    }
                )
                while (
                    len(result.model_dump_json().encode("utf-8"))
                    > self.context.limits.max_tool_bytes
                ):
                    if not result.terminals:
                        raise AgentError("TOOL_OUTPUT_LIMIT", "终端状态超出工具输出预算。")
                    result.terminals.pop()
            elif isinstance(args, StartTerminalArgs):
                result = await self.terminals.open(
                    OpenTerminalParams(
                        project_id=self.context.project_id,
                        command=args.command,
                        cwd=args.cwd,
                    ),
                    self.context,
                    call.tool_call_id,
                )
            elif isinstance(args, TerminalParams):
                current = await self.terminals.read(
                    ReadTerminalParams(terminal_id=args.terminal_id)
                )
                if (
                    current.summary.project_id != self.context.project_id
                    or current.summary.session_id != self.context.session_id
                ):
                    raise AgentError("TERMINAL_SCOPE_DENIED", "终端未关联当前成员会话。")
                if isinstance(args, WriteTerminalParams):
                    result = await self.terminals.write(args, self.context)
                elif isinstance(args, ReadTerminalParams):
                    result = await self.terminals.read(args)
                elif call.name == "interrupt_terminal":
                    result = await self.terminals.interrupt(args, self.context)
                else:
                    result = await self.terminals.stop(args, self.context)
            else:
                raise AgentError("INVALID_TOOL_ARGUMENTS", "终端工具参数类型无效。")
            if isinstance(result, TerminalView):
                result = self._bounded(result)
            return ToolResult(
                tool_call_id=call.tool_call_id, content=result.model_dump_json(), is_error=False
            )
        except AgentError as exc:
            if exc.code == "CANCELLED":
                raise
            return failed_tool_result(call, exc)

    def _bounded(self, result: TerminalView) -> TerminalView:
        """保留最早未读块，按 next_seq 续读。

        Keep first unread chunks for paging.
        """
        result = result.model_copy(deep=True)
        while len(result.model_dump_json().encode("utf-8")) > self.context.limits.max_tool_bytes:
            if not result.output:
                raise AgentError("TOOL_OUTPUT_LIMIT", "终端状态超出工具输出预算，请调整设置。")
            if len(result.output) == 1 and len(result.output[0].text) > 1:
                chunk = result.output[0]
                result.output[0] = chunk.model_copy(
                    update={"text": chunk.text[: len(chunk.text) // 2]}
                )
            else:
                result.output.pop()
            result.truncated = True
            result.next_seq = result.output[-1].seq if result.output else 0
        return result
