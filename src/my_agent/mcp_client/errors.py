"""从异常类型提取可操作的 MCP 错误，不转发秘密或服务正文。

Classify MCP failures without forwarding credentials or server response text.
"""

from collections.abc import Iterator

import httpx2
from mcp.client.auth import OAuthFlowError, OAuthRegistrationError, OAuthTokenError
from mcp.shared.exceptions import MCPError
from mcp_types import REQUEST_TIMEOUT

from my_agent.errors import AgentError


def _causes(error: BaseException, seen: set[int]) -> Iterator[BaseException]:
    """展开 SDK 的异常组与原因链，避免循环引用。

    Walk SDK exception groups and causes without cycling."""
    if id(error) in seen:
        return
    seen.add(id(error))
    yield error
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            yield from _causes(child, seen)
    cause = error.__cause__ or error.__context__
    if cause:
        yield from _causes(cause, seen)


def public_error(error: Exception, *, connecting: bool) -> AgentError:
    """保留已知业务错误，按状态码 / 类型提供固定说明。

    Preserve known business failures and explain HTTP status/type with fixed messages.
    """
    causes = list(_causes(error, set()))
    for cause in causes:
        if isinstance(cause, AgentError):
            return cause
        if isinstance(cause, MCPError) and cause.code == REQUEST_TIMEOUT:
            return AgentError("MCP_TIMEOUT", "等待服务响应超时，请检查服务状态或调整超时。")
        if isinstance(cause, httpx2.HTTPStatusError):
            status = cause.response.status_code
            messages = {
                401: ("MCP_AUTH_REQUIRED", "服务要求认证或令牌已失效（401），请编辑认证配置。"),
                403: (
                    "MCP_ACCESS_DENIED",
                    "服务拒绝访问（403），请检查令牌权限及组织 / SSO 授权。",
                ),
                429: ("MCP_RATE_LIMITED", "服务请求额度或频率受限（429），请查看账户额度后再试。"),
            }
            code, message = messages.get(
                status,
                ("MCP_HTTP_ERROR", f"服务返回 HTTP {status}，请检查服务地址或稍后重试。"),
            )
            return AgentError(code, message)
    if any(isinstance(c, (TimeoutError, httpx2.TimeoutException)) for c in causes):
        return AgentError("MCP_TIMEOUT", "连接或调用超时，请检查网络、服务状态或调整超时。")
    if any(isinstance(c, httpx2.TransportError) for c in causes):
        return AgentError("MCP_NETWORK_ERROR", "无法完成网络传输，请检查网络和服务地址。")
    if any(isinstance(c, OAuthRegistrationError) for c in causes):
        return AgentError(
            "MCP_OAUTH_REGISTRATION",
            "服务未接受自动客户端登记；请填写自己的 Client ID / Secret 引用，"
            "或核对服务的 OAuth 说明。",
        )
    if any(isinstance(c, OAuthTokenError) for c in causes):
        return AgentError(
            "MCP_OAUTH_TOKEN",
            "服务未完成令牌交换；请检查 Client ID、Secret、回调地址及权限后重新登录。",
        )
    if any(isinstance(c, OAuthFlowError) for c in causes):
        return AgentError(
            "MCP_OAUTH_FLOW",
            "OAuth 发现或回调未完成；请核对服务地址与登记配置后重新登录。",
        )
    stage = "连接" if connecting else "调用"
    return AgentError(
        "MCP_CONNECTION_FAILED" if connecting else "MCP_CALL_FAILED",
        f"MCP {stage}失败（{type(error).__name__}），请检查服务配置；未自动重试。",
    )
