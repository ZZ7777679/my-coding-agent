"""按需加载 ConPTY，并用 Job 清理自有进程树。 Lazy ConPTY with owned job cleanup.

pywinpty contract: https://github.com/andfoy/pywinpty/blob/master/src/lib.rs
"""

import ctypes
import importlib
import importlib.util
import os
import subprocess
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from typing import Protocol, cast

from my_agent.errors import AgentError
from my_agent.execution.windows import Accounting, ExtendedLimits


class NativePty(Protocol):
    """仅描述实际使用的 pywinpty 原生契约。

    Describe the used pywinpty native contract.
    """

    @property
    def pid(self) -> int | None:
        """真实进程身份。 Actual process identity."""
        ...

    @property
    def fd(self) -> int | None:
        """pywinpty 持有的进程句柄。 Process handle owned by pywinpty."""
        ...

    def spawn(self, appname: str, *, cmdline: str, cwd: str, env: str) -> bool:
        """创建显式程序。 Spawn an explicit program."""
        ...

    def read(self, *, blocking: bool = False) -> str:
        """读取合并输出。 Read merged output."""
        ...

    def write(self, text: str) -> int:
        """写入输入字符。 Write input characters."""
        ...

    def set_size(self, cols: int, rows: int) -> None:
        """调整字符网格。 Resize character grid."""
        ...

    def isalive(self) -> bool:
        """查询真实退出。 Query actual exit."""
        ...

    def get_exitstatus(self) -> int | None:
        """读取实际退出码。 Read actual exit code."""
        ...

    def cancel_io(self) -> bool:
        """取消待处理原生 I/O。 Cancel pending native I/O."""
        ...


def availability() -> tuple[bool, str | None]:
    """缺失 PTY 只影响终端，不在模块导入时阻断聊天。

    Missing PTY affects only terminals.
    """
    if os.name != "nt":
        return False, "本阶段交互终端使用 Windows ConPTY。"
    if importlib.util.find_spec("winpty") is None:
        return False, "交互终端缺少 pywinpty；普通命令与会话仍可使用。"
    return True, None


