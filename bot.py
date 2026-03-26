import re
import sqlite3
import unicodedata
import os
from datetime import time
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters

# =========================
# TOKEN
# =========================
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN não encontrado no Railway")

print("👑 BOT INICIANDO...")

# =========================
# CONFIG
# =========================
LIDER_ID = -1003806440152
PRESENCA_ID = "16325"

# =========================
# BANCO
# =========================
conn = sqlite3.connect("legends.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
nome TEXT PRIMARY KEY,
xp INTEGER
)
""")

conn.commit()

# =========================
# FUNÇÕES
# =========================
def normalizar_nome(texto):
    linha = texto.split("\n")[0]
    linha = unicodedata.normalize("NFD", linha).encode("ascii","ignore").decode()
    linha = re.sub(r"[^\w\s]", "", linha)
    return linha.strip().upper()

def extrair(texto):
    try:
        nome = normalizar_nome(texto)
        xp = int(re.search(r"XP:\s*(\d+)", texto).group(1))
        return nome, xp
    except:
        return None

def salvar(nome, xp):
    cursor.execute("""
    INSERT INTO players VALUES (?,?)
    ON CONFLICT(nome) DO UPDATE SET xp=?
    """, (nome, xp, xp))
    conn.commit()

# =========================
# COMANDO XP
# =========================
async def xp(update, context):
    cursor.execute("SELECT nome, xp FROM players ORDER BY xp DESC LIMIT 10")
    dados = cursor.fetchall()

    if not dados:
        await update.message.reply_text("Sem dados ainda.")
        return

    txt = "🏆 Ranking XP\n\n"
    for i,(n,v) in enumerate(dados,1):
        txt += f"{i}. {n} — {v}\n"

    await update.message.reply_text(txt)

# =========================
# LEITOR
# =========================
async def ler(update, context):
    try:
        if not update.message:
            return

        msg = update.message
        texto = msg.text or msg.caption

        if not texto:
            return

        if "XP:" in texto:
            dados = extrair(texto)
            if dados:
                nome, xp_valor = dados
                salvar(nome, xp_valor)
                await msg.reply_text(f"📜 {nome} registrado!")
    except Exception as e:
        print("ERRO:", e)

# =========================
# START
# =========================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("xp", xp))
    app.add_handler(MessageHandler(filters.ALL, ler))

    print("👑 BOT ONLINE")

    app.run_polling()

if __name__ == "__main__":
    main()
