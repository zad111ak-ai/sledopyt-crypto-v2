"""
Webhook endpoint для CryptoBot.
Запускается как отдельный сервис или внутри бота.
"""
import json
import logging
import os
from aiohttp import web

from payment_handler import PaymentHandler

logger = logging.getLogger(__name__)

CRYPTOBOT_TOKEN = os.environ.get("CRYPTOBOT_TOKEN", "")
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8080"))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # Для верификации

payment = PaymentHandler(CRYPTOBOT_TOKEN)


async def webhook_handler(request: web.Request) -> web.Response:
    """Обрабатывает webhook от CryptoBot."""
    try:
        body = await request.text()
        signature = request.headers.get("Crypto-Pay-API-Signature", "")
        
        result = payment.process_webhook(body, signature)
        
        if result is None:
            return web.json_response({"error": "invalid signature"}, status=403)
        
        if result.get("ignored"):
            return web.json_response({"ok": True})
        
        if result.get("success"):
            logger.info(
                "webhook_ok invoice=%s user=%s credits=%s",
                result.get("invoice_id", "?"),
                result.get("user_id", "?"),
                result.get("credits_added", "?"),
            )
            return web.json_response({"ok": True})
        
        return web.json_response({"error": "processing failed"}, status=500)
        
    except Exception as e:
        logger.error("webhook_error: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def health_handler(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({"status": "ok"})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/webhook/cryptobot", webhook_handler)
    app.router.add_get("/health", health_handler)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting webhook server on port %d", WEBHOOK_PORT)
    web.run_app(create_app(), port=WEBHOOK_PORT)
