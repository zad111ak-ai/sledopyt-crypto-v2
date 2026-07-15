"""
Алерты в Telegram при критических ошибках.
"""
import aiohttp
import time
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class AlertManager:
    SPAM_PROTECTION = 300

    def __init__(self, admin_id: int, bot_token: str):
        self.admin_id = admin_id
        self.bot_token = bot_token
        self.recent: Dict[str, float] = {}

    async def send(self, level: str, event: str, details: Optional[Dict] = None, force: bool = False):
        details = details or {}
        key = f"{level}:{event}"
        now = time.time()
        if not force and key in self.recent and now - self.recent[key] < self.SPAM_PROTECTION:
            return
        self.recent[key] = now

        emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(level, "🔔")
        msg = f"{emoji} *{level.upper()}: {event}*\n\n"
        for k, v in details.items():
            msg += f"*{k}:* {str(v)[:200]}\n"

        try:
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json={"chat_id": self.admin_id, "text": msg, "parse_mode": "Markdown"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception as e:
            logger.error("alert_send_failed: %s", e)

    async def critical(self, event, details=None):
        await self.send("critical", event, details)

    async def warning(self, event, details=None):
        await self.send("warning", event, details)

    async def info(self, event, details=None):
        await self.send("info", event, details)
