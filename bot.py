import os
import re
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL não encontrado")

# ID do tópico presença diária
TOPICO_PRESENCA = 16325

# conexão banco
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS perfis (
    user_id BIGINT PRIMARY KEY,
    nome TEXT,
    level INT,
    xp BIGINT,
    atk INT,
    defesa FLOAT,
    crit INT,
    hp TEXT,
    gold INT,
    tofu INT
)
""")
conn.commit()


def extrair_dados(texto):
    try:
        nome = texto.split("\n")[0]

        level = re.search(r"Lv\s+(\d+)", texto)
        xp = re.search(r"XP:\s+([\d]+)", texto)
        atk = re.search(r"ATK\s+(\d+)", texto)
        defesa = re.search(r"DEF\s+([\d\.]+)", texto)
        crit = re.search(r"CRIT\s+(\d+)", texto)
        hp = re.search(r"HP:\s+([\d/]+)", texto)
        gold = re.search(r"Gold:\s+(\d+)", texto)
        tofu = re.search(r"Tofus:\s+(\d+)", texto)

        return {
            "nome": nome,
            "level": int(level.group(1)) if level else 0,
            "xp": int(xp.group(1)) if xp else 0,
            "atk": int(atk.group(1)) if atk else 0,
            "defesa": float(defesa.group(1)) if defesa else 0,
            "crit": int(crit.group(1)) if crit else 0,
            "hp": hp.group(1) if hp else "0/0",
            "gold": int(gold.group(1)) if gold else 0,
            "tofu": int(tofu.group(1)) if tofu else 0
        }

    except:
        return None


async def salvar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg:
        return

    # ✅ CORREÇÃO APLICADA AQUI
    if not msg.message_thread_id or int(msg.message_thread_id) != int(TOPICO_PRESENCA):
        return

    texto = msg.text or msg.caption

    if not texto:
        return

    if "ATK" not in texto or "HP:" not in texto:
        return

    dados = extrair_dados(texto)

    if not dados:
        return

    user_id = msg.from_user.id

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

    print(f"SALVO: {dados['nome']} ({user_id})")


async def ver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT * FROM perfis WHERE user_id = %s",
