"""
Daily streaks + achievements для sledopyt-crypto-v2.
"""
import time
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

ACHIEVEMENTS = {
    "first_check": {"name": "🔍 Первый шаг", "check": lambda u: u["total_scans"] >= 1, "reward": 5},
    "check_10": {"name": "🎯 10 проверок", "check": lambda u: u["total_scans"] >= 10, "reward": 15},
    "check_100": {"name": "💯 100 проверок", "check": lambda u: u["total_scans"] >= 100, "reward": 50},
    "streak_7": {"name": "🔥 Неделя подряд", "check": lambda u: u.get("streak", 0) >= 7, "reward": 25},
    "streak_30": {"name": "🔥🔥 Месяц подряд", "check": lambda u: u.get("streak", 0) >= 30, "reward": 100},
}


def update_streak(db_conn, user_id: int, is_scam: bool) -> dict:
    """
    Обновляет streak после проверки.
    Возвращает: {"streak": int, "bonus": int, "new_achievements": list}
    """
    cursor = db_conn.cursor()

    # Получаем текущий streak
    row = cursor.execute(
        "SELECT streak, last_check_date, total_scans FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if not row:
        return {"streak": 0, "bonus": 0, "new_achievements": []}

    old_streak = row["streak"]
    last_date_str = row["last_check_date"]
    total_scans = row["total_scans"]

    today = datetime.now().date()
    new_streak = 1
    bonus = 0

    if last_date_str:
        try:
            last_date = datetime.fromisoformat(last_date_str).date()
            diff = (today - last_date).days

            if diff == 1:
                # Продолжаем серию
                new_streak = old_streak + 1
                bonus = min(new_streak * 2, 20)  # Макс 20 бонусных кредитов
            elif diff == 0:
                # Уже проверял сегодня
                new_streak = old_streak
            # diff > 1 — серия сброшена
        except (ValueError, TypeError):
            pass

    # Обновляем streak и last_check_date
    cursor.execute(
        "UPDATE users SET streak = ?, last_check_date = ? WHERE user_id = ?",
        (new_streak, today.isoformat(), user_id),
    )
    db_conn.commit()

    # Проверяем achievements
    new_achievements = []
    user_data = {"total_scans": total_scans + 1, "streak": new_streak}

    for ach_id, ach in ACHIEVEMENTS.items():
        # Проверяем, не разблокировано ли уже
        exists = cursor.execute(
            "SELECT 1 FROM achievements WHERE user_id = ? AND ach_id = ?",
            (user_id, ach_id),
        ).fetchone()

        if not exists and ach["check"](user_data):
            cursor.execute(
                "INSERT INTO achievements (user_id, ach_id, unlocked_at) VALUES (?, ?, ?)",
                (user_id, ach_id, datetime.now().isoformat()),
            )
            new_achievements.append({"id": ach_id, "name": ach["name"], "reward": ach["reward"]})

    db_conn.commit()

    return {"streak": new_streak, "bonus": bonus, "new_achievements": new_achievements}
