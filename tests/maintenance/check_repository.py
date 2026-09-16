"""检查候选仓库文件的编码、本地文档引用与测试集中位置。

Check candidate file encoding, local documentation references and centralized test placement.
"""

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".mts",
    ".json",
    ".toml",
    ".lock",
    ".md",
    ".css",
    ".html",
    ".yml",
    ".yaml",
    ".cmd",
}


def main() -> None:
    """只检查 Git 候选文件并汇总问题，不读取忽略的个人配置或运行应用。

    Inspect only Git candidates and report issues, without reading ignored personal files.
    """

    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode("utf-8")
        .split("\0")
    )
    paths = [ROOT / name for name in names if name and (ROOT / name).is_file()]
    problems: list[str] = []
    documents = links = 0
    for file in paths:
        relative = file.relative_to(ROOT)
        test_file = (
            "tests" in relative.parts
            or file.name == "conftest.py"
            or (file.name.startswith("test_") and file.suffix == ".py")
            or re.search(r"\.(test|spec)\.(mjs|[jt]sx?)$", file.name)
        )
        if test_file and relative.parts[0] not in {"tests", "examples"}:
            problems.append(f"Test outside centralized tests/: {relative.as_posix()}")
        if file.suffix not in TEXT_SUFFIXES and not file.name.startswith("."):
            continue
        text = file.read_text(encoding="utf-8")
        if "\ufffd" in text or text.startswith("\ufeff"):
            problems.append(f"Invalid text encoding: {relative.as_posix()}")
        if not text.endswith("\n"):
            problems.append(f"Missing final newline: {relative.as_posix()}")
        if any(
            line.rstrip(" \t") != line and not (file.suffix == ".md" and line.endswith("  "))
            for line in text.splitlines()
        ):
            problems.append(f"Trailing whitespace: {relative.as_posix()}")
        if file.suffix != ".md":
            continue
        documents += 1
        if len(re.findall(r"^```", text, re.M)) % 2:
            problems.append(f"Unbalanced code fence: {relative.as_posix()}")
        for value in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if "://" in value or value.startswith(("mailto:", "#")):
                continue
            target_path, _, anchor = value.strip("<>").partition("#")
            target = (file.parent / unquote(target_path)).resolve()
            links += 1
            if not target.exists():
                problems.append(f"Missing local link in {relative.as_posix()}: {target_path}")
            elif anchor and target.suffix == ".md":
                headings = re.findall(r"^#{1,6}\s+(.+)$", target.read_text(encoding="utf-8"), re.M)
                slugs = [
                    re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
                    for heading in headings
                ]
                if unquote(anchor) not in slugs:
                    problems.append(f"Missing local anchor in {relative.as_posix()}: {anchor}")
    if problems:
        raise SystemExit("\n".join(problems))
    print(
        json.dumps(
            {
                "files": len(paths),
                "markdown": documents,
                "local_links": links,
                "test_layout": "centralized",
                "format": "ok",
            }
        )
    )


if __name__ == "__main__":
    main()
