"""
Smart API Router: weighted round-robin + circuit breaker + кэш + dedup.
"""
import asyncio
import time
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger(__name__)


class APIEndpoint:
    """Описание одного API endpoint."""

    def __init__(self, name: str, weight: int, rate_limit: int):
        self.name = name
        self.weight = weight
        self.rate_limit = rate_limit

        self.requests_this_minute = 0
        self.minute_start = time.time()
        self.total_requests = 0
        self.total_errors = 0
        self.consecutive_errors = 0

        self.is_healthy = True
        self.disabled_until = 0.0

    def can_use(self) -> bool:
        if not self.is_healthy:
            if time.time() < self.disabled_until:
                return False
            self.is_healthy = True
            self.consecutive_errors = 0

        if time.time() - self.minute_start > 60:
            self.requests_this_minute = 0
            self.minute_start = time.time()

        safe_limit = int(self.rate_limit * 0.8)
        return self.requests_this_minute < safe_limit

    def on_success(self):
        self.requests_this_minute += 1
        self.total_requests += 1
        self.consecutive_errors = 0

    def on_error(self):
        self.total_errors += 1
        self.consecutive_errors += 1

        if self.consecutive_errors >= 3:
            self.is_healthy = False
            self.disabled_until = time.time() + 300
            logger.warning(
                "circuit_breaker_open api=%s errors=%d",
                self.name, self.consecutive_errors,
            )


class SmartRouter:
    """Умный роутер запросов с fallback и circuit breaker."""

    def __init__(self):
        from services.api.api_registry import API_GROUPS

        self.endpoints: Dict[str, APIEndpoint] = {}
        self.groups = API_GROUPS

        for group_name, group_data in API_GROUPS.items():
            for api_info in group_data["apis"]:
                name = api_info["name"]
                if name not in self.endpoints:
                    self.endpoints[name] = APIEndpoint(
                        name=name,
                        weight=api_info["weight"],
                        rate_limit=api_info["rate_limit"],
                    )

        self.rr_counters = defaultdict(int)
        self.cache: Dict[str, dict] = {}
        self.in_flight: Dict[str, asyncio.Task] = {}
        self.in_flight_lock = asyncio.Lock()

    async def call(
        self,
        group: str,
        call_func: Callable,
        cache_key: str,
        **kwargs,
    ) -> Any:
        """
        Главный метод.
        call_func(api_name, **kwargs) → result
        """
        cache_ttl = self.groups.get(group, {}).get("cache_ttl", 60)
        cached = self.cache.get(cache_key)
        if cached and time.time() - cached["time"] < cache_ttl:
            logger.debug("cache_hit key=%s source=%s", cache_key, cached.get("source"))
            return cached["data"]

        async with self.in_flight_lock:
            if cache_key in self.in_flight:
                logger.debug("dedup_wait key=%s", cache_key)
                return await self.in_flight[cache_key]

            future = asyncio.create_task(
                self._execute_with_fallback(group, call_func, **kwargs)
            )
            self.in_flight[cache_key] = future

        try:
            result = await future
            self.cache[cache_key] = {
                "data": result,
                "time": time.time(),
                "source": result.get("_source") if isinstance(result, dict) else None,
            }
            return result
        finally:
            async with self.in_flight_lock:
                self.in_flight.pop(cache_key, None)

    async def _execute_with_fallback(
        self, group: str, call_func: Callable, **kwargs
    ) -> Any:
        """Пробует API в группе по очереди с fallback."""
        group_data = self.groups.get(group)
        if not group_data:
            raise ValueError(f"Unknown group: {group}")

        apis = group_data["apis"]
        first_api = self._weighted_round_robin(group, apis)
        order = [first_api] + [a for a in apis if a["name"] != first_api["name"]]

        last_error = None
        for api_info in order:
            api_name = api_info["name"]
            endpoint = self.endpoints.get(api_name)

            if not endpoint or not endpoint.can_use():
                continue

            try:
                logger.info("api_call_start api=%s group=%s", api_name, group)
                result = await call_func(api_name, **kwargs)
                endpoint.on_success()

                if isinstance(result, dict):
                    result["_source"] = api_name
                    result["_timestamp"] = time.time()

                return result

            except Exception as e:
                endpoint.on_error()
                last_error = e
                logger.warning(
                    "api_call_failed api=%s group=%s error=%s",
                    api_name, group, str(e)[:200],
                )
                continue

        raise RuntimeError(
            f"All APIs in group '{group}' failed. Last error: {last_error}"
        )

    def _weighted_round_robin(self, group: str, apis: List[dict]) -> dict:
        healthy = [a for a in apis if self.endpoints[a["name"]].can_use()]
        if not healthy:
            healthy = apis

        total_weight = sum(a["weight"] for a in healthy)
        if total_weight == 0:
            return healthy[0]

        self.rr_counters[group] += 1
        position = self.rr_counters[group] % total_weight

        current = 0
        for api in healthy:
            current += api["weight"]
            if position < current:
                return api

        return healthy[0]

    def get_stats(self) -> Dict:
        return {
            name: {
                "total_requests": ep.total_requests,
                "total_errors": ep.total_errors,
                "error_rate": round(ep.total_errors / max(1, ep.total_requests) * 100, 2),
                "is_healthy": ep.is_healthy,
                "rate_usage": f"{ep.requests_this_minute}/{ep.rate_limit}",
            }
            for name, ep in self.endpoints.items()
        }


router = SmartRouter()
