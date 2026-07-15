"""
Ежедневное расследование — пост в канал.
Запускается по cron в 9:00 MSK (12:00 MSK = UTC+3 → 06:00 UTC... 9:00 UTC).
"""
import os
import random
import logging
from datetime import datetime

log = logging.getLogger(__name__)

CHANNEL_ID = int(os.environ.get("INVESTIGATIONS_CHANNEL", "0"))


async def daily_investigation(bot):
    """Постит ежедневное расследование в канал."""
    if not CHANNEL_ID:
        log.warning("INVESTIGATIONS_CHANNEL not set, skipping daily post")
        return

    from services.visual.share_card import generate_report_card
    from aiogram.types import BufferedInputFile

    # Берём случайный подтверждённый скам-репорт
    import db
    conn = db._conn()
    report = conn.execute(
        """SELECT token_address, chain, evidence FROM scam_reports
           WHERE status = 'confirmed'
           ORDER BY RANDOM() LIMIT 1"""
    ).fetchall()
    conn.close()

    address = None
    chain = None

    if report:
        address = report[0]["token_address"]
        chain = report[0]["chain"]
    else:
        # Fallback: trending token из DexScreener
        address, chain = await _get_trending_token()

    if not address or not chain:
        return

    # Расследуем
    from services.detective.investigator import TokenInvestigator
    investigator = TokenInvestigator()

    try:
        result = await investigator.investigate(address, chain)
    finally:
        await investigator.close()

    prob = result["scam_probability"]
    if prob < 30 and not report:
        return  # Неинтересно для канала

    # Формируем пост
    verdict_text, verdict_level = result["verdict"]
    lines = [
        "🕵️ <b>РАССЛЕДОВАНИЕ ДНЯ</b>\n",
        f"📍 Адрес: <code>{address[:20]}...</code>",
        f"⛓ Сеть: {chain.upper()}\n",
        f"<b>Вердикт:</b> {verdict_text}",
        f"🎯 Scam probability: <b>{prob}%</b>",
    ]

    if result["creator"] and result["creator"] != "Неизвестен":
        lines.append(f"👤 Создатель: <code>{result['creator'][:20]}...</code>")

    if result["siblings_count"] > 0:
        lines.append(
            f"📦 Токенов создателя: {result['siblings_count']} "
            f"(💀 {result['dead_count']} мёртвых)"
        )

    if result["red_flags"]:
        lines.append("\n🚨 <b>Красные флаги:</b>")
        for f in result["red_flags"][:3]:
            lines.append(f"• {f}")

    if prob >= 70:
        lines.extend([
            "\n💡 <b>Паттерн:</b> Серийный скамер",
            "⚠️ НЕ ИНВЕСТИРУЙ В ЭТОТ ТОКЕН",
        ])
    elif prob >= 40:
        lines.extend(["\n💡 <b>Паттерн:</b> Подозрительная активность"])
    else:
        lines.extend(["\n💡 <b>Паттерн:</b> Красных флагов мало, но проверь вручную"])

    lines.extend([
        f"\n🔍 Проверить свой токен: @Cryptop_q_bot",
        f"\n#CryptoDetective #Расследование",
    ])

    # PNG-карточка
    token_data = {
        "symbol": result.get("current_data", {}).get("symbol", "TOKEN") if result.get("current_data") else "TOKEN",
        "name": result.get("current_data", {}).get("name", "") if result.get("current_data") else "",
        "chain": chain,
        "price": result.get("current_data", {}).get("price", 0) if result.get("current_data") else 0,
        "market_cap": 0,
        "liquidity": result.get("current_data", {}).get("liquidity", 0) if result.get("current_data") else 0,
        "holders": 0,
    }
    security = {
        "score": 100 - prob,
        "flags": result.get("red_flags", []),
        "risk_level": verdict_level,
    }

    img_bytes = generate_report_card(token_data, security)
    photo = BufferedInputFile(img_bytes, filename="daily_investigation.png")

    try:
        await bot.send_photo(
            CHANNEL_ID,
            photo=photo,
            caption="\n".join(lines),
            parse_mode="HTML",
        )
        log.info(f"Daily investigation posted: {address[:12]}... prob={prob}%")
    except Exception as e:
        log.error(f"Failed to post daily investigation: {e}")


async def _get_trending_token() -> tuple[str | None, str | None]:
    """Fallback: берём trending токен из DexScreener."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.dexscreener.com/token-boosts/latest/v1")
            tokens = r.json()
            if tokens:
                t = random.choice(tokens)
                return t.get("tokenAddress"), "solana"  # Most boosts are Solana
    except Exception as e:
        log.warning(f"get_trending_token error: {e}")
    return None, None
