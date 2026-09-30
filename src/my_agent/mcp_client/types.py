"""MCP 配置与公开连接状态。

MCP configuration and public connection status."""

from typing import Annotated, Literal

from pydantic import Field, SecretStr, WithJsonSchema

from my_agent.models.types import JsonObject, ModelData
from my_agent.sessions.types import SessionId


class McpOAuthConfig(ModelData):
    """OAuth 的公开登记选项；空身份使用服务器支持的动态登记。

    Public OAuth registration options; an empty identity uses server registration.
    """

    client_id: str = ""
    client_secret_env: str = ""
    token_auth_method: Literal["none", "client_secret_post", "client_secret_basic"] = "none"
    client_metadata_url: str = ""
    scope: str = ""
    callback_port: int = Field(default=0, ge=0, le=65535)
    login_timeout_seconds: float = Field(default=600, gt=0)


class McpAuth(ModelData):
    """HTTP 认证只保存来源和组装方式。

    Store HTTP authentication source and formatting, never the token."""

    source: Literal["none", "environment", "saved", "oauth"] = "none"
    env_var: str = ""
    header: str = "Authorization"
    prefix: str = "Bearer"
    oauth: McpOAuthConfig = Field(default_factory=McpOAuthConfig)


class McpServer(ModelData):
    """只保存凭据引用，活动连接采用启动时快照。

    Store credential references and connection snapshots."""

    server_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", max_length=64)
    name: str
    description: str = ""
    transport: Literal["stdio", "http", "browser"] = "stdio"
    enabled: bool = True
    project_ids: list[str] = Field(default_factory=list)
    all_projects: bool = True
    command: str = ""
    arguments: list[str] = Field(default_factory=list)
    url: str = ""
    env_refs: dict[str, str] = Field(default_factory=dict)
    header_refs: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=120, gt=0)
    browser_executable: str = ""
    preset_id: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    auth: McpAuth = Field(default_factory=McpAuth)


class McpToolset(ModelData):
    """预设服务的可选工具组，不限制实际服务定义。

    Suggested toolsets do not restrict the server's actual definitions."""

    name: str
    title: str


class McpPreset(ModelData):
    """由后端提供可编辑的服务预设与官方说明。

    Supply editable service presets and official setup information."""

    preset_id: str
    server: McpServer
    docs_url: str
    credential_url: str
    auth_help: str
    suggested_env: str
    toolsets: list[McpToolset] = Field(default_factory=list)
    oauth_url: str = ""
    oauth_help: str = ""
    oauth_setup_url: str = ""


class McpConfig(ModelData):
    """已登记服务清单。

    Registered server configuration."""

    servers: list[McpServer] = Field(default_factory=list)


class McpParams(ModelData):
    """设置与会话使用同一目录。

    Settings and sessions share one catalog."""

    project_id: str | None = None
    session_id: SessionId | None = None


class SaveMcpParams(McpParams):
    """显式新增或保存服务。

    Explicit server registration or update."""

    server: McpServer
    # 只写参数不进入目录；声明普通字符串兼容 Ajv，不放宽 Python 的类型约束。
    # A write-only input stays out of catalogs; JSON uses a string compatible with Ajv.
    credential_value: (
        Annotated[SecretStr, WithJsonSchema({"type": "string", "writeOnly": True})] | None
    ) = Field(default=None, repr=False)
    clear_credential: bool = False


class McpControlParams(McpParams):
    """只控制指定连接或浏览器安装。

    Control a selected connection or browser installation."""

    server_id: str
    action: Literal[
        "connect",
        "refresh",
        "close",
        "remove",
        "install_browser",
        "oauth_login",
        "oauth_cancel",
        "oauth_logout",
    ]


class McpOAuthView(ModelData):
    """只向管理界面提供授权状态与短期网页入口。

    Expose authorization status and a temporary browser link to management UI only.
    """

    status: Literal[
        "not_logged_in",
        "stored",
        "discovering",
        "awaiting_user",
        "exchanging",
        "authorized",
        "failed",
        "cancelled",
    ] = "not_logged_in"
    authorization_url: str = ""
    redirect_uri: str = ""
    scope: str = ""
    error: str = ""
    expires_at: float | None = None


class McpServerView(ModelData):
    """配置与实际状态分开显示。

    Display configuration separately from actual status."""

    server: McpServer
    status: str
    error: str = ""
    tools: list[JsonObject] = Field(default_factory=list)
    credential_status: Literal["not_required", "configured", "missing", "unavailable"] = (
        "not_required"
    )
    credential_message: str = ""
    needs_reconnect: bool = False
    oauth: McpOAuthView | None = None


class McpCatalog(ModelData):
    """公开目录不含解析后的凭据。

    Public catalog excludes resolved credentials."""

    servers: list[McpServerView]
    issues: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    installing_browser: bool = False
    install_error: str = ""
    presets: list[McpPreset] = Field(default_factory=list)


class McpArtifactParams(McpParams):
    """仅按服务产物身份分页读取图片。

    Page an image by owned artifact identity."""

    artifact_id: str = Field(min_length=1)
    offset: int = Field(default=0, ge=0)


class McpArtifact(ModelData):
    """图片字节分段，避免超过协议帧。

    Image byte chunks stay below protocol frame limits."""

    mime_type: str
    data: str
    next_offset: int | None
