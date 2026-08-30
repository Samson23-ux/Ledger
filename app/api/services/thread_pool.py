from typing import Callable
from starlette.concurrency import run_in_threadpool


class ThreadPool:
    async def run_in_pool(self, callable: Callable, **kwargs):
        result = await run_in_threadpool(callable, **kwargs)
        return result
