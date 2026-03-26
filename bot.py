import os
import re
import unicodedata
import psycopg2
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise Exception("TOKEN não encontrado")

if not DATABASE_URL:
    raise Exception("DATABASE_URL não encontrado")

TOPICO_PRESENCA_ID = 16325

# =========================
# CONEXÃO POSTGRES
# =========================
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# =========================
# CRIAR TABELAS
# =========================
cursor.execute("CREATE TABLE IF NOT EXISTS players (nome TEXT PRIMARY KEY, nivel INT, xp INT, atk INT, def REAL, crit INT, hp INT, gold INT, tofu INT)")
cursor.execute("CREATE TABLE IF NOT EXISTS presenca (nome TEXT, data DATE, PRIMARY KEY(nome, data))")
conn.commit()

# =========================
# LIMPAR NOME
# =========================
def limpar_nome(texto):
    linha = texto.split("\n")[0]
    linha = unicodedata.normalize("NFD", linha).encode("ascii","ignore").decode()
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
    cursor.execute(
        "INSERT INTO players VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (nome) DO UPDATE SET nivel=%s, xp=%s, atk=%s, def=%s, crit=%s, hp=%s, gold=%s, tofu=%s",
        (d["nome"], d["nivel"], d["xp"], d["atk"], d["def"], d["crit"], d["hp"], d["gold"], d["tofu"],
         d["nivel"], d["xp"], d["atk"], d["def"], d["crit"], d["hp"], d["gold"], d["tofu"])
    )
    conn.commit()

# =========================
# PRESENÇA
# =========================
def registrar_presenca(nome):
    cursor.execute(
        "INSERT INTO presenca VALUES (%s, CURRENT_DATE) ON CONFLICT DO NOTHING",
        (nome,)
    )
    conn.commit()

# =========================
# HANDLER PERFIL
# =========================
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

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

    print(f"{dados['nome']} salvo no POSTGRES")

    await update.message.reply_text(
        f"📜 O Pilar grava a sua jornada, {dados['nome']}."
    )

# =========================
# /ver
# =========================
async def ver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT * FROM players ORDER BY nivel DESC")
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

    app.add_handler(CommandHandler("ver", ver))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    print("🚀 BOT COM POSTGRES ATIVO")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
