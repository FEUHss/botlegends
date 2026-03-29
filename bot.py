import os
import re
import psycopg2
from datetime import datetime

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# ================= CONFIG =================

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

CLAN_CHAT_ID = -1003792787717
TOPICO_PRESENCA = 16325

LIDER_CHAT_ID = -1003806440152
TOPICO_LISTA = 116

# ================= BANCO =================

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS presencas (
    nome TEXT,
    data DATE,
    PRIMARY KEY (nome, data)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS membros (
    nome TEXT PRIMARY KEY
)
""")

# ================= FUNÇÕES =================

def extrair_nome(texto):
    """
    Extrai nome do perfil Teletofus
    Funciona com:
    - [LG] Nome
    - Nome simples
    """
    match = re.search(r"\d+\s+(.+?)\nClasse:", texto)
    if match:
        nome = match.group(1).strip()
        nome = re.sub(r"\[.*?\]", "", nome).strip()  # remove [LG]
        return nome.upper()
    return None


def eh_perfil_teletofus(msg):
    if not msg.forward_from:
        return False

    if msg.forward_from.username != "Teletofus":
        return False

    texto = msg.text or msg.caption or ""

    if "Classe:" in texto and "Lv" in texto and "HP:" in texto:
        return True

    return False


def salvar_presenca(nome):
    hoje = datetime.now().date()

    try:
        cur.execute(
            "INSERT INTO presencas (nome, data) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (nome, hoje)
        )

        cur.execute(
            "INSERT INTO membros (nome) VALUES (%s) ON CONFLICT DO NOTHING",
            (nome,)
        )

        return True

    except Exception as e:
        print("Erro ao salvar:", e)
        conn.rollback()
        return False


async def atualizar_lista(context):
    hoje = datetime.now().date()

    cur.execute("SELECT nome FROM membros ORDER BY nome")
    todos = [r[0] for r in cur.fetchall()]

    cur.execute("SELECT nome FROM presencas WHERE data = %s", (hoje,))
    presentes = [r[0] for r in cur.fetchall()]

    faltantes = [n for n in todos if n not in presentes]

    texto = "📋 PRESENÇA DIÁRIA\n\n"

    texto += "✅ PRESENTES:\n"
    for nome in presentes:
        texto += f"✔ {nome}\n"

    texto += "\n❌ FALTANTES:\n"
    for nome in faltantes:
        texto += f"✖ {nome}\n"

    await context.bot.send_message(
        chat_id=LIDER_CHAT_ID,
        message_thread_id=TOPICO_LISTA,
        text=texto
    )


# ================= HANDLER =================

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg:
        return

    # Só lê da aba correta
    if msg.chat_id != CLAN_CHAT_ID:
        return

    if msg.message_thread_id != TOPICO_PRESENCA:
        return

    # Só aceita perfil válido
    if not eh_perfil_teletofus(msg):
        return

    texto = msg.text or msg.caption or ""
    nome = extrair_nome(texto)

    if not nome:
        return

    if salvar_presenca(nome):
        await context.bot.send_message(
            chat_id=LIDER_CHAT_ID,
            message_thread_id=TOPICO_LISTA,
            text=f"✅ Presença: {nome}"
        )

        await atualizar_lista(context)


# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, detectar))

    print("🚀 Bot rodando...")

    app.run_polling()


if __name__ == "__main__":
    main()
