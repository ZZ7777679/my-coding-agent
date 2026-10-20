"""Windows AppContainer 资源租约；只为明确选定目录授予临时访问。

Windows AppContainer leases grant temporary access only to explicitly selected directories.
"""

import ctypes
import json
import os
import shutil
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from my_agent.errors import AgentError
from my_agent.execution.types import EnvironmentView
from my_agent.execution.windows import WindowsProcess
from my_agent.models.types import ModelData
from my_agent.storage import read_document, write_document


class SidAttributes(ctypes.Structure):
    """能力 SID 的 Win32 ABI。 Win32 capability SID ABI."""

    _fields_ = [("sid", ctypes.c_void_p), ("attributes", wintypes.DWORD)]


class SecurityCapabilities(ctypes.Structure):
    """启动属性保持原生指针有效至 CreateProcess 返回。 Keep native pointers alive through launch."""

    _fields_ = [
        ("sid", ctypes.c_void_p),
        ("capabilities", ctypes.c_void_p),
        ("count", wintypes.DWORD),
        ("reserved", wintypes.DWORD),
    ]


class Trustee(ctypes.Structure):
    """按 SID 指定唯一 ACL 主体。 Identify one ACL trustee by its SID."""

    _fields_ = [
        ("multiple", ctypes.c_void_p),
        ("operation", wintypes.DWORD),
        ("form", wintypes.DWORD),
        ("kind", wintypes.DWORD),
        ("name", ctypes.c_void_p),
    ]


class ExplicitAccess(ctypes.Structure):
    """只添加或删除本租约主体的访问项。 Add/remove access only for this lease identity."""

    _fields_ = [
        ("permissions", wintypes.DWORD),
        ("mode", wintypes.DWORD),
        ("inheritance", wintypes.DWORD),
        ("trustee", Trustee),
    ]


class SecurityDescriptor(ctypes.Structure):
    """仅设置 DACL 所需的绝对描述符。 Absolute descriptor used to set only the DACL."""

    _fields_ = [
        ("revision", wintypes.BYTE),
        ("reserved", wintypes.BYTE),
        ("control", wintypes.WORD),
        ("owner", ctypes.c_void_p),
        ("group", ctypes.c_void_p),
        ("sacl", ctypes.c_void_p),
        ("dacl", ctypes.c_void_p),
    ]


class SandboxRecord(ModelData):
    """崩溃后仅清理本应用创建的主体和目录授权。 Recover only this app's identity and grants."""

    name: str
    principal: str
    grants: list[str] = Field(default_factory=list)
    traverse_grants: list[str] = Field(default_factory=list)
    skipped_ancestors: dict[str, int] = Field(default_factory=dict)


