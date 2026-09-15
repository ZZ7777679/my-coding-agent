"""事件身份与顺序草案，尚未实现事件存储或实时流。

Draft event identity and ordering, without an event store or live stream.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SessionEvent:
    """预留会话、运行与序号字段；持久化与顺序保证留待运行时实现。

    Reserve session, run and sequence fields; persistence and ordering remain unimplemented.
    """

    session_id: str
    run_id: str
    # 预留会话内持久单调序号，区别于 RPC ID；保证尚待运行时实现。
    # Reserve a durable session sequence distinct from RPC IDs; guarantees are not implemented yet.
    seq: int
    kind: Literal["run.started", "run.completed", "run.failed"]
