from flask import Flask, request, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import os
from datetime import datetime, timedelta

# -------------------------
# Configuración
# -------------------------
app = Flask(__name__)
API_SECRET = os.environ.get("API_SECRET", "MiClaveSuperSegura2025")
JWT_SECRET = os.environ.get("JWT_SECRET", "ClaveSuperSecretaJWT")
JWT_ALGORITHM = "HS256"
JWT_EXP_DELTA_SECONDS = 3600 * 24  # Token válido por 24h

# -------------------------
# Base de datos
# -------------------------
conn = sqlite3.connect("saldos.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    username TEXT PRIMARY KEY,
    password TEXT,
    saldo REAL DEFAULT 0,
    created_at TEXT
)
""")
conn.commit()

# -------------------------
# Registro de usuario
# -------------------------
@app.route("/api/registro", methods=["POST"])
def registro():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Falta username o password"}), 400

    cur.execute("SELECT * FROM usuarios WHERE username = ?", (username,))
    if cur.fetchone():
        return jsonify({"error": "Usuario ya existe"}), 400

    hashed_password = generate_password_hash(password)
    cur.execute(
        "INSERT INTO usuarios (username, password, created_at) VALUES (?, ?, ?)",
        (username, hashed_password, datetime.now().isoformat())
    )
    conn.commit()

    return jsonify({"success": True, "mensaje": "Usuario registrado correctamente"}), 201

# -------------------------
# Login de usuario
# -------------------------
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    cur.execute("SELECT password FROM usuarios WHERE username = ?", (username,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Usuario no existe"}), 404

    hashed_password = row[0]
    if not check_password_hash(hashed_password, password):
        return jsonify({"error": "Contraseña incorrecta"}), 401

    # Crear token JWT
    payload = {
        "username": username,
        "exp": datetime.utcnow() + timedelta(seconds=JWT_EXP_DELTA_SECONDS)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return jsonify({"success": True, "token": token, "username": username}), 200

# -------------------------
# Endpoint protegido ejemplo
# -------------------------
@app.route("/api/saldo", methods=["GET"])
def ver_saldo():
    token = request.headers.get("Authorization")
    if not token:
        return jsonify({"error": "No autorizado"}), 401

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload["username"]
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expirado"}), 401
    except Exception:
        return jsonify({"error": "Token inválido"}), 401

    cur.execute("SELECT saldo FROM usuarios WHERE username = ?", (username,))
    result = cur.fetchone()
    saldo = result[0] if result else 0

    return jsonify({"username": username, "saldo": saldo})

