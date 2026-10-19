"""语言服务配置与查询契约。

Language service configuration and query contracts.
"""

import json
from importlib.resources import files
from typing import Literal

from pydantic import Field, JsonValue

from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData

INTELLIGENCE_DEFAULTS = json.loads(
    files("my_agent").joinpath("defaults.json").read_text(encoding="utf-8")
)["intelligence"]


class LanguageServer(ModelData):
    """一个显式登记的 stdio 服务，不在启动时安装。

    An explicit stdio server, never installed on startup.
    """

    server_id: str
    languages: list[str]
    program: str
    arguments: list[str] = Field(default_factory=list)
    enabled: bool = True
    initialization_options: dict[str, JsonValue] = Field(default_factory=dict)
    settings: dict[str, JsonValue] = Field(default_factory=dict)


class IntelligenceParams(ModelData):
    """限定当前项目的服务操作。

    Scope service operations to the current project.
    """

    project_id: EntityId


class SaveLanguageServers(IntelligenceParams):
    """保存项目服务登记，下一次查询生效。

    Save project registrations for subsequent queries.
    """

    servers: list[LanguageServer]
    timeout_seconds: float = Field(default=INTELLIGENCE_DEFAULTS["timeout_seconds"], gt=0)


class LanguageServerState(ModelData):
    """真实连接状态与最后错误。

    Actual connection state and last error.
    """

    server_id: str
    status: Literal["not_started", "running", "failed"]
    message: str | None = None


class LanguageServerCatalog(SaveLanguageServers):
    """配置与实际状态分开显示。

    Display configuration separately from actual state.
    """

    states: list[LanguageServerState] = Field(default_factory=list)


class LanguageQuery(IntelligenceParams):
    """位置为 LSP 零基 UTF-16；内容为空时读取磁盘。

    Positions use LSP zero-based UTF-16; absent text reads disk.
    """

    path: str
    language: str
    action: Literal[
        "definition", "references", "symbols", "hover", "diagnostics", "completion", "rename"
    ]
    line: int = Field(default=0, ge=0)
    character: int = Field(default=0, ge=0)
    content: str | None = None
    version: int = Field(default=1, ge=1)
    new_name: str | None = None


class LanguageDocumentSnapshot(ModelData):
    """重命名建议所用正文；无法读取时保留局部错误。

    Text snapshots for rename suggestions, retaining local errors when unavailable.
    """

    path: str
    content: str | None
    source: Literal["disk", "draft"]
    version: int | None
    error: str | None = None


class LanguageResult(ModelData):
    """返回服务原生资料及所用材料，不将诊断当成测试。

    Return native data and input provenance, not test results.
    """

    project_id: EntityId
    server_id: str
    path: str
    action: str
    source: Literal["disk", "draft"]
    version: int
    content: str
    result: JsonValue
    observed_at: str
    rename_documents: list[LanguageDocumentSnapshot] = Field(default_factory=list)


class LanguageConfiguration(ModelData):
    """应用数据根中的配置，不改项目文件。

    Configuration in the data root, without project writes.
    """

    projects: list[SaveLanguageServers] = Field(default_factory=list)
