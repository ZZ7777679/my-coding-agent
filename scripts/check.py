"""按需执行完整 M0 工程验收，使用隔离数据和哨兵凭据。

Run full M0 acceptance when needed, using isolated data and sentinel credentials.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts/tests"


def run(
    args: list[str], *, cwd: Path = ROOT, expected: int = 0, failure_marker: str | None = None
) -> None:
    """在明确工作目录运行有界检查，可验证示例的预期失败原因。

    Run a bounded check in an explicit directory, optionally verifying an expected failure.
    """

    print("\n> " + subprocess.list2cmdline(args), flush=True)
    result = subprocess.run(
        args,
        cwd=cwd,
        timeout=240,
        check=False,
        capture_output=failure_marker is not None,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != expected:
        raise SystemExit(f"Check failed: expected exit {expected}, got {result.returncode}")
    if failure_marker is not None:
        if failure_marker not in result.stderr:
            raise SystemExit("The sample failed for an unexpected reason.")
        print("Expected sample defect reproduced: timeout=0 was replaced by the default.")


def tool(name: str) -> str:
    """定位本次工程检查需要的工具，缺失时结束该检查入口。

    Locate a tool required by this engineering check and stop this entry if it is absent.
    """

    executable = shutil.which(name)
    if executable is None:
        raise SystemExit(f"Missing developer tool: {name}")
    return executable


def versions() -> None:
    """核对完整验收的精确环境基线及锁文件；该检查不是应用启动前提。

    Verify exact acceptance baselines and lockfiles; this is not an application startup gate.
    """

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "apps/desktop/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "apps/desktop/package-lock.json").read_text(encoding="utf-8"))
    python = (ROOT / ".python-version").read_text().strip()
    node = (ROOT / ".node-version").read_text().strip()
    actual_node = subprocess.check_output([tool("node"), "--version"], text=True).strip()
    if ".".join(map(str, sys.version_info[:3])) != python or actual_node != "v" + node:
        raise SystemExit("Use the Python and Node versions in the repository version files.")
    if project["project"]["version"] != package["version"]:
        raise SystemExit("Python and desktop application versions differ.")
    for group in ("dependencies", "devDependencies"):
        if package[group] != lock["packages"][""][group]:
            raise SystemExit(f"npm lock differs from package.json: {group}")


def verify_wheel(uv: str, temporary: Path) -> None:
    """构建并在隔离环境安装 wheel，从包外调用实际 CLI 验证资源与入口。

    Build and install a wheel in isolation, checking its real CLI from outside the package.
    """

    wheel_dir = temporary / "wheels"
    run([uv, "build", "--wheel", "--out-dir", str(wheel_dir)])
    wheels = list(wheel_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Expected exactly one built wheel.")
    environment = temporary / "wheel-env"
    run([uv, "venv", "--python", sys.executable, str(environment)])
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    requirements = temporary / "wheel-requirements.txt"
    run(
        [
            uv,
            "export",
            "--quiet",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--output-file",
            str(requirements),
        ]
    )
    run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--requirement",
            str(requirements),
            str(wheels[0]),
        ]
    )
    for args in (
        ["--help"],
        ["--version"],
        ["--data-dir", str(temporary / "unused"), "config", "show", "--json"],
    ):
        entry = environment / ("Scripts/my-agent.exe" if os.name == "nt" else "bin/my-agent")
        run([str(entry), *args], cwd=temporary)
    if (temporary / "unused").exists():
        raise SystemExit("Read-only wheel smoke test unexpectedly initialized data.")


def main() -> None:
    """装配显式请求的完整验收；只在独立目录操作样本，不调用真实模型。

    Assemble requested full acceptance in isolated directories without real model calls.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", action="store_true", help="Also run real Electron UI tests")
    args = parser.parse_args()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    os.environ["RUFF_CACHE_DIR"] = str(ARTIFACTS / "ruff-cache")
    os.environ["MYPY_CACHE_DIR"] = str(ARTIFACTS / "mypy-cache")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    # 哨兵优先于 Windows 用户凭据；本入口不读取真实秘密。
    # The sentinel takes precedence over Windows user credentials without reading real secrets.
    os.environ["OPENCODE_API_KEY"] = "engineering-check-sentinel"
    os.environ.pop("MY_AGENT_DATA_DIR", None)
    os.environ.pop("MY_AGENT_PROJECT_DIR", None)
    uv, npm = tool("uv"), tool("npm.cmd" if os.name == "nt" else "npm")
    versions()
    run([sys.executable, "tests/maintenance/check_repository.py"])
    run([uv, "lock", "--check"])
    run([sys.executable, "-m", "ruff", "format", "--check", "src", "scripts", "tests"])
    run([sys.executable, "-m", "ruff", "check", "src", "scripts", "tests"])
    run([sys.executable, "-m", "mypy", "src/my_agent"])
    with tempfile.TemporaryDirectory(prefix="checks-", dir=ARTIFACTS) as work:
        temporary = Path(work).resolve()
        if not temporary.is_relative_to(ARTIFACTS.resolve()):
            raise SystemExit("Invalid test artifact directory.")
        run([sys.executable, "-m", "pytest", "--basetemp", str(temporary / "pytest"), "-q"])
        run([sys.executable, "scripts/export_schemas.py", "--check"])
        for task in (
            "format:check",
            "types:check",
            "typecheck",
            "test:contracts",
            "test:launch",
            "test:gateway",
            "build",
        ):
            run([npm, "--prefix", "apps/desktop", "run", task])
        if args.desktop:
            run([npm, "--prefix", "apps/desktop", "run", "test:desktop"])
        sample = temporary / "timeout-config"
        shutil.copytree(
            ROOT / "examples/timeout-config", sample, ignore=shutil.ignore_patterns("__pycache__")
        )
        run([sys.executable, "-m", "pytest", "-q", "test_config.py"], cwd=sample)
        run(
            [sys.executable, "acceptance.py"],
            cwd=sample,
            expected=1,
            failure_marker="AssertionError: Explicit zero must mean no timeout",
        )
        verify_wheel(uv, temporary)
        run(
            [
                sys.executable,
                "-m",
                "my_agent",
                "--data-dir",
                str(temporary / "doctor"),
                "doctor",
                "--dev",
                "--json",
            ]
        )
    print("\nM0 checks passed. No real model request was made.")


if __name__ == "__main__":
    main()
