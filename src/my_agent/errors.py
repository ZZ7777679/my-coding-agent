"""稳定的公开错误契约；原始输入不得直接成为错误信息。

Stable public errors; raw inputs must not become error messages.
"""

from typing import Literal


class AgentError(Exception):
    """携带稳定错误码、公开说明和修复提示的业务异常。

    Carry a stable code, public message and remediation for an expected failure.
    """

    def __init__(self, code: str, message: str, remediation: str = "") -> None:
        """保存经过调用方筛选的公开错误字段。

        Store public error fields selected by the caller.
        """

        super().__init__(message)
        self.code = code
        self.message = message
        self.remediation = remediation


def http_error_code(status: int, error_kind: str | None = None) -> str:
    """按 HTTP 状态与服务错误类型分类，不猜测含糊的额度或限流原因。

    Classify HTTP failures without guessing ambiguous quota or rate-limit causes.
    """

    if status == 401:
        return "AUTHENTICATION_FAILED"
    if status == 403:
        return "ACCESS_DENIED"
    if status == 429:
        if error_kind in {"insufficient_quota", "quota_exceeded"}:
            return "QUOTA_EXCEEDED"
        if error_kind == "rate_limit_exceeded":
            return "RATE_LIMITED"
        return "SERVICE_RESTRICTED"
    return "SERVICE_ERROR" if status >= 500 else "HTTP_ERROR"


DataSource = Literal["cli", "environment", "default"]
