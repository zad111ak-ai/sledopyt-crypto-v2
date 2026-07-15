"""
Event loop monitor + ConcurrencyLimiter для параллельных API вызовов.
"""
import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class ConcurrencyLimiter:
    """Ограничивает количество параллельных задач."""

    def __init__(self, max_concurrent: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, coro):
        async with self.semaphore:
            return await coro


# Глобальный лимитер для API вызовов
api_limiter = ConcurrencyLimiter(max_concurrent=5)


async def monitor_event_loop():
    """Проверяет что event loop не блокируется."""
    while True:
        start = time.monotonic()
        await asyncio.sleep(1)
        delay = time.monotonic() - start - 1

        if delay > 0.5:
            logger.warning(
                "event_loop_blocked delay_ms=%d",
                round(delay * 1000),
            )
