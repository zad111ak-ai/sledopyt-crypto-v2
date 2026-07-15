"""
Карта нативных сетей для популярных токенов.
Приоритет: сначала ищем в нативной сети, потом fallback.
"""
from typing import Optional

NATIVE_CHAINS = {
    # Major tokens
    "BTC": ["bitcoin", "ethereum"],
    "BITCOIN": ["bitcoin", "ethereum"],
    "ETH": ["ethereum"],
    "ETHEREUM": ["ethereum"],
    "SOL": ["solana"],
    "SOLANA": ["solana"],
    "TON": ["ton"],
    "GRAM": ["ton"],
    "BNB": ["bsc"],
    "XRP": ["ripple"],
    "ADA": ["cardano"],
    "DOGE": ["doge"],
    "AVAX": ["avalanche"],
    "MATIC": ["polygon"],
    "DOT": ["polkadot"],
    "LINK": ["ethereum"],

    # TON ecosystem
    "NOT": ["ton"],
    "HMSTR": ["ton"],
    "DOGS": ["ton"],
    "CATI": ["ton"],
    "REDO": ["ton"],

    # Ethereum meme
    "PEPE": ["ethereum"],
    "SHIB": ["ethereum"],
    "FLOKI": ["ethereum", "bsc"],

    # Solana meme
    "BONK": ["solana"],
    "WIF": ["solana"],
    "POPCAT": ["solana"],

    # Base
    "BRETT": ["base"],
}

# ЖЕСТКИЙ МАППИНГ: токены ВСЕГДА в родной сети (ignore liquidity)
ABSOLUTE_NATIVE = {
    "BTC": "bitcoin",
    "BITCOIN": "bitcoin",
    "ETH": "ethereum",
    "ETHEREUM": "ethereum",
    "SOL": "solana",
    "SOLANA": "solana",
    "TON": "ton",
    "GRAM": "ton",
    "BNB": "bsc",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "doge",
    "DOGECOIN": "doge",
    "AVAX": "avalanche",
    "AVALANCHE": "avalanche",
    "MATIC": "polygon",
    "POLYGON": "polygon",
    "DOT": "polkadot",
    "POLKADOT": "polkadot",
    "LINK": "ethereum",
    "CHAINLINK": "ethereum",
    "UNI": "ethereum",
    "UNISWAP": "ethereum",
    "AAVE": "ethereum",
    "TRX": "tron",
    "TRON": "tron",
    "USDT": "ethereum",
    "USDC": "ethereum",
}

# Токены экосистем (живут в конкретных сетях)
ECOSYSTEM_TOKENS = {
    # TON ecosystem
    "NOT": "ton",
    "HMSTR": "ton",
    "DOGS": "ton",
    "CATI": "ton",
    "REDO": "ton",
    # Solana meme
    "BONK": "solana",
    "WIF": "solana",
    "POPCAT": "solana",
    "JUP": "solana",
    # Ethereum meme
    "PEPE": "ethereum",
    "SHIB": "ethereum",
    "FLOKI": "ethereum",
    # Base
    "BRETT": "base",
}

# Wrapped-маркеры
WRAPPED_KEYWORDS = {"wrapped", "wbtc", "weth", "wton", "bridge", "bridged"}


def get_preferred_chains(symbol: str) -> list:
    return NATIVE_CHAINS.get(symbol.upper(), [])


def is_wrapped(token_name: str) -> bool:
    name_lower = token_name.lower()
    return any(kw in name_lower for kw in WRAPPED_KEYWORDS)


def force_native_chain(query: str) -> Optional[str]:
    """Возвращает принудительную сеть для известных токенов.
    Если токен известен - ВСЕГДА показываем родную сеть."""
    q = query.upper().strip()
    return ABSOLUTE_NATIVE.get(q) or ECOSYSTEM_TOKENS.get(q)


def smart_sort(tokens: list, query: str) -> list:
    """Сортировка с приоритетом нативной сети."""
    preferred = get_preferred_chains(query)
    quality = {"ethereum", "bsc", "ton", "bitcoin", "solana", "base", "arbitrum"}

    def key(t):
        chain = t.get("chain", "")
        liq = float(t.get("liquidity", 0) or 0)
        # Preferred chain = 100M bonus
        bonus = 100_000_000 if chain in preferred else 0
        q_bonus = 10_000 if chain in quality else 0
        return bonus + q_bonus + liq

    return sorted(tokens, key=key, reverse=True)