class SandboxLease:
    """同项目与配置共享主体至应用退出，清理失败保留记录。

    Share an identity for a project/configuration until app exit, retaining failed cleanup records.
    """

    pool: dict[tuple[str, str, str], "SandboxLease"] = {}
    pool_lock = threading.RLock()

    def __init__(self, directory: Path) -> None:
        """延迟绑定 Windows API，不影响直接执行或非 Windows 导入。 Bind APIs only on demand."""
        if os.name != "nt":
            raise AgentError("SANDBOX_UNAVAILABLE", "当前原生沙箱仅支持 Windows。")
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.userenv = ctypes.WinDLL("userenv", use_last_error=True)
        self.advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.userenv.CreateAppContainerProfile.argtypes = [wintypes.LPCWSTR] * 3 + [
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.userenv.CreateAppContainerProfile.restype = ctypes.c_long
        self.userenv.DeleteAppContainerProfile.argtypes = [wintypes.LPCWSTR]
        self.userenv.DeleteAppContainerProfile.restype = ctypes.c_long
        self.advapi.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.LPWSTR),
        ]
        self.advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
        self.advapi.ConvertStringSidToSidW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.advapi.ConvertStringSidToSidW.restype = wintypes.BOOL
        self.advapi.FreeSid.argtypes = [ctypes.c_void_p]
        self.advapi.FreeSid.restype = ctypes.c_void_p
        self.kernel.LocalFree.argtypes = [ctypes.c_void_p]
        self.kernel.LocalFree.restype = ctypes.c_void_p
        self.sid = ctypes.c_void_p()
        self.network_sids: list[ctypes.c_void_p] = []
        self.record: SandboxRecord | None = None
        self.path = directory / (uuid4().hex + ".json")
        self.capabilities = SecurityCapabilities()
        self.temporary: Path | None = None

    @classmethod
    def acquire(
        cls, directory: Path, root: Path, view: EnvironmentView, env: dict[str, str]
    ) -> "SandboxLease":
        """同项目同配置复用主体和系统授权，直到应用退出。

        Reuse an identity and its OS authorization for the same project/settings until app exit.
        """
        directory, root = directory.resolve(), root.resolve(strict=True)
        grants = cls.directory_grants(root, view)
        binding = view.execution
        if binding is None:
            raise AgentError("SANDBOX_CONFIG_REQUIRED", "启动未包含沙箱配置。")
        # 仅真实授权变化需要新主体；名称、探测、等待预算等不影响隔离边界。
        # Only actual grants need a new identity, not labels, probes or wait budgets.
        key = (
            str(directory),
            str(root),
            json.dumps(
                {
                    "network": binding.sandbox.network,
                    "grants": sorted((str(path), mode) for path, mode in grants.items()),
                }
            ),
        )
        with cls.pool_lock:
            lease = cls.pool.get(key)
            if lease is None:
                lease = cls(directory)
                try:
                    lease.start(view, env, grants)
                except BaseException:
                    lease.close()
                    raise
                cls.pool[key] = lease
            if lease.temporary is not None:
                env["TEMP"] = env["TMP"] = str(lease.temporary)
            return lease

    @classmethod
    def close_all(cls, directory: Path) -> None:
        """进程全部清理后撤销本数据根的共享授权。

        Revoke this data root's grants after reaping processes.
        """
        with cls.pool_lock:
            failure: AgentError | OSError | None = None
            for key, lease in list(cls.pool.items()):
                if lease.directory == directory:
                    try:
                        lease.close()
                    except (AgentError, OSError) as exc:
                        failure = failure or exc
                    finally:
                        del cls.pool[key]
            if failure:
                raise failure

    @staticmethod
    def directory_grants(root: Path, view: EnvironmentView) -> dict[Path, Literal["RX", "M"]]:
        """解析实际目录权限，供复用身份与启动共用；写授权优先。

        Resolve effective grants once for reuse and startup; writes take priority.
        """
        binding = view.execution
        if binding is None or binding.mode != "sandbox":
            raise AgentError("SANDBOX_CONFIG_REQUIRED", "启动未包含沙箱配置。")
        grants: dict[Path, Literal["RX", "M"]] = {}
        for values, permission in (
            ([*binding.sandbox.read_paths, view.prefix], "RX"),
            (binding.sandbox.write_paths, "M"),
        ):
            for value in values:
                if not value:
                    continue
                try:
                    path = (root / value).resolve(strict=True)
                except OSError as exc:
                    raise AgentError(
                        "SANDBOX_PATH_UNAVAILABLE", f"沙箱目录不可用：{value}。"
                    ) from exc
                if not path.is_dir():
                    raise AgentError("SANDBOX_PATH_UNAVAILABLE", f"沙箱授权需要目录：{path}。")
                grants[path] = "M" if permission == "M" else "RX"
        grants[root] = "M"
        return grants

    def acl(
        self, path: Path, principal: str, permission: str | None, *, inherit: bool = True
    ) -> None:
        """按唯一主体修改 ACL，不替换原 ACL、不修改系统策略。

        Modify only the unique principal ACE.
        """
        # 直接更新明确对象的 DACL；icacls 对卷根的处理会长时间扫描，不适合启动链路。
        # Update the named object's DACL directly; icacls volume-root scans can stall launch.
        pointer = ctypes.c_void_p
        api = self.advapi
        api.GetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(pointer),
            ctypes.POINTER(pointer),
            ctypes.POINTER(pointer),
            ctypes.POINTER(pointer),
            ctypes.POINTER(pointer),
        ]
        api.GetNamedSecurityInfoW.restype = wintypes.DWORD
        api.SetEntriesInAclW.argtypes = [
            wintypes.ULONG,
            ctypes.POINTER(ExplicitAccess),
            pointer,
            ctypes.POINTER(pointer),
        ]
        api.SetEntriesInAclW.restype = wintypes.DWORD
        api.GetExplicitEntriesFromAclW.argtypes = [
            pointer,
            ctypes.POINTER(wintypes.ULONG),
            ctypes.POINTER(ctypes.POINTER(ExplicitAccess)),
        ]
        api.GetExplicitEntriesFromAclW.restype = wintypes.DWORD
        api.EqualSid.argtypes = [pointer, pointer]
        api.EqualSid.restype = wintypes.BOOL
        api.SetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            pointer,
            pointer,
            pointer,
            pointer,
        ]
        api.SetNamedSecurityInfoW.restype = wintypes.DWORD
        api.InitializeSecurityDescriptor.argtypes = [pointer, wintypes.DWORD]
        api.InitializeSecurityDescriptor.restype = wintypes.BOOL
        api.SetSecurityDescriptorDacl.argtypes = [pointer, wintypes.BOOL, pointer, wintypes.BOOL]
        api.SetSecurityDescriptorDacl.restype = wintypes.BOOL
        api.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, pointer]
        api.SetFileSecurityW.restype = wintypes.BOOL
        sid, descriptor, old, updated = pointer(), pointer(), pointer(), pointer()
        entries = ctypes.POINTER(ExplicitAccess)()

        def checked(code: int) -> None:
            """保留真实系统错误，不能假报权限已生效。 Retain actual OS errors, never fake grants."""
            if code:
                raise AgentError(
                    "SANDBOX_ACCESS_FAILED", f"沙箱目录授权未完成：{path}（系统错误 {code}）。"
                ) from ctypes.WinError(code)

        try:
            if not api.ConvertStringSidToSidW(principal.removeprefix("*"), ctypes.byref(sid)):
                checked(ctypes.get_last_error())
            checked(
                api.GetNamedSecurityInfoW(
                    str(path), 1, 4, None, None, ctypes.byref(old), None, ctypes.byref(descriptor)
                )
            )
            if permission is None:
                if not old:
                    return
                count = wintypes.ULONG()
                checked(
                    api.GetExplicitEntriesFromAclW(old, ctypes.byref(count), ctypes.byref(entries))
                )
                # 本应用只添加普通 SID ACE；失败前的日志不代表 ACE 已成功写入。
                # This app adds plain SID ACEs only; a journaled attempt need not have written one.
                if not any(
                    entries[index].trustee.form == 0
                    and entries[index].trustee.name
                    and api.EqualSid(entries[index].trustee.name, sid)
                    for index in range(count.value)
                ):
                    return
            entry = ExplicitAccess(
                {"RX": 0x1200A9, "M": 0x1301BF, "(X,RA,REA,RC,S)": 0x1200A8}[permission]
                if permission
                else 0,
                1 if permission else 4,  # GRANT_ACCESS / REVOKE_ACCESS
                3 if inherit and permission else 0,  # OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE
                Trustee(None, 0, 0, 0, sid),
            )
            checked(api.SetEntriesInAclW(1, ctypes.byref(entry), old, ctypes.byref(updated)))
            if inherit:
                checked(api.SetNamedSecurityInfoW(str(path), 1, 4, None, None, updated, None))
            else:
                # 此旧 API 的不传播语义适用于祖先目录；新 API 会重遍历子树，
                # 而 MAXIMUM_ALLOWED 句柄会与正在使用的 cwd 产生共享冲突。
                # This legacy API deliberately avoids child propagation; modern setters
                # traverse subtrees, while MAXIMUM_ALLOWED conflicts with open cwd handles.
                local = SecurityDescriptor()
                if not api.InitializeSecurityDescriptor(ctypes.byref(local), 1):
                    checked(ctypes.get_last_error())
                if not api.SetSecurityDescriptorDacl(ctypes.byref(local), True, updated, False):
                    checked(ctypes.get_last_error())
                if not api.SetFileSecurityW(str(path), 4, ctypes.byref(local)):
                    checked(ctypes.get_last_error())
        finally:
            for allocation in (sid, descriptor, updated, entries):
                if allocation:
                    self.kernel.LocalFree(allocation)

    def grant_ancestor(self, path: Path) -> None:
        """祖先元数据授权仅增强工具兼容性，拒绝授权不替代实际启动结果。

        Ancestor metadata grants only improve tool compatibility; denial does not gate launch.
        """
        if self.record is None:
            raise AgentError("SANDBOX_CLOSED", "沙箱已经关闭。")
        self.record.grants.append(str(path))
        self.record.traverse_grants.append(str(path))
        write_document(self.path, self.record)
        try:
            self.acl(path, self.record.principal, "(X,RA,REA,RC,S)", inherit=False)
        except AgentError as exc:
            cause = exc.__cause__
            if not isinstance(cause, OSError) or cause.winerror != 5:
                raise
            # 访问已授权子目录不要求能打开每个祖先；保留未授予事实，不放宽真实目录权限。
            # A granted child need not open every ancestor; retain denial without broadening grants.
            self.record.skipped_ancestors[str(path)] = cause.winerror
            write_document(self.path, self.record)

    def start(
        self, view: EnvironmentView, env: dict[str, str], grants: dict[Path, Literal["RX", "M"]]
    ) -> None:
        """用项目设置创建隔离主体；所选环境只读，临时数据可写。

        Create a restricted identity from settings; selected environments are read-only.
        """
        binding = view.execution
        if binding is None or binding.mode != "sandbox":
            raise AgentError("SANDBOX_CONFIG_REQUIRED", "启动未包含沙箱配置。")
        name = "MyCodingAgent." + uuid4().hex
        result = self.userenv.CreateAppContainerProfile(
            name, name, "My Coding Agent project execution", None, 0, ctypes.byref(self.sid)
        )
        if result:
            raise AgentError(
                "SANDBOX_CREATE_FAILED", f"AppContainer 创建失败：{result & 0xFFFFFFFF:08x}。"
            )
        text = wintypes.LPWSTR()
        try:
            if not self.advapi.ConvertSidToStringSidW(self.sid, ctypes.byref(text)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.record = SandboxRecord(name=name, principal="*" + str(text.value))
            write_document(self.path, self.record)
        except BaseException:
            if self.record is None:
                self.userenv.DeleteAppContainerProfile(name)
            raise
        finally:
            if text:
                self.kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))
        control = self.directory / self.path.stem
        temporary = control / "tmp"
        temporary.mkdir(parents=True)
        self.temporary = temporary
        grants[temporary] = "M"
        # PowerShell/.NET 会查询祖先目录元数据；仅授予遍历和属性读取，不继承到兄弟文件。
        # PowerShell/.NET inspect ancestors; metadata/traverse access never inherits to siblings.
        ancestors = {parent for path in grants for parent in path.parents if parent not in grants}
        for path in sorted(ancestors, key=lambda path: len(path.parts)):
            self.grant_ancestor(path)
        for path, permission in grants.items():
            # 先记录后授权，即使调用期间退出也能在下次启动清理。
            # Journal before granting so interrupted calls remain recoverable.
            self.record.grants.append(str(path))
            write_document(self.path, self.record)
            self.acl(path, self.record.principal, permission)
        env["TEMP"] = env["TMP"] = str(temporary)
        if binding.sandbox.network == "enabled":
            for suffix in (1, 2, 3):
                sid = ctypes.c_void_p()
                if not self.advapi.ConvertStringSidToSidW(f"S-1-15-3-{suffix}", ctypes.byref(sid)):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.network_sids.append(sid)
        self.entries = (SidAttributes * len(self.network_sids))(
            *(SidAttributes(sid, 4) for sid in self.network_sids)
        )
        # 零项能力必须使用空指针，否则 CreateProcess 返回 ERROR_INVALID_PARAMETER。
        # A zero-capability list needs a null pointer to avoid ERROR_INVALID_PARAMETER.
        self.capabilities = SecurityCapabilities(
            self.sid,
            ctypes.cast(self.entries, ctypes.c_void_p) if self.network_sids else None,
            len(self.network_sids),
            0,
        )

    def close(self) -> None:
        """撤销本次授权后删除主体；失败保留日志供恢复，不假报成功。

        Revoke grants before removing the identity; preserve journals on cleanup failure.
        """
        try:
            if self.record:
                # 仅回收旧版本遗留助手；新执行路径从不启动提权程序。
                # Recover legacy helpers only; new execution never launches elevation.
                control = self.directory / self.path.stem
                if (control / "network.ready").exists():
                    (control / "network.stop").write_text("stop", encoding="utf-8")
                    deadline = time.monotonic() + 10
                    while not self.network_finished(control):
                        if time.monotonic() >= deadline:
                            raise AgentError(
                                "SANDBOX_NETWORK_CLEANUP", "旧网络授权尚未清理，请重试。"
                            )
                        time.sleep(0.05)
                for value in reversed(self.record.grants):
                    if Path(value).exists():
                        self.acl(
                            Path(value),
                            self.record.principal,
                            None,
                            inherit=value not in self.record.traverse_grants,
                        )
                code = self.userenv.DeleteAppContainerProfile(self.record.name)
                if code not in (0, -2147024894):
                    raise AgentError("SANDBOX_CLEANUP_FAILED", "沙箱主体清理失败，已保留恢复记录。")
                self.path.unlink(missing_ok=True)
                self.record = None
                temporary = (self.directory / self.path.stem / "tmp").resolve()
                if temporary.is_relative_to(self.directory.resolve()) and temporary.exists():
                    shutil.rmtree(temporary)
                bridge = (control / "bridge").resolve()
                if bridge.is_relative_to(self.directory.resolve()) and bridge.exists():
                    shutil.rmtree(bridge)
        finally:
            for sid in self.network_sids:
                self.kernel.LocalFree(sid)
            self.network_sids.clear()
            if self.sid:
                self.advapi.FreeSid(self.sid)
                self.sid = ctypes.c_void_p()

    @staticmethod
    def network_finished(control: Path) -> bool:
        """完成标记必须有真实结果，预创建的文件不等于授权已撤销。

        Require the completed fact; a precreated marker does not prove revocation.
        """
        try:
            return (
                json.loads((control / "network.done").read_text(encoding="utf-8")).get("finished")
                is True
            )
        except (OSError, ValueError):
            return False

    @classmethod
    def recover(cls, directory: Path) -> None:
        """应用持有单写者锁后清理遗留主体，不恢复历史进程。

        Clean orphaned leases, never replay processes.
        """
        if not directory.exists():
            return
        failures: list[str] = []
        for path in directory.glob("*.json"):
            try:
                record = read_document(path, SandboxRecord)
                if not record.name.startswith("MyCodingAgent.") or not record.principal.startswith(
                    "*S-1-15-2-"
                ):
                    raise AgentError("SANDBOX_RECORD_INVALID", "沙箱清理记录主体不属于本应用。")
                lease = cls(directory)
                lease.path, lease.record = path, record
                lease.close()
            except (AgentError, OSError) as exc:
                # 一份坏记录不能跳过其他独立租约；失败项仍留在原处，不猜测其权限。
                # One bad journal must not skip independent leases; preserve failed records as-is.
                code = exc.code if isinstance(exc, AgentError) else type(exc).__name__
                failures.append(f"{path.name}: {code}")
        if failures:
            raise AgentError(
                "SANDBOX_CLEANUP_FAILED",
                "其他租约已处理；以下记录仍待清理（普通开发可继续）：" + "；".join(failures),
            )


class SandboxProcess(WindowsProcess):
    """进程使用共享沙箱租约，权限由应用退出统一释放。

    Use a shared lease revoked at application exit.
    """

    def __init__(
        self,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        output_limit: int,
        directory: Path,
        root: Path,
        view: EnvironmentView,
    ) -> None:
        """获取项目租约后创建受限进程。

        Acquire the project lease before restricted process creation.
        """
        self.lease = SandboxLease.acquire(directory, root, view, env)
        self.environment = dict(env)
        super().__init__(
            command, cwd, env, output_limit, security_capabilities=self.lease.capabilities
        )

    def close(self) -> None:
        """结束进程句柄，共享主体仍供同项目后续命令使用。

        Close process handles while retaining the shared identity.
        """
        super().close()
