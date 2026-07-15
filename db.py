"""
db.py — SQLite база для sledopyt-crypto-v2
"""
import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sledopyt_crypto.db")

def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            balance INTEGER DEFAULT 0,
            total_scans INTEGER DEFAULT 0,
            total_spent REAL DEFAULT 0,
            created_at REAL,
            last_scan_at REAL,
            streak INTEGER DEFAULT 0,
            last_check_date TEXT,
            pro_until TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount_ton REAL,
            credits INTEGER,
            status TEXT DEFAULT 'pending',
            created_at REAL,
            paid_at REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            address TEXT,
            risk_level TEXT,
            scan_time_ms INTEGER,
            created_at REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            token_address TEXT,
            token_symbol TEXT DEFAULT '',
            chain TEXT,
            added_at REAL,
            UNIQUE(user_id, token_address)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            token_address TEXT,
            chain TEXT,
            rule_type TEXT,
            rule_value REAL,
            triggered INTEGER DEFAULT 0,
            created_at REAL,
            UNIQUE(user_id, token_address, rule_type)
        )
    """)
    # --- Production payment tables ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_payments (
            invoice_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            product TEXT NOT NULL,
            amount_ton REAL NOT NULL,
            credits_added INTEGER,
            status TEXT DEFAULT 'pending',
            payload TEXT,
            created_at REAL,
            paid_at REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS credit_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            tx_type TEXT NOT NULL,
            description TEXT,
            invoice_id TEXT,
            created_at REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            user_id INTEGER,
            ach_id TEXT,
            unlocked_at TEXT,
            PRIMARY KEY (user_id, ach_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS scam_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER,
            token_address TEXT,
            chain TEXT,
            evidence TEXT,
            status TEXT DEFAULT 'pending',
            points INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_reporter ON scam_reports(reporter_id)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS creators_cache (
            creator TEXT NOT NULL,
            chain TEXT NOT NULL,
            siblings_json TEXT,
            cached_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (creator, chain)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS investigation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            token_address TEXT,
            chain TEXT,
            verdict TEXT,
            scam_probability INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_investigation_addr ON investigation_results(token_address)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER UNIQUE,
            referral_code TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            bonus_given INTEGER DEFAULT 0,
            created_at REAL,
            converted_at REAL
        )
    """)
    # Indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cp_invoice ON crypto_payments(invoice_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cp_user ON crypto_payments(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cp_status ON crypto_payments(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ct_user ON credit_transactions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ref_code ON referrals(referral_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ref_referrer ON referrals(referrer_id)")
    conn.commit()
    conn.close()

def get_user(uid: int) -> dict:
    conn = _conn()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    conn2 = _conn()
    conn2.execute(
        "INSERT INTO users (user_id, balance, created_at) VALUES (?, 0, ?)",
        (uid, time.time()),
    )
    conn2.commit()
    conn2.close()
    return {"user_id": uid, "username": "", "balance": 0, "total_scans": 0, "total_spent": 0, "created_at": time.time(), "last_scan_at": 0}

def update_username(uid: int, username: str):
    conn = _conn()
    conn.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, uid))
    conn.commit()
    conn.close()

def add_balance(uid: int, credits: int):
    conn = _conn()
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (credits, uid))
    conn.commit()
    conn.close()

def get_balance(uid: int) -> int:
    return get_user(uid)["balance"]

def spend_balance(uid: int, credits: int) -> bool:
    bal = get_balance(uid)
    if bal < credits:
        return False
    conn = _conn()
    conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (credits, uid))
    conn.commit()
    conn.close()
    return True

def extend_pro(uid: int, days: int):
    """Продлевает Pro подписку на days дней."""
    conn = _conn()
    from datetime import datetime, timedelta
    now = datetime.now()
    
    # Получаем текущую дату окончания
    row = conn.execute("SELECT pro_until FROM users WHERE user_id = ?", (uid,)).fetchone()
    if row and row["pro_until"]:
        try:
            current_end = datetime.fromisoformat(row["pro_until"])
            if current_end > now:
                new_end = current_end + timedelta(days=days)
            else:
                new_end = now + timedelta(days=days)
        except (ValueError, TypeError):
            new_end = now + timedelta(days=days)
    else:
        new_end = now + timedelta(days=days)
    
    conn.execute("UPDATE users SET pro_until = ? WHERE user_id = ?", (new_end.isoformat(), uid))
    conn.commit()
    conn.close()
    return new_end


