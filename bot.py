import os
import re
import sqlite3
import unicodedata
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise Exception("TOKEN não encontrado")

# =========================
# BANCO
# =========================
conn = sqlite3.connect("legends.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
nome TEXT PRIMARY KEY,
xp INTEGER,
atk INTEGER,
def REAL,
crit INTEGER,
hp INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS presenca (
nome TEXT,
data TEXT,
PRIMARY KEY(nome, data)
)
""")

conn.commit()

# =========================
# LIMPAR NOME
# =========================
def limpar_nome(texto):
    linha = texto.split("\n")[0]

    linha = unicodedata.normalize("NFD", linha)
    linha = linha.encode("ascii","ignore").decode()

    linha = re.sub(r"\[.*?\]", "", linha)  # remove [LG]
    linha = re.sub(r"\d+", "", linha)      # remove números
    linha = re.sub(r"[^\w\s]", "", linha)  # remove símbolos

    return linha.strip().upper()

# =========================
# SALVAR PLAYER
# =========================
def salvar_player(nome, xp, atk, defesa, crit, hp):
    cursor.execute("""
    INSERT INTO players VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(nome) DO UPDATE SET
    xp=?, atk=?, def=?, crit=?, hp=?
    """, (nome, xp, atk, defesa, crit, hp,
          xp, atk, defesa, crit, hp))

    conn.commit()

# =========================
# PRESENÇA
# =========================
def registrar_presenca(nome):
    cursor.execute("""
    INSERT OR IGNORE INTO presenca VALUES (?, date('now'))
    """, (nome,))
    conn.commit()

# =========================
# HANDLER
# =========================
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message:
            return

        texto = update.message.text or update.message.caption

        if not texto or "XP:" not in texto:
            return

        # =========================
        # EXTRAÇÃO
        # =========================
        nome = limpar_nome(texto)

        xp = int(re.search(r"XP:\s*(\d+)", texto).group(1))
        atk = int(re.search(r"ATK\s*(\d+)", texto).group(1))
        defesa = float(re.search(r"DEF\s*([\d\.]+)", texto).group(1))
        crit = int(re.search(r"CRIT\s*(\d+)", texto).group(1))
        hp = int(re.search(r"HP:\s*\d+/(\d+)", texto).group(1))

        # =========================
        # SALVAR
        # =========================
        salvar_player(nome, xp, atk, defesa, crit, hp)
        registrar_presenca(nome)

        print(f"{nome} salvo + presença")

        await update.message.reply_text(
            f"📜 O Pilar grava a sua jornada, {nome}."
        )

    except Exception as e:
        print("ERRO:", e)

# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, responder))

    print("🚀 BOT INICIANDO...")

    app.run_polling(
        drop_pending_updates=True,
        close_loop=False,
        allowed_updates=["message"],
        poll_interval=2
    )

# =========================
# START
# =========================
if __name__ == "__main__":
    main()
