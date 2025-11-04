from flask import Flask, request, jsonify
import sqlite3
import os

app = Flask(__name__)
API_SECRET = os.environ.get("API_SECRET", "1234")

# Crear base local
conn = sqlite3.connect("saldos.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    username TEXT PRIMARY KEY,
    saldo REAL DEFAULT 0
)
""")
conn.commit()

@app.route("/api/agregar_saldo", methods=["POST"])
def agregar_saldo():
    data = request.get_json()
    if not data or request.headers.get("X-SECRET-KEY") != API_SECRET:
        return jsonify({"error": "No autorizado"}), 401

    username = data.get("username")
    monto = float(data.get("monto", 0))
    if not username:
        return jsonify({"error": "Falta username"}), 400

    cur.execute("INSERT OR IGNORE INTO usuarios (username, saldo) VALUES (?, 0)", (username,))
    cur.execute("UPDATE usuarios SET saldo = saldo + ? WHERE username = ?", (monto, username))
    conn.commit()

    return jsonify({"success": True, "mensaje": f"Saldo de {username} actualizado +{monto}"}), 200

@app.route("/api/saldo", methods=["GET"])
def ver_saldo():
    username = request.args.get("username")
    if not username:
        return jsonify({"error": "Falta username"}), 400

    cur.execute("SELECT saldo FROM usuarios WHERE username = ?", (username,))
    result = cur.fetchone()
    saldo = result[0] if result else 0
    return jsonify({"username": username, "saldo": saldo})

@app.route("/")
def index():
    return "API de saldos activa ✅"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
