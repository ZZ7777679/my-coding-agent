"""将 python -m my_agent 交给共用 CLI 入口。

Route python -m my_agent through the shared CLI entry point.
"""

from my_agent.cli import entrypoint

entrypoint()
