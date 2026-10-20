"""隔离目录内的真实受限进程负载。 Real restricted-process payload for isolated fixtures."""

import ctypes
import json
import socket
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path


def denied(action):
    """仅将权限拒绝记为隔离有效，不把其他异常充数。 Count access denial, not unrelated failures."""
    try:
        action()
    except PermissionError:
        return True
    return False


def main():
    """验证令牌、文件边界、网络与子进程继承。 Probe token, files, network and child inheritance."""
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    outside, readonly, writable = (Path(config[name]) for name in ("outside", "read", "write"))
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    token, value, size = wintypes.HANDLE(), wintypes.DWORD(), wintypes.DWORD()
    assert advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token))
    try:
        assert advapi.GetTokenInformation(token, 29, ctypes.byref(value), 4, ctypes.byref(size))
    finally:
        kernel.CloseHandle(token)
    Path("inside.txt").write_text("inside", encoding="utf-8")
    (writable / "allowed.txt").write_text("allowed", encoding="utf-8")
    results = {
        "appcontainer_token": value.value == 1,
        "project_read_write": Path("inside.txt").read_text() == "inside",
        "extra_read": (readonly / "sentinel.txt").read_text() == "original",
        "extra_read_write_denied": denied(lambda: (readonly / "sentinel.txt").write_text("bad")),
        "extra_write": (writable / "allowed.txt").read_text() == "allowed",
        "outside_read_denied": denied(lambda: (outside / "sentinel.txt").read_text()),
        "outside_write_denied": denied(lambda: (outside / "sentinel.txt").write_text("bad")),
        "parent_traversal_denied": denied(lambda: Path("../outside/sentinel.txt").read_text()),
        "junction_denied": denied(lambda: Path("escape/sentinel.txt").write_text("bad")),
    }
    try:
        with socket.create_connection(("127.0.0.1", config["port"]), timeout=1):
            results["offline_network_denied"] = False
    except (PermissionError, TimeoutError):
        results["offline_network_denied"] = True
    # 第二个进程重新执行文件权限探测，不能凭父进程令牌推断继承。
    # Probe permissions in a real child instead of inferring inheritance from the parent token.
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(outside / 'sentinel.txt')!r}).write_text('bad')",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    results["child_write_denied"] = child.returncode != 0 and "PermissionError" in child.stderr
    print(json.dumps(results), flush=True)
    assert all(results.values()), results


if __name__ == "__main__":
    main()
