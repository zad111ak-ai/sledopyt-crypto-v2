"""
CPU-bound задачи в executor чтобы не блокировать event loop.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

_executor = ThreadPoolExecutor(max_workers=4)


async def run_in_executor(func, *args, **kwargs):
    """Запускает sync функцию в отдельном потоке."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        partial(func, *args, **kwargs),
    )
