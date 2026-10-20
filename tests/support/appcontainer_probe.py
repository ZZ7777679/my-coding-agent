"""M6 原生隔离可行性探针：仅操作测试目录和临时 profile。

M6 native isolation probe; touches only test artifacts and a temporary AppContainer profile.
"""

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4

from my_agent.execution.windows import WindowsProcess
from my_agent.terminals.sandbox_native import SandboxPty


class SecurityCapabilities(ctypes.Structure):
    """Win32 安全能力 ABI。 Win32 security-capability ABI."""

    _fields_ = [
        ("sid", ctypes.c_void_p),
        ("capabilities", ctypes.c_void_p),
        ("count", wintypes.DWORD),
        ("reserved", wintypes.DWORD),
    ]


def main() -> None:
    """创建临时主体，测试 CMD 和文件访问，然后删除授权与 profile。

    Create a temporary identity, probe CMD/file access, then remove its grants and profile.
    """
    root = (
        Path(__file__).resolve().parents[2] / ".artifacts/tests" / ("appcontainer-" + uuid4().hex)
    ).resolve()
    project, outside = root / "project", root / "outside"
    project.mkdir(parents=True)
    outside.mkdir()
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--plain-terminal", action="store_true")
    options = parser.parse_args()
    runtime = options.runtime.resolve() if options.runtime else root / "python-runtime"
    if not runtime.is_relative_to(root.parent):
        raise ValueError("Probe runtime must stay inside .artifacts/tests")
    if options.runtime is None:
        shutil.copytree(Path(sys.base_prefix), runtime)
    name = "MyCodingAgent.Probe." + uuid4().hex
    userenv = ctypes.WinDLL("userenv", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    userenv.CreateAppContainerProfile.argtypes = [wintypes.LPCWSTR] * 3 + [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    userenv.CreateAppContainerProfile.restype = ctypes.c_long
    userenv.DeleteAppContainerProfile.argtypes = [wintypes.LPCWSTR]
    userenv.DeleteAppContainerProfile.restype = ctypes.c_long
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi.FreeSid.argtypes = [ctypes.c_void_p]
    advapi.FreeSid.restype = ctypes.c_void_p
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    sid = ctypes.c_void_p()
    result = userenv.CreateAppContainerProfile(
        name, name, "M6 isolated probe", None, 0, ctypes.byref(sid)
    )
    if result != 0:
        raise RuntimeError(f"CreateAppContainerProfile HRESULT={result & 0xFFFFFFFF:08x}")
    sid_text = wintypes.LPWSTR()
    granted = False
    runtime_granted = False
    results = {}
    try:
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise ctypes.WinError(ctypes.get_last_error())
        principal = "*" + str(sid_text.value)
        capabilities = SecurityCapabilities(sid, None, 0, 0)
        system = Path(os.environ["SystemRoot"])
        icacls = str(system / "System32/icacls.exe")
        grant = subprocess.run(
            [icacls, str(project), "/grant", principal + ":(OI)(CI)M"],
            capture_output=True,
            timeout=15,
        )
        if grant.returncode:
            raise RuntimeError(f"icacls grant failed: {grant.returncode}")
        granted = True
        runtime_grant = subprocess.run(
            [icacls, str(runtime), "/grant", principal + ":(OI)(CI)RX"],
            capture_output=True,
            timeout=15,
        )
        if runtime_grant.returncode:
            raise RuntimeError(f"runtime grant failed: {runtime_grant.returncode}")
        runtime_granted = True
        command = [
            str(system / "System32/cmd.exe"),
            "/d",
            "/c",
            f"echo INSIDE>{project / 'inside.txt'} & echo OUTSIDE>{outside / 'outside.txt'}",
        ]
        environment = {
            key: os.environ[key]
            for key in (
                "SystemRoot",
                "SystemDrive",
                "USERPROFILE",
                "LOCALAPPDATA",
                "APPDATA",
                "TEMP",
                "TMP",
            )
            if key in os.environ
        }
        process = WindowsProcess(
            command, system, environment, 8192, security_capabilities=capabilities
        )
        try:
            deadline = time.monotonic() + 10
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            results = {
                "exit_code": process.poll(),
                "inside_written": (project / "inside.txt").exists(),
                "outside_written": (outside / "outside.txt").exists(),
            }
            process.finish(5)
            results["output"] = str(list(process.buffer))
        finally:
            process.close()
        script = project / "probe.py"
        script.write_text(
            "from pathlib import Path\nimport sys, subprocess\n"
            "Path('python.txt').write_text(sys.version)\n"
            "subprocess.run([sys.executable, '-c', 'print(123)'], check=True)\n",
            encoding="utf-8",
        )
        process = WindowsProcess(
            [str(runtime / "python.exe"), str(script)],
            project,
            environment,
            8192,
            security_capabilities=capabilities,
        )
        try:
            deadline = time.monotonic() + 10
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            results["python_exit_code"] = process.poll()
            results["python_written"] = (project / "python.txt").exists()
            process.finish(5)
            results["python_output"] = str(list(process.buffer))
        finally:
            process.close()
        terminal = SandboxPty(
            [str(system / "System32/cmd.exe"), "/d", "/q"],
            project,
            environment,
            100,
            25,
            None if options.plain_terminal else capabilities,
            8192,
        )
        try:
            terminal.write("echo TERMINAL_OK\r\nexit\r\n")
            deadline = time.monotonic() + 10
            output = ""
            while terminal.poll() is None and time.monotonic() < deadline:
                output += terminal.read()
                time.sleep(0.02)
            results["terminal_exit_code"] = terminal.poll()
            terminal.finish(5)
            output += terminal.read()
            results["terminal_output"] = output
        finally:
            terminal.close()
    finally:
        if runtime_granted:
            removed = subprocess.run(
                [icacls, str(runtime), "/remove:g", principal], capture_output=True, timeout=15
            )
            results["runtime_grant_removed"] = removed.returncode == 0
        if granted:
            removed = subprocess.run(
                [icacls, str(project), "/remove:g", principal], capture_output=True, timeout=15
            )
            results["grant_removed"] = removed.returncode == 0
        if sid_text:
            kernel.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
        advapi.FreeSid(sid)
        results["profile_removed"] = userenv.DeleteAppContainerProfile(name) == 0
        (root / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"artifact": str(root), **results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
