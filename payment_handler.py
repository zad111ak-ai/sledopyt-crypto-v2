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
        """Создаёт инвойс. Возвращает {invoice_id, pay_url, amount, ...}"""
        product = PRICES[product_key]
        db.get_user(user_id)
        invoice = await self.api.create_invoice(user_id, product_key, BOT_USERNAME)
        db.save_crypto_payment(
            invoice_id=invoice["invoice_id"],
            user_id=user_id,
            product=product_key,
            amount_ton=invoice["amount"],
            credits_added=product["credits"],
            payload=json.dumps({"product": product_key}),
        )
        logger.info("invoice_created user=%d product=%s invoice=%s",
                     user_id, product_key, invoice["invoice_id"])
        return {**invoice, "description": product["description"]}

    def process_webhook(self, body: str, signature: str) -> Optional[Dict]:
        """Обрабатывает webhook от CryptoBot с защитой от None."""
        if not self.api.verify_signature(body, signature):
            logger.warning("invalid_webhook_signature")
            return {"success": False, "error": "invalid signature"}

        try:
            update = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error("webhook_json_error: %s", e)
            return {"success": False, "error": "invalid json"}

        if update.get("update_type") != "invoice_paid":
            return {"success": True, "ignored": True}

        invoice_data = update.get("payload", {})
        invoice_id = str(invoice_data.get("invoice_id", ""))
        if not invoice_id:
            return {"success": False, "error": "no invoice_id"}

        result = db.process_payment_idempotent(invoice_id)

        # ЗАЩИТА ОТ None
        if not result:
            logger.warning("payment_not_found invoice=%s", invoice_id)
            return {"success": False, "error": "invoice not found"}

        if result.get("already_processed"):
            return {"success": True, "already_processed": True}

        logger.info("payment_completed user=%d invoice=%s credits=%d",
                     result["user_id"], invoice_id, result["credits_added"])

        try:
            self._try_referral_bonus(result["user_id"])
        except Exception as e:
            logger.error("referral_bonus_failed: %s", e)

        return {"success": True, **result}

    async def poll_pending(self) -> int:
        """Fallback: проверяет pending платежи через polling."""
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
        try:
            db.process_referral_bonus(user_id)
        except Exception as e:
            logger.error("referral_bonus_error user=%d: %s", user_id, e)

    def get_balance(self, user_id: int) -> int:
        return db.get_balance(user_id)

    def spend(self, user_id: int, amount: int, description: str) -> bool:
        ok = db.spend_balance(user_id, amount)
        if ok:
            db.log_credit_transaction(user_id, -amount, "spend", description)
        return ok

    def get_history(self, user_id: int, limit: int = 10):
        return db.get_credit_history(user_id, limit)
