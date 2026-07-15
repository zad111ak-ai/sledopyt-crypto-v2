"""
/investigate — глубокое расследование токена.
Проверяет создателя, другие токены, связи со скамами.
"""
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

router = Router()


def _detect_chain(address: str) -> str:
    """Определяет цепочку по адресу."""
    if address.startswith("0x"):
        return "ethereum"
    if address.startswith("T"):
        return "tron"
    if address.startswith("UQ") or address.startswith("EQ"):
        return "ton"
    if len(address) > 30:
        return "solana"
    return "bitcoin"


@router.message(Command("investigate"))
async def cmd_investigate(m: Message, command: CommandObject):
    """Глубокое расследование токена."""
    if not command.args or not command.args.strip():
        await m.answer(
            "🕵️ <b>РАССЛЕДОВАНИЕ</b>\n\n"
            "Использование: <code>/investigate 0x1234...</code>\n\n"
            "Проверяем:\n"
            "• Кто создал контракт\n"
            "• Сколько других токенов запустил\n"
            "• Сколько из них «мёртвые»\n"
            "• Вероятность скама",
            parse_mode=ParseMode.HTML,
        )
        return

    address = command.args.strip()
    chain = _detect_chain(address)

    status = await m.answer("🕵️ <b>Начинаю расследование...</b>", parse_mode=ParseMode.HTML)

    try:
        from services.detective.investigator import investigate_token
        result = await investigate_token(address, chain)
    except Exception as e:
        from services.detective.investigator import log
        log.error(f"Investigate error: {e}")
        await status.edit_text(
            "❌ Ошибка расследования\n\nПопробуй другой адрес или позже.",
        )
        return

    verdict_text, verdict_level = result["verdict"]
    emoji_map = {"danger": "🔴", "warning": "🟡", "safe": "🟢"}
    emoji = emoji_map.get(verdict_level, "⚪")

    lines = [
        "🕵️ <b>РАССЛЕДОВАНИЕ ЗАВЕРШЕНО</b>\n",
        f"📍 Адрес: <code>{address[:20]}...</code>",
        f"⛓ Сеть: <b>{chain.upper()}</b>\n",
        f"<b>Вердикт:</b> {verdict_text}",
        f"🎯 Scam probability: <b>{result['scam_probability']}%</b>\n",
    ]

    if result["creator"] and result["creator"] != "Неизвестен":
        lines.append(f"👤 Создатель: <code>{result['creator'][:20]}...</code>")

    if result["other_tokens"]:
        lines.append(
            f"\n📦 <b>Другие токены создателя:</b> {result['total_tokens']}"
        )
        lines.append(f"💀 Из них мёртвых: {result['dead_tokens']}")

        if result["dead_tokens"] / max(result["total_tokens"], 1) > 0.7:
            lines.append(
                "\n⚠️ <b>Паттерн:</b> Создатель запускал токены, которые быстро умирали"
            )

    if result["current_liquidity"] < 5000:
        lines.append(f"\n💧 Ликвидность: <b>${result['current_liquidity']:.0f}</b> (низкая)")

    lines.append(f"\n{emoji} <b>Вывод:</b> {'Не инвестируй в этот токен' if verdict_level == 'danger' else 'Проверь другие факторы перед покупкой'}")

    # Кнопки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Шерить расследование", callback_data=f"share:{address}")],
        [InlineKeyboardButton(text="🔍 Новый адрес", callback_data="menu:search")],
    ])

    await status.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