class ConPtyProcess:
    """持有原生 PTY 和 kill-on-close Job；不宣称文件或网络隔离。

    Own native PTY and a kill-on-close job without claiming filesystem/network isolation.
    """

    def __init__(
        self, command: list[str], cwd: Path, env: dict[str, str], cols: int, rows: int
    ) -> None:
        """复用解析后的程序与环境，不从用户项目加载宿主配置。

        Use resolved argv and environment.
        """
        available, message = availability()
        if not available:
            raise AgentError("TERMINAL_UNAVAILABLE", message or "交互终端不可用。")
        self.job = 0
        self.pid: int | None = None
        self.pty: NativePty | None = None
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._signatures()
        try:
            # C 扩展没有静态类型；仅此受信库边界使用契约 cast，不接收模型对象。
            # The C extension has no static typing; constrain the cast to this trusted boundary.
            factory = cast(Callable[..., NativePty], importlib.import_module("winpty").PTY)
            self.pty = factory(cols, rows, backend=0)  # pywinpty Backend.ConPTY
            self.job = int(self.kernel.CreateJobObjectW(None, None) or 0)
            self._require(bool(self.job), "CreateJobObject")
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            self._require(
                bool(
                    self.kernel.SetInformationJobObject(
                        self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
                    )
                ),
                "SetInformationJobObject",
            )
            self._require(
                self.pty.spawn(
                    command[0],
                    cmdline=" " + subprocess.list2cmdline(command[1:]),
                    cwd=str(cwd),
                    env="\0".join(f"{key}={value}" for key, value in env.items()) + "\0",
                ),
                "ConPTYSpawn",
            )
            self.pid = self.pty.pid
            handle = self.pty.fd
            if handle is None:
                raise AgentError("TERMINAL_START_FAILED", "终端未返回实际进程句柄。")
            # pywinpty 创建后立即纳入 Job，后续子进程继承；进程句柄仍归 pywinpty。
            # Assign after spawn; later children inherit. pywinpty retains its process handle.
            if self.pty.isalive():
                self._require(
                    bool(self.kernel.AssignProcessToJobObject(self.job, handle)),
                    "AssignProcessToJobObject",
                )
        except BaseException as exc:
            try:
                if self.pty is not None and self.pty.fd is not None and self.pty.isalive():
                    self.kernel.TerminateProcess(self.pty.fd, 1)
                self.close()
            finally:
                if not isinstance(exc, (AgentError, KeyboardInterrupt, SystemExit)):
                    raise AgentError(
                        "TERMINAL_START_FAILED", "ConPTY 启动失败，未自动重试。"
                    ) from exc
            raise

    def _signatures(self) -> None:
        """声明 64 位句柄 ABI，避免句柄截断。 Declare 64-bit handle ABI."""
        handle, pointer, dword = wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD
        for name, arguments, result in (
            ("CreateJobObjectW", [pointer, wintypes.LPCWSTR], handle),
            ("SetInformationJobObject", [handle, ctypes.c_int, pointer, dword], wintypes.BOOL),
            (
                "QueryInformationJobObject",
                [handle, ctypes.c_int, pointer, dword, pointer],
                wintypes.BOOL,
            ),
            ("AssignProcessToJobObject", [handle, handle], wintypes.BOOL),
            ("TerminateJobObject", [handle, wintypes.UINT], wintypes.BOOL),
            ("TerminateProcess", [handle, wintypes.UINT], wintypes.BOOL),
            ("CloseHandle", [handle], wintypes.BOOL),
        ):
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result

    @staticmethod
    def _require(success: bool, operation: str) -> None:
        """只报告固定操作与系统码。 Report only fixed operation and system code."""
        if not success:
            raise AgentError(
                "TERMINAL_API_FAILED",
                f"终端系统操作失败：{operation} / {ctypes.get_last_error()}。",
            )

    def read(self) -> str:
        """非阻塞读取原生输出。 Read native output without waiting for input."""
        return self.pty.read(blocking=False) if self.pty is not None else ""

    def poll(self) -> int | None:
        """只查询自有句柄，提示符不代表成功。

        Query owned process state, never prompt appearance.
        """
        if self.pty is None:
            raise AgentError("TERMINAL_CLOSED", "终端句柄已关闭。")
        return None if self.pty.isalive() else self.pty.get_exitstatus()

    def write(self, text: str) -> None:
        """写入完整字符；不把用户输入作为宿主日志保存。

        Write text without logging user input.
        """
        if self.pty is None or not self.pty.isalive():
            raise AgentError("TERMINAL_NOT_RUNNING", "终端已退出，不能继续输入。")
        self.pty.write(text)

    def resize(self, cols: int, rows: int) -> None:
        """更新 ConPTY 尺寸。 Update actual ConPTY dimensions."""
        if self.pty is not None:
            self.pty.set_size(cols, rows)

    def terminate(self) -> None:
        """关闭时终止 Job 子树；中断另用 Ctrl+C。

        Kill the job tree on close; Ctrl+C is separate.
        """
        if self.job:
            self._require(bool(self.kernel.TerminateJobObject(self.job, 1)), "TerminateJobObject")

    def finish(self, timeout: float) -> None:
        """根进程退出也清理保留子进程并核实活动计数。

        Reap children even after root exit.
        """
        self.terminate()
        deadline = time.monotonic() + timeout
        while self.job:
            accounting = Accounting()
            self._require(
                bool(
                    self.kernel.QueryInformationJobObject(
                        self.job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
                    )
                ),
                "QueryInformationJobObject",
            )
            if accounting.active == 0:
                break
            if time.monotonic() >= deadline:
                raise AgentError("PROCESS_CLEANUP_FAILED", "终端子进程尚未确认退出。")
            time.sleep(0.02)

    def close(self) -> None:
        """释放原生所有权，Job 关闭作为异常退出后备。

        Release ownership with kill-on-close fallback.
        """
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = 0
        self.pty = None
