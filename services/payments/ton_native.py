"""
TON Native Payments — замена CryptoBot.
Оплата через Telegram TON Space (LabeledPrice).
"""
import time
import logging
from decimal import Decimal

from aiogram.types import LabeledPrice

log = logging.getLogger(__name__)

TON_NANO = Decimal("1000000000")  # 1 TON = 10^9 nanoTON

PRODUCTS = {
    "credits_10": {"ton": "1.0", "credits": 10, "desc": "10 кредитов"},
    "credits_50": {"ton": "4.5", "credits": 50, "desc": "50 кредитов"},
    "credits_200": {"ton": "15.0", "credits": 200, "desc": "200 кредитов"},
    "pro_week": {"ton": "50.0", "credits": None, "days": 7, "desc": "Pro на неделю"},
    "pro_month": {"ton": "180.0", "credits": None, "days": 30, "desc": "Pro на месяц"},
}


async def create_ton_invoice(bot, user_id: int, product_key: str) -> str:
    """
    Создаёт инвойс для оплаты через TON Space.
    Возвращает payload для идемпотентности.
    """
    product = PRODUCTS.get(product_key)
    if not product:
        raise ValueError(f"Unknown product: {product_key}")

    amount_nano = int(Decimal(product["ton"]) * TON_NANO)
    payload = f"{user_id}:{product_key}:{int(time.time())}"

    await bot.send_invoice(
        chat_id=user_id,
        title=product["desc"],
        description=f"Оплата через TON Space",
        payload=payload,
        provider_token="",  # Пусто = нативный TON
        currency="TON",
        prices=[LabeledPrice(label=product["desc"], amount=amount_nano)],
    )

    log.info(f"Invoice created: user={user_id} product={product_key}")
    return payload


def parse_payload(payload: str) -> dict | None:
    """
    Парсит payload: user_id:product_key:timestamp
    """
    try:
        parts = payload.split(":")
        if len(parts) != 3:
            return None
        return {
            "user_id": int(parts[0]),
            "product_key": parts[1],
            "timestamp": int(parts[2]),
        }
    except (ValueError, IndexError):
        return None


def get_product(product_key: str) -> dict | None:
    return PRODUCTS.get(product_key)
