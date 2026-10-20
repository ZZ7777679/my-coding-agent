"""以普通用户管道连接沙箱预览，不修改防火墙或回环豁免。

Expose sandbox previews through unprivileged pipes, without firewall or loopback exemptions.
"""

import ctypes
import logging
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from my_agent.errors import AgentError
from my_agent.execution.listeners import local_endpoint
from my_agent.execution.sandbox import SandboxProcess
from my_agent.execution.windows import WindowsProcess
from my_agent.storage import write_document


def bridge_executable(process: SandboxProcess, timeout: float) -> Path:
    """使用系统编译器准备租约内的小转发器；无安装、提权或项目文件修改。

    Build a small lease-local relay with the system compiler, without installation or elevation.
    """
    lease = process.lease
    folder = lease.directory / lease.path.stem / "bridge"
    executable = folder / "bridge.exe"
    with lease.pool_lock:
        if executable.exists():
            return executable
        # 查询实际系统目录，不假定 Windows 安装盘符。
        # Query the real system directory rather than assuming its drive.
        query = process.kernel.GetWindowsDirectoryW
        query.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
        query.restype = ctypes.c_uint
        buffer = ctypes.create_unicode_buffer(query(None, 0))
        if not query(buffer, len(buffer)):
            raise AgentError("SANDBOX_PREVIEW_UNAVAILABLE", "无法定位 Windows 系统目录。")
        windows = Path(buffer.value)
        compilers = [
            candidate
            for framework in ("Framework64", "Framework")
            for candidate in sorted(
                (windows / "Microsoft.NET" / framework).glob("*/csc.exe"), reverse=True
            )
        ]
        if not compilers:
            raise AgentError(
                "SANDBOX_PREVIEW_UNAVAILABLE", "缺少 Windows .NET 编译器，无法准备沙箱预览转发器。"
            )
        folder.mkdir(parents=True, exist_ok=True)
        pending = folder / "bridge.pending.exe"
        try:
            result = subprocess.run(
                [
                    str(compilers[0]),
                    "/nologo",
                    "/target:exe",
                    f"/out:{pending}",
                    str(Path(__file__).with_name("sandbox_bridge.cs")),
                ],
                cwd=folder,
                env=process.environment,
                capture_output=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AgentError(
                "SANDBOX_PREVIEW_BUILD_FAILED",
                "沙箱预览转发器未能在就绪时限内准备，请查看运行环境。",
            ) from exc
        if result.returncode:
            raise AgentError("SANDBOX_PREVIEW_BUILD_FAILED", "沙箱预览转发器编译失败。")
        if lease.record is None:
            raise AgentError("SANDBOX_CLOSED", "沙箱已经关闭。")
        lease.record.grants.append(str(folder))
        write_document(lease.path, lease.record)
        lease.acl(folder, lease.record.principal, "RX")
        pending.replace(executable)
    return executable


def disconnect(connection: socket.socket) -> None:
    """解除读写阻塞；对端已断开也视为断开，不隐藏其他执行错误。

    Unblock reads and writes, including connections already closed by the peer.
    """
    try:
        connection.shutdown(socket.SHUT_RDWR)
    except OSError:
        # 关闭/重置的 socket 没有待完成的网络传输。 Closed/reset sockets need no shutdown.
        return


class SandboxPreview:
    """持有一个宿主预览端口及同沙箱转发 Job，随原服务一起清理。

    Own a host preview port and same-sandbox relay jobs for the lifetime of one service.
    """

    def __init__(
        self,
        process: SandboxProcess,
        url: str,
        timeout: float,
        startup_timeout: float | None = None,
    ) -> None:
        """准备转发后绑定随机本地端口，返回用户实际应该访问的 URL。

        Prepare forwarding and bind a free local port, exposing the actual browser URL.
        """
        self.process = process
        self.target = local_endpoint(url)
        self.executable = bridge_executable(process, startup_timeout or timeout)
        self.timeout = timeout
        self.closed = False
        self.lock = threading.Lock()
        self.clients: dict[socket.socket, WindowsProcess | None] = {}
        self.threads: list[threading.Thread] = []
        self.failure: AgentError | None = None
        self.listener = socket.socket()
        try:
            self.listener.bind(("127.0.0.1", 0))
            self.listener.listen()
            self.listener.settimeout(0.25)
            parsed = urlsplit(url)
            self.url = urlunsplit(
                parsed._replace(netloc=f"127.0.0.1:{self.listener.getsockname()[1]}")
            )
            self.acceptor = threading.Thread(target=self._accept, daemon=True)
            self.acceptor.start()
        except BaseException:
            self.listener.close()
            raise

    def _accept(self) -> None:
        """为实际连接创建转发线程，生命周期始终由服务持有。

        Start forwarding only for actual connections, always owned by the service.
        """
        while not self.closed:
            try:
                connection, _ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                if not self.closed:
                    self.failure = AgentError("SANDBOX_PREVIEW_FAILED", "沙箱预览监听中断。")
                return
            with self.lock:
                if self.closed:
                    connection.close()
                    return
                self.clients[connection] = None
                worker = threading.Thread(target=self._forward, args=(connection,), daemon=True)
                self.threads = [thread for thread in self.threads if thread.is_alive()]
                self.threads.append(worker)
                worker.start()

    def _forward(self, connection: socket.socket) -> None:
        """通过同主体进程转发原始字节，支持半关闭且不截断大响应。

        Relay raw bytes through a same-identity process, preserving half-close and large responses.
        """
        relay: WindowsProcess | None = None

        def receive(data: bytes) -> None:
            """输出直接送浏览器；服务 EOF 解除宿主读取等待。

            Send output directly to the browser and unblock reads at service EOF.
            """
            if data:
                connection.sendall(data)
            else:
                disconnect(connection)

        try:
            with self.lock:
                if self.closed:
                    return
                relay = WindowsProcess(
                    [str(self.executable), self.target[0], str(self.target[1])],
                    self.executable.parent,
                    self.process.environment,
                    8192,
                    security_capabilities=self.process.lease.capabilities,
                    input_pipe=True,
                    stdout_sink=receive,
                )
                self.clients[connection] = relay
            while data := connection.recv(65536):
                relay.write_input(data)
            relay.close_input()
            # 客户端输入 EOF 不意味着响应已结束，允许服务完成输出。
            # Client input EOF does not imply response EOF; let the service finish output.
            while not self.closed and relay.poll() is None:
                time.sleep(0.02)
            if not self.closed and relay.poll() != 0:
                logging.getLogger(__name__).warning(
                    "SANDBOX_PREVIEW_CONNECTION_EXIT code=%s", relay.poll()
                )
        except OSError:
            # 浏览器取消请求是连接生命周期事件，不中止开发服务。
            # Browser cancellation ends this connection, not the development service.
            logging.getLogger(__name__).debug("Sandbox preview client disconnected")
        except AgentError as exc:
            self.failure = exc
        finally:
            disconnect(connection)
            if relay is not None:
                try:
                    relay.finish(self.timeout)
                except AgentError as exc:
                    self.failure = exc
                finally:
                    relay.close()
            connection.close()
            with self.lock:
                self.clients.pop(connection, None)

    def close(self) -> None:
        """停止监听和全部转发 Job；核实线程结束，不遗留后台助手。

        Stop listening and all relay jobs, verifying threads exit without orphan helpers.
        """
        with self.lock:
            self.closed = True
            self.listener.close()
            for connection, process in self.clients.items():
                disconnect(connection)
                # Windows 的 shutdown 不保证唤醒另一线程阻塞的 recv；关闭句柄才释放它。
                # On Windows shutdown may leave another thread in recv; close the socket too.
                connection.close()
                if process is not None:
                    process.terminate()
        deadline = time.monotonic() + self.timeout
        for thread in [self.acceptor, *self.threads]:
            thread.join(max(0, deadline - time.monotonic()))
        if any(thread.is_alive() for thread in [self.acceptor, *self.threads]):
            raise AgentError("PROCESS_CLEANUP_FAILED", "沙箱预览转发尚未结束。")
