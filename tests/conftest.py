"""集中隔离 pytest 产物与凭据，避免测试修改个人数据或读取真实密钥。

Centralize pytest artifact and credential isolation to protect personal data and keys.
"""

from pathlib import Path
from uuid import uuid4

import pytest

from my_agent import credentials


def pytest_configure(config):
    """限定临时根为产物目录内的独立子目录，防止 pytest 清理其他位置。

    Constrain temporary roots to dedicated artifact children so pytest cannot clean other paths.
    """

    artifacts = (Path(__file__).resolve().parents[1] / ".artifacts/tests").resolve()
    base = (
        Path(config.option.basetemp).resolve()
        if config.option.basetemp
        else artifacts / ("python-" + uuid4().hex)
    )
    if base == artifacts or not base.is_relative_to(artifacts):
        raise pytest.UsageError("Use a separate --basetemp directory inside .artifacts/tests/.")
    base.parent.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(base)


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    """为每个测试清除目录覆盖并替换用户凭据读取，不访问真实密钥。

    Clear data-root overrides and replace user-key lookup for each test without reading real keys.
    """

    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("MY_AGENT_DATA_DIR", raising=False)
    monkeypatch.setattr(credentials, "read_windows_user", lambda name: None)
