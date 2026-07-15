"""
Верифицированные wrapped-токены от известных эмитентов.
Фильтрует скам-клоны с накрученной ликвидностью.
"""
import logging

logger = logging.getLogger(__name__)

# Верифицированные адреса (только проверенные эмитенты)
VERIFIED_ADDRS = {
    # Bitcoin wrapped
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # WBTC Wormhole
    "qfnqNqs3nCAHjnyCgLRDbBtq4p2MtHZxw8YjSyYhPoL",   # WBTC Allbridge
    "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",       # WBTC BitGo (ETH)
    # Ethereum wrapped
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",  # WETH Wormhole
    "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",       # ETH Binance Peg (BSC)
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",       # WETH (ETH mainnet)
}

# Допустимое отклонение цены wrapped от оригинала
MAX_PRICE_DIFF_PCT = 15.0

# Минимальная ликвидность для wrapped
MIN_LIQUIDITY_USD = 500_000


def is_verified_wrapped(address: str) -> bool:
    """Проверяет является ли адрес верифицированным wrapped токеном."""
    return address.lower() in {a.lower() for a in VERIFIED_ADDRS}


def filter_wrapped(
    original_price: float,
    candidates: list[dict],
    max_results: int = 3,
) -> list[dict]:
    """
    Фильтрует wrapped-кандидатов:
    1. Только верифицированные адреса ИЛИ цена ±15% от оригинала
    2. Минимальная ликвидность $500K
    3. Максимум max_results результатов
    """
    if not candidates:
        return []

    verified = []
    scam_count = 0

    for t in candidates:
        addr = t.get("address", "")
        price = t.get("price_usd", 0)
        liq = t.get("liquidity_usd", 0) or t.get("liquidity", 0)

        # Минимальная ликвидность
        if liq < MIN_LIQUIDITY_USD:
            scam_count += 1
            continue

        # Проверка цены (если оригинал известен)
        if original_price > 0 and price > 0:
            diff_pct = abs(price - original_price) / original_price * 100
            if diff_pct > MAX_PRICE_DIFF_PCT:
                logger.info("wrapped_scam filtered addr=%s diff=%.1f%%", addr, diff_pct)
                scam_count += 1
                continue

        # Верифицированный адрес — приоритет
        if is_verified_wrapped(addr):
            verified.insert(0, t)  # В начало
        else:
            verified.append(t)

    if scam_count > 0:
        logger.info("wrapped_filtered scam_count=%d kept=%d", scam_count, len(verified))

    return verified[:max_results]
