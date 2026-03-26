import os
import re
import sqlite3
import unicodedata
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise Exception("TOKEN não encontrado")

# 🔥 ID DO TÓPICO PRESENÇA
TOPICO_PRESENCA_ID = 16325

# =========================
# BANCO
# =========================
conn = sqlite3.connect("legends.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
nome TEXT PRIMARY KEY,
nivel INTEGER,
xp INTEGER,
atk INTEGER,
def REAL,
crit INTEGER,
hp INTEGER,
gold INTEGER,
tofu INTEGER
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

    linha = re.sub(r"\[.*?\]", "", linha)
    linha = re.sub(r"\d+", "", linha)
    linha = re.sub(r"[^\w\s]", "", linha)

    return linha.strip().upper()

# =========================
# EXTRAIR PERFIL
# =========================
def extrair(texto):
    try:
        return {
            "nome": limpar_nome(texto),
            "nivel": int(re.search(r"Lv\s*(\d+)", texto).group(1)),
            "xp": int(re.search(r"XP:\s*(\d+)", texto).group(1)),
            "atk": int(re.search(r"ATK\s*(\d+)", texto).group(1)),
            "def": float(re.search(r"DEF\s*([\d\.]+)", texto).group(1)),
            "crit": int(re.search(r"CRIT\s*(\d+)", texto).group(1)),
            "hp": int(re.search(r"HP:\s*\d+/(\d+)", texto).group(1)),
            "gold": int(re.search(r"Gold:\s*(\d+)", texto).group(1)),
            "tofu": int(re.search(r"Tofus:\s*(\d+)", texto).group(1))
        }
    except:
        return None

# =========================
# SALVAR PLAYER
# =========================
def salvar_player(d):
    cursor.execute("""
    INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(nome) DO UPDATE SET
    nivel=?, xp=?, atk=?, def=?, crit=?, hp=?, gold=?, tofu=?
    """, (
        d["nome"], d["nivel"], d["xp"], d["atk"], d["def"], d["crit"], d["hp"], d["gold"], d["tofu"],
        d["nivel"], d["xp"], d["atk"], d["def"], d["crit"], d["hp"], d["gold"], d["tofu"]
    ))
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

        # 🔥 FILTRO DE TÓPICO
        if update.message.message_thread_id != TOPICO_PRESENCA_ID:
            return

        texto = update.message.text or update.message.caption

        if not texto or "XP:" not in texto:
            return

        dados = extrair(texto)

        if not dados:
            return

        salvar_player(dados)
        registrar_presenca(dados["nome"])

        print(f"{dados['nome']} salvo")

        await update.message.reply_text(
            f"📜 O Pilar grava a sua jornada, {dados['nome']}."
        )

    except Exception as e:
        print("ERRO:", e)

# =========================
# /ver
# =========================
async def ver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT * FROM players")
    dados = cursor.fetchall()

    if not dados:
        await update.message.reply_text("❌ Nenhum jogador salvo.")
        return

    txt = "📊 Jogadores registrados:\n\n"

    for j in dados:
        txt += (
            f"👤 {j[0]}\n"
            f"📈 Lv {j[1]} | XP {j[2]}\n"
            f"⚔️ ATK {j[3]} | 🛡️ DEF {j[4]}\n"
            f"🎯 CRIT {j[5]} | ❤️ HP {j[6]}\n"
            f"💰 Gold {j[7]} | 🧀 Tofus {j[8]}\n\n"
        )

    await update.message.reply_text(txt)

# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, responder))
    app.add_handler(CommandHandler("ver", ver))

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
