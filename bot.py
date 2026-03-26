import re
import sqlite3
import unicodedata
import os
from telegram.ext import Application, MessageHandler, filters

TOKEN = os.getenv("TOKEN")

TOPICO_PRESENCA_ID = 16325

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

cursor.execute("""
CREATE TABLE IF NOT EXISTS presenca (
nome TEXT,
data TEXT,
status TEXT
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
    linha = re.sub(r"\s+", " ", linha)

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
# PRESENÇA
# =========================
def registrar_presenca(n):
    cursor.execute("""
    SELECT 1 FROM presenca 
    WHERE nome=? AND data=date('now')
    """, (n,))

    if cursor.fetchone():
        return

    cursor.execute("""
    INSERT INTO presenca VALUES (?,date('now'),'P')
    """, (n,))

    conn.commit()

# =========================
# LEITOR (FILTRADO)
# =========================
async def ler(update, context):
    try:
        if not update.message:
            return

        # 🔥 FILTRO DO TÓPICO
        if update.message.message_thread_id != TOPICO_PRESENCA_ID:
            return

        txt = update.message.text or update.message.caption
        if not txt:
            return

        if "XP:" in txt:
            dados = extrair(txt)

            if dados:
                n, xp = dados

                salvar(n, xp)
                registrar_presenca(n)

                print(f"✔ {n} salvo (presença registrada)")

    except Exception as e:
        print("ERRO:", e)

# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT, ler))

    print("👑 BOT ONLINE")

    app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    main()
