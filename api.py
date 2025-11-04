from flask import Flask, request, jsonify
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------------
# Configuración del Flask
# -------------------------
app = Flask(__name__)
API_SECRET = os.environ.get("API_SECRET", "MiClaveSuperSegura2025")

# -------------------------
# Conexión a la base de datos
# -------------------------
conn = sqlite3.connect("saldos.db", check_same_thread=False)
cur = conn.cursor()

# Tabla de usuarios
cur.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    username TEXT PRIMARY KEY,
    password TEXT,
    saldo REAL DEFAULT 0
)
""")
conn.commit()

# Tabla de transacciones del bot (opcional)
cur.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    metodo TEXT,
    monto REAL,
    estado TEXT,
    foto_id TEXT,
    created_at TEXT
)
""")
conn.commit()

# -------------------------
# Rutas de usuario
# -------------------------

# Registro de usuario
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
    cur.execute("INSERT INTO usuarios (username, password) VALUES (?, ?)", (username, hashed_password))
    conn.commit()
    return jsonify({"success": True, "mensaje": "Usuario registrado correctamente"}), 201

# Login de usuario
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
    return jsonify({"success": True, "mensaje": "Login correcto", "username": username}), 200

# Consultar saldo
@app.route("/api/saldo", methods=["GET"])
def ver_saldo():
    username = request.args.get("username")
    if not username:
        return jsonify({"error": "Falta username"}), 400
    cur.execute("SELECT saldo FROM usuarios WHERE username = ?", (username,))
    result = cur.fetchone()
    saldo = result[0] if result else 0
    return jsonify({"username": username, "saldo": saldo})

# -------------------------
# Rutas de recarga (bot)
# -------------------------
@app.route("/api/agregar_saldo", methods=["POST"])
def agregar_saldo():
    data = request.get_json()
    if not data or request.headers.get("X-SECRET-KEY") != API_SECRET:
        return jsonify({"error": "No autorizado"}), 401
    username = data.get("username")
    monto = float(data.get("monto", 0))
    metodo = data.get("metodo", "YAPE")
    # Verificar que el usuario existe
    cur.execute("SELECT * FROM usuarios WHERE username = ?", (username,))
    if not cur.fetchone():
        return jsonify({"error": "Usuario no existe"}), 404
    # Actualizar saldo
    cur.execute("UPDATE usuarios SET saldo = saldo + ? WHERE username = ?", (monto, username))
    conn.commit()
    # Registrar transacción (opcional)
    cur.execute("INSERT INTO transactions (username, metodo, monto, estado, foto_id, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
                (username, metodo, monto, "aprobado", "",))
    conn.commit()
    return jsonify({"success": True, "mensaje": f"Saldo de {username} actualizado +{monto}"}), 200

# Ruta principal
@app.route("/")
def index():
    return "API de saldos activa ✅"

# -------------------------
# Arrancar el servidor
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
