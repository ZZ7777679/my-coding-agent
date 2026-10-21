"""独立恢复入口，仅依赖标准库，可在应用无法导入时使用。

Standalone restoration using only the standard library, even when the app cannot import.
"""

import base64
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def restore(directory: Path) -> dict[str, object]:
    """只恢复清单中的确切文件，保留其后的用户修改。

    Restore the manifest's exact file while preserving subsequent user edits.
    """
    record = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    root = Path(record["project_root"]).resolve(strict=True)
    target = (root / record["path"]).resolve(strict=False)
    if not target.is_relative_to(root) or target == root:
        raise ValueError("Recovery target is outside the recorded project")
    before = base64.b64decode(record["before"]) if record["before"] is not None else None
    after = base64.b64decode(record["after"])
    actual = target.read_bytes() if target.exists() else None
    result: dict[str, object] = {
        "candidate_id": record["candidate_id"],
        "at": datetime.now(UTC).isoformat(),
        "status": "reverted",
        "path": record["path"],
    }
    if actual == before:
        result["message"] = "The original content is already present."
    elif actual != after:
        result.update(status="changed", message="Later changes are present; nothing overwritten.")
    elif before is None:
        target.unlink()
        result["message"] = "Removed the file introduced by this candidate."
    else:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(before)
                stream.flush()
                os.fsync(stream.fileno())
            if target.read_bytes() != after:
                raise ValueError("Target changed while preparing restoration; nothing overwritten")
            os.replace(temporary, target)
            result["message"] = "Original bytes restored. Restart the application."
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    destination = directory / "result.json"
    temporary_result = directory / "result.tmp"
    temporary_result.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary_result, destination)
    return result


if __name__ == "__main__":
    print(json.dumps(restore(Path(__file__).resolve().parent), ensure_ascii=True, indent=2))
