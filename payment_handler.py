"""
Payment Handler — центральный модуль для платежей.

Связывает: CryptoBot API + SQLite + handlers.
Все операции IDEMPOTENT и ATOMIC.
"""
import json
import logging
from typing import Dict, Optional

from cryptobot import CryptoBotAPI, PRICES
import db

logger = logging.getLogger(__name__)

BOT_USERNAME = "Cryptop_q_bot"


class PaymentHandler:
    def __init__(self, cryptobot_token: str):
        self.api = CryptoBotAPI(cryptobot_token)

    async def create_payment(self, user_id: int, product_key: str) -> Dict:
        """
        Создаёт инвойс. Возвращает:
        {invoice_id, pay_url, amount, asset, description}
        """
        product = PRICES[product_key]

        # Гарантируем что пользователь существует
        db.get_user(user_id)

        # Создаём инвойс в CryptoBot
        invoice = await self.api.create_invoice(user_id, product_key, BOT_USERNAME)

        # Сохраняем в БД (idempotent — если invoice_id уже есть, вернёт False)
        db.save_crypto_payment(
            invoice_id=invoice["invoice_id"],
            user_id=user_id,
            product=product_key,
            amount_ton=invoice["amount"],
            credits_added=product["credits"],
            payload=json.dumps({"product": product_key}),
        )

        logger.info(
            "invoice_created user=%d product=%s invoice=%s amount=%.2f",
            user_id, product_key, invoice["invoice_id"], invoice["amount"],
        )

        return {
            **invoice,
            "description": product["description"],
        }

    def process_webhook(self, body: str, signature: str) -> Optional[Dict]:
        """
        Обрабатывает webhook от CryptoBot.
        Возвращает: {success, user_id, credits_added} или None
        """
        if not self.api.verify_signature(body, signature):
            logger.warning("Invalid webhook signature!")
            return None

        update = json.loads(body)
        update_type = update.get("update_type")

        if update_type != "invoice_paid":
            logger.info("webhook_ignored type=%s", update_type)
            return {"success": True, "ignored": True}

        invoice_data = update["payload"]
        invoice_id = str(invoice_data.get("invoice_id", ""))

        # Идемпотентная обработка
        result = db.process_payment_idempotent(invoice_id)

        if result and not result.get("already_processed"):
            logger.info(
                "payment_completed user=%d invoice=%s credits=%d",
                result["user_id"], invoice_id, result["credits_added"],
            )

            # Реферальный бонус (если первая оплата)
            self._try_referral_bonus(result["user_id"])

        return result

    async def poll_pending(self) -> int:
        """
        Fallback: проверяет pending платежи через polling.
        Возвращает количество обработанных.
        """
        pending = db.get_crypto_payments_pending()
        processed = 0

        for p in pending:
            invoice = await self.api.get_invoice(p["invoice_id"])
            if invoice and invoice.get("status") == "paid":
                result = db.process_payment_idempotent(p["invoice_id"])
                if result and not result.get("already_processed"):
                    processed += 1
                    self._try_referral_bonus(result["user_id"])

        return processed

    def _try_referral_bonus(self, user_id: int):
        """Пытается начислить реферальный бонус (если первая оплата)."""
        try:
            db.process_referral_bonus(user_id)
        except Exception as e:
            logger.error("referral_bonus_error user=%d: %s", user_id, e)

    def get_balance(self, user_id: int) -> int:
        """Возвращает баланс кредитов."""
        return db.get_balance(user_id)

    def spend(self, user_id: int, amount: int, description: str) -> bool:
        """Списывает кредиты."""
        ok = db.spend_balance(user_id, amount)
        if ok:
            db.log_credit_transaction(user_id, -amount, "spend", description)
        return ok

    def get_history(self, user_id: int, limit: int = 10):
        """История транзакций."""
        return db.get_credit_history(user_id, limit)
