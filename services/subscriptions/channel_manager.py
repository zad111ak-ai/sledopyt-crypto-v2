"""
Smart Channel Subscriptions — управление доступом в приватный канал.
"""
import os
import time
import logging
import asyncio
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ID приватного канала (задай в .env или замени)
CHANNEL_ID = int(os.environ.get("PRO_CHANNEL_ID", "0"))


async def grant_access(bot, user_id: int, days: int) -> bool:
    """
    Выдаёт одноразовую ссылку для вступления в канал.
    """
    if not CHANNEL_ID:
        log.warning("PRO_CHANNEL_ID not set, skipping grant_access")
        return False

    expires = datetime.now() + timedelta(days=days)

    try:
        link = await bot.create_chat_invite_link(
            CHANNEL_ID,
            member_limit=1,
            expire_date=int(expires.timestamp()),
        )
        log.info(f"Access granted: user={user_id} days={days} link={link.invite_link}")
        return True
    except Exception as e:
        log.error(f"grant_access failed: user={user_id} error={e}")
        return False


async def revoke_expired(bot):
    """
    Проверяет подписки и банит просроченных.
    Вызывать по cron каждые 6 часов.
    """
    if not CHANNEL_ID:
        return

    # Получаем просроченные подписки из БД
    # TODO: implement get_expired_subscriptions in db.py
    log.info("revoke_expired: checking subscriptions")


async def check_access(user_id: int) -> bool:
    """
    Проверяет, есть ли у пользователя активная подписка.
    """
    # TODO: implement subscription check in db.py
    return False
