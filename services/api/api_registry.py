"""
Группировка API по типу монет + приоритеты.
Для каждой группы — основной API + fallback'ы.
"""

API_GROUPS = {
    # L1 монеты (BTC, ETH, SOL, TON, DOGE)
    "l1_prices": {
        "apis": [
            {"name": "coingecko", "weight": 50, "rate_limit": 30},
            {"name": "coinpaprika", "weight": 30, "rate_limit": 100},
            {"name": "messari", "weight": 20, "rate_limit": 50},
        ],
        "cache_ttl": 60,
    },

    # EVM токены (ETH, BSC, Polygon, Base, Arbitrum)
    "evm_security": {
        "apis": [
            {"name": "goplus", "weight": 40, "rate_limit": 100},
            {"name": "honeypot_is", "weight": 30, "rate_limit": 60},
            {"name": "dexscreener_security", "weight": 30, "rate_limit": 300},
        ],
        "cache_ttl": 300,
    },

    # Solana токены
    "solana_security": {
        "apis": [
            {"name": "rugcheck", "weight": 50, "rate_limit": 60},
            {"name": "birdeye", "weight": 30, "rate_limit": 100},
        ],
        "cache_ttl": 300,
    },

    # TON токены
    "ton_security": {
        "apis": [
            {"name": "tonapi", "weight": 60, "rate_limit": 100},
            {"name": "tonviewer", "weight": 40, "rate_limit": 50},
        ],
        "cache_ttl": 300,
    },

    # Цены и ликвидность (все сети)
    "prices": {
        "apis": [
            {"name": "dexscreener", "weight": 40, "rate_limit": 300},
            {"name": "geckoterminal", "weight": 30, "rate_limit": 30},
            {"name": "birdeye", "weight": 20, "rate_limit": 100},
        ],
        "cache_ttl": 30,
    },
}

# Маппинг сетей → группы
CHAIN_TO_GROUPS = {
    "bitcoin": ["l1_prices"],
    "ethereum": ["l1_prices", "evm_security", "prices"],
    "solana": ["l1_prices", "solana_security", "prices"],
    "ton": ["l1_prices", "ton_security", "prices"],
    "doge": ["l1_prices"],
    "bnb": ["l1_prices"],
    "xrp": ["l1_prices"],
    "ada": ["l1_prices"],
    "bsc": ["evm_security", "prices"],
    "polygon": ["evm_security", "prices"],
    "base": ["evm_security", "prices"],
    "arbitrum": ["evm_security", "prices"],
    "optimism": ["evm_security", "prices"],
    "avalanche": ["evm_security", "prices"],
}
