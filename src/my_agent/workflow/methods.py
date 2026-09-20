"""读取随应用版本管理的内置工作方法，不加载用户目录中的执行指令。

Load versioned bundled work methods without importing executable instructions from user directories.
"""

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files

from my_agent.errors import AgentError
from my_agent.workflow.types import WorkMethod


@dataclass(frozen=True)
class MethodResource:
    """方法身份、版本和文本；方法提供步骤建议，不扩大权限。

    A method identity, version and text that guide work without enlarging permissions.
    """

    name: WorkMethod
    version: str
    text: str


@lru_cache
def load_method(name: WorkMethod) -> MethodResource:
    """只从包内固定方法集合读取，缺失只阻断所选方法而非应用启动。

    Read only the fixed bundled method set; missing resources affect the chosen method, not startup.
    """
    if name not in {"discuss", "plan", "implement", "diagnose", "review", "handoff"}:
        raise AgentError("WORK_METHOD_INVALID", "不支持该工作方法。")
    try:
        text = (
            files("my_agent.workflow").joinpath("methods", f"{name}.md").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError) as exc:
        raise AgentError(
            "WORK_METHOD_UNAVAILABLE", "内置工作方法不可读取，请修复应用资源。"
        ) from exc
    return MethodResource(name, "1", text)
