"""
CryptoBot API клиент для приёма платежей.
Docs: https://help.send.t.me/collections/13845938
"""
import aiohttp
import hashlib
import hmac
import json
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Продукты и цены
PRICES = {
    "credits_10":  {"amount": 1.0,   "credits": 10,  "description": "10 кредитов"},
    "credits_50":  {"amount": 4.5,   "credits": 50,  "description": "50 кредитов (-10%)"},
    "credits_200": {"amount": 15.0,  "credits": 200, "description": "200 кредитов (-25%)"},
}


class CryptoBotAPI:
    """CryptoBot API для инвойсов."""

    BASE_URL = "https://pay.crypt.bot/api"

    def __init__(self, api_token: str):
        self.api_token = api_token
        self.headers = {"Crypto-Pay-API-Token": api_token}

    async def create_invoice(
        self,
        user_id: int,
        product_key: str,
        bot_username: str,
    ) -> Dict:
        """Создаёт инвойс. Возвращает {invoice_id, pay_url, amount, asset}."""
        product = PRICES[product_key]
        payload_json = json.dumps({
            "user_id": user_id,
            "product": product_key,
            "credits": product["credits"],
        })

        body = {
            "asset": "TON",
            "amount": str(product["amount"]),
            "description": product["description"],
            "paid_btn_name": "openBot",
            "paid_btn_url": f"https://t.me/{bot_username}",
            "payload": payload_json,
            "expires_in": 3600,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.BASE_URL}/createInvoice",
                headers=self.headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status != 200 or not data.get("ok"):
                    logger.error("CryptoBot createInvoice failed: %s", data)
                    raise RuntimeError(f"CryptoBot error: {data}")

                inv = data["result"]
                return {
                    "invoice_id": str(inv["invoice_id"]),
                    "pay_url": inv["pay_url"],
                    "amount": float(inv["amount"]),
                    "asset": inv["asset"],
                }

    async def get_invoice(self, invoice_id: str) -> Optional[Dict]:
        """Проверяет статус инвойса."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BASE_URL}/getInvoices",
                headers=self.headers,
                params={"invoice_ids": invoice_id},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                items = data.get("result", {}).get("items", [])
                return items[0] if items else None

    def verify_signature(self, body: str, signature: str) -> bool:
        """Проверяет HMAC-SHA256 подпись webhook."""
        secret = hashlib.sha256(self.api_token.encode()).digest()
        computed = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, signature)
