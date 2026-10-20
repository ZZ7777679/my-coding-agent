"""带 AppContainer 属性的原生 ConPTY。 Native ConPTY with AppContainer launch attributes.

ABI reference: https://learn.microsoft.com/en-us/windows/console/createpseudoconsole
"""

import codecs
import ctypes
import os
import threading
from ctypes import wintypes
from pathlib import Path

from my_agent.errors import AgentError
from my_agent.execution.sandbox import SandboxLease
from my_agent.execution.types import EnvironmentView
from my_agent.execution.windows import WindowsProcess


class Coordinate(ctypes.Structure):
    """ConPTY 使用的 COORD 布局。 COORD layout used by ConPTY."""

    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short)]


class SandboxPty:
    """先建立伪控制台，再以受限令牌创建受 Job 管理的进程。

    Create a pseudoconsole then launch a restricted, job-owned process.
    """

    def __init__(
        self,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        cols: int,
        rows: int,
        capabilities: ctypes.Structure | None,
        output_limit: int,
    ) -> None:
        """只继承控制台连接，持续消费输出避免关闭死锁。

        Inherit only the console connection and drain output continuously to avoid close deadlocks.
        """
        import msvcrt

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreatePseudoConsole.argtypes = [
            Coordinate,
            wintypes.HANDLE,
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        self.kernel.CreatePseudoConsole.restype = ctypes.c_long
        self.kernel.ResizePseudoConsole.argtypes = [wintypes.HANDLE, Coordinate]
        self.kernel.ResizePseudoConsole.restype = ctypes.c_long
        self.kernel.ClosePseudoConsole.argtypes = [wintypes.HANDLE]
        self.kernel.ClosePseudoConsole.restype = None
        self.console = wintypes.HANDLE()
        self.input_fd: int | None = None
        self.process: WindowsProcess | None = None
        self.reader: threading.Thread | None = None
        self.buffer = ""
        self.dropped = 0
        self.limit = output_limit
        self.lock = threading.Lock()
        input_read, self.input_fd = os.pipe()
        output_read, output_write = os.pipe()
        try:
            code = self.kernel.CreatePseudoConsole(
                Coordinate(cols, rows),
                msvcrt.get_osfhandle(input_read),
                msvcrt.get_osfhandle(output_write),
                0,
                ctypes.byref(self.console),
            )
            self._require(code, "CreatePseudoConsole")
            self.reader = threading.Thread(target=self._consume, args=(output_read,), daemon=True)
            self.reader.start()
            self.process = WindowsProcess(
                command,
                cwd,
                env,
                output_limit,
                security_capabilities=capabilities,
                pseudo_console=self.console.value or 0,
            )
            self.pid = self.process.pid
        except BaseException:
            self.close()
            if self.reader is None:
                os.close(output_read)
            raise
        finally:
            os.close(input_read)
            os.close(output_write)

    @staticmethod
    def _require(code: int, operation: str) -> None:
        """报告实际 HRESULT，不回退到无隔离模式。 Report HRESULT without an unisolated fallback."""
        if code < 0:
            raise AgentError(
                "TERMINAL_API_FAILED", f"{operation} / HRESULT {code & 0xFFFFFFFF:08x}"
            )

    def _consume(self, descriptor: int) -> None:
        """单独线程消费 UTF-8 终端字节。 Drain UTF-8 console bytes on a dedicated thread."""
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while chunk := os.read(descriptor, 8192):
                with self.lock:
                    self.buffer += decoder.decode(chunk)
                    if len(self.buffer) > self.limit:
                        self.dropped += len(self.buffer) - self.limit
                        self.buffer = self.buffer[-self.limit :]
        except OSError:
            with self.lock:
                self.buffer += "\n[ConPTY output pipe closed]\n"
        finally:
            os.close(descriptor)

    def read(self) -> str:
        """非阻塞消费已缓冲输出。 Consume buffered output without blocking."""
        with self.lock:
            text, self.buffer = self.buffer, ""
            if self.dropped:
                text = f"[Earlier console output truncated: {self.dropped} characters]\n" + text
                self.dropped = 0
            return text

    def poll(self) -> int | None:
        """查询自有进程退出码。 Query the owned process exit code."""
        if self.process is None:
            raise AgentError("TERMINAL_CLOSED", "终端已关闭。")
        return self.process.poll()

    def write(self, text: str) -> None:
        """按 UTF-8 写入终端输入。 Send UTF-8 console input."""
        if self.input_fd is None or self.poll() is not None:
            raise AgentError("TERMINAL_NOT_RUNNING", "终端已退出。")
        data = text.encode("utf-8")
        while data:
            sent = os.write(self.input_fd, data)
            data = data[sent:]

    def resize(self, cols: int, rows: int) -> None:
        """更新实际控制台尺寸。 Resize the actual pseudoconsole."""
        if self.console:
            self._require(
                self.kernel.ResizePseudoConsole(self.console, Coordinate(cols, rows)),
                "ResizePseudoConsole",
            )

    def terminate(self) -> None:
        """终止受限进程及其子树。 Terminate the restricted process tree."""
        if self.process:
            self.process.terminate()

    def finish(self, timeout: float) -> None:
        """核实子树退出并收完终端尾部。 Reap the job tree and drain final console output."""
        if self.process:
            self.process.finish(timeout)
        if self.console:
            self.kernel.ClosePseudoConsole(self.console)
            self.console = wintypes.HANDLE()
        if self.reader:
            self.reader.join(timeout)
            if self.reader.is_alive():
                raise AgentError("TERMINAL_DRAIN_TIMEOUT", "终端已退出，但尾部输出尚未收完。")

    def close(self) -> None:
        """释放 Job 与控制台；输出线程持续消费直到管道关闭。

        Release job and console while the reader drains until pipe closure.
        """
        if self.process:
            self.process.close()
            self.process = None
        if self.console:
            self.kernel.ClosePseudoConsole(self.console)
            self.console = wintypes.HANDLE()
        if self.input_fd is not None:
            os.close(self.input_fd)
            self.input_fd = None


class SandboxTerminal(SandboxPty):
    """将项目沙箱租约与终端生命周期绑定。 Bind a project sandbox lease to its terminal."""

    def __init__(
        self,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        cols: int,
        rows: int,
        directory: Path,
        root: Path,
        view: EnvironmentView,
        output_limit: int,
    ) -> None:
        """按已接纳设置启动，复用项目授权。

        Launch with accepted settings and the shared project lease.
        """
        self.lease = SandboxLease.acquire(directory, root, view, env)
        super().__init__(command, cwd, env, cols, rows, self.lease.capabilities, output_limit)

    def close(self) -> None:
        """关闭终端进程；共享授权保留至应用退出。

        Close the process; keep shared grants until app exit.
        """
        super().close()
