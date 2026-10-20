"""用户登记的执行环境与项目绑定，单写者原子保存。

Atomically persist user-selected environments and project bindings under the app writer lock.
"""

import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import Field, model_validator

from my_agent.config import DEFAULTS
from my_agent.errors import AgentError
from my_agent.execution.types import (
    BindEnvironmentParams,
    CondaEnvironment,
    EnvironmentCatalog,
    EnvironmentDefinition,
    EnvironmentProbe,
    EnvironmentRecord,
    EnvironmentView,
    ExecutionSettings,
    ProjectExecution,
    PythonEnvironment,
    RemoveEnvironmentParams,
    SaveEnvironmentParams,
    SaveExecutionSettings,
    SystemEnvironment,
    UvEnvironment,
)
from my_agent.models.types import ModelData
from my_agent.projects import ProjectService
from my_agent.storage import Storage, read_document, write_document
from my_agent.tools.policy import relative_path

SENSITIVE_ENV_NAME = re.compile(r"KEY|PASSWORD|SECRET|TOKEN", re.IGNORECASE)
AUTH_ENV_NAME = re.compile(r"(?:^|_)(?:AUTH|AUTHORIZATION|CREDENTIALS?|PASSWD|PWD)$", re.IGNORECASE)
CONNECTION_ENV_NAME = re.compile(
    r"(?:^|_)(?:URL|URI|DSN|CONNECTION_?STRING|CONN_?STR)$", re.IGNORECASE
)
CONNECTION_PASSWORD = re.compile(r"(?:^|;)\s*(?:password|pwd)\s*=\s*[^;\s]", re.IGNORECASE)
APP_CREDENTIAL_NAMES = frozenset({"OPENCODE_API_KEY", "DEEPSEEK_API_KEY"})


def sensitive_environment_value(name: str, value: str) -> bool:
    """仅识别凭据名称及含密码的连接配置，保留无认证代理与工具环境。

    Recognize credential names and password-bearing connections, retaining ordinary tool settings.
    """
    if SENSITIVE_ENV_NAME.search(name) or (name.upper() != "PWD" and AUTH_ENV_NAME.search(name)):
        return True
    if not CONNECTION_ENV_NAME.search(name):
        return False
    if CONNECTION_PASSWORD.search(value):
        return True
    try:
        # 只在内存检查配置值，不记录地址或密码；普通代理地址仍可继承。
        # Inspect values only in memory; never log credentials or remove ordinary proxy URLs.
        return urlsplit(value).password is not None
    except ValueError:
        return False


class EnvironmentIndex(ModelData):
    """环境与项目默认同文件提交，不改变已有项目索引。

    Commit defaults without rewriting projects."""

    schema_version: Literal[1] = 1
    revision: int = 0
    environments: list[EnvironmentRecord] = Field(default_factory=list)
    bindings: list[ProjectExecution] = Field(default_factory=list)
    settings: ExecutionSettings

    @model_validator(mode="after")
    def references(self) -> "EnvironmentIndex":
        """拒绝重复身份和悬空绑定，不重置损坏记录。

        Reject duplicate identities and dangling bindings."""
        identifiers = [item.environment_id for item in self.environments]
        projects = [item.project_id for item in self.bindings]
        if (
            self.revision < 0
            or len(set(identifiers)) != len(identifiers)
            or len(set(projects)) != len(projects)
            or any(
                item.environment_id and item.environment_id not in identifiers
                for item in self.bindings
            )
        ):
            raise ValueError("Invalid environment references")
        return self


def inherited_environment(passthrough: tuple[str, ...] = ()) -> dict[str, str]:
    """筛除宿主凭据，受信配置可明确传入项目变量，但不能带入模型服务密钥。

    Scrub host credentials, allowing explicitly configured project variables but not model keys.
    """
    allowed = {name.upper() for name in passthrough}
    return {
        name: value
        for name, value in os.environ.items()
        if name.upper() not in APP_CREDENTIAL_NAMES
        and not name.upper().startswith("MY_AGENT_")
        and (name.upper() in allowed or not sensitive_environment_value(name, value))
    }


