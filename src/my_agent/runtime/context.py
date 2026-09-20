"""运行上下文接口与持久版本引用。 Runtime context contract and durable revision reference."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SharedContext:
    """请求采用的任务版本与文本，不含其他会话原生历史。

    Task context excluding other sessions' native history.
    """

    task_id: str
    revision: int
    text: str
