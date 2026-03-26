import re
import sqlite3
import unicodedata
import os
from telegram.ext import Application, MessageHandler, CommandHandler, filters

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN não encontrado")

print("👑 BOT INICIANDO...")

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
# NOME LIMPO
# =========================
def nome(txt):
    linha = txt.split("\n")[0]

    linha = unicodedata.normalize("NFD", linha)
    linha = linha.encode("ascii","ignore").decode()

    linha = re.sub(r"\[.*?\]", "", linha)
    linha = re.sub(r"\d+", "", linha)
    linha = re.sub(r"[^a-zA-Z\s]", "", linha)

    return linha.strip().upper()

# =========================
# EXTRAIR XP
# =========================
def extrair(txt):
    try:
        n = nome(txt)
        xp = int(re.search(r"XP:\s*(\d+)", txt).group(1))
        return n, xp
    except:
        return None

# =========================
# SALVAR
# =========================
def salvar(n, xp):
    cursor.execute("""
    INSERT INTO players (nome,xp)
    VALUES (?,?)
    ON CONFLICT(nome) DO UPDATE SET xp=excluded.xp
    """, (n, xp))

    conn.commit()

# =========================
# COMANDOS
# =========================
async def rank(update, context):
    cursor.execute("SELECT nome,xp FROM players ORDER BY xp DESC LIMIT 10")

    txt = "🏆 Ranking XP\n\n"

    for i,(n,v) in enumerate(cursor.fetchall(),1):
        txt += f"{i}. {n} — {v}\n"

    await update.message.reply_text(txt or "Sem dados")

# =========================
# LEITOR
# =========================
async def ler(update, context):
    try:
        if not update.message:
            return

        txt = update.message.text or update.message.caption
        if not txt:
            return

        if "XP:" in txt:
            dados = extrair(txt)

            if dados:
                n, xp = dados
                salvar(n, xp)

                await update.message.reply_text(f"📜 {n} salvo")

    except Exception as e:
        print("ERRO:", e)

# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("rank", rank))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ler))

    print("👑 BOT ONLINE")

    app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    main()