def execution_environment(view: EnvironmentView) -> dict[str, str]:
    """继承已有工具环境，剔除凭据与应用变量，再叠加所选环境路径。

    Inherit tool settings minus credentials/app variables, then overlay selected environment paths.
    """
    # 对齐 DSH 的继承后筛除方式，避免白名单遗漏 JAVA_HOME 等正常工具配置。
    # Follow DSH's inherit-then-scrub approach instead of dropping normal tool configuration.
    env = inherited_environment(
        tuple(view.execution.environment_passthrough) if view.execution else ()
    )
    paths: list[str] = []
    if view.prefix:
        prefix = Path(view.prefix)
        paths.extend(str(prefix / suffix) for suffix in ("", "Scripts", "Library/bin", "bin"))
        if view.record.definition.kind == "conda":
            env["CONDA_PREFIX"] = str(prefix)
        elif (prefix / "pyvenv.cfg").is_file():
            env["VIRTUAL_ENV"] = str(prefix)
    if view.interpreter:
        paths.insert(0, str(Path(view.interpreter).parent))
    if view.launcher:
        paths.append(str(Path(view.launcher).parent))
    env["PATH"] = os.pathsep.join([*paths, env.get("PATH", "")])
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    # 这些是本应用传给子进程的变量，不修改机器或用户持久环境。
    # These variables exist only in the child, never in persistent host configuration.
    env["NO_COLOR"] = "1"
    return env


