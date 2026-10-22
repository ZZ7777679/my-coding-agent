"""稳定的公开错误契约；原始输入不得直接成为错误信息。

Stable public errors; raw inputs must not become error messages.
"""

from typing import Literal

EffectState = Literal["not_executed", "saved", "partial", "unknown"]


def recovery_hint(code: str, cause_code: str | None = None) -> str:
    """提供针对根因的下一步，不据此自动重试或重新取得写入授权。

    Suggest an actionable next step without triggering retries or acquiring write authority.
    """
    root = cause_code or code
    if code.startswith("BUDGET_") or root.startswith("BUDGET_"):
        return "在运行设置中提高对应累计预算或改为不限，再明确继续；已完成的工作仍保留。"
    if root in {
        "AUTHENTICATION_FAILED",
        "CREDENTIAL_MISSING",
        "CREDENTIAL_RESTRICTED",
        "api_key_expired",
    }:
        return "检查设置中的凭据来源和认证状态；更新后再发起请求。"
    if root in {"QUOTA_EXCEEDED", "SERVICE_RESTRICTED", "RATE_LIMITED"}:
        return "检查服务额度或限流说明，恢复后继续；不会自动切换模型。"
    if code in {"CANCELLED", "APP_CLOSED", "PROCESS_INTERRUPTED"}:
        return "查看已保存进度后明确继续；中断的命令和工具不会自动重放。"
    if root == "HTTP_ERROR":
        return "查看 Trace 中的服务拒绝原因和请求材料，修正后再发起请求。"
    if root.startswith("MODEL_") or root == "SERVICE_ERROR":
        return "检查连接诊断和最后响应阶段，恢复后继续；部分输出可查看但不代表完整回答。"
    return "查看关联 Trace 和已保存成果，确认原因后继续；结果未知的操作先核对实际状态。"


class AgentError(Exception):
    """携带稳定错误码、公开说明和修复提示的业务异常。

    Carry a stable code, public message and remediation for an expected failure.
    """

    def __init__(
        self,
        code: str,
        message: str,
        remediation: str = "",
        *,
        cause_code: str | None = None,
        phase: str | None = None,
        diagnostic_id: str | None = None,
        tool_call_id: str | None = None,
        effect_state: EffectState | None = None,
    ) -> None:
        """保存经过调用方筛选的公开错误字段。

        Store public error fields selected by the caller.
        """

        super().__init__(message)
        self.code = code
        self.message = message
        self.remediation = remediation or recovery_hint(code, cause_code)
        self.cause_code = cause_code
        self.phase = phase
        self.diagnostic_id = diagnostic_id
        self.tool_call_id = tool_call_id
        self.effect_state = effect_state


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
