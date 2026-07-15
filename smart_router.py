"""
smart_router.py — Умный роутер запросов к бесплатным API

Архитектура:
  L1: In-memory cache (60 сек)
  L2: Request deduplication (in-flight)
  L3: Weighted round-robin + circuit breaker
  L4: Fallback cascade

API:
  DexScreener (300 req/min) — основной
  GeckoTerminal (30 req/min) — бэкап
  DexPaprika (unlimited) — основной для поиска
  Birdeye (1000/day) — холдеры Solana
"""

import asyncio
import time
import hashlib
import json
import httpx
from collections import defaultdict
from typing import Any, Optional

# ═══════════════════════════════════════════════════════════════════
#  API ENDPOINT
# ═══════════════════════════════════════════════════════════════════


class APIEndpoint:
    """Описание одного API с метриками и circuit breaker"""

    def __init__(
        self,
        name: str,
        base_url: str,
        rate_limit_per_min: int,  # -1 = unlimited
        weight: int,
        timeout: int = 15,
        proxy: str = "",
    ):
        self.name = name
        self.base_url = base_url
        self.rate_limit = rate_limit_per_min
        self.weight = weight
        self.timeout = timeout
        self.proxy = proxy

        # Метрики
        self.requests_this_minute = 0
        self.minute_start = time.time()
        self.total_requests = 0
        self.total_errors = 0
        self.consecutive_errors = 0
        self.is_healthy = True
        self.disabled_until = 0.0

    def can_make_request(self) -> bool:
        """Можно ли делать запрос (rate limit + circuit breaker)"""
        # Circuit breaker
        if not self.is_healthy:
            if time.time() < self.disabled_until:
                return False
            # Попробуем восстановить
            self.is_healthy = True
            self.consecutive_errors = 0

        # Unlimited
        if self.rate_limit == -1:
            return True

        # Reset counter each minute
        now = time.time()
        if now - self.minute_start > 60:
            self.requests_this_minute = 0
            self.minute_start = now

        # 80% safe limit
        safe_limit = int(self.rate_limit * 0.8)
        return self.requests_this_minute < safe_limit

    def record_success(self):
        self.requests_this_minute += 1
        self.total_requests += 1
        self.consecutive_errors = 0

    def record_error(self):
        self.total_errors += 1
        self.consecutive_errors += 1

        # Circuit breaker: 3 consecutive errors → disable 5 min
        if self.consecutive_errors >= 3:
            self.is_healthy = False
            self.disabled_until = time.time() + 300

    def get_stats(self) -> dict:
        return {
            "name": self.name,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": round(
                self.total_errors / max(1, self.total_requests) * 100, 1
            ),
            "requests_this_minute": self.requests_this_minute,
            "rate_limit": self.rate_limit,
            "is_healthy": self.is_healthy,
            "consecutive_errors": self.consecutive_errors,
        }


# ═══════════════════════════════════════════════════════════════════
#  SMART ROUTER
# ═══════════════════════════════════════════════════════════════════


