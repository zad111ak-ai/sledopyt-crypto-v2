"""
/investigate — глубокое расследование токена.
Проверяет создателя, siblings, связи со скамами.
Стоимость: 5 кредитов.
"""
import asyncio
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

import db

router = Router()

INVESTIGATE_COST = 5


def _detect_chain(address: str) -> str:
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
            "🕵️ <b>РАССЛЕДОВАНИЕ ТОКЕНА</b>\n\n"
            "Использование:\n"
            "<code>/investigate 0x1234...</code>\n\n"
            "Бот найдёт:\n"
            "• Кто создал токен\n"
            "• Какие ещё токены создавал\n"
            "• Живы ли эти другие токены\n"
            "• Есть ли связи со скамами\n\n"
            f"💰 Стоимость: {INVESTIGATE_COST} кредитов",
            parse_mode=ParseMode.HTML,
        )
        return

    address = command.args.strip()
    uid = m.from_user.id
    user = db.get_user(uid)
    if not user:
        await m.answer("❌ Ошибка. Попробуй /start")
        return

    if user["balance"] < INVESTIGATE_COST:
        await m.answer(
            f"💎 Недостаточно кредитов\n\n"
            f"Баланс: {user['balance']} | Нужно: {INVESTIGATE_COST}\n\n"
            f"Купи кредиты: /buy",
            parse_mode=ParseMode.HTML,
        )
        return

    # Списываем кредиты
    if not db.spend_balance(uid, INVESTIGATE_COST):
        await m.answer("❌ Не удалось списать кредиты. Попробуй позже.")
        return
    db.log_credit_transaction(uid, -INVESTIGATE_COST, "spend", f"Расследование {address[:12]}...")

    status = await m.answer(
        "🕵️ <b>Начинаю расследование...</b>\n⏳ Определяю сеть",
        parse_mode=ParseMode.HTML,
    )

    chain = _detect_chain(address)
    if chain == "bitcoin":
        await status.edit_text(
            "❌ Расследование пока работает для EVM/Solana/TON\n\n"
            "Кредит возвращён ✅",
        )
        db.add_balance(uid, INVESTIGATE_COST)
        db.log_credit_transaction(uid, INVESTIGATE_COST, "refund", "Возврат: неизвестная сеть")
        return

    # Запускаем расследование с прогрессом
    from services.detective.investigator import TokenInvestigator
    investigator = TokenInvestigator()

    steps = [
        "🕵️ <b>Расследование...</b>\n⏳ Ищу создателя контракта...",
        "🕵️ <b>Расследование...</b>\n✅ Создатель найден\n⏳ Ищу другие токены создателя...",
        "🕵️ <b>Расследование...</b>\n✅ Создатель найден\n✅ Токены найдены\n⏳ Анализирую каждый...",
        "🕵️ <b>Расследование...</b>\n✅ Создатель найден\n✅ Токены найдены\n✅ Анализ завершён\n⏳ Проверяю связи со скамами...",
    ]

    # Запускаем расследование в фоне
    result_task = asyncio.create_task(investigator.investigate(address, chain))

    # Показываем прогресс
    for step_text in steps:
        try:
            await status.edit_text(step_text, parse_mode=ParseMode.HTML)
        except Exception:
            pass
        try:
            result = await asyncio.wait_for(asyncio.shield(result_task), timeout=3)
            break
        except asyncio.TimeoutError:
            continue

    # Ждём финальный результат
    try:
        result = await asyncio.wait_for(result_task, timeout=30)
    except asyncio.TimeoutError:
        await status.edit_text(
            "⏱ <b>Таймаут расследования</b>\n\n"
            "Попробуй другой адрес или позже\n"
            "Кредит возвращён ✅",
            parse_mode=ParseMode.HTML,
        )
        db.add_balance(uid, INVESTIGATE_COST)
        db.log_credit_transaction(uid, INVESTIGATE_COST, "refund", "Возврат: таймаут")
        return
    finally:
        await investigator.close()

    # Сохраняем результат
    db._conn().execute(
        """INSERT INTO investigation_results
           (user_id, token_address, chain, verdict, scam_probability)
           VALUES (?, ?, ?, ?, ?)""",
        (uid, address, chain, result["verdict"][0], result["scam_probability"]),
    )
    db._conn().commit()

    # Формируем отчёт
    report = _format_report(address, chain, result)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Шерить", callback_data=f"share:{address}"),
            InlineKeyboardButton(text="🎯 Репортить скам", callback_data=f"report_quick:{address}"),
        ],
        [InlineKeyboardButton(text="🔍 Новый адрес", callback_data="menu:search")],
    ])

    try:
        await status.edit_text(report, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        await m.answer(report, reply_markup=keyboard, parse_mode=ParseMode.HTML)


def _format_report(address: str, chain: str, result: dict) -> str:
    verdict_text, verdict_level = result["verdict"]
    emoji_map = {"danger": "🔴", "warning": "🟡", "safe": "🟢"}
    emoji = emoji_map.get(verdict_level, "⚪")

    lines = [
        "🕵️ <b>РАССЛЕДОВАНИЕ ЗАВЕРШЕНО</b>\n",
        f"📍 {address[:20]}...{address[-8:]}",
        f"⛓ {chain.upper()}\n",
        f"<b>Вердикт:</b> {verdict_text}",
        f"🎯 Scam probability: <b>{result['scam_probability']}%</b>\n",
    ]

    if result["creator"] and result["creator"] != "Неизвестен":
        lines.append(f"👤 <b>Создатель:</b> <code>{result['creator'][:20]}...</code>")

    if result["siblings_count"] > 0:
        lines.append(f"\n📦 Других токенов создателя: <b>{result['siblings_count']}</b>")
        lines.append(f"💀 Из них мёртвых: <b>{result['dead_count']}</b>")

    if result["scam_connections"]:
        total = sum(len(c["common_holders"]) for c in result["scam_connections"])
        lines.append(f"\n🔗 Связей со скамами: <b>{len(result['scam_connections'])}</b>")
        lines.append(f"👥 Общих холдеров: <b>{total}</b>")

    if result["red_flags"]:
        lines.append("\n🚨 <b>КРАСНЫЕ ФЛАГИ:</b>")
        for flag in result["red_flags"][:5]:
            lines.append(f"• {flag}")

    # Паттерн
    if result["scam_probability"] >= 70:
        lines.extend([
            "\n💡 <b>Паттерн:</b> Классический серийный скамер",
            "Создаёт токен → накачивает → rug pull → повторяет",
            "\n⚠️ <b>НЕ РЕКОМЕНДУЕТСЯ К ПОКУПКЕ</b>",
        ])
    elif result["scam_probability"] >= 40:
        lines.extend([
            "\n💡 <b>Паттерн:</b> Есть подозрительные признаки",
            "Будь осторожен, проверь вручную",
        ])
    else:
        lines.extend([
            "\n💡 <b>Паттерн:</b> Серийного скама не обнаружено",
            "Но это не гарантирует безопасность",
        ])

    return "\n".join(lines)


# ─── Быстрый репорт через инлайн ──────────────────────────────
@router.callback_query(F.data.startswith("report_quick:"))
async def cb_report_quick(cq: CallbackQuery):
    """Быстрый репорт скама из /investigate."""
    address = cq.data.split(":", 1)[1]
    chain = _detect_chain(address)

    conn = db._conn()
    conn.execute(
        "INSERT INTO scam_reports (reporter_id, token_address, chain, evidence) VALUES (?, ?, ?, ?)",
        (cq.from_user.id, address, chain, "Reported via /investigate"),
    )
    conn.commit()
    conn.close()

    await cq.answer("✅ Репорт принят!", show_alert=True)
