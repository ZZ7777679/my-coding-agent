"""执行受信开发工具的有界探测，不承担用户项目的命令执行。

Run bounded probes of trusted developer tools, not commands from user projects.
"""

import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


def probe_environment() -> dict[str, str]:
    """构造探测环境白名单，保留必要代理设置并排除模型密钥。

    Build a probe environment allowlist, retaining proxy settings but excluding model keys.
    """

    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "SYSTEMDRIVE",
        "UV_CACHE_DIR",
        "UV_PYTHON_INSTALL_DIR",
        "LANG",
        "PYTHONIOENCODING",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
    }
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


@dataclass(frozen=True)
class ProbeResult:
    """保存探测状态、退出码与有界内部输出；原始输出不直接进入公开报告。

    Hold probe status, exit code and bounded output, which stays out of public reports.
    """

    code: str
    returncode: int | None
    output: str


def run_probe(command: list[str], timeout: float = 3, limit: int = 65536) -> ProbeResult:
    """并发消费双管道；超时或超量时终止自有进程并等待管道清理。

    Drain both pipes concurrently; stop owned processes on timeout or overflow and clean up.
    """

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=probe_environment(),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
    except FileNotFoundError:
        return ProbeResult("DEPENDENCY_MISSING", None, "")
    except OSError:
        return ProbeResult("ENVIRONMENT_RESTRICTED", None, "")
    overflow = threading.Event()
    stopping = threading.Lock()
    outputs: list[bytes] = [b"", b""]

    def terminate() -> None:
        """串行化重复终止请求；Windows 处理自有进程树，其他平台处理进程组。

        Serialize stop requests; target the owned Windows process tree or POSIX process group.
        """

        with stopping:
            if process.poll() is not None:
                return
            if sys.platform == "win32":
                system = os.environ.get("SystemRoot", "")
                executable = Path(system) / "System32/taskkill.exe"
                if system and executable.is_file():
                    try:
                        subprocess.run(
                            [str(executable), "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=2,
                            check=False,
                            env=probe_environment(),
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        # 辅助终止失败后仍结束自有进程，后续管道等待会识别残留。
                        # Stop the owned process; pipe completion detects leftovers.
                        process.kill()
                else:
                    process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    return
            if process.poll() is None:
                process.kill()

    def consume(stream: BinaryIO, slot: int) -> None:
        """持续读取一条管道，超限后触发终止并始终关闭句柄。

        Drain one pipe, terminate on overflow and always close its handle.
        """

        chunks: list[bytes] = []
        size = 0
        try:
            while chunk := stream.read(4096):
                size += len(chunk)
                if size <= limit:
                    chunks.append(chunk)
                else:
                    overflow.set()
                    terminate()
            outputs[slot] = b"".join(chunks)
        finally:
            stream.close()

    assert process.stdout is not None and process.stderr is not None
    readers = [
        threading.Thread(target=consume, args=(process.stdout, 0), daemon=True),
        threading.Thread(target=consume, args=(process.stderr, 1), daemon=True),
    ]
    for reader in readers:
        reader.start()
    code = "OK"
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        code = "TIMEOUT"
        terminate()
        process.wait()
    for reader in readers:
        reader.join(timeout=1)
    if any(reader.is_alive() for reader in readers):
        return ProbeResult("PROCESS_CLEANUP_FAILED", process.returncode, "")
    if overflow.is_set():
        code = "OUTPUT_TOO_LARGE"
    elif code == "OK" and process.returncode != 0:
        code = "COMMAND_FAILED"
    return ProbeResult(
        code, process.returncode, b"\n".join(outputs).decode("utf-8", errors="replace")
    )
