"""
coingecko.py — CoinGecko API для L1 токенов (Bitcoin, ETH, SOL, TON, etc.)

Бесплатный тир: 10-30 req/min, без ключа.
Кэш: 5 минут (L1 цены не меняются каждую секунду).
"""

import time
import httpx
from typing import Optional

PROXY = "http://127.0.0.1:1082"
BASE = "https://api.coingecko.com/api/v3"
CACHE_TTL = 300  # 5 минут

# ═══════════════════════════════════════════════════════════════════
#  МАППИНГ → CoinGecko ID
# ═══════════════════════════════════════════════════════════════════

CG_IDS = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "solana": "solana", "sol": "solana",
    "binancecoin": "binancecoin", "bnb": "binancecoin",
    "the-open-network": "the-open-network", "ton": "the-open-network",
    "ripple": "ripple", "xrp": "ripple",
    "cardano": "cardano", "ada": "cardano",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "avalanche-2": "avalanche-2", "avax": "avalanche-2",
    "polkadot": "polkadot", "dot": "polkadot",
    "chainlink": "chainlink", "link": "chainlink",
    "tron": "tron", "trx": "tron",
    "tether": "tether", "usdt": "tether",
    "usd-coin": "usd-coin", "usdc": "usd-coin",
    "matic-network": "matic-network", "matic": "matic-network",
    "polygon": "matic-network",
    "tron": "tron", "trx": "tron",
    "litecoin": "litecoin", "ltc": "litecoin",
    "stellar": "stellar", "xlm": "stellar",
    "cosmos": "cosmos", "atom": "cosmos",
    "uniswap": "uniswap", "uni": "uniswap",
    "aave": "aave",
    "near": "near",
    "aptos": "aptos", "apt": "aptos",
    "sui": "sui",
    "arbitrum": "arbitrum",
    "optimism": "optimism", "op": "optimism",
}

# ═══════════════════════════════════════════════════════════════════
#  КЭШ
# ═══════════════════════════════════════════════════════════════════

_CACHE: dict[str, dict] = {}


def _cache_get(key: str) -> Optional[dict]:
    entry = _CACHE.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["data"]
    if entry:
        del _CACHE[key]
    return None


def _cache_set(key: str, data: dict):
    _CACHE[key] = {"data": data, "ts": time.time()}


# ═══════════════════════════════════════════════════════════════════
#  ПРОВЕРКА — L1 ЛИ ТОКЕН?
# ═══════════════════════════════════════════════════════════════════

# Токены, у которых CoinGecko mainnet ≠ обёртка на DEX
L1_TOKENS = {
    "bitcoin", "ethereum", "solana", "binancecoin",
    "the-open-network", "ripple", "cardano", "dogecoin",
    "avalanche-2", "polkadot", "chainlink", "tron",
    "litecoin", "stellar", "cosmos", "near",
    "aptos", "sui", "arbitrum", "optimism",
}


def is_l1_token(query: str) -> bool:
    """Проверяет, является ли запрос L1 токеном"""
    cg_id = CG_IDS.get(query.lower())
    return cg_id in L1_TOKENS if cg_id else False


# ═══════════════════════════════════════════════════════════════════
#  API ЗАПРОСЫ
# ═══════════════════════════════════════════════════════════════════

async def get_coin_data(query: str) -> Optional[dict]:
    """
    Получает данные по L1 токену из CoinGecko.
    Возвращает dict с ценой, market cap, rank и т.д.
    """
    query_lower = query.lower().strip()

    # Кэш
    cached = _cache_get(f"cg:{query_lower}")
    if cached:
        return cached

    # Маппинг
    cg_id = CG_IDS.get(query_lower)
    if not cg_id:
        # Пробуем поиск
        cg_id = await _search_coin(query)
        if not cg_id:
            return None

    try:
        async with httpx.AsyncClient(proxy=PROXY, timeout=15) as client:
            url = f"{BASE}/coins/{cg_id}"
            params = {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
            }
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            md = data.get("market_data", {})
            result = {
                "id": cg_id,
                "name": data.get("name", ""),
                "symbol": (data.get("symbol") or "").upper(),
                "is_l1": True,
                "native_chain": data.get("asset_platform_id") or cg_id,
                "price_usd": md.get("current_price", {}).get("usd"),
                "market_cap": md.get("market_cap", {}).get("usd"),
                "market_cap_rank": data.get("market_cap_rank"),
                "volume_24h": md.get("total_volume", {}).get("usd"),
                "price_change_24h": md.get("price_change_percentage_24h"),
                "price_change_7d": md.get("price_change_percentage_7d"),
                "price_change_30d": md.get("price_change_percentage_30d"),
                "ath": md.get("ath", {}).get("usd"),
                "ath_change_percent": md.get("ath_change_percentage", {}).get("usd"),
                "atl": md.get("atl", {}).get("usd"),
                "circulating_supply": md.get("circulating_supply"),
                "total_supply": md.get("total_supply"),
                "max_supply": md.get("max_supply"),
                "trust_score": 100,  # CoinGecko verified
                "is_verified": True,
            }

            _cache_set(f"cg:{query_lower}", result)
            return result

    except Exception as e:
        print(f"[CoinGecko] Error for {query}: {e}")
        return None


async def _search_coin(query: str) -> Optional[str]:
    """Поиск CoinGecko ID по названию"""
    try:
        async with httpx.AsyncClient(proxy=PROXY, timeout=10) as client:
            resp = await client.get(f"{BASE}/search", params={"query": query})
            resp.raise_for_status()
            data = resp.json()
            coins = data.get("coins", [])
            if coins:
                return coins[0]["id"]
    except Exception:
        pass
    return None


def get_cache_stats() -> dict:
    """Статистика кэша"""
    now = time.time()
    active = sum(1 for v in _CACHE.values() if now - v["ts"] < CACHE_TTL)
    return {"total": len(_CACHE), "active": active}
