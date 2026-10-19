"""搜索 / Git 生命周期检查的受控慢后端，仅供隔离网关测试。

Controlled slow backend for isolated search/Git lifecycle gateway checks only.
"""

import time
from pathlib import Path

from my_agent.cli import entrypoint
from my_agent.local_git.settings import GitSettingsStore
from my_agent.tools.policy import checkpoint
from my_agent.tools.read_only import ReadTools

original_search = ReadTools._search
original_move = GitSettingsStore._move


def slow_search(self, args):
    """特定夹具查询等待取消，保留真实文件搜索与清理路径。

    Hold the fixture query until cancelled, retaining actual search and cleanup paths.
    """
    if args.query != "__slow_fixture__":
        return original_search(self, args)
    root = self.policy.root
    (root / "search-entered").write_text("entered", encoding="utf-8")
    try:
        while not self.stop.wait(0.05):
            pass
        checkpoint(self.stop)
    finally:
        with (root / "search-cleaned").open("a", encoding="utf-8") as stream:
            stream.write("cleaned\n")


def slow_move(source: Path, target: Path) -> None:
    """关闭夹具仓库时延迟超过原退出宽限，随后真实移动。

    Delay fixture disable past the old shutdown grace, then perform the real move.
    """
    if source.name == ".git":
        (source.parent / "move-entered").write_text("entered", encoding="utf-8")
        time.sleep(17)
    original_move(source, target)


if __name__ == "__main__":
    ReadTools._search = slow_search
    GitSettingsStore._move = staticmethod(slow_move)
    entrypoint()
