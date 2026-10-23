"""稳定的公开错误契约；原始输入不得直接成为错误信息。

Stable public errors; raw inputs must not become error messages.
"""

import re
from collections.abc import Iterable
from typing import Literal

from pydantic import JsonValue, ValidationError

EffectState = Literal["not_executed", "saved", "partial", "unknown"]


def redact_error_text(value: str, secrets: Iterable[str] = ()) -> str:
    """保留排障文字，只移除已知凭据和常见秘密值。

    Preserve diagnostic text while removing known credentials and common secret values.
    """
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[redacted]")
    value = re.sub(r"(?i)\b(?:Bearer|Basic)\s+[^\s\"',;]+", "[redacted auth]", value)
    value = re.sub(r"(?i)\b(?:sk-|gh[pousr]_|github_pat_)[A-Za-z0-9_-]+", "[redacted]", value)
    value = re.sub(
        r"""(?ix)\b(?:[a-z0-9_]*[_-])?(?:api[_-]?key|token|password|passwd|secret|
        authorization|cookie|credential|connection_string|database_url)\b
        [\"']?\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;&]+)""",
        "[redacted]",
        value,
    )
    return re.sub(r"(\w+://)[^\s/@]+:[^\s/@]+@", r"\1[redacted]@", value)


def exception_message(exception: BaseException, secrets: Iterable[str] = ()) -> str:
    """保留具体异常说明；校验错误仅保留字段和规则，不回显输入。

    Keep concrete exception messages; validation failures expose fields/rules, not inputs.
    """
    if isinstance(exception, ValidationError):
        text = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['type']}"
            for item in exception.errors(
                include_input=False, include_context=False, include_url=False
            )
        )
    else:
        text = str(exception)
    return redact_error_text(text, secrets)


def redact_error_data(value: JsonValue, secrets: tuple[str, ...] = ()) -> JsonValue:
    """逐值清洗诊断结构，保留字段、数字和有效 JSON。

    Sanitize diagnostic values without breaking fields, numbers or JSON structure.
    """
    if isinstance(value, str):
        return redact_error_text(value, secrets)
    if isinstance(value, list):
        return [redact_error_data(item, secrets) for item in value]
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if re.search(
                r"(?i)(?:authorization|cookie|password|secret|token|api.?key|credential)", key
            )
            else redact_error_data(item, secrets)
            for key, item in value.items()
        }
    return value


def recovery_hint(code: str, cause_code: str | None = None) -> str:
    """提供针对根因的下一步，不据此自动重试或重新取得写入授权。

    Suggest an actionable next step without triggering retries or acquiring write authority.
    """
    root = cause_code or code
    hints = {
        "WORKERS_DISABLED": (
            "点击会话输入区旁的「开启子 Agent」，或进入子 Agent 工作空间的委派设置；"
            "开启不自动启动任务。"
        ),
        "WORKER_CONTEXT_UNSUPPORTED": (
            "由父会话拆分工作；当前内部子任务直接完成自身分工，不重复调用创建子任务。"
        ),
        "FILE_CHANGED": "重新读取当前文件，合并外部修改后调整编辑；本次没有覆盖文件。",
        "EDIT_NOT_FOUND": "读取目标片段，按当前原文重新定位；无需补传 hash。",
        "EDIT_NOT_UNIQUE": "扩大原文片段直到唯一匹配，再提交编辑。",
        "FILE_NOT_FOUND": "核对路径或列出父目录；需要新文件时使用创建工具。",
        "FILE_EXISTS": "核对已有文件，选择编辑或另一个路径；创建不会覆盖原文件。",
        "FILE_TYPE": "确认目标是文件还是目录，并选择对应工具。",
        "DOCUMENT_CONFLICT": "比较磁盘与编辑草稿，合并后保存；未保存草稿仍保留。",
        "PATH_DENIED": "核对真实目标与所选项目；项目外文件可以明确读取，写入请切换到所属项目。",
        "GIT_REPOSITORY_REQUIRED": "在项目工作台的本地 Git 中启用或初始化仓库；无需配置远端。",
        "GIT_DISABLED": "在项目的本地 Git 面板开启 Git；已移出的仓库可从应用保留副本恢复。",
        "TERMINAL_SCOPE_DENIED": "在交互终端中核对关联会话和输入控制归属，选择当前会话的终端。",
        "SKILL_DOWNLOAD_SIZE": (
            "查看下载大小与导入限制，选择更小的 Skill 包或解压后通过本地目录导入。"
        ),
        "WEB_SEARCH_UNAVAILABLE": (
            "服务已返回响应但未提供原生搜索结果，暂不能据此确定网络、额度或别名原因。"
            "查看具体诊断；已有网址可明确改用 web_fetch 读取。"
        ),
        "WEB_SEARCH_FAILED": (
            "查看诊断中的服务搜索错误码；修正服务问题后再搜索，"
            "已有网址也可用 web_fetch 读取。"
        ),
        "INVALID_TOOL_ARGUMENTS": (
            "按当前工具 schema 核对缺项、字段类型及不支持字段，再调整调用；无需重复原调用。"
        ),
        "TOOL_NOT_ALLOWED": (
            "核对当前 Plan／常规模式与工具职责；Plan 内使用只读入口，执行需要明确的执行请求。"
        ),
    }
    if root in hints or code in hints:
        return hints.get(root, hints.get(code, ""))
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
        details: dict[str, JsonValue] | None = None,
        diagnostic_issue: str | None = None,
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
        self.details = details or {}
        self.diagnostic_issue = diagnostic_issue


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