class EnvironmentStore:
    """登记仅引用已有环境，检查按需执行；路径失效不回退。

    Register existing references and probe on demand; never fall back from an invalid binding.
    """

    def __init__(self, storage: Storage) -> None:
        """绑定应用数据根；不读取项目配置授予权限。

        Bind app storage, not project-granted permissions."""
        self.storage = storage
        self.path = storage.root / "environments.json"
        self.projects = ProjectService(storage)
        self.sandbox_issue: str | None = None

    def read(self) -> EnvironmentIndex:
        """缺失时采用集中默认，已有损坏数据保留。

        Default only for absence; preserve corrupt data."""
        if self.path.resolve() != self.path:
            raise AgentError("ENVIRONMENT_STORAGE_INVALID", "执行环境记录不支持链接路径。")
        if not self.path.exists():
            return EnvironmentIndex(
                settings=ExecutionSettings.model_validate(DEFAULTS["execution"])
            )
        return read_document(self.path, EnvironmentIndex)

    def project_root(self, project_id: str | None) -> Path:
        """按登记身份重新核实项目，不按 cwd 猜测。

        Revalidate a registered project, never infer cwd."""
        item = next((p for p in self.projects.read().projects if p.project_id == project_id), None)
        if item is None:
            raise AgentError("PROJECT_REQUIRED", "请先选择项目，再使用项目相对环境。")
        view = self.projects.summary(item)
        if not view.available:
            raise AgentError(view.unavailable_code or "PROJECT_UNAVAILABLE", "项目目录当前不可用。")
        return Path(view.canonical_path)

    def _path(
        self,
        value: str,
        scope: str,
        project_id: str | None,
        *,
        directory: bool = False,
    ) -> Path:
        """按用户选择解析真实环境路径，不安装缺失内容。

        Resolve selected paths without installation."""
        if scope == "project":
            selected = self.project_root(project_id).joinpath(*relative_path(value).parts)
        else:
            selected = Path(value)
            if not selected.is_absolute():
                raise AgentError("ENVIRONMENT_PATH_INVALID", "本机环境路径需要完整绝对路径。")
        try:
            path = selected.resolve(strict=True)
            if (directory and not path.is_dir()) or (not directory and not path.is_file()):
                raise OSError
            if not directory and os.name == "nt" and path.suffix.casefold() != ".exe":
                raise AgentError(
                    "ENVIRONMENT_EXECUTABLE", "请选择实际 .exe 入口；脚本通过显式 shell 执行。"
                )
            return path
        except (OSError, RuntimeError) as exc:
            raise AgentError("ENVIRONMENT_UNAVAILABLE", "登记的环境路径不存在或不可访问。") from exc

    def resolve(self, record: EnvironmentRecord, project_id: str | None) -> EnvironmentView:
        """解析当前可用性，不运行解释器、不凭版本拒绝。

        Check paths without executing or version-gating."""
        definition = record.definition
        interpreter: Path | None = None
        launcher: Path | None = None
        prefix: Path | None = None
        issue: str | None = None
        try:
            if isinstance(definition, (PythonEnvironment, UvEnvironment)):
                interpreter = self._path(definition.interpreter, definition.scope, project_id)
                candidate = interpreter.parent.parent
                prefix = candidate if (candidate / "pyvenv.cfg").is_file() else interpreter.parent
            if isinstance(definition, (CondaEnvironment, UvEnvironment)):
                launcher = self._path(definition.launcher, "absolute", project_id)
            if isinstance(definition, CondaEnvironment):
                prefix = self._path(definition.prefix, definition.scope, project_id, directory=True)
                candidate = prefix / "python.exe"
                interpreter = candidate.resolve() if candidate.is_file() else None
        except AgentError as exc:
            issue = exc.code
        probe = record.probe
        if not isinstance(definition, SystemEnvironment) and definition.scope == "project":
            if probe and probe.project_id != project_id:
                record = record.model_copy(update={"probe": None})
        return EnvironmentView(
            record=record,
            available=issue is None,
            issue=issue,
            interpreter=str(interpreter) if interpreter else None,
            launcher=str(launcher) if launcher else None,
            prefix=str(prefix) if prefix else None,
        )

    @staticmethod
    def binding(index: EnvironmentIndex, project_id: str) -> ProjectExecution:
        """未配置项目直接使用本机环境，旧信任字段不再表示执行权限。

        Use system tools when unconfigured; the legacy trust flag no longer grants execution.
        """
        binding = next(
            (item for item in index.bindings if item.project_id == project_id),
            ProjectExecution(
                project_id=project_id,
                environment_id=None,
                mode="direct",
            ),
        )
        # 只投影当前行为，读取配置不修改磁盘；旧客户端仍能读取该兼容字段。
        # Project current behavior without rewriting storage; old clients retain the field.
        return binding.model_copy(update={"trusted": True})

    def catalog(self, project_id: str | None) -> EnvironmentCatalog:
        """返回设置视图与当下路径事实，不触发探测。

        Return settings and path facts without probing."""
        index = self.read()
        return EnvironmentCatalog(
            revision=index.revision,
            environments=[self.resolve(item, project_id) for item in index.environments],
            binding=self.binding(index, project_id) if project_id else None,
            settings=index.settings,
            sandbox_issue=self.sandbox_issue,
        )

    def _write(self, index: EnvironmentIndex, expected_revision: int) -> None:
        """在单写者线程内比较版本再原子保存。

        Compare revision and atomically save on the writer."""
        self.storage.require_writer()
        if index.revision != expected_revision:
            raise AgentError("ENVIRONMENT_REVISION_CONFLICT", "执行环境设置已更新，请刷新后保存。")
        updated = index.model_copy(update={"revision": index.revision + 1})
        # 再校验引用约束，不以 model_copy 绕过完整记录验证。
        # Revalidate references instead of bypassing them through model_copy.
        write_document(self.path, EnvironmentIndex.model_validate(updated.model_dump()))

    def save(self, params: SaveEnvironmentParams) -> EnvironmentCatalog:
        """导入引用并检查路径存在，不执行、安装或同步依赖。

        Import references without executing tools."""
        index = self.read()
        if params.environment_id and not any(
            e.environment_id == params.environment_id for e in index.environments
        ):
            raise AgentError("ENVIRONMENT_NOT_FOUND", "环境登记不存在，请刷新。")
        duplicate = next((e for e in index.environments if e.definition == params.definition), None)
        identifier = params.environment_id or (
            duplicate.environment_id if duplicate else str(uuid4())
        )
        record = EnvironmentRecord(
            environment_id=identifier, name=params.name, definition=params.definition
        )
        view = self.resolve(record, params.project_id)
        if not view.available:
            raise AgentError(view.issue or "ENVIRONMENT_UNAVAILABLE", "环境路径不可用，未保存。")
        updated = [item for item in index.environments if item.environment_id != identifier] + [
            record
        ]
        self._write(index.model_copy(update={"environments": updated}), params.expected_revision)
        return self.catalog(params.project_id)

    def bind(self, params: BindEnvironmentParams) -> EnvironmentCatalog:
        """保存项目默认与执行方式，不改变活动程序。

        Save environment and mode defaults without altering live programs."""
        if not any(p.project_id == params.project_id for p in self.projects.read().projects):
            raise AgentError("PROJECT_REQUIRED", "项目登记不存在。")
        index = self.read()
        if params.environment_id:
            record = next(
                (e for e in index.environments if e.environment_id == params.environment_id), None
            )
            if record is None:
                raise AgentError("ENVIRONMENT_NOT_FOUND", "所选环境登记不存在。")
            view = self.resolve(record, params.project_id)
            if not view.available:
                raise AgentError(
                    view.issue or "ENVIRONMENT_UNAVAILABLE", "该环境当前不可用，未保存绑定。"
                )
        binding = ProjectExecution.model_validate(
            params.model_dump(exclude={"expected_revision", "trusted"})
        )
        bindings = [item for item in index.bindings if item.project_id != params.project_id] + [
            binding
        ]
        self._write(index.model_copy(update={"bindings": bindings}), params.expected_revision)
        return self.catalog(params.project_id)

    def remove(self, params: RemoveEnvironmentParams) -> EnvironmentCatalog:
        """仅移除未被绑定的登记，不删除任何环境文件。

        Remove unbound references without file deletion."""
        index = self.read()
        if any(item.environment_id == params.environment_id for item in index.bindings):
            raise AgentError("ENVIRONMENT_IN_USE", "请先更换或清除项目默认环境，再移除登记。")
        entries = [
            item for item in index.environments if item.environment_id != params.environment_id
        ]
        if len(entries) == len(index.environments):
            raise AgentError("ENVIRONMENT_NOT_FOUND", "该环境登记不存在。")
        self._write(index.model_copy(update={"environments": entries}), params.expected_revision)
        return self.catalog(params.project_id)

    def settings(self, params: SaveExecutionSettings) -> EnvironmentCatalog:
        """保存后续启动预算，不重启已运行程序。

        Save budgets for future launches without restarts."""
        index = self.read()
        self._write(
            index.model_copy(update={"settings": params.settings}), params.expected_revision
        )
        return self.catalog(params.project_id)

    def selected(
        self, project_id: str, sandbox_supported: bool = False
    ) -> tuple[EnvironmentView, ExecutionSettings, int]:
        """读取当前环境与执行方式，显式绑定失效不回退。

        Read the environment and execution mode without falling back from invalid bindings."""
        index = self.read()
        binding = self.binding(index, project_id)
        if binding.mode == "sandbox" and not sandbox_supported:
            raise AgentError(
                "SANDBOX_ENTRY_UNAVAILABLE",
                "此入口尚未接入原生沙箱；请使用沙箱命令或终端，未回退到直接执行。",
            )
        record = next(
            (e for e in index.environments if e.environment_id == binding.environment_id), None
        )
        if binding.environment_id is None:
            # 无绑定直接复用本机工具；显式绑定失效仍报错，不能悄悄换解释器。
            # Unbound projects use system tools; invalid explicit bindings never change interpreter.
            record = EnvironmentRecord(
                environment_id=str(uuid5(NAMESPACE_URL, "my-agent:system-environment")),
                name="本机工具（默认）",
                definition=SystemEnvironment(kind="system"),
            )
        if record is None:
            raise AgentError("ENVIRONMENT_NOT_FOUND", "项目绑定的环境登记不存在，请调整绑定。")
        view = self.resolve(record, project_id)
        if not view.available:
            raise AgentError(
                view.issue or "ENVIRONMENT_UNAVAILABLE", "项目环境已失效，未改用全局环境。"
            )
        return view.model_copy(update={"execution": binding}), index.settings, index.revision

    def read_roots(self, project_id: str) -> tuple[Path, ...] | None:
        """沙箱文件读取共用项目目录配置，直接模式保持现有显式读取。

        Share sandbox directory settings with file reads; preserve direct-mode explicit access.
        """
        binding = self.binding(self.read(), project_id)
        if binding.mode == "direct":
            return None
        root = self.project_root(project_id)
        return (
            root,
            *(
                (root / value).resolve()
                for value in (
                    *binding.sandbox.read_paths,
                    *binding.sandbox.write_paths,
                )
            ),
        )

    def save_probe(
        self,
        environment_id: str,
        definition: EnvironmentDefinition,
        probe: EnvironmentProbe,
    ) -> EnvironmentCatalog:
        """只将探测保存到同一环境定义，避免迟到结果覆盖新路径。

        Guard delayed probe provenance."""
        index = self.read()
        record = next((e for e in index.environments if e.environment_id == environment_id), None)
        if record is None or record.definition != definition:
            raise AgentError("ENVIRONMENT_CHANGED", "探测期间环境引用已改变，结果未覆盖新设置。")
        updated = [
            e.model_copy(update={"probe": probe}) if e.environment_id == environment_id else e
            for e in index.environments
        ]
        self._write(index.model_copy(update={"environments": updated}), index.revision)
        return self.catalog(probe.project_id)


