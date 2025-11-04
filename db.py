import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("SERVIS_DB_PATH", os.path.join(os.path.dirname(__file__), "servis.db"))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # Users table: stores hashed passwords and balance
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0,
            chat_id TEXT,
            created_at TEXT NOT NULL
        );
        """
    )

    # Transactions table: register all balance operations and proofs
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            amount REAL NOT NULL,
            method TEXT NOT NULL,
            status TEXT NOT NULL,
            proof_file_id TEXT,
            admin TEXT,
            created_at TEXT NOT NULL
        );
        """
    )

    # Telegram links table: map chat_id to telegram username and bound user
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_links (
            chat_id TEXT PRIMARY KEY,
            telegram_username TEXT,
            bound_username TEXT
        );
        """
    )

    # Pending intent (last method/amount for a chat)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_intents (
            chat_id TEXT PRIMARY KEY,
            method TEXT,
            amount REAL,
            created_at TEXT
        );
        """
    )

    conn.commit()
    conn.close()


def upsert_telegram_link(chat_id: str, telegram_username: str | None, bound_username: str | None = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO telegram_links (chat_id, telegram_username, bound_username) VALUES (?,?,?)\n"
        "ON CONFLICT(chat_id) DO UPDATE SET telegram_username=excluded.telegram_username, bound_username=COALESCE(telegram_links.bound_username, excluded.bound_username);",
        (str(chat_id), telegram_username, bound_username),
    )
    conn.commit()
    conn.close()


def set_pending_intent(chat_id: str, method: str, amount: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO pending_intents (chat_id, method, amount, created_at) VALUES (?,?,?,?)\n"
        "ON CONFLICT(chat_id) DO UPDATE SET method=excluded.method, amount=excluded.amount, created_at=excluded.created_at;",
        (str(chat_id), method, float(amount), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_pending_intent(chat_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT method, amount FROM pending_intents WHERE chat_id=?", (str(chat_id),))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"method": row["method"], "amount": row["amount"]}


def add_transaction(username: str, amount: float, method: str, status: str, proof_file_id: str | None = None, admin: str | None = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions (username, amount, method, status, proof_file_id, admin, created_at) VALUES (?,?,?,?,?,?,?)",
        (
            username,
            float(amount),
            method,
            status,
            proof_file_id,
            admin,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def credit_balance(username: str, amount: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = COALESCE(balance,0) + ? WHERE username = ?", (float(amount), username))
    conn.commit()
    conn.close()