"""工单实验的轻量源码与配置快照，不保存原始差异或秘密。

Lightweight ticket experiment provenance without raw patches or secrets.
"""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATHS = (
    "src/my_agent",
    "apps/desktop/src",
    "scripts",
    "tests/models",
    "tests/support",
    "tests/fixtures",
    "pyproject.toml",
    "uv.lock",
    "apps/desktop/package.json",
    "apps/desktop/package-lock.json",
)


def digest(value: bytes) -> str:
    """仅摘要源码 / 合成提示，不摘要凭据。 Digest source/synthetic prompts, never credentials."""
    return hashlib.sha256(value).hexdigest()


def source_manifest(repository: Path = ROOT) -> dict[str, object]:
    """只采集明确源码范围，包含暂存、未暂存与未跟踪内容指纹。

    Fingerprint explicit source scopes, including staged, unstaged and untracked content.
    """

    def git(*args: str) -> bytes:
        """只读 Git，不输出补丁。 Read Git without printing patches."""
        return subprocess.check_output(["git", *args], cwd=repository)

    names = git("ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *SOURCE_PATHS)
    files = {}
    for name in sorted(set(names.decode("utf-8").split("\0")) - {""}):
        path = repository / name
        if path.is_file() and path.resolve().is_relative_to(repository.resolve()):
            files[name] = digest(path.read_bytes())
    diffs = {}
    for label, option in (("unstaged", ()), ("staged", ("--cached",))):
        patch = git("diff", *option, "--binary", "--", *SOURCE_PATHS)
        diffs[label] = {"sha256": digest(patch), "bytes": len(patch)}
    return {
        "head": git("rev-parse", "HEAD").decode().strip(),
        "files": files,
        "dirty_diff": diffs,
        "file_set_sha256": digest(json.dumps(files, sort_keys=True).encode()),
    }


def save_manifest(
    directory: Path, phase: str, config: dict[str, object], prompt: str
) -> dict[str, object]:
    """每阶段另存不可覆盖快照，限额 / 提示变化不抹去上一版本。

    Save a non-overwriting phase snapshot so limit/prompt changes preserve prior versions.
    """
    manifest = {
        "schema_version": 1,
        "at": datetime.now(UTC).isoformat(),
        "phase": phase,
        "config": config,
        "prompt_sha256": digest(prompt.encode("utf-8")),
        "source": source_manifest(),
        # 白名单合成输入 / Agent 种子，保证后续编辑对照从相同实现开始。
        # Whitelist synthetic inputs/agent seeds so follow-up comparisons start identically.
        "project_inputs": {
            name: digest(path.read_bytes())
            for name in (
                "AGENTS.md",
                "REQUIREMENTS.md",
                "tickets.csv",
                "empty.csv",
                "bad-header.csv",
                "ticket_report.py",
                "README.md",
            )
            if (path := directory / "project" / name).is_file()
            and path.resolve().is_relative_to(directory.resolve())
        },
    }
    path = directory / ("manifest-" + phase + "-" + uuid4().hex[:8] + ".json")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return {"path": path.name, **manifest}
