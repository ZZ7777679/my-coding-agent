"""官方服务预设只填表，不自动安装或连接。

Official presets fill configuration without installing or connecting automatically.
"""

from my_agent.mcp_client.types import McpAuth, McpPreset, McpServer, McpToolset


def service_presets() -> list[McpPreset]:
    """返回独立的可编辑默认值；每个登记仍有自己的身份。

    Return independent editable defaults; registrations retain their own identities.
    """
    return [
        McpPreset(
            preset_id="context7",
            server=McpServer(
                server_id="context7",
                preset_id="context7",
                name="Context7 文档",
                description="查找库和框架的版本文档、API 用法与代码示例。",
                transport="http",
                url="https://mcp.context7.com/mcp",
                all_projects=False,
            ),
            docs_url="https://github.com/upstash/context7",
            credential_url="https://context7.com/dashboard",
            auth_help="可先匿名尝试；API Key 可提高额度。是否需要认证以服务返回为准。",
            suggested_env="CONTEXT7_API_KEY",
            oauth_url="https://mcp.context7.com/mcp/oauth",
            oauth_help="使用 Context7 官方 OAuth 地址，在浏览器登录并授权，无需手动复制 API Key。",
            oauth_setup_url="https://context7.com/docs/security/auth-and-access-control",
        ),
        McpPreset(
            preset_id="github",
            server=McpServer(
                server_id="github",
                preset_id="github",
                name="GitHub",
                description="访问仓库、Issue、PR、Review 与 Actions 构建结果。",
                transport="http",
                url="https://api.githubcopilot.com/mcp/",
                all_projects=False,
                headers={"X-MCP-Toolsets": "repos,issues,pull_requests,actions,users"},
                auth=McpAuth(source="saved", env_var="GITHUB_MCP_TOKEN"),
            ),
            docs_url="https://github.com/github/github-mcp-server",
            credential_url="https://github.com/settings/personal-access-tokens",
            auth_help=(
                "使用 GitHub Personal Access Token（PAT）。按要操作的仓库和功能设置权限；"
                "组织仓库还可能需要组织批准 / SSO。也可切换 OAuth，配置自己的应用登记。"
            ),
            suggested_env="GITHUB_MCP_TOKEN",
            oauth_url="https://api.githubcopilot.com/mcp/",
            oauth_help=(
                "GitHub 远程 OAuth 需要自己的 OAuth App / GitHub App Client ID，"
                "通常还需要 Client Secret 环境变量引用。回调登记为 "
                "http://127.0.0.1/oauth/callback；原 PAT 方式仍可使用。"
            ),
            oauth_setup_url="https://github.com/settings/developers",
            toolsets=[
                McpToolset(name="repos", title="仓库与代码"),
                McpToolset(name="issues", title="Issue"),
                McpToolset(name="pull_requests", title="PR 与 Review"),
                McpToolset(name="actions", title="Actions 与 CI"),
                McpToolset(name="users", title="账户信息"),
                McpToolset(name="discussions", title="Discussions"),
                McpToolset(name="projects", title="项目看板"),
            ],
        ),
    ]