def is_pro(uid: int) -> bool:
    """Проверяет, активна ли Pro подписка."""
    conn = _conn()
    row = conn.execute("SELECT pro_until FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    
    if not row or not row["pro_until"]:
        return False
    
    try:
        from datetime import datetime
        return datetime.fromisoformat(row["pro_until"]) > datetime.now()
    except (ValueError, TypeError):
        return False


def record_scan(uid: int, address: str, risk_level: str, scan_time_ms: int):
    conn = _conn()
    conn.execute(
        "INSERT INTO scans (user_id, address, risk_level, scan_time_ms, created_at) VALUES (?, ?, ?, ?, ?)",
        (uid, address, risk_level, scan_time_ms, time.time()),
    )
    conn.execute(
        "UPDATE users SET total_scans = total_scans + 1, last_scan_at = ? WHERE user_id = ?",
        (time.time(), uid),
    )
    conn.commit()
    conn.close()

def save_invoice(user_id: int, amount_ton: float, credits: int) -> int:
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO invoices (user_id, amount_ton, credits, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (user_id, amount_ton, credits, time.time()),
    )
    inv_id = cur.lastrowid
    conn.commit()
    conn.close()
    return inv_id

def mark_invoice_paid(invoice_id: int):
    conn = _conn()
    conn.execute("UPDATE invoices SET status = 'paid', paid_at = ? WHERE invoice_id = ?", (time.time(), invoice_id))
    conn.commit()
    conn.close()

def get_pending_invoices(uid: int) -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM invoices WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC",
        (uid,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_bot_stats() -> dict:
    conn = _conn()
    users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    scans = conn.execute("SELECT COUNT(*) as c FROM scans").fetchone()["c"]
    revenue = conn.execute("SELECT COALESCE(SUM(amount_ton), 0) as r FROM invoices WHERE status = 'paid'").fetchone()["r"]
    conn.close()
    return {"total_users": users, "total_scans": scans, "total_revenue_ton": revenue}

# ---- Watchlist ----
def add_to_watchlist(user_id: int, address: str, symbol: str, chain: str) -> bool:
    conn = _conn()
    count = conn.execute("SELECT COUNT(*) as c FROM watchlist WHERE user_id=?", (user_id,)).fetchone()["c"]
    if count >= 5:
        conn.close()
        return False
    try:
        conn.execute(
            "INSERT OR REPLACE INTO watchlist (user_id, token_address, token_symbol, chain, added_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, address, symbol, chain, time.time()),
        )
        conn.commit()
    finally:
        conn.close()
    return True

def get_watchlist(user_id: int) -> list:
    conn = _conn()
    rows = conn.execute("SELECT * FROM watchlist WHERE user_id=? ORDER BY added_at DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def remove_from_watchlist(user_id: int, address: str) -> bool:
    conn = _conn()
    cur = conn.execute("DELETE FROM watchlist WHERE user_id=? AND token_address=?", (user_id, address))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

# ---- Alerts ----
def add_alert(user_id: int, address: str, chain: str, rule_type: str, rule_value: float) -> bool:
    conn = _conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO alerts (user_id, token_address, chain, rule_type, rule_value, triggered, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (user_id, address, chain, rule_type, rule_value, time.time()),
        )
        conn.commit()
    finally:
        conn.close()
    return True

def get_pending_alerts() -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT a.*, w.token_symbol FROM alerts a LEFT JOIN watchlist w ON a.user_id=w.user_id AND a.token_address=w.token_address WHERE a.triggered=0"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mark_alert_triggered(alert_id: int):
    conn = _conn()
    conn.execute("UPDATE alerts SET triggered=1 WHERE id=?", (alert_id,))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════
#  PRODUCTION PAYMENT SYSTEM (CryptoBot)
#  WAL + Idempotent + Atomic Transactions
# ═══════════════════════════════════════════════════════════════════

def save_crypto_payment(invoice_id: str, user_id: int, product: str,
                         amount_ton: float, credits_added: int, payload: str = "") -> bool:
    """Сохраняет pending платёж. Возвращает False если invoice уже существует."""
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO crypto_payments (invoice_id, user_id, product, amount_ton, credits_added, status, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (invoice_id, user_id, product, amount_ton, credits_added, payload, time.time()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Уже существует (idempotent)
    finally:
        conn.close()


def process_payment_idempotent(invoice_id: str) -> dict:
    """
    Идемпотентная обработка платежа.
    АТОМАРНАЯ транзакция: либо всё, либо ничего.
    Можно вызывать 100 раз — результат один.
    
    Возвращает: {success: bool, user_id: int, credits_added: int} или None
    """
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        
        # 1. Проверяем существование и статус
        row = conn.execute(
            "SELECT user_id, credits_added, status FROM crypto_payments WHERE invoice_id = ?",
            (invoice_id,)
        ).fetchone()
        
        if not row:
            conn.execute("ROLLBACK")
            return None  # Не наш инвойс
        
        user_id = row[0]
        credits = row[1]
        status = row[2]
        
        # 2. Если уже оплачен — просто выходим (idempotent)
        if status == "paid":
            conn.execute("ROLLBACK")
            return {"success": True, "user_id": user_id, "credits_added": credits, "already_processed": True}
        
        # 3. Обновляем статус платежа
        conn.execute(
            "UPDATE crypto_payments SET status = 'paid', paid_at = ? WHERE invoice_id = ? AND status = 'pending'",
            (time.time(), invoice_id)
        )
        
        # Проверяем что реально обновили (race condition protection)
        if conn.total_changes == 0:
            conn.execute("ROLLBACK")
            return {"success": True, "user_id": user_id, "credits_added": credits, "already_processed": True}
        
        # 4. Начисляем кредиты (атомарно)
        if credits and credits > 0:
            conn.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                (credits, user_id)
            )
            
            # Логируем транзакцию
            conn.execute(
                "INSERT INTO credit_transactions (user_id, amount, tx_type, description, invoice_id, created_at) "
                "VALUES (?, ?, 'purchase', 'Покупка кредитов', ?, ?)",
                (user_id, credits, invoice_id, time.time())
            )
        
        conn.execute("COMMIT")
        
        return {"success": True, "user_id": user_id, "credits_added": credits}
        
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"[DB ERROR] process_payment_idempotent failed: {e}")
        return None
    finally:
        conn.close()


def get_crypto_payments_pending() -> list:
    """Возвращает pending платежи за последний час (для polling fallback)."""
    conn = _conn()
    cutoff = time.time() - 3600  # 1 час назад
    rows = conn.execute(
        "SELECT * FROM crypto_payments WHERE status = 'pending' AND created_at > ?",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_credit_transaction(user_id: int, amount: int, tx_type: str, description: str, invoice_id: str = ""):
    """Логирует транзакцию кредитов."""
    conn = _conn()
    conn.execute(
        "INSERT INTO credit_transactions (user_id, amount, tx_type, description, invoice_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, amount, tx_type, description, invoice_id, time.time())
    )
    conn.commit()
    conn.close()


def get_credit_history(user_id: int, limit: int = 10) -> list:
    """Последние N транзакций кредитов пользователя."""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM credit_transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════
#  REFERRAL SYSTEM
# ═══════════════════════════════════════════════════════════════════

import secrets

def get_or_create_referral_code(user_id: int) -> str:
    """Получает или создаёт уникальный реферальный код."""
    conn = _conn()
    
    # Проверяем существующий код
    existing = conn.execute(
        "SELECT referral_code FROM referrals WHERE referrer_id = ? LIMIT 1",
        (user_id,)
    ).fetchone()
    
    if existing:
        conn.close()
        return existing[0]
    
    # Генерируем уникальный код (8 символов)
    for _ in range(10):  # max 10 попыток
        code = secrets.token_urlsafe(6)[:8]
        exists = conn.execute(
            "SELECT 1 FROM referrals WHERE referral_code = ?", (code,)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO referrals (referrer_id, referral_code, status, created_at) VALUES (?, ?, 'active', ?)",
                (user_id, code, time.time())
            )
            conn.commit()
            conn.close()
            return code
    
    conn.close()
    return ""  # Не удалось сгенерировать (крайне маловероятно)


def register_referral(new_user_id: int, referral_code: str) -> bool:
    """Регистрирует нового пользователя по реф-коду."""
    conn = _conn()
    
    # 1. Находим referrer
    referrer = conn.execute(
        "SELECT referrer_id FROM referrals WHERE referral_code = ? AND status = 'active' LIMIT 1",
        (referral_code,)
    ).fetchone()
    
    if not referrer:
        conn.close()
        return False
    
    referrer_id = referrer[0]
    
    # 2. Защита от самореферала
    if referrer_id == new_user_id:
        conn.close()
        return False
    
    # 3. Проверяем что юзер ещё не был рефералом
    existing = conn.execute(
        "SELECT 1 FROM referrals WHERE referred_id = ?", (new_user_id,)
    ).fetchone()
    
    if existing:
        conn.close()
        return False
    
    # 4. Записываем
    try:
        conn.execute(
            "INSERT INTO referrals (referrer_id, referred_id, referral_code, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (referrer_id, new_user_id, referral_code, time.time())
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def process_referral_bonus(user_id: int) -> bool:
    """
    Начисляет бонус при ПЕРВОЙ оплате реферала.
    IDEMPOTENT — бонус даётся один раз.
    """
    BONUS = 10  # Кредитов обоим
    
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        
        # 1. Проверяем: реферал?
        referral = conn.execute(
            "SELECT id, referrer_id, bonus_given FROM referrals WHERE referred_id = ? AND status = 'pending'",
            (user_id,)
        ).fetchone()
        
        if not referral:
            conn.execute("ROLLBACK")
            return False
        
        ref_id, referrer_id, bonus_given = referral
        
        # 2. Уже получали бонус?
        if bonus_given:
            conn.execute("ROLLBACK")
            return True
        
        # 3. Обновляем статус
        conn.execute(
            "UPDATE referrals SET status = 'converted', converted_at = ?, bonus_given = 1 WHERE id = ?",
            (time.time(), ref_id)
        )
        
        # 4. Начисляем обоим
        for uid in [referrer_id, user_id]:
            conn.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                (BONUS, uid)
            )
            desc = "Реферальный бонус" if uid == referrer_id else "Бонус за регистрацию"
            conn.execute(
                "INSERT INTO credit_transactions (user_id, amount, tx_type, description, created_at) "
                "VALUES (?, ?, 'bonus', ?, ?)",
                (uid, BONUS, desc, time.time())
            )
        
        conn.execute("COMMIT")
        return True
        
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"[DB ERROR] process_referral_bonus failed: {e}")
        return False
    finally:
        conn.close()


def get_referral_stats(user_id: int) -> dict:
    """Статистика рефералов пользователя."""
    conn = _conn()
    
    code = get_or_create_referral_code(user_id)
    
    total = conn.execute(
        "SELECT COUNT(*) as c FROM referrals WHERE referrer_id = ? AND referred_id IS NOT NULL",
        (user_id,)
    ).fetchone()["c"]
    
    converted = conn.execute(
        "SELECT COUNT(*) as c FROM referrals WHERE referrer_id = ? AND status = 'converted'",
        (user_id,)
    ).fetchone()["c"]
    
    earned = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM credit_transactions "
        "WHERE user_id = ? AND tx_type = 'bonus' AND description LIKE '%Реферальный%'",
        (user_id,)
    ).fetchone()["total"]
    
    conn.close()
    
    return {
        "code": code,
        "total_referred": total,
        "converted": converted,
        "pending": total - converted,
        "earned_credits": earned,
    }
