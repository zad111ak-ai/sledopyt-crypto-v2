"""
/scam — репортить скам-токен.
/leaderboard — топ охотников за скамом.
"""
import os
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.enums import ParseMode

import db

router = Router()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))


@router.message(Command("report", "scam"))
async def cmd_report(m: Message, command: CommandObject):
    """Репорт скам-токена."""
    if not command.args or not command.args.strip():
        await m.answer(
            "🎯 <b>Репортить скам</b>\n\n"
            "Использование:\n"
            "<code>/report 0x1234... описание</code>\n\n"
            "Если скам подтвердится:\n"
            "+100 очков + 10 кредитов",
            parse_mode=ParseMode.HTML,
        )
        return

    parts = command.args.strip().split(maxsplit=1)
    address = parts[0]
    evidence = parts[1] if len(parts) > 1 else ""

    # Определяем цепочку
    chain = "ethereum"
    if address.startswith("T"):
        chain = "tron"
    elif address.startswith("UQ") or address.startswith("EQ"):
        chain = "ton"
    elif len(address) > 30:
        chain = "solana"

    conn = db._conn()
    conn.execute(
        "INSERT INTO scam_reports (reporter_id, token_address, chain, evidence) VALUES (?, ?, ?, ?)",
        (m.from_user.id, address, chain, evidence),
    )
    conn.commit()
    conn.close()

    await m.answer(
        f"✅ <b>Репорт принят!</b>\n\n"
        f"📍 Адрес: <code>{address[:20]}...</code>\n"
        f"⛓ Сеть: {chain.upper()}\n\n"
        f"Проверим в течение 24 часов.\n"
        f"Если скам подтвердится — +100 очков + 10 кредитов\n\n"
        f"🏆 /leaderboard — твой рейтинг",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("leaderboard", "top_hunters"))
async def cmd_leaderboard(m: Message):
    """Топ охотников за скамом."""
    conn = db._conn()
    rows = conn.execute(
        """SELECT reporter_id, SUM(points) as total, COUNT(*) as reports
           FROM scam_reports
           WHERE status = 'confirmed'
           GROUP BY reporter_id
           ORDER BY total DESC
           LIMIT 10"""
    ).fetchall()
    conn.close()

    if not rows:
        await m.answer(
            "🏆 <b>TOP SCAM HUNTERS</b>\n\n"
            "Пока нет подтверждённых репортов.\n\n"
            "Начни первым: /report 0x1234...",
            parse_mode=ParseMode.HTML,
        )
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>TOP SCAM HUNTERS</b>\n"]

    for i, row in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i+1}."
        uid = row["reporter_id"]
        # Try to get username
        try:
            # Can't get username from DB, use ID
            name = f"User#{uid}"
        except Exception:
            name = f"User#{uid}"
        lines.append(f"{medal} <b>{name}</b> — {row['total']} очков ({row['reports']} репортов)")

    # My position
    my = conn.execute(
        "SELECT SUM(points) as total FROM scam_reports WHERE reporter_id = ? AND status = 'confirmed'",
        (m.from_user.id,),
    ).fetchone() if False else {"total": 0}

    # Re-fetch my stats
    conn2 = db._conn()
    my = conn2.execute(
        "SELECT SUM(points) as total FROM scam_reports WHERE reporter_id = ? AND status = 'confirmed'",
        (m.from_user.id,),
    ).fetchone()
    conn2.close()

    my_total = my["total"] if my and my["total"] else 0
    lines.append(f"\n📊 <b>Ты:</b> {my_total} очков")

    lines.append("\n🎯 /report — репортить скам")

    await m.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(Command("confirm_scam"))
async def cmd_confirm_scam(m: Message, command: CommandObject):
    """Админ-команда подтверждения скама (только для админа)."""
    if m.from_user.id != ADMIN_ID:
        return

    if not command.args:
        await m.answer("Использование: /confirm_scam <report_id>")
        return

    try:
        report_id = int(command.args.strip())
    except ValueError:
        await m.answer("ID должен быть числом")
        return

    conn = db._conn()
    row = conn.execute(
        "SELECT reporter_id FROM scam_reports WHERE id = ?", (report_id,)
    ).fetchone()

    if not row:
        await m.answer(f"Репорт #{report_id} не найден")
        conn.close()
        return

    conn.execute(
        "UPDATE scam_reports SET status = 'confirmed', points = 100 WHERE id = ?",
        (report_id,),
    )
    conn.commit()
    conn.close()

    # Начисляем кредиты
    reporter_id = row["reporter_id"] if row else None
    if not reporter_id:
        await m.answer("Ошибка")
        conn.close()
        return

    db.add_balance(reporter_id, 10)
    db.log_credit_transaction(reporter_id, 10, "reward", "Подтверждённый скам")

    await m.answer(f"✅ Репорт #{report_id} подтверждён!\n+100 очков + 10 кредитов отправлены")
