"""受信后端持有秘密值；公开对象仅包含凭据状态。

Only the trusted backend holds secrets; public objects contain credential status.
"""

import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from pydantic import SecretStr

from my_agent.rpc.dto import CredentialInfo

KEY_ENV: Final = "OPENCODE_API_KEY"


@dataclass(frozen=True)
class ResolvedCredential:
    """将受保护的秘密值与可公开的来源状态分开保存。

    Keep the protected secret separate from public source metadata.
    """

    secret: SecretStr | None
    info: CredentialInfo


def read_windows_user(name: str) -> str | None:
    """只查询指定的当前用户环境变量；不存在与读取失败分别处理。

    Read one current-user variable, distinguishing absence from access failure.
    """

    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value if isinstance(value, str) else None
    except FileNotFoundError:
        return None


def resolve_credential(
    environ: Mapping[str, str] | None = None,
    user_reader: Callable[[str], str | None] | None = None,
    platform: str = sys.platform,
) -> ResolvedCredential:
    """非空进程凭据优先，再查 Windows 用户变量；返回状态，不输出秘密。

    Prefer a nonblank process key, then a Windows user key; return status without logging.
    """

    env = os.environ if environ is None else environ
    value = env.get(KEY_ENV, "")
    if value.strip():
        return ResolvedCredential(
            SecretStr(value), CredentialInfo(env_var=KEY_ENV, source="process", present=True)
        )
    if platform == "win32":
        try:
            value = (user_reader or read_windows_user)(KEY_ENV) or ""
        except OSError:
            return ResolvedCredential(
                None, CredentialInfo(env_var=KEY_ENV, source="restricted", present=None)
            )
        if value.strip():
            return ResolvedCredential(
                SecretStr(value),
                CredentialInfo(env_var=KEY_ENV, source="windows_user", present=True),
            )
    return ResolvedCredential(None, CredentialInfo(env_var=KEY_ENV, source="none", present=False))
