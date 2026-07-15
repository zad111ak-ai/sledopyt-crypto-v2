"""
Rate limiter для защиты от спама и абуза API.
"""
import time
from collections import defaultdict
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """In-memory rate limiter per user."""

    def __init__(self):
        self.actions: Dict[int, list] = defaultdict(list)

    def check(self, user_id: int, max_per_minute: int = 10) -> Tuple[bool, int]:
        """Returns (allowed, wait_seconds)."""
        now = time.time()
        self.actions[user_id] = [t for t in self.actions[user_id] if now - t < 60]

        if len(self.actions[user_id]) >= max_per_minute:
            oldest = min(self.actions[user_id])
            wait = int(60 - (now - oldest)) + 1
            logger.warning("rate_limit user=%d count=%d", user_id, len(self.actions[user_id]))
            return False, wait

        self.actions[user_id].append(now)
        return True, 0


rate_limiter = RateLimiter()
