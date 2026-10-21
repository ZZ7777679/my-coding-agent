"""在被修改的源码目录外保存可启动的恢复入口。

Save a runnable recovery entry outside the source tree being modified.
"""

import base64
import json
import sys
from pathlib import Path

from my_agent.evolution.types import EvolutionCandidate
from my_agent.storage import atomic_write


def prepare_recovery(
    directory: Path,
    candidate: EvolutionCandidate,
    root: Path,
    target: Path,
    before: bytes | None,
    after: bytes,
) -> str:
    """先保存原始字节与独立脚本，再允许源码采用。

    Preserve original bytes and standalone script before adopting source changes.
    """
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "candidate_id": candidate.candidate_id,
        "project_root": str(root),
        "path": target.relative_to(root).as_posix(),
        "before": base64.b64encode(before).decode("ascii") if before is not None else None,
        "after": base64.b64encode(after).decode("ascii"),
    }
    atomic_write(directory / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    atomic_write(
        directory / "restore.py", Path(__file__).with_name("restore.py").read_text(encoding="utf-8")
    )
    # Batch 中仅使用已解析解释器与自身目录；% 必须按 batch 字面值转义。
    # Use the resolved interpreter and own directory, escaping literal percent signs in batch.
    interpreter = sys.executable.replace("%", "%%")
    atomic_write(
        directory / "Restore.cmd",
        f'@echo off\nsetlocal DisableDelayedExpansion\n"{interpreter}" "%~dp0restore.py"\npause\n',
    )
    return str(directory)
