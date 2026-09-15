"""验证共享契约、只读诊断和受控进程探测，不调用真实模型。

Check shared contracts, read-only diagnostics and controlled probes without real model calls.
"""

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from my_agent.cli import app
from my_agent.diagnostics import diagnose
from my_agent.processes import ProbeResult, run_probe
from my_agent.rpc.dto import PUBLIC_TYPES

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "tests/fixtures/contracts.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_contract(case):
    """使用与 Ajv 共用的正反样本检查 Python 校验结果。

    Check Python validation against the same positive and negative fixtures used by Ajv.
    """

    model = PUBLIC_TYPES[case["type"]]
    raw = json.dumps(case["data"])
    if case["valid"]:
        model.model_validate_json(raw)
    else:
        with pytest.raises(ValidationError):
            model.model_validate_json(raw)


def test_doctor_is_read_only_and_never_claims_authentication(tmp_path):
    """确认默认诊断不创建数据或联网，也不宣称认证通过。

    Confirm default diagnostics create no data, use no network and claim no authentication.
    """

    root = tmp_path / "absent-data"
    report = diagnose(str(root))
    assert not root.exists()
    assert not any(check.blocking for check in report.checks)
    assert report.authentication_verified == "not_checked"
    assert report.tool_roundtrip_verified == "not_checked"
    assert report.catalog_reachable == "not_checked"


def test_dev_diagnostic_paths_follow_backend_source_not_cwd(tmp_path, monkeypatch):
    """在任意 cwd 仍检查后端源码；模拟安装布局缺少开发文件时明确报告。

    Check backend sources from any cwd and report missing dev files in an installed layout.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("my_agent.diagnostics.shutil.which", lambda name: str(tmp_path / name))
    monkeypatch.setattr(
        "my_agent.diagnostics.run_probe", lambda *args, **kwargs: ProbeResult("OK", 0, "1.0.0")
    )
    root = tmp_path / "data"
    report = diagnose(str(root), dev=True)
    files = [check for check in report.checks if check.check_id.startswith("file.")]
    assert files and all(check.code == "OK" for check in files)
    lock = next(check for check in files if check.check_id == "file.uv.lock")
    assert lock.evidence["path"] == str(ROOT / "uv.lock")
    assert not root.exists()

    monkeypatch.setattr(
        "my_agent.diagnostics.__file__",
        str(tmp_path / "wheel" / "site-packages" / "my_agent" / "diagnostics.py"),
    )
    installed = diagnose(str(root), dev=True)
    missing = [check for check in installed.checks if check.check_id.startswith("file.")]
    assert missing and all(check.code == "DEPENDENCY_MISSING" for check in missing)
    assert not root.exists()


def test_doctor_failure_still_returns_single_json_report(tmp_path):
    """确认损坏配置仍输出一个可解析的诊断报告与失败退出码。

    Confirm corrupted config still yields one parseable report and a failure exit code.
    """

    root = tmp_path / "data"
    root.mkdir()
    (root / "config.toml").write_text("invalid=", encoding="utf-8")
    result = CliRunner().invoke(app, ["--data-dir", str(root), "doctor", "--json"])
    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert any(check["code"] == "CONFIG_INVALID" for check in report["checks"])


def test_global_model_override_applies_to_doctor(tmp_path):
    """确认 CLI 模型覆盖进入诊断，而非只作用于配置展示。

    Confirm CLI model overrides affect diagnostics as well as configuration display.
    """

    result = CliRunner().invoke(
        app,
        [
            "--data-dir",
            str(tmp_path / "data"),
            "--model",
            "deepseek-v4.1-flash",
            "doctor",
            "--json",
        ],
    )
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert (
        next(check for check in report["checks"] if check["check_id"] == "config")["evidence"][
            "model"
        ]
        == "deepseek-v4.1-flash"
    )


def test_bounded_probes_and_filtered_environment(monkeypatch):
    """验证非零退出、超时、输出上限与凭据环境隔离。

    Verify nonzero exit, timeouts, output bounds and credential environment isolation.
    """

    assert run_probe([sys.executable, "-c", "import sys; sys.exit(7)"]).returncode == 7
    assert (
        run_probe([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.1).code
        == "TIMEOUT"
    )
    assert (
        run_probe([sys.executable, "-c", "print('x'*1000000)"], limit=1000).code
        == "OUTPUT_TOO_LARGE"
    )
    monkeypatch.setenv("OPENCODE_API_KEY", "should-not-reach-probe")
    result = run_probe([sys.executable, "-c", "import os; print('OPENCODE_API_KEY' in os.environ)"])
    assert result.output.strip() == "False"
