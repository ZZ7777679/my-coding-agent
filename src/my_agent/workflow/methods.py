"""读取随应用版本管理的内置工作方法，不加载用户目录中的执行指令。

Load versioned bundled work methods without importing executable instructions from user directories.
"""

from dataclasses import dataclass
from pathlib import Path

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


def bundled_skills_root() -> Path:
    """定位随包发布的 Skill；旧方法与资源目录共用正文。

    Locate packaged skills, sharing bodies between legacy methods and the catalog.
    """
    return Path(__file__).resolve().parents[1] / "skills" / "bundled"


def load_method(name: WorkMethod) -> MethodResource:
    """只从包内固定方法集合读取，缺失只阻断所选方法而非应用启动。

    Read only the fixed bundled method set; missing resources affect the chosen method, not startup.
    """
    if name not in {"discuss", "plan", "implement", "diagnose", "review", "handoff"}:
        raise AgentError("WORK_METHOD_INVALID", "不支持该工作方法。")
    try:
        path = bundled_skills_root() / name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        # 与目录版本一致；下次调用重新读取，不将旧正文缓存在整个进程中。
        # Match catalog versions and refresh on the next call instead of caching old bodies.
        version = str(path.stat().st_mtime_ns)
    except (OSError, UnicodeError) as exc:
        raise AgentError(
            "WORK_METHOD_UNAVAILABLE", "内置工作方法不可读取，请修复应用资源。"
        ) from exc
    return MethodResource(name, version, text)
