"""
/museum — список легенд.
from aiogram.enums import ParseMode
Определение легендарных адресов при проверке.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

SIGN_EMOJI = {"legendary": "🌟", "important": "⭐", "infamous": "💀"}


@router.message(Command("museum", "legends"))
async def cmd_museum(m: Message):
    from services.legends.legends_db import list_legends

    legends = list_legends()

    lines = ["🏛 <b>МУЗЕЙ КРИПТЫ</b>\n"]
    for l in legends:
        emoji = SIGN_EMOJI.get(l.significance, "❓")
        lines.append(
            f"{emoji} <b>{l.name}</b> ({l.year})\n"
            f"   <code>{l.address[:20]}...</code> — {l.owner}\n"
        )

    lines.append("💡 Отправь адрес легенды для просмотра карточки")
    lines.append("Пример: <code>1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa</code>")

    await m.answer("\n".join(lines), parse_mode=ParseMode.HTML)


def format_legend_card(legend) -> str:
    emoji = SIGN_EMOJI.get(legend.significance, "❓")
    return (
        f"{emoji} <b>ЛЕГЕНДА: {legend.name}</b>\n\n"
        f"👤 {legend.owner} ({legend.year})\n\n"
        f"📖 {legend.story}\n\n"
        f"💰 Баланс: {legend.balance}\n"
        f"⛓ Сеть: {legend.chain.upper()}\n\n"
        f"💡 <i>{legend.lesson}</i>"
    )


def check_legend(address: str) -> str | None:
    """Проверяет address на легенду. Возвращает HTML-карточку или None."""
    from services.legends.legends_db import get_legend
    legend = get_legend(address)
    if legend:
        return format_legend_card(legend)
    return None
