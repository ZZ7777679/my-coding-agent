"""运行时的工具装配接口。 Runtime tool composition contracts."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from my_agent.models.types import JsonObject, ToolCall, ToolResult
from my_agent.runtime.modes import RunMode
from my_agent.runtime.settings import RunLimits

if TYPE_CHECKING:
    from my_agent.runtime.events import RunSink


@dataclass(frozen=True)
class ToolContext:
    """来自受信入口的单次运行权限与归属。 Per-run scope supplied by the trusted entry point."""

    root: Path
    limits: RunLimits
    stop: threading.Event
    project_id: str
    session_id: str
    run_id: str
    mode: RunMode
    plan_document: str | None
    request_sink: RunSink | None = None
    collaboration_id: str | None = None


class ToolExecutor(Protocol):
    """循环只依赖工具能力，不创建具体实现。

    The loop consumes capabilities without constructing tools."""

    def definitions(self) -> list[JsonObject]:
        """返回当前模式可用 schema。 Return schemas allowed by the current mode."""
        ...

    def is_mutating(self, name: str) -> bool:
        """标记会改变文件或程序状态的工具，供模式分流使用。

        Identify file or program effects for mode-specific tool routing."""
        ...

    async def execute(self, call: ToolCall) -> ToolResult:
        """执行完整且已校验的工具输入。 Execute complete, validated tool input."""
        ...
