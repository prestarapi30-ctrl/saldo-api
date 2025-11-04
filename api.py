import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import requests

from db import get_conn, init_db, add_transaction, credit_balance


APP = Flask(__name__)

# Config
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-dev-secret")
JWT_EXP_HOURS = int(os.environ.get("JWT_EXP_HOURS", "12"))
API_SECRET = os.environ.get("API_SECRET", "change-me-api-secret")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")  # e.g., PAGASEGUROBOT
STAFF_CHAT_ID = os.environ.get("STAFF_CHAT_ID", "")  # optional, for notifications
API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:5001")


def make_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXP_HOURS),
        "iss": "servis-api",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"require": ["exp", "iat", "sub"]})
        return payload.get("sub")
    except Exception:
        return None


@APP.after_request
def add_cors_headers(resp):
    # Simple CORS for local dev
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-SECRET-KEY"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@APP.route("/api/registro", methods=["POST", "OPTIONS"])
def registro():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or not password:
        return jsonify({"success": False, "error": "username y password son requeridos"}), 400
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
            (username, generate_password_hash(password), datetime.utcnow().isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "error": "usuario ya existe"}), 409
    conn.close()
    token = make_token(username)
    return jsonify({"success": True, "token": token})


@APP.route("/api/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or not password:
        return jsonify({"success": False, "error": "username y password son requeridos"}), 400
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"success": False, "error": "credenciales inválidas"}), 401
    token = make_token(username)
    return jsonify({"success": True, "token": token})


def auth_username_from_header() -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1]
    return decode_token(token)


@APP.route("/api/saldo", methods=["GET", "OPTIONS"])
def saldo():
    if request.method == "OPTIONS":
        return ("", 204)
    username = auth_username_from_header()
    if not username:
        return jsonify({"error": "no autorizado"}), 401
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    balance = float(row["balance"]) if row else 0.0
    return jsonify({"username": username, "saldo": balance})


@APP.route("/api/agregar_saldo", methods=["POST", "OPTIONS"])
def agregar_saldo():
    if request.method == "OPTIONS":
        return ("", 204)
    secret = request.headers.get("X-SECRET-KEY", "")
    if secret != API_SECRET:
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    metodo = (data.get("metodo") or "").strip().upper()
    monto = float(data.get("monto") or 0)
    if not username or monto <= 0 or not metodo:
        return jsonify({"error": "datos inválidos"}), 400
    # Verify user exists
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "usuario no encontrado"}), 404

    credit_balance(username, monto)
    add_transaction(username, monto, metodo, status="credited", admin="api")
    return jsonify({"ok": True, "username": username, "nuevo_saldo": monto})


@APP.route("/api/solicitar_recarga", methods=["POST", "OPTIONS"])
def solicitar_recarga():
    if request.method == "OPTIONS":
        return ("", 204)
    username = auth_username_from_header()
    if not username:
        return jsonify({"error": "no autorizado"}), 401
    data = request.get_json(force=True) or {}
    metodo = (data.get("metodo") or "").strip().upper()
    monto = float(data.get("monto") or 0)
    if not metodo or monto <= 0:
        return jsonify({"error": "datos inválidos"}), 400

    # Register request transaction
    add_transaction(username, monto, metodo, status="requested")

    deep_link = None
    messaged = False
    # Try to notify the user via Telegram if chat_id is known
    if BOT_TOKEN:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT chat_id FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        conn.close()
        if row and row["chat_id"]:
            chat_id = row["chat_id"]
            text = (
                f"Solicitud de recarga: {metodo} {monto}.\n"
                "Envía una foto del comprobante aquí y espera confirmación del admin."
            )
            try:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                    timeout=10,
                )
                messaged = True
            except Exception:
                messaged = False

    if BOT_USERNAME:
        deep_link = f"https://t.me/{BOT_USERNAME}?start={metodo}_{monto}"

    return jsonify({"ok": True, "metodo": metodo, "monto": monto, "deep_link": deep_link, "messaged": messaged})


if __name__ == "__main__":
    init_db()
    APP.run(host="0.0.0.0", port=5001)
