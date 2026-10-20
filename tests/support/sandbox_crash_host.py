"""在独立宿主启动沙箱后等待外部终止，验证真实崩溃恢复。

Start a sandbox under a disposable host and wait to be killed for crash-recovery verification.
"""

import ctypes
import json
import sys
import time
from pathlib import Path

from my_agent.execution.environments import execution_environment
from my_agent.execution.sandbox import SandboxProcess
from my_agent.execution.sandbox_preview import SandboxPreview
from my_agent.execution.types import EnvironmentView


def main():
    """读取隔离样本配置并保存实际 PID，不主动执行清理。

    Load isolated configuration and record actual PIDs without performing voluntary cleanup.
    """
    base = Path(sys.argv[1]).resolve(strict=True)
    artifacts = Path(__file__).resolve().parents[2] / ".artifacts/tests"
    assert base.is_relative_to(artifacts.resolve())
    view = EnvironmentView.model_validate_json((base / "view.json").read_text(encoding="utf-8"))
    root = base / "project"
    command = [view.interpreter, "-c", "import time; time.sleep(300)"]
    port_file = base / "port.json"
    if port_file.exists():
        command = [
            view.interpreter,
            "-m",
            "http.server",
            str(json.loads(port_file.read_text())),
            "--bind",
            "127.0.0.1",
        ]
    process = SandboxProcess(
        command,
        root,
        execution_environment(view),
        65536,
        base / "leases",
        root,
        view,
    )
    preview = None
    if port_file.exists():
        preview = SandboxPreview(
            process, f"http://127.0.0.1:{json.loads(port_file.read_text())}", 10
        )
    (base / "ready.json").write_text(
        json.dumps(
            {
                "pid": process.pid,
                "url": preview.url if preview else None,
                "elevated": bool(ctypes.windll.shell32.IsUserAnAdmin()),
            }
        ),
        encoding="utf-8",
    )
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
