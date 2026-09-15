"""用真实自有子进程验证超时清理，不启动用户项目命令。

Verify timeout cleanup with owned child processes, never user-project commands.
"""

import ctypes
import os
import sys
import time

from my_agent.processes import run_probe


def test_timeout_terminates_descendant_and_closes_pipes():
    """确认超时结束后代进程并关闭继承管道；Windows 额外核实进程状态。

    Confirm timeout stops descendants and closes inherited pipes, checking Windows process state.
    """

    script = (
        "import subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        "print(child.pid, flush=True); child.wait()"
    )
    started = time.monotonic()
    result = run_probe([sys.executable, "-c", script], timeout=0.5)
    assert result.code == "TIMEOUT"
    assert time.monotonic() - started < 5
    descendant = int(result.output.strip())
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, descendant)
        if handle:
            try:
                code = ctypes.c_ulong()
                assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                assert code.value != 259  # STILL_ACTIVE
            finally:
                kernel.CloseHandle(handle)
