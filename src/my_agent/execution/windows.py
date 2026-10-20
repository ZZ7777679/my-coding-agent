"""以原生句柄管理自有 Windows 进程树，不提供文件隔离。

Own Windows process trees through native handles, without claiming filesystem isolation.
API reference: https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
"""

import ctypes
import os
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from ctypes import wintypes
from pathlib import Path

from my_agent.errors import AgentError


class StartupInfo(ctypes.Structure):
    """Win32 启动结构的 ABI 布局。

    ABI layout for Win32 startup settings."""

    _fields_ = [
        ("cb", wintypes.DWORD),
        ("reserved", wintypes.LPWSTR),
        ("desktop", wintypes.LPWSTR),
        ("title", wintypes.LPWSTR),
        ("x", wintypes.DWORD),
        ("y", wintypes.DWORD),
        ("x_size", wintypes.DWORD),
        ("y_size", wintypes.DWORD),
        ("x_chars", wintypes.DWORD),
        ("y_chars", wintypes.DWORD),
        ("fill", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("show", wintypes.WORD),
        ("reserved_size", wintypes.WORD),
        ("reserved_data", ctypes.c_void_p),
        ("stdin", wintypes.HANDLE),
        ("stdout", wintypes.HANDLE),
        ("stderr", wintypes.HANDLE),
    ]


class ExtendedStartupInfo(ctypes.Structure):
    """限制继承句柄的扩展启动布局。

    Extended startup layout with an inherited-handle list."""

    _fields_ = [("startup", StartupInfo), ("attributes", ctypes.c_void_p)]


class ProcessInfo(ctypes.Structure):
    """CreateProcess 返回的实际句柄与身份。

    Actual handles and IDs returned by CreateProcess."""

    _fields_ = [
        ("process", wintypes.HANDLE),
        ("thread", wintypes.HANDLE),
        ("pid", wintypes.DWORD),
        ("tid", wintypes.DWORD),
    ]


class BasicLimits(ctypes.Structure):
    """Job 基础限制的原生布局。

    Native layout of basic job limits."""

    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD),
        ("min_working", ctypes.c_size_t),
        ("max_working", ctypes.c_size_t),
        ("active_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class IoCounters(ctypes.Structure):
    """与 Win32 IO_COUNTERS 大小一致的计数字段。

    Counters matching the Win32 IO_COUNTERS layout."""

    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "read_ops",
            "write_ops",
            "other_ops",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class ExtendedLimits(ctypes.Structure):
    """Job 扩展限制，仅启用关闭句柄终止进程树。

    Extended job limits enabling kill-on-close only."""

    _fields_ = [
        ("basic", BasicLimits),
        ("io", IoCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process", ctypes.c_size_t),
        ("peak_job", ctypes.c_size_t),
    ]


class Accounting(ctypes.Structure):
    """通过实际活动进程数核对清理。

    Verify cleanup using the job's live process count."""

    _fields_ = [
        ("user_time", ctypes.c_longlong),
        ("kernel_time", ctypes.c_longlong),
        ("period_user", ctypes.c_longlong),
        ("period_kernel", ctypes.c_longlong),
        ("faults", wintypes.DWORD),
        ("total", wintypes.DWORD),
        ("active", wintypes.DWORD),
        ("terminated", wintypes.DWORD),
    ]


class WindowsProcess:
    """先暂停创建并加入 Job，再执行；输出始终消费且缓冲有界。

    Assign a suspended child to its job before execution; continuously drain bounded output.
    """

    def __init__(
        self,
        command: list[str],
        cwd: Path,
        environment: Mapping[str, str],
        output_limit: int,
        *,
        security_capabilities: ctypes.Structure | None = None,
        pseudo_console: int | None = None,
        input_pipe: bool = False,
        stdout_sink: Callable[[bytes], None] | None = None,
    ) -> None:
        """显式 exe / argv / 环境启动隐藏控制台，失败清理全部自有资源。

        Launch explicit exe/argv/environment without a console; clean up owned resources on failure.
        """
        if os.name != "nt":
            raise AgentError("EXECUTION_PLATFORM_UNSUPPORTED", "当前项目执行后端仅支持 Windows。")
        import msvcrt

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._signatures()
        self.process = 0
        self.job = 0
        self.pid = 0
        self.output_limit = output_limit
        self.buffer: deque[tuple[str, bytes]] = deque()
        self.buffer_size = 0
        self.dropped = 0
        self.output_failed = False
        self.buffer_lock = threading.Lock()
        self.handle_lock = threading.RLock()
        self.readers: list[threading.Thread] = []
        self.input_fd: int | None = None
        self.stdout_sink = stdout_sink
        descriptors: list[int] = []
        thread_handle = 0
        attributes = ctypes.c_void_p()
        attributes_ready = False
        try:
            self.job = int(self.kernel.CreateJobObjectW(None, None) or 0)
            self._require(bool(self.job), "CreateJobObject")
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            self._require(
                bool(
                    self.kernel.SetInformationJobObject(
                        self.job,
                        9,
                        ctypes.byref(limits),
                        ctypes.sizeof(limits),
                    )
                ),
                "SetInformationJobObject",
            )
            out_read, out_write = os.pipe()
            descriptors.extend((out_read, out_write))
            err_read, err_write = os.pipe()
            descriptors.extend((err_read, err_write))
            if input_pipe:
                stdin, self.input_fd = os.pipe()
            else:
                stdin = os.open(os.devnull, os.O_RDONLY)
            descriptors.append(stdin)
            child_fds = (stdin, out_write, err_write)
            handles = (wintypes.HANDLE * 3)(*(msvcrt.get_osfhandle(fd) for fd in child_fds))
            for fd in child_fds:
                os.set_handle_inheritable(msvcrt.get_osfhandle(fd), True)
            size = ctypes.c_size_t()
            attribute_count = 2 if security_capabilities is not None else 1
            self.kernel.InitializeProcThreadAttributeList(
                None, attribute_count, 0, ctypes.byref(size)
            )
            self._require(bool(size.value), "InitializeProcThreadAttributeList")
            attribute_memory = ctypes.create_string_buffer(size.value)
            attributes = ctypes.cast(attribute_memory, ctypes.c_void_p)
            self._require(
                bool(
                    self.kernel.InitializeProcThreadAttributeList(
                        attributes,
                        attribute_count,
                        0,
                        ctypes.byref(size),
                    )
                ),
                "InitializeProcThreadAttributeList",
            )
            attributes_ready = True
            if security_capabilities is not None:
                self._require(
                    bool(
                        self.kernel.UpdateProcThreadAttribute(
                            attributes,
                            0,
                            0x20009,
                            ctypes.byref(security_capabilities),
                            ctypes.sizeof(security_capabilities),
                            None,
                            None,
                        )
                    ),
                    "AppContainerSecurityCapabilities",
                )
            self._require(
                bool(
                    self.kernel.UpdateProcThreadAttribute(
                        attributes,
                        0,
                        0x20016 if pseudo_console is not None else 0x20002,
                        ctypes.c_void_p(pseudo_console)
                        if pseudo_console is not None
                        else ctypes.byref(handles),
                        ctypes.sizeof(ctypes.c_void_p)
                        if pseudo_console is not None
                        else ctypes.sizeof(handles),
                        None,
                        None,
                    )
                ),
                "UpdateProcThreadAttribute",
            )
            startup = ExtendedStartupInfo()
            startup.startup.cb = ctypes.sizeof(startup)
            # ConPTY 显式使用空标准句柄，避免 Windows 复制宿主重定向管道。
            # Explicit null standard handles prevent host pipe duplication into ConPTY.
            startup.startup.flags = 0x100
            if pseudo_console is None:
                startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = handles
            startup.attributes = attributes
            info = ProcessInfo()
            arguments = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
            env_block = ctypes.create_unicode_buffer(
                "\x00".join(
                    f"{key}={value}"
                    for key, value in sorted(
                        environment.items(),
                        key=lambda item: item[0].upper(),
                    )
                )
                + "\x00\x00"
            )
            # 明确 applicationName；不让 Windows 根据带空格命令猜测程序。
            # An explicit applicationName avoids ambiguous executable selection.
            self._require(
                bool(
                    self.kernel.CreateProcessW(
                        command[0],
                        arguments,
                        None,
                        None,
                        pseudo_console is None,
                        0x4 | 0x400 | 0x80000 | (0 if pseudo_console is not None else 0x8000000),
                        env_block,
                        str(cwd),
                        ctypes.byref(startup),
                        ctypes.byref(info),
                    )
                ),
                "CreateProcess",
            )
            self.process, thread_handle, self.pid = (
                int(info.process),
                int(info.thread),
                int(info.pid),
            )
            for fd in child_fds:
                os.close(fd)
                descriptors.remove(fd)
            self._require(
                bool(self.kernel.AssignProcessToJobObject(self.job, self.process)),
                "AssignProcessToJobObject",
            )
            self._require(self.kernel.ResumeThread(thread_handle) != 0xFFFFFFFF, "ResumeThread")
            for fd, channel in ((out_read, "stdout"), (err_read, "stderr")):
                reader = threading.Thread(target=self._consume, args=(fd, channel), daemon=True)
                reader.start()
                descriptors.remove(fd)
                self.readers.append(reader)
        except BaseException:
            # 即使加入 Job 失败，暂停的根进程也必须被终止。
            # Kill the suspended root even when job assignment itself failed.
            if self.process:
                self.kernel.TerminateProcess(self.process, 1)
            if self.job:
                self.kernel.TerminateJobObject(self.job, 1)
            for reader in self.readers:
                reader.join(timeout=2)
            self.close()
            raise
        finally:
            if thread_handle:
                self.kernel.CloseHandle(thread_handle)
            if attributes_ready:
                self.kernel.DeleteProcThreadAttributeList(attributes)
            for fd in descriptors:
                os.close(fd)

    def _signatures(self) -> None:
        """显式声明 FFI 指针宽度，避免 64 位句柄被截断。

        Declare FFI widths to preserve 64-bit handles."""
        handle, pointer, dword = wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD
        signatures = (
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
            ("WaitForSingleObject", [handle, dword], dword),
            ("GetExitCodeProcess", [handle, pointer], wintypes.BOOL),
            ("ResumeThread", [handle], dword),
            ("InitializeProcThreadAttributeList", [pointer, dword, dword, pointer], wintypes.BOOL),
            (
                "UpdateProcThreadAttribute",
                [pointer, dword, ctypes.c_size_t, pointer, ctypes.c_size_t, pointer, pointer],
                wintypes.BOOL,
            ),
            ("DeleteProcThreadAttributeList", [pointer], None),
            (
                "CreateProcessW",
                [
                    wintypes.LPCWSTR,
                    wintypes.LPWSTR,
                    pointer,
                    pointer,
                    wintypes.BOOL,
                    dword,
                    pointer,
                    wintypes.LPCWSTR,
                    pointer,
                    pointer,
                ],
                wintypes.BOOL,
            ),
        )
        for name, arguments, result in signatures:
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result

    @staticmethod
    def _require(success: bool, operation: str) -> None:
        """只返回固定操作名与系统码，不回传命令或环境。

        Report an operation and code, never raw env."""
        if not success:
            raise AgentError(
                "PROCESS_API_FAILED",
                f"Windows 进程管理失败：{operation} / {ctypes.get_last_error()}。",
            )

    def _consume(self, fd: int, channel: str) -> None:
        """持续读取并保留有界尾部，超量不让子进程管道阻塞。

        Drain pipes into bounded tails."""
        try:
            with os.fdopen(fd, "rb", buffering=0) as stream:
                while chunk := stream.read(4096):
                    if channel == "stdout" and self.stdout_sink is not None:
                        # 二进制转发使用背压，不能套用日志尾部丢弃规则。
                        # Binary transport uses backpressure, never log-tail truncation.
                        self.stdout_sink(chunk)
                        continue
                    with self.buffer_lock:
                        self.buffer.append((channel, chunk))
                        self.buffer_size += len(chunk)
                        while self.buffer_size > self.output_limit and self.buffer:
                            old_channel, old = self.buffer.popleft()
                            removed = min(len(old), self.buffer_size - self.output_limit)
                            if removed < len(old):
                                self.buffer.appendleft((old_channel, old[removed:]))
                            self.buffer_size -= removed
                            self.dropped += removed
        except OSError:
            self.output_failed = True
        finally:
            if channel == "stdout" and self.stdout_sink is not None:
                try:
                    self.stdout_sink(b"")
                except OSError:
                    self.output_failed = True

    def write_input(self, data: bytes) -> None:
        """向显式启用的输入管道写完整数据；由单个转发线程持有。

        Write a full chunk to the optional pipe, owned by one forwarding thread.
        """
        if self.input_fd is None:
            raise BrokenPipeError("Process input is closed")
        remaining = memoryview(data)
        while remaining:
            remaining = remaining[os.write(self.input_fd, remaining) :]

    def close_input(self) -> None:
        """关闭输入以发送 EOF；进程清理前先终止 Job，解除阻塞写入。

        Send EOF; terminate the job before cleanup to unblock pending writes.
        """
        if self.input_fd is not None:
            descriptor, self.input_fd = self.input_fd, None
            os.close(descriptor)

    def drain(self) -> tuple[list[tuple[str, bytes]], int]:
        """取得新输出与累计丢弃量，不读取子进程环境。

        Take output and cumulative dropped-byte count."""
        with self.buffer_lock:
            chunks = list(self.buffer)
            self.buffer.clear()
            self.buffer_size = 0
            return chunks, self.dropped

    def poll(self) -> int | None:
        """由实际进程句柄查询退出；不以 PID 重新接管。

        Query the live handle rather than reopening a PID."""
        with self.handle_lock:
            if not self.process:
                raise AgentError("PROCESS_CLOSED", "程序句柄已释放。")
            status = self.kernel.WaitForSingleObject(self.process, 0)
            if status == 258:
                return None
            self._require(status == 0, "WaitForSingleObject")
            code = wintypes.DWORD()
            self._require(
                bool(self.kernel.GetExitCodeProcess(self.process, ctypes.byref(code))),
                "GetExitCodeProcess",
            )
            return int(code.value)

    def terminate(self) -> None:
        """终止本实例持有的 Job 中所有进程。

        Terminate only this instance's owned job."""
        with self.handle_lock:
            if self.job:
                self._require(
                    bool(self.kernel.TerminateJobObject(self.job, 1)), "TerminateJobObject"
                )

    def finish(self, timeout: float) -> None:
        """根进程结束后清理其子树，并核实管道与活动进程退出。

        Reap the tree and verify cleanup."""
        self.terminate()
        deadline = time.monotonic() + timeout
        while self.job:
            accounting = Accounting()
            self._require(
                bool(
                    self.kernel.QueryInformationJobObject(
                        self.job,
                        1,
                        ctypes.byref(accounting),
                        ctypes.sizeof(accounting),
                        None,
                    )
                ),
                "QueryInformationJobObject",
            )
            if accounting.active == 0:
                break
            if time.monotonic() >= deadline:
                raise AgentError("PROCESS_CLEANUP_FAILED", "受管进程尚未确认退出。")
            time.sleep(0.02)
        for reader in self.readers:
            reader.join(timeout=max(0, deadline - time.monotonic()))
        if any(reader.is_alive() for reader in self.readers):
            raise AgentError("PROCESS_CLEANUP_FAILED", "程序输出管道尚未结束。")
        self.close()

    def close(self) -> None:
        """释放自有句柄；Job 的 kill-on-close 也是异常退出后备。

        Release handles with kill-on-close."""
        with self.handle_lock:
            for name in ("job", "process"):
                handle = getattr(self, name)
                if handle:
                    self.kernel.CloseHandle(handle)
                    setattr(self, name, 0)
            self.close_input()