def executable(name: str, env: dict[str, str], cwd: Path) -> str:
    """明确解析程序，禁用 cwd 隐式搜索及批处理隐式 shell。

    Resolve executables without implicit shell."""
    supplied = Path(name)
    if supplied.is_absolute():
        target = supplied
    elif "/" in name or "\\" in name:
        target = cwd / supplied
    else:
        # 只检查明确 PATH 目录，不调用会按 Windows 规则隐式加入 cwd 的 which。
        # Search explicit PATH entries only, avoiding which's implicit Windows cwd lookup.
        target = Path()
        for directory in env.get("PATH", "").split(os.pathsep):
            directory = directory.strip('"')
            if not directory or not Path(directory).is_absolute():
                continue
            candidates = (
                [Path(directory) / name]
                if supplied.suffix
                else [Path(directory) / (name + suffix) for suffix in (".exe", ".cmd", ".bat", "")]
            )
            found = next((candidate for candidate in candidates if candidate.is_file()), None)
            if found:
                target = found
                break
    try:
        target = target.resolve(strict=True)
        if not target.is_file():
            raise OSError
    except (OSError, RuntimeError) as exc:
        raise AgentError("PROGRAM_UNAVAILABLE", "程序不存在或未在所选环境 PATH 中找到。") from exc
    if os.name == "nt" and target.suffix.casefold() != ".exe":
        raise AgentError("PROGRAM_REQUIRES_SHELL", "批处理或脚本请使用显式 PowerShell 命令。")
    return str(target)