class SmartRouter:
    """Умный роутер запросов к бесплатным API"""

    def __init__(self, proxy: str = ""):
        self.proxy = proxy

        # API endpoints
        self.endpoints: dict[str, APIEndpoint] = {
            "dexscreener": APIEndpoint(
                name="dexscreener",
                base_url="https://api.dexscreener.com/latest/dex",
                rate_limit_per_min=300,
                weight=30,
                proxy=proxy,
            ),
            "geckoterminal": APIEndpoint(
                name="geckoterminal",
                base_url="https://api.geckoterminal.com/api/v2",
                rate_limit_per_min=30,
                weight=3,
                proxy=proxy,
            ),
            "dexpaprika": APIEndpoint(
                name="dexpaprika",
                base_url="https://api.dexpaprika.com",
                rate_limit_per_min=-1,  # unlimited
                weight=50,
                proxy=proxy,
            ),
        }

        # Routing rules: request_type → [api_name, ...] (priority order)
        self.routing_rules: dict[str, list[str]] = {
            "token_search": ["dexpaprika", "dexscreener", "geckoterminal"],
            "token_price": ["dexscreener", "dexpaprika", "geckoterminal"],
            "token_pairs": ["dexscreener", "geckoterminal"],
            "token_ohlc": ["dexscreener", "geckoterminal"],
        }

        # Weighted round-robin counters
        self._rr_counters: dict[str, int] = defaultdict(int)

        # In-memory cache (L1)
        self._cache: dict[str, dict] = {}
        self._cache_ttl = 60  # seconds

        # In-flight deduplication
        self._in_flight: dict[str, asyncio.Task] = {}
        self._in_flight_lock = asyncio.Lock()

        # Global httpx client (reuse connections)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            transport_kwargs = {}
            if self.proxy:
                transport_kwargs["proxy"] = self.proxy
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                **transport_kwargs,
            )
        return self._client

    # ─── CACHE HELPERS ────────────────────────────────────────────

    def _cache_key(self, request_type: str, kwargs: dict) -> str:
        raw = f"{request_type}:{json.dumps(kwargs, sort_keys=True, default=str)}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _cache_get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry and time.time() - entry["ts"] < self._cache_ttl:
            return entry["data"]
        if entry:
            del self._cache[key]
        return None

    def _cache_set(self, key: str, data: Any):
        self._cache[key] = {"data": data, "ts": time.time()}
        # Evict stale entries if cache grows too large
        if len(self._cache) > 500:
            now = time.time()
            stale = [k for k, v in self._cache.items() if now - v["ts"] > self._cache_ttl]
            for k in stale[:200]:
                del self._cache[k]

    # ─── MAIN ROUTE METHOD ────────────────────────────────────────

    async def route(self, request_type: str, **kwargs) -> dict:
        """
        Главный метод — маршрутизирует запрос.
        Возвращает dict с данными + _source, _cached fields.
        """
        cache_key = self._cache_key(request_type, kwargs)

        # L1: Memory cache
        cached = self._cache_get(cache_key)
        if cached is not None:
            return {**cached, "_cached": True}

        # L2: In-flight deduplication
        async with self._in_flight_lock:
            if cache_key in self._in_flight:
                # Wait for the same request already in progress
                try:
                    result = await self._in_flight[cache_key]
                    return {**result, "_cached": True}
                except Exception:
                    raise

            # Create future
            task = asyncio.create_task(
                self._execute_with_fallback(request_type, **kwargs)
            )
            self._in_flight[cache_key] = task

        try:
            result = await task
            self._cache_set(cache_key, result)
            return result
        finally:
            async with self._in_flight_lock:
                self._in_flight.pop(cache_key, None)

    # ─── EXECUTION WITH FALLBACK ──────────────────────────────────

    async def _execute_with_fallback(
        self, request_type: str, **kwargs
    ) -> dict:
        """Выполняет запрос с fallback cascade"""
        api_list = self.routing_rules.get(request_type, ["dexscreener"])

        # Filter healthy + rate-limited
        available = [
            name
            for name in api_list
            if name in self.endpoints
            and self.endpoints[name].can_make_request()
        ]

        if not available:
            # Fallback: any healthy endpoint
            available = [
                name
                for name, ep in self.endpoints.items()
                if ep.is_healthy and ep.can_make_request()
            ]

        if not available:
            return {
                "success": False,
                "error": "All APIs unavailable or rate limited",
                "_source": "none",
            }

        errors = []
        tried: set[str] = set()

        for _ in range(len(available)):
            chosen = self._weighted_rr(request_type, available, tried)
            if chosen is None:
                break
            tried.add(chosen)
            endpoint = self.endpoints[chosen]

            try:
                data = await self._call_api(chosen, endpoint, request_type, **kwargs)
                endpoint.record_success()
                return {
                    "success": True,
                    "data": data,
                    "_source": chosen,
                    "_cached": False,
                    "_timestamp": time.time(),
                }
            except Exception as e:
                endpoint.record_error()
                errors.append(f"{chosen}: {e}")

        return {
            "success": False,
            "error": f"All APIs failed: {'; '.join(errors)}",
            "_source": "none",
        }

    # ─── WEIGHTED ROUND ROBIN ─────────────────────────────────────

    def _weighted_rr(
        self, request_type: str, available: list[str], exclude: set[str]
    ) -> Optional[str]:
        """Weighted round-robin выбор API"""
        candidates = [a for a in available if a not in exclude]
        if not candidates:
            return None

        total_weight = sum(self.endpoints[a].weight for a in candidates)
        if total_weight <= 0:
            return candidates[0]

        self._rr_counters[request_type] += 1
        pos = self._rr_counters[request_type] % total_weight

        current = 0
        for name in candidates:
            current += self.endpoints[name].weight
            if pos < current:
                return name
        return candidates[0]

    # ─── HTTP CALLS ───────────────────────────────────────────────

    async def _call_api(
        self, api_name: str, endpoint: APIEndpoint, request_type: str, **kwargs
    ) -> Any:
        """Делает HTTP запрос к конкретному API"""
        client = await self._get_client()

        if api_name == "dexscreener":
            return await self._call_dexscreener(client, request_type, **kwargs)
        elif api_name == "geckoterminal":
            return await self._call_geckoterminal(client, request_type, **kwargs)
        elif api_name == "dexpaprika":
            return await self._call_dexpaprika(client, request_type, **kwargs)
        else:
            raise ValueError(f"Unknown API: {api_name}")

    async def _call_dexscreener(
        self, client: httpx.AsyncClient, request_type: str, **kwargs
    ) -> Any:
        if request_type == "token_search":
            q = kwargs.get("query", "")
            r = await client.get(
                f"https://api.dexscreener.com/latest/dex/search/?q={q}"
            )
            r.raise_for_status()
            return r.json()
        elif request_type == "token_price":
            addr = kwargs.get("address", "")
            r = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{addr}"
            )
            r.raise_for_status()
            return r.json()
        elif request_type == "token_pairs":
            addr = kwargs.get("address", "")
            r = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{addr}"
            )
            r.raise_for_status()
            return r.json()
        else:
            raise ValueError(f"DexScreener doesn't support: {request_type}")

    async def _call_geckoterminal(
        self, client: httpx.AsyncClient, request_type: str, **kwargs
    ) -> Any:
        if request_type == "token_search":
            q = kwargs.get("query", "")
            r = await client.get(
                "https://api.geckoterminal.com/api/v2/search/pools",
                params={"query": q},
            )
            r.raise_for_status()
            return r.json()
        elif request_type == "token_price":
            network = kwargs.get("network", "eth")
            addr = kwargs.get("address", "")
            r = await client.get(
                f"https://api.geckoterminal.com/api/v2/networks/{network}/tokens/{addr}"
            )
            r.raise_for_status()
            return r.json()
        else:
            raise ValueError(f"GeckoTerminal doesn't support: {request_type}")

    async def _call_dexpaprika(
        self, client: httpx.AsyncClient, request_type: str, **kwargs
    ) -> Any:
        if request_type == "token_search":
            q = kwargs.get("query", "")
            r = await client.get(
                "https://api.dexpaprika.com/networks/all/tokens/search",
                params={"query": q},
            )
            r.raise_for_status()
            return r.json()
        elif request_type == "token_price":
            chain = kwargs.get("chain", "ethereum")
            addr = kwargs.get("address", "")
            r = await client.get(
                f"https://api.dexpaprika.com/networks/{chain}/tokens/{addr}"
            )
            r.raise_for_status()
            return r.json()
        else:
            raise ValueError(f"DexPaprika doesn't support: {request_type}")

    # ─── STATS ────────────────────────────────────────────────────

    def get_all_stats(self) -> list[dict]:
        """Статистика по всем API"""
        return [ep.get_stats() for ep in self.endpoints.values()]

    def get_cache_stats(self) -> dict:
        """Статистика кэша"""
        now = time.time()
        active = sum(1 for v in self._cache.values() if now - v["ts"] < self._cache_ttl)
        return {
            "total_entries": len(self._cache),
            "active_entries": active,
            "in_flight_requests": len(self._in_flight),
        }

    async def close(self):
        """Закрытие httpx клиента"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ═══════════════════════════════════════════════════════════════════
#  SINGLETON
# ═══════════════════════════════════════════════════════════════════

_router: Optional[SmartRouter] = None


def get_router(proxy: str = "") -> SmartRouter:
    """Получить singleton роутер"""
    global _router
    if _router is None:
        _router = SmartRouter(proxy=proxy)
    return _router
