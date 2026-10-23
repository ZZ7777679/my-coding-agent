"""MCP 专用凭据引用与 Windows 加密保存；不向公开 DTO 返回秘密。

Resolve MCP credentials and persist Windows-encrypted tokens without exposing secrets.
"""

import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, ValidationError

from my_agent.credentials import read_windows_user
from my_agent.errors import AgentError
from my_agent.mcp_client.types import McpConnectionValues, McpServer
from my_agent.models.types import ModelData
from my_agent.storage import read_document, write_document


class _Blob(ctypes.Structure):
    """Windows DATA_BLOB 的有长度字节区。

    Length-prefixed bytes for the Windows DATA_BLOB ABI."""

    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


class _EncryptedToken(ModelData):
    """磁盘只保存 DPAPI 输出。

    Persist DPAPI output only."""

    encrypted: str


def _crypt(data: bytes, *, decrypt: bool) -> bytes:
    """使用当前 Windows 用户的 DPAPI，释放系统分配的输出区。

    Use current-user DPAPI and release the system-allocated output buffer.
    """
    if sys.platform != "win32":
        raise AgentError(
            "MCP_CREDENTIAL_UNAVAILABLE", "加密保存目前支持 Windows；可改用环境变量引用。"
        )
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    library = ctypes.WinDLL("crypt32", use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(_Blob),
        ctypes.c_void_p if decrypt else wintypes.LPCWSTR,
        ctypes.POINTER(_Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_Blob),
    ]
    function.restype = wintypes.BOOL
    # UI_FORBIDDEN 防止后台弹系统对话框；不使用 LOCAL_MACHINE，绑定当前用户。
    # UI_FORBIDDEN avoids background dialogs; omit LOCAL_MACHINE to bind the current user.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise AgentError(
            "MCP_CREDENTIAL_UNAVAILABLE", "Windows 无法处理此凭据，请重新输入或改用环境变量。"
        )
    release = ctypes.WinDLL("kernel32", use_last_error=True).LocalFree
    release.argtypes = [ctypes.c_void_p]
    release.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        release(ctypes.cast(target.data, ctypes.c_void_p))


def environment_value(name: str) -> str:
    """只查指定变量，进程优先，Windows 用户变量作为后备。

    Read one explicit variable, preferring the process over Windows user storage.
    """
    if not name.strip():
        raise AgentError("MCP_CREDENTIAL_MISSING", "请填写凭据的环境变量名称。")
    value = os.environ.get(name, "")
    if value.strip():
        return value
    if sys.platform == "win32":
        try:
            value = read_windows_user(name) or ""
        except OSError as exc:
            raise AgentError(
                "MCP_CREDENTIAL_UNAVAILABLE", f"无法读取用户环境变量 {name}。"
            ) from exc
        if value.strip():
            return value
    raise AgentError(
        "MCP_CREDENTIAL_MISSING", f"未找到环境变量 {name}，可填写后重试或加密保存令牌。"
    )


class McpCredentials:
    """按服务身份保存凭据，只在连接装配时解密。

    Store credentials by server identity and decrypt only when assembling a connection.
    """

    def __init__(self, root: Path, *, directory_name: str = "mcp-credentials") -> None:
        """绑定应用数据根，不自动创建凭据目录。

        Bind app data without eagerly creating credential files."""
        self.directory = root / directory_name

    def path(self, server_id: str) -> Path:
        """身份来自已校验的 McpServer，目录不接受服务返回路径。

        IDs come from validated McpServer values, never server-returned paths."""
        return self.directory / f"{server_id}.json"

    def save(self, server_id: str, value: SecretStr) -> None:
        """加密成功后原子替换对应文件。

        Atomically replace the owned file after successful encryption."""
        token = value.get_secret_value().strip()
        if not token:
            raise AgentError("MCP_CREDENTIAL_MISSING", "令牌为空；请填写或保留原凭据。")
        encrypted = base64.b64encode(_crypt(token.encode("utf-8"), decrypt=False)).decode("ascii")
        self.directory.mkdir(parents=True, exist_ok=True)
        write_document(self.path(server_id), _EncryptedToken(encrypted=encrypted))

    def read(self, server_id: str) -> str:
        """解密当前用户保存的令牌，损坏时保留原文件。

        Decrypt the current user's token, retaining damaged files on failure."""
        path = self.path(server_id)
        if not path.exists():
            raise AgentError("MCP_CREDENTIAL_MISSING", "尚未保存此服务的令牌，请编辑连接配置。")
        stored = read_document(path, _EncryptedToken)
        try:
            return _crypt(base64.b64decode(stored.encrypted, validate=True), decrypt=True).decode(
                "utf-8"
            )
        except (ValueError, UnicodeError) as exc:
            raise AgentError(
                "MCP_CREDENTIAL_UNAVAILABLE", "保存的凭据无法读取，请重新输入。"
            ) from exc

    def remove(self, server_id: str) -> None:
        """仅删除所选服务的凭据文件。

        Remove only the selected service's credential file."""
        try:
            self.path(server_id).unlink(missing_ok=True)
        except OSError as exc:
            raise AgentError("MCP_CREDENTIAL_UNAVAILABLE", "无法删除保存的凭据。") from exc


class McpSavedValues:
    """复用 DPAPI 保存导入的变量与多请求头，不回传其值。

    Reuse DPAPI for imported environment and header values without reading them back to UI.
    """

    def __init__(self, root: Path) -> None:
        """使用独立凭据文件，保持原令牌格式兼容。

        Keep legacy tokens compatible in separate files."""
        self.credentials = McpCredentials(root, directory_name="mcp-connection-values")

    def read(self, server_id: str) -> McpConnectionValues:
        """解密并验证自身数据；损坏不重置。 Decrypt owned data without resetting corrupt files."""
        try:
            return McpConnectionValues.model_validate_json(self.credentials.read(server_id))
        except ValidationError as exc:
            raise AgentError(
                "MCP_CREDENTIAL_UNAVAILABLE", "保存的连接变量损坏，请重新填写。"
            ) from exc

    def save(self, server: McpServer, update: McpConnectionValues | None) -> None:
        """合并显式更新，只保存仍被配置引用的名称。

        Merge explicit updates and retain configured names only."""
        if update is None:
            return
        if not server.stored_env and not server.stored_headers:
            self.credentials.remove(server.server_id)
            return
        current = (
            self.read(server.server_id)
            if self.credentials.path(server.server_id).is_file()
            else McpConnectionValues()
        )
        merged: dict[str, dict[str, str]] = {}
        for name, wanted, old, new in (
            ("env", server.stored_env, current.env, update.env),
            ("headers", server.stored_headers, current.headers, update.headers),
        ):
            values = {**old, **new}
            missing = [key for key in wanted if key not in values]
            if missing:
                raise AgentError("MCP_CREDENTIAL_MISSING", "请填写新增连接变量的值。")
            merged[name] = {key: values[key].get_secret_value() for key in wanted}
        self.credentials.save(server.server_id, SecretStr(json.dumps(merged, ensure_ascii=False)))

    def values(self, server: McpServer, kind: Literal["env", "headers"]) -> dict[str, str]:
        """只在连接装配时返回所需变量。 Resolve configured values only at connection assembly."""
        names = server.stored_env if kind == "env" else server.stored_headers
        if not names:
            return {}
        stored = self.read(server.server_id)
        values = stored.env if kind == "env" else stored.headers
        if any(name not in values for name in names):
            raise AgentError("MCP_CREDENTIAL_MISSING", "已保存连接变量缺失，请编辑服务配置。")
        return {name: values[name].get_secret_value() for name in names}
