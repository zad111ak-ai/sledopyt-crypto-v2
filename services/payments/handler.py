"""
Обработчик платежей: инвойсы, webhook, начисление, списание.
"""
import json
import logging
from typing import Dict, Optional

from .cryptobot import CryptoBotAPI, PRICES
from .database import (
    ensure_user, get_balance, spend_credits, add_credits,
    save_pending_payment, mark_paid, get_pending_payments,
    get_tx_history,
)

logger = logging.getLogger(__name__)


class PaymentHandler:
    def __init__(self, cryptobot_token: str, db_path: str = "payments.db"):
        self.api = CryptoBotAPI(cryptobot_token)
        self.db_path = db_path
        # Инициализация БД при старте
        from .database import init_db
        init_db(db_path)

    # ── Создание платежа ──────────────────────────────────────────

    async def create_payment(self, user_id: int, product_key: str,
                             bot_username: str) -> Dict:
        """Создаёт инвойс. Возвращает {invoice_id, pay_url, amount, asset, description}."""
        product = PRICES[product_key]
        ensure_user(user_id, db_path=self.db_path)

        invoice = await self.api.create_invoice(user_id, product_key, bot_username)

        save_pending_payment(
            invoice_id=invoice["invoice_id"],
            user_id=user_id,
            product=product_key,
            amount=invoice["amount"],
            credits=product["credits"],
            payload=json.dumps({"product": product_key}),
            db_path=self.db_path,
        )

        logger.info("Invoice created: %s for user %d (%s)", invoice["invoice_id"], user_id, product_key)

        return {
            **invoice,
            "description": product["description"],
        }

    # ── Обработка webhook / polling ───────────────────────────────

    async def process_webhook(self, body: str, signature: str) -> bool:
        """Обрабатывает webhook от CryptoBot."""
        if not self.api.verify_signature(body, signature):
            logger.warning("Invalid webhook signature!")
            return False

        update = json.loads(body)
        if update.get("update_type") != "invoice_paid":
            return True

        invoice_data = update["payload"]
        return self._process_invoice(invoice_data)

    async def process_pending_polling(self):
        """Fallback: проверяет pending платежи через polling."""
        pending = get_pending_payments(self.db_path)
        for p in pending:
            invoice = await self.api.get_invoice(p["invoice_id"])
            if invoice and invoice.get("status") == "paid":
                self._process_invoice(invoice)

    def _process_invoice(self, invoice_data: Dict) -> bool:
        """Начисляет кредиты по оплаченному инвойсу."""
        invoice_id = str(invoice_data.get("invoice_id", ""))
        record = mark_paid(invoice_id, self.db_path)
        if not record:
            return False

        credits = record.get("credits_added", 0) or 0
        if credits > 0:
            add_credits(
                user_id=record["user_id"],
                amount=credits,
                description=record.get("product", ""),
                invoice_id=invoice_id,
                db_path=self.db_path,
            )
            logger.info("Credited %d to user %d (invoice %s)", credits, record["user_id"], invoice_id)

        return True

    # ── Баланс и списание ─────────────────────────────────────────

    def check_balance(self, user_id: int) -> Dict:
        ensure_user(user_id, db_path=self.db_path)
        return get_balance(user_id, self.db_path)

    def spend(self, user_id: int, amount: int, description: str) -> bool:
        return spend_credits(user_id, amount, description, self.db_path)

    def history(self, user_id: int, limit: int = 10):
        return get_tx_history(user_id, limit, self.db_path)
