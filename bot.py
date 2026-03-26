import os
import re
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL não encontrado")

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS perfis (user_id BIGINT PRIMARY KEY, nome TEXT, level INT, xp TEXT, atk TEXT, defesa TEXT, crit TEXT, hp TEXT, gold TEXT, tofu TEXT)")
conn.commit()

TOPICO_PRESENCA = 16325


def extrair_dados(texto):
    try:
        linhas = texto.split("\n")

        nome = linhas[0]

        level = re.search(r"Lv (\d+)", texto)
        xp = re.search(r"XP: ([\d]+)", texto)
        atk = re.search(r"ATK (\d+)", texto)
        defesa = re.search(r"DEF ([\d\.]+)", texto)
        crit = re.search(r"CRIT (\d+%)", texto)
        hp = re.search(r"HP: (\d+/\d+)", texto)
        gold = re.search(r"Gold: (\d+)", texto)
        tofu = re.search(r"Tofus: (\d+)", texto)

        return {
            "nome": nome,
            "level": int(level.group(1)) if level else 0,
            "xp": xp.group(1) if xp else "0",
            "atk": atk.group(1) if atk else "0",
            "defesa": defesa.group(1) if defesa else "0",
            "crit": crit.group(1) if crit else "0%",
            "hp": hp.group(1) if hp else "0/0",
            "gold": gold.group(1) if gold else "0",
            "tofu": tofu.group(1) if tofu else "0"
        }
    except:
        return None


async def salvar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.message_thread_id != TOPICO_PRESENCA:
        return

    dados = extrair_dados(update.message.text)
    if not dados:
        return

    user_id = update.message.from_user.id

    cursor.execute("""
        INSERT INTO perfis (user_id, nome, level, xp, atk, defesa, crit, hp, gold, tofu)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (user_id) DO UPDATE SET
        nome=EXCLUDED.nome,
        level=EXCLUDED.level,
        xp=EXCLUDED.xp,
        atk=EXCLUDED.atk,
        defesa=EXCLUDED.defesa,
        crit=EXCLUDED.crit,
        hp=EXCLUDED.hp,
        gold=EXCLUDED.gold,
        tofu=EXCLUDED.tofu
    """, (
        user_id,
        dados["nome"],
        dados["level"],
        dados["xp"],
        dados["atk"],
        dados["defesa"],
        dados["crit"],
        dados["hp"],
        dados["gold"],
        dados["tofu"]
    ))

    conn.commit()

    await update.message.reply_text("📜 O Pilar grava a sua jornada.")


async def ver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    cursor.execute("SELECT * FROM perfis WHERE user_id = %s", (user_id,))
    j = cursor.fetchone()

    if not j:
        await update.message.reply_text("❌ Nenhum perfil salvo.")
        return

    mensagem = f"""📈
Lv {j[2]} | XP {j[3]}
ATK {j[4]}
DEF {j[5]}
CRIT {j[6]}
HP {j[7]}
GOLD {j[8]}
TOFU {j[9]}
"""

    await update.message.reply_text(mensagem)


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, salvar))
app.add_handler(CommandHandler("ver", ver))

print("🚀 BOT FINAL ATIVO (POSTGRES + FILTROS)")

app.run_polling()
