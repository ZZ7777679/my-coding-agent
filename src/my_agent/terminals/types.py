"""受管终端、输入控制与输出的公开契约。 Public managed-terminal contracts."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from my_agent.execution.types import Command
from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData

Dimension = Annotated[int, Field(ge=1, le=32767)]


class OpenTerminalParams(ModelData):
    """明确程序、项目与可选成员归属。

    Explicit program, project and optional member ownership.
    """

    project_id: str
    command: Command
    cwd: str = "."
    cols: Dimension = 100
    rows: Dimension = 28
    member_id: EntityId | None = None
    session_id: EntityId | None = None


class ListTerminalsParams(ModelData):
    """列出指定项目保留的终端。 List retained terminals for one project."""

    project_id: str


class TerminalParams(ModelData):
    """使用终端身份而非任意 PID。 Address an owned terminal, never an arbitrary PID."""

    terminal_id: EntityId


class ReadTerminalParams(TerminalParams):
    """从已消费序号后读取有界输出。 Read bounded output after an observed sequence."""

    after_seq: Annotated[int, Field(ge=0)] = 0


class WriteTerminalParams(TerminalParams):
    """向当前控制者的真实输入通道写入。

    Write to the current controller's real input channel.
    """

    text: Annotated[str, Field(min_length=1, max_length=64000)]


class ResizeTerminalParams(TerminalParams):
    """更新实际 ConPTY 字符尺寸。 Resize the actual ConPTY character grid."""

    cols: Dimension
    rows: Dimension


class TerminalControlParams(TerminalParams):
    """用户显式接管或交还指定成员会话。

    Explicitly take over or return member-session control.
    """

    controller: Literal["user", "member"]
    member_id: EntityId | None = None
    session_id: EntityId | None = None

    @model_validator(mode="after")
    def member_session(self) -> "TerminalControlParams":
        """成员输入必须关联会话；用户接管保留已有来源。

        Member input requires a session.
        """
        if self.controller == "member" and self.session_id is None:
            raise ValueError("Member control requires a session_id")
        return self


class TerminalSummary(ModelData):
    """真实状态与输入归属，不由提示符猜测命令成功。

    Real state without prompt-based success guesses.
    """

    terminal_id: EntityId
    mode: Literal["direct", "sandbox"] = "direct"
    project_id: str
    session_id: EntityId | None
    member_id: EntityId | None
    run_id: EntityId | None
    tool_call_id: str | None
    controller: Literal["user", "member"]
    command: Command
    status: Literal["starting", "running", "stopping", "exited", "stopped", "failed", "interrupted"]
    pid: int | None
    exit_code: int | None
    cwd: str
    environment_name: str
    cols: int
    rows: int
    created_at: str
    finished_at: str | None
    code: str | None = None
    message: str | None = None
    dropped_bytes: int = 0


class TerminalChunk(ModelData):
    """顺序编号的合并 PTY 输出，不冒充独立 stderr。 Ordered merged PTY output."""

    seq: int
    text: str


class TerminalView(ModelData):
    """公开状态与按帧分页的输出。 Public state and frame-paged output."""

    summary: TerminalSummary
    output: list[TerminalChunk]
    next_seq: int
    truncated: bool


class TerminalPage(ModelData):
    """项目终端与可选能力可用性。

    Project terminals and optional capability availability.
    """

    terminals: list[TerminalSummary]
    active_count: int
    unavailable_count: int
    available: bool
    message: str | None
