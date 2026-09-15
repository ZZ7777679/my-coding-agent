"""默认只读诊断；写入与网络探测由调用方显式开启。

Diagnostics are read-only by default; callers explicitly enable write and network probes.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from my_agent import __version__
from my_agent.config import load_config, resolve_data_dir
from my_agent.credentials import ResolvedCredential, resolve_credential
from my_agent.errors import AgentError
from my_agent.processes import run_probe
from my_agent.projects import ProjectService
from my_agent.rpc.dto import DiagnosticCheck, DiagnosticReport
from my_agent.storage import Storage, utc_now


def diagnose(
    data_dir: str | None = None,
    *,
    model: str | None = None,
    dev: bool = False,
    network: bool = False,
    write_probe: bool = False,
    credential: ResolvedCredential | None = None,
    storage: Storage | None = None,
) -> DiagnosticReport:
    """汇总当前环境与存储状态；可复用已有写入者，不把目录可达当成认证成功。

    Report environment and storage status; reuse the owner and never infer authentication.
    """

    checks: list[DiagnosticCheck] = []

    def add(
        name: str,
        code: str,
        summary: str,
        *,
        blocking: bool = False,
        evidence: dict[str, str | bool | int | None] | None = None,
        unchecked: bool = False,
        remediation: str = "",
    ) -> None:
        """将单项证据归一为公开诊断状态，区分警告、阻塞与未检查。

        Normalize one public check, distinguishing warnings, blockers and unchecked states.
        """

        checks.append(
            DiagnosticCheck(
                check_id=name,
                status="not_checked"
                if unchecked
                else ("ok" if code == "OK" else "error" if blocking else "warning"),
                code=code,
                summary=summary,
                blocking=blocking,
                evidence=evidence or {},
                remediation=remediation,
            )
        )

    valid_python = sys.version_info[:2] == (3, 13)
    add(
        "python",
        "OK" if valid_python else "PYTHON_VERSION_UNSUPPORTED",
        "应用解释器版本已检查。",
        blocking=not valid_python,
        evidence={"version": ".".join(map(str, sys.version_info[:3]))},
    )
    try:
        store = storage or Storage(resolve_data_dir(data_dir))
        location = store.location
        config = load_config(location, model)
        add("config", "OK", "应用配置有效。", evidence={"model": config.model.model_id})
        info = store.info()
        ProjectService(store).read()
        parent = store.root
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        writable = os.access(parent, os.W_OK)
        add(
            "storage",
            "OK" if writable else "DATA_DIR_NOT_WRITABLE",
            "数据路径与读取条件已检查；写入能力需显式探测。",
            blocking=not writable,
            evidence={"data_dir": info.data_dir, "source": info.source, "status": info.status},
        )
        add(
            "writer",
            "DATA_DIR_BUSY" if info.status == "busy" else "OK",
            "数据目录已被使用。" if info.status == "busy" else "写入锁状态正常。",
            blocking=info.status == "busy",
        )
        free = shutil.disk_usage(parent).free
        add(
            "disk",
            "OK" if free >= 1024 * 1024 else "DISK_FULL",
            "可用空间已检查。",
            blocking=free < 1024 * 1024,
            evidence={"free_bytes": min(free, 2**53 - 1)},
        )
        if write_probe:
            if info.status == "busy":
                add(
                    "write_probe",
                    "DATA_DIR_BUSY",
                    "数据目录被占用，未执行写入探测。",
                    blocking=True,
                )
            else:
                with tempfile.TemporaryFile(dir=parent) as stream:
                    stream.write(b"my-agent-probe")
                    stream.flush()
                    os.fsync(stream.fileno())
                add(
                    "write_probe",
                    "OK",
                    "独立临时文件写入与清理成功。",
                    evidence={"path": str(parent)},
                )
        else:
            add("write_probe", "NOT_CHECKED", "未执行写入探测。", unchecked=True)
    except AgentError as exc:
        add(
            "configuration_storage",
            exc.code,
            exc.message,
            blocking=True,
            remediation=exc.remediation,
        )
    except OSError:
        add("storage_access", "ENVIRONMENT_RESTRICTED", "数据目录检查受限。", blocking=True)

    resolved = credential or resolve_credential()
    info_credential = resolved.info
    add(
        "credential",
        "OK"
        if info_credential.present
        else (
            "ENVIRONMENT_RESTRICTED" if info_credential.present is None else "CREDENTIAL_MISSING"
        ),
        "凭据来源已检查；尚未验证认证或模型调用。",
        evidence={"source": info_credential.source, "present": info_credential.present},
    )
    if dev:
        for name in ("uv", "node", "npm", "git", "rg"):
            executable = shutil.which("npm.cmd" if name == "npm" and os.name == "nt" else name)
            if executable is None:
                add(name, "DEPENDENCY_MISSING", "缺少开发工具：" + name, blocking=True)
                continue
            result = run_probe([executable, "--version"])
            version = re.search(r"\d+\.\d+\.\d+", result.output)
            add(
                name,
                result.code,
                name + " 版本检查已完成。",
                blocking=result.code != "OK",
                evidence={"version": version.group(0) if version else None},
            )
        # 开发文件归属于后端源码树，不能由终端或被选项目的 cwd 决定。
        # Developer files belong to the backend source tree, not the shell or project cwd.
        source_root = Path(__file__).resolve().parents[2]
        for name in (
            "pyproject.toml",
            "uv.lock",
            "apps/desktop/package-lock.json",
            "apps/desktop/node_modules/typescript/package.json",
        ):
            present = (source_root / name).is_file()
            add(
                "file." + name.replace("/", "."),
                "OK" if present else "DEPENDENCY_MISSING",
                "开发文件检查：" + name,
                blocking=not present,
                evidence={"path": str(source_root / name)},
            )
        docker = shutil.which("docker")
        if docker:
            result = run_probe([docker, "info", "--format", "{{.OSType}}"], timeout=3)
            add(
                "execution_backend",
                "OK" if result.code == "OK" else "EXECUTION_BACKEND_UNAVAILABLE",
                "容器后端检查完成；M0 不执行项目命令。",
            )
        else:
            add("execution_backend", "EXECUTION_BACKEND_UNAVAILABLE", "容器后端待后续阶段配置。")
    catalog: str = "not_checked"
    if network:
        result = run_probe([sys.executable, "-m", "my_agent.network_probe"], timeout=6)
        try:
            payload = json.loads(result.output) if result.code == "OK" else {"code": result.code}
            code = payload["code"]
            if not isinstance(code, str):
                raise ValueError("Invalid probe code")
            catalog = "ok" if code == "OK" else "error"
            add("catalog", code, "未携带凭据的目录请求已结束。", blocking=code != "OK")
            if code == "OK" and not payload.get("models_confirmed"):
                add("catalog_models", "MODEL_NOT_CONFIRMED", "目录尚未确认全部默认模型。")
        except (ValueError, KeyError, TypeError):
            catalog = "error"
            add("catalog", "INVALID_SERVICE_RESPONSE", "目录检查未返回有效结果。", blocking=True)
    else:
        add("catalog", "NOT_CHECKED", "默认不联网，模型目录未检查。", unchecked=True)
    mode = ["local"]
    if dev:
        mode.append("dev")
    if network:
        mode.append("network")
    if write_probe:
        mode.append("write_probe")
    return DiagnosticReport.model_validate(
        {
            "report_schema_version": 1,
            "checked_at": utc_now(),
            "app_version": __version__,
            "mode": mode,
            "checks": checks,
            "credential_present": info_credential.present,
            "catalog_reachable": catalog,
            "authentication_verified": "not_checked",
            "tool_roundtrip_verified": "not_checked",
        }
    )
