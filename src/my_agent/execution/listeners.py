"""验证 HTTP 预览监听器确属本次 Job。

Verify that preview listeners belong to the owned job."""

import ctypes
import ipaddress
import socket
from ctypes import wintypes
from urllib.parse import urlsplit

from my_agent.errors import AgentError
from my_agent.execution.windows import WindowsProcess


class TcpRow(ctypes.Structure):
    """IPv4 监听记录的 Win32 ABI。

    Win32 ABI of an IPv4 listener record."""

    _fields_ = [
        (name, wintypes.DWORD)
        for name in ("state", "local_address", "local_port", "remote_address", "remote_port", "pid")
    ]


class Tcp6Row(ctypes.Structure):
    """IPv6 监听记录的 Win32 ABI。

    Win32 ABI of an IPv6 listener record."""

    _fields_ = [
        ("local_address", ctypes.c_ubyte * 16),
        ("local_scope", wintypes.DWORD),
        ("local_port", wintypes.DWORD),
        ("remote_address", ctypes.c_ubyte * 16),
        ("remote_scope", wintypes.DWORD),
        ("remote_port", wintypes.DWORD),
        ("state", wintypes.DWORD),
        ("pid", wintypes.DWORD),
    ]


def local_endpoint(url: str) -> tuple[str, int]:
    """仅解析无凭据的本机 HTTP(S) 地址，不执行 DNS 或外网请求。

    Accept local HTTP(S) URLs only."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError
        if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
            raise ValueError
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return host, port
    except ValueError as exc:
        raise AgentError(
            "SERVICE_URL_INVALID", "预览地址必须是不含凭据的本机 HTTP / HTTPS 地址。"
        ) from exc


def listener_pids(url: str) -> set[int]:
    """读取匹配本机地址的实时监听身份。 Read live listener identities for a local endpoint."""
    host, port = local_endpoint(url)
    library = ctypes.WinDLL("iphlpapi")
    query = library.GetExtendedTcpTable
    query.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    query.restype = wintypes.DWORD
    pids: set[int] = set()
    for family, row_type in ((socket.AF_INET, TcpRow), (socket.AF_INET6, Tcp6Row)):
        if host != "localhost" and (":" in host) != (family == socket.AF_INET6):
            continue
        size = wintypes.DWORD()
        result = query(None, ctypes.byref(size), False, family, 3, 0)
        if result not in {0, 122}:  # ERROR_INSUFFICIENT_BUFFER: 请求真实所需大小 / query size.
            raise AgentError("SERVICE_OWNERSHIP_UNAVAILABLE", "无法核实本机服务监听来源。")
        buffer = ctypes.create_string_buffer(size.value)
        result = query(buffer, ctypes.byref(size), False, family, 3, 0)
        if result == 122:
            # 表在两次读取间增长，停止本次核对，不假称端口空闲。
            # Fail this check if the table grew; never claim the port is unused.
            raise AgentError("SERVICE_LISTENERS_CHANGED", "监听表刚发生变化，请稍后重新检查。")
        if result:
            raise AgentError("SERVICE_OWNERSHIP_UNAVAILABLE", "无法核实本机服务监听来源。")
        count = wintypes.DWORD.from_buffer_copy(buffer).value
        if 4 + count * ctypes.sizeof(row_type) > len(buffer):
            raise AgentError("SERVICE_OWNERSHIP_UNAVAILABLE", "本机监听信息格式异常。")
        for index in range(count):
            row = row_type.from_buffer_copy(buffer, 4 + index * ctypes.sizeof(row_type))
            if socket.ntohs(row.local_port & 0xFFFF) != port:
                continue
            address = (
                socket.inet_ntop(socket.AF_INET, int(row.local_address).to_bytes(4, "little"))
                if isinstance(row, TcpRow)
                else socket.inet_ntop(socket.AF_INET6, bytes(row.local_address))
            )
            accepted = (
                {"0.0.0.0", "::", host}
                if host != "localhost"
                else {"0.0.0.0", "::", "127.0.0.1", "::1"}
            )
            if address not in accepted:
                continue
            pids.add(row.pid)
    return pids


def owns_listener(process: WindowsProcess, url: str) -> bool:
    """全部匹配监听器必须属于当前 Job，避免复用端口产生假就绪。

    Require all matching listeners to belong to the job, avoiding shared-port false readiness.
    """
    kernel = process.kernel
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.IsProcessInJob.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.BOOL),
    ]
    kernel.IsProcessInJob.restype = wintypes.BOOL
    pids = listener_pids(url)
    for pid in pids:
        with process.handle_lock:
            if not process.job:
                return False
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            try:
                belongs = wintypes.BOOL()
                if (
                    not kernel.IsProcessInJob(handle, process.job, ctypes.byref(belongs))
                    or not belongs.value
                ):
                    return False
            finally:
                kernel.CloseHandle(handle)
    return bool(pids)
