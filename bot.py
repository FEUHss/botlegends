import os
import re
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise Exception("BOT_TOKEN não encontrado")

if not DATABASE_URL:
    raise Exception("DATABASE_URL não encontrado")

# 🔥 CONFIG DO GRUPO
GRUPO_ID = -1003792787717
TOPICO_PRESENCA_ID = 16325

# =========================
# CONEXÃO POSTGRES
# =========================
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS perfis (
    user_id BIGINT PRIMARY KEY,
    level INT,
    xp BIGINT,
    atk INT,
    defesa FLOAT,
    crit INT,
    hp INT,
    gold INT,
    tofu INT
)
""")
conn.commit()

# =========================
# SALVAR PERFIL
# =========================
async def salvar_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message:
            return

        # 🔒 FILTRO DE GRUPO
        if update.effective_chat.id != GRUPO_ID:
            return

        # 🔒 FILTRO DE TÓPICO (PRESENÇA)
        if update.message.message_thread_id != TOPICO_PRESENCA_ID:
            return

        text = update.message.text

        if not text:
            return

        # valida perfil
        if "XP:" not in text or "ATK" not in text:
            return

        user_id = update.effective_user.id

        level = int(re.search(r"Lv\s*(\d+)", text).group(1))
        xp = int(re.search(r"XP:\s*(\d+)", text).group(1))
        atk = int(re.search(r"ATK\s*(\d+)", text).group(1))
        defesa = float(re.search(r"DEF\s*([\d\.]+)", text).group(1))
        crit = int(re.search(r"CRIT\s*(\d+)%", text).group(1))
        hp = int(re.search(r"HP:\s*(\d+)", text).group(1))
        gold = int(re.search(r"Gold:\s*(\d+)", text).group(1))
        tofu = int(re.search(r"Tofus:\s*(\d+)", text).group(1))

        cursor.execute("""
        INSERT INTO perfis (user_id, level, xp, atk, defesa, crit, hp, gold, tofu)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (user_id) DO UPDATE SET
            level=EXCLUDED.level,
            xp=EXCLUDED.xp,
            atk=EXCLUDED.atk,
            defesa=EXCLUDED.defesa,
            crit=EXCLUDED.crit,
            hp=EXCLUDED.hp,
            gold=EXCLUDED.gold,
            tofu=EXCLUDED.tofu
        """, (user_id, level, xp, atk, defesa, crit, hp, gold, tofu))

        conn.commit()

        print(f"SALVO: {user_id}")

        await update.message.reply_text("📜 O Pilar grava a sua jornada.")

    except Exception as e:
        print("ERRO AO SALVAR:", e)

# =========================
# /ver
# =========================
async def ver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT * FROM perfis WHERE user_id = %s", (user_id,))
    data = cursor.fetchone()

    if not data:
        await update.message.reply_text("❌ Nenhum perfil salvo.")
        return

    _, level, xp, atk, defesa, crit, hp, gold, tofu = data

    msg = (
        f"📊 SEU PERFIL\n\n"
        f"📈
