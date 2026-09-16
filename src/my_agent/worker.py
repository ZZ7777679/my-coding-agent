"""业务文件操作的唯一受控线程。 One controlled worker for business file operations."""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial


class BusinessWorker:
    """串行执行文件工作，避免阻塞模型与取消通道。 Serialize I/O without blocking cancellation."""

    def __init__(self) -> None:
        """创建专用线程池，不占用网络事件循环。 Create a worker separate from network execution."""
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-storage")

    async def call[T](self, function: Callable[..., T], *args: object, **kwargs: object) -> T:
        """取消等待时仍收回已开始的文件操作。

        Reap started file work even when awaiting is cancelled.
        """
        future = asyncio.get_running_loop().run_in_executor(
            self.executor, partial(function, *args, **kwargs)
        )
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            await future
            raise

    def close(self) -> None:
        """在所有调用完成后释放线程。 Release the worker after outstanding calls finish."""
        self.executor.shutdown(wait=True)
