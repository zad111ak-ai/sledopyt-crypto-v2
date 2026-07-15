"""
База данных для кредитов и платежей.
SQLite — хранит балансы, платежи, рефералов.
"""
import sqlite3
import logging
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

DB_PATH = "payments.db"


def get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str = DB_PATH):
    """Создаёт таблицы. Вызывать при старте бота."""
    conn = get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id    INTEGER PRIMARY KEY,
            username   TEXT,
            credits    INTEGER DEFAULT 3,
            referred_by INTEGER,
            referral_credits_earned INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS payments (
            invoice_id   TEXT PRIMARY KEY,
            user_id      INTEGER NOT NULL,
            product      TEXT NOT NULL,
            amount_ton   REAL NOT NULL,
            credits_added INTEGER,
            status       TEXT DEFAULT 'pending',
            payload      TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at      TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS credit_transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            amount      INTEGER NOT NULL,
            tx_type     TEXT NOT NULL,
            description TEXT,
            invoice_id  TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_pay_invoice ON payments(invoice_id);
        CREATE INDEX IF NOT EXISTS idx_pay_user    ON payments(user_id);
        CREATE INDEX IF NOT EXISTS idx_tx_user     ON credit_transactions(user_id);
    """)
    conn.close()
    logger.info("Payments DB initialized: %s", db_path)


def ensure_user(user_id: int, username: str = "", db_path: str = DB_PATH):
    """Гарантирует наличие пользователя с 3 кредитами."""
    conn = get_conn(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, credits) VALUES (?, ?, 3)",
        (user_id, username or ""),
    )
    conn.commit()
    conn.close()


def get_balance(user_id: int, db_path: str = DB_PATH) -> Dict:
    """Возвращает {credits: int}."""
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT credits FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        ensure_user(user_id, db_path=db_path)
        return {"credits": 3}
    return {"credits": row["credits"]}


def spend_credits(user_id: int, amount: int, description: str,
                  db_path: str = DB_PATH) -> bool:
    """Списывает кредиты. False если недостаточно."""
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT credits FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not row or row["credits"] < amount:
        conn.close()
        return False

    conn.execute(
        "UPDATE users SET credits = credits - ? WHERE user_id = ?",
        (amount, user_id),
    )
    conn.execute(
        "INSERT INTO credit_transactions (user_id, amount, tx_type, description) "
        "VALUES (?, ?, 'spend', ?)",
        (user_id, -amount, description),
    )
    conn.commit()
    conn.close()
    return True


def add_credits(user_id: int, amount: int, description: str,
                invoice_id: str = "", db_path: str = DB_PATH):
    """Начисляет кредиты."""
    conn = get_conn(db_path)
    conn.execute(
        "UPDATE users SET credits = credits + ? WHERE user_id = ?",
        (amount, user_id),
    )
    conn.execute(
        "INSERT INTO credit_transactions (user_id, amount, tx_type, description, invoice_id) "
        "VALUES (?, ?, 'purchase', ?, ?)",
        (user_id, amount, description, invoice_id),
    )
    conn.commit()
    conn.close()


def save_pending_payment(invoice_id: str, user_id: int, product: str,
                         amount: float, credits: int, payload: str,
                         db_path: str = DB_PATH):
    """Сохраняет pending платёж."""
    conn = get_conn(db_path)
    conn.execute(
        "INSERT INTO payments (invoice_id, user_id, product, amount_ton, credits_added, status, payload) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (invoice_id, user_id, product, amount, credits, payload),
    )
    conn.commit()
    conn.close()


def mark_paid(invoice_id: str, db_path: str = DB_PATH) -> Optional[Dict]:
    """Помечает платёж как оплаченный. Возвращает данные или None."""
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT * FROM payments WHERE invoice_id = ?", (invoice_id,)
    ).fetchone()
    if not row or row["status"] != "pending":
        conn.close()
        return None

    conn.execute(
        "UPDATE payments SET status = 'paid', paid_at = CURRENT_TIMESTAMP "
        "WHERE invoice_id = ?",
        (invoice_id,),
    )
    conn.commit()
    conn.close()
    return dict(row)


def get_pending_payments(db_path: str = DB_PATH) -> List[Dict]:
    """Возвращает pending платежи за последний час."""
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM payments WHERE status = 'pending' "
        "AND created_at > datetime('now', '-1 hour')"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tx_history(user_id: int, limit: int = 10,
                   db_path: str = DB_PATH) -> List[Dict]:
    """Последние N транзакций кредитов."""
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM credit_transactions WHERE user_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
