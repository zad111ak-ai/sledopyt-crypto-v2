"""
/hot — горячие токены + scam risk.
Топ трендовых токенов с быстрой проверкой на скам.
"""
import asyncio
import httpx
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

router = Router()

PROXY = "http://127.0.0.1:1082"


async def _get_trending() -> list[dict]:
    """Топ трендовых токенов из DexScreener."""
    try:
        async with httpx.AsyncClient(proxy=PROXY, timeout=15) as client:
            r = await client.get("https://api.dexscreener.com/token-boosts/latest/v1")
            tokens = r.json()
            results = []
            for t in tokens[:5]:
                addr = t.get("tokenAddress", "")
                chain = "solana" if len(addr) > 40 else "ethereum"
                results.append({
                    "address": addr,
                    "chain": chain,
                    "icon": t.get("icon", ""),
                    "description": t.get("description", ""),
                })
            return results
    except Exception:
        return []


async def _quick_risk(address: str, chain: str) -> dict:
    """Быстрая проверка риска через DexScreener."""
    try:
        async with httpx.AsyncClient(proxy=PROXY, timeout=10) as client:
            r = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{address}"
            )
            pairs = r.json().get("pairs", [])
            if not pairs:
                return {"score": 50, "label": "❓", "reason": "Нет данных"}

            pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
            liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
            vol = float(pair.get("volume", {}).get("h24", 0) or 0)
            change = float(pair.get("priceChange", {}).get("h24", 0) or 0)
            symbol = pair.get("baseToken", {}).get("symbol", "?")
            price = float(pair.get("priceUsd", 0) or 0)

            # Быстрый scoring
            score = 0
            if liq < 1000:
                score += 40
            elif liq < 10000:
                score += 20
            if vol < 100:
                score += 30
            elif vol < 1000:
                score += 15
            if change < -80:
                score += 20
            elif change < -50:
                score += 10

            if score >= 70:
                label, emoji = "🔴 ВЫСОКИЙ", "🔴"
            elif score >= 40:
                label, emoji = "🟡 СРЕДНИЙ", "🟡"
            else:
                label, emoji = "🟢 НИЗКИЙ", "🟢"

            return {
                "score": score,
                "label": label,
                "emoji": emoji,
                "symbol": symbol,
                "price": price,
                "liquidity": liq,
                "volume": vol,
                "change_24h": change,
            }
    except Exception:
        return {"score": 50, "label": "❓", "emoji": "❓", "symbol": "?", "price": 0, "liquidity": 0, "volume": 0, "change_24h": 0}


@router.message(Command("hot"))
async def cmd_hot(m: Message):
    """Горячие токены + scam risk."""
    status = await m.answer("🔥 Ищу горячие токены...")

    trending = await _get_trending()
    if not trending:
        await status.edit_text("❌ Не удалось получить тренды. Попробуй позже.")
        return

    lines = ["🔥 <b>ГОРЯЧИЕ ТОКЕНЫ + SCAM RISK</b>\n"]

    tasks = [_quick_risk(t["address"], t["chain"]) for t in trending]
    risks = await asyncio.gather(*tasks, return_exceptions=True)

    for i, (t, risk) in enumerate(zip(trending, risks), 1):
        if isinstance(risk, Exception):
            risk = {"emoji": "❓", "label": "❓", "symbol": "?", "price": 0, "liquidity": 0, "volume": 0, "change_24h": 0, "score": 0}

        sym = risk.get("symbol", "?")
        price = risk.get("price", 0)
        liq = risk.get("liquidity", 0)
        vol = risk.get("volume", 0)
        change = risk.get("change_24h", 0)
        emoji = risk.get("emoji", "❓")
        score = risk.get("score", 0)

        change_str = f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"
        liq_str = f"${liq/1e6:.1f}M" if liq >= 1e6 else f"${liq/1e3:.0f}K" if liq >= 1000 else f"${liq:.0f}"

        lines.append(
            f"{i}. <b>{sym}</b> {emoji}\n"
            f"   💰 ${price:.6f} | 📈 {change_str}\n"
            f"   💧 {liq_str} | 📊 {risk['label']}\n"
        )

    lines.append("💡 🔴 = не рекомендую | 🟡 = осторожно | 🟢 = чисто")
    lines.append("\n🔍 /investigate — глубокое расследование")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="hot:refresh")],
        [InlineKeyboardButton(text="🔍 Investigate", callback_data="menu:investigate")],
    ])

    try:
        await status.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        await m.answer("\n".join(lines), reply_markup=keyboard, parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "hot:refresh")
async def cb_hot_refresh(cq: CallbackQuery):
    """Обновить горячие токены."""
    await cq.answer("🔄 Обновляю...")
    # Re-run the same logic
    trending = await _get_trending()
    if not trending:
        await cq.message.edit_text("❌ Не удалось обновить")
        return

    lines = ["🔥 <b>ГОРЯЧИЕ ТОКЕНЫ + SCAM RISK</b>\n"]

    tasks = [_quick_risk(t["address"], t["chain"]) for t in trending]
    risks = await asyncio.gather(*tasks, return_exceptions=True)

    for i, (t, risk) in enumerate(zip(trending, risks), 1):
        if isinstance(risk, Exception):
            risk = {"emoji": "❓", "label": "❓", "symbol": "?", "price": 0, "liquidity": 0, "change_24h": 0}

        sym = risk.get("symbol", "?")
        price = risk.get("price", 0)
        liq = risk.get("liquidity", 0)
        change = risk.get("change_24h", 0)
        emoji = risk.get("emoji", "❓")

        change_str = f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"
        liq_str = f"${liq/1e6:.1f}M" if liq >= 1e6 else f"${liq/1e3:.0f}K" if liq >= 1000 else f"${liq:.0f}"

        lines.append(
            f"{i}. <b>{sym}</b> {emoji}\n"
            f"   💰 ${price:.6f} | 📈 {change_str}\n"
            f"   💧 {liq_str} | 📊 {risk['label']}\n"
        )

    lines.append("💡 🔴 = не рекомендую | 🟡 = осторожно | 🟢 = чисто")
    lines.append("\n🔍 /investigate — глубокое расследование")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="hot:refresh")],
        [InlineKeyboardButton(text="🔍 Investigate", callback_data="menu:investigate")],
    ])

    try:
        await cq.message.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        pass
