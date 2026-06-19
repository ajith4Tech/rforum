"""
Lightweight async task queue.

Interface is stable so the backing implementation can be swapped for
Celery / Redis Queue without changing callers.

Usage:
    task_queue.enqueue(my_async_fn, arg1, arg2, kwarg=val)
"""
import asyncio
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger("rforum.tasks")


class AsyncTaskQueue:
    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._worker_task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the background worker. Must be called inside a running event loop."""
        self._worker_task = asyncio.create_task(self._run(), name="task-queue-worker")

    async def stop(self) -> None:
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    def enqueue(self, coro_fn: Callable[..., Coroutine], *args: Any, **kwargs: Any) -> None:
        """Non-blocking. Drops silently if the queue is full."""
        try:
            self._queue.put_nowait((coro_fn, args, kwargs))
        except asyncio.QueueFull:
            logger.warning(
                "task_queue_full",
                extra={"task": getattr(coro_fn, "__name__", "unknown")},
            )

    async def _run(self) -> None:
        while True:
            coro_fn, args, kwargs = await self._queue.get()
            try:
                await coro_fn(*args, **kwargs)
            except Exception as exc:
                logger.error(
                    "task_failed",
                    extra={
                        "task": getattr(coro_fn, "__name__", "unknown"),
                        "error": str(exc),
                    },
                )
            finally:
                self._queue.task_done()


task_queue = AsyncTaskQueue()
