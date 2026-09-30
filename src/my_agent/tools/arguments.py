"""工具参数错误的简短说明，不改变解析规则。 Concise errors without changing validation."""

from pydantic import ValidationError


def argument_message(error: ValidationError, *, example: str | None = None) -> str:
    """给出错误字段与预期格式，不回显传入值或命令正文。

    Explain erroneous fields and expected formats without echoing values or command text.
    """
    issues = error.errors(include_input=False, include_context=False, include_url=False)
    details = "; ".join(
        f"{'.'.join(str(part) for part in issue['loc']) or 'arguments'}: {issue['msg']}"
        for issue in issues[:5]
    )
    message = "工具参数错误：" + details
    if len(issues) > 5:
        message += f"；另有 {len(issues) - 5} 项，请核对工具定义。"
    if example:
        message += "。正确用法示例：" + example
    return message
