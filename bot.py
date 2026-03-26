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

# Criar tabela
cursor.execute("""
CREATE TABLE IF NOT EXISTS perfis (
    user_id BIGINT PRIMARY KEY,
    nome TEXT,
    classe TEXT,
    nivel INT,
    atk TEXT,
    defesa TEXT,
    crit TEXT,
    hp TEXT
)
""")
conn.commit()

# IDs
CHAT_ID = -1003792787717
TOPICO_PRESENCA = 16325


def extrair_perfil(texto):
    try:
        nome = re.search(r"\d+\s(.+)", texto).group(1)
        classe = re.search(r"Classe:\s(.+)", texto).group(1)
        nivel = int(re.search(r"Lv\s(\d+)", texto).group(1))
        atk = re.search(r"ATK\s(\d+)", texto).group(1)
        defesa = re.search(r"DEF\s([\d\.]+)", texto).group(1)
        crit = re.search(r"CRIT\s(\d+%)", texto).group(1)
        hp = re.search(r"HP:\s([\d/]+)", texto).group(1)

        return {
            "nome": nome,
            "classe": classe,
            "nivel": nivel,
            "atk": atk,
            "defesa": defesa,
            "crit": crit,
            "hp": hp
        }
    except:
        return None


async def salvar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if update.effective_chat.id != CHAT_ID:
        return

    # 🔥 CORREÇÃO AQUI (forma robusta de pegar o tópico)
    thread_id = getattr(update.message, "message_thread_id", None)

    if thread_id is None or int(thread_id) != int(TOPICO_PRESENCA):
        return

    texto = update.message.text

    if "Classe:" not in texto:
        return

    perfil = extrair_perfil(texto)
    if not perfil:
        return

    user_id = update.message.from_user.id

    cursor.execute("""
    INSERT INTO perfis (user_id, nome, classe, nivel, atk, defesa, crit, hp)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (user_id) DO UPDATE SET
    nome = EXCLUDED.nome,
    classe = EXCLUDED.classe,
    nivel = EXCLUDED.nivel,
    atk = EXCLUDED.atk,
    defesa = EXCLUDED.defesa,
    crit = EXCLUDED.crit,
    hp = EXCLUDED.hp
    """, (
        user_id,
        perfil["nome"],
        perfil["classe"],
        perfil["nivel"],
        perfil["atk"],
        perfil["defesa"],
        perfil["crit"],
        perfil["hp"]
    ))

    conn.commit()


async def ver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    cursor.execute("SELECT * FROM perfis WHERE user_id = %s", (user_id,))
    dados = cursor.fetchone()

    if not dados:
        await update.message.reply_text("❌ Nenhum perfil salvo.")
        return

    nome = dados[1]
    classe = dados[2]
    nivel = dados[3]
    atk = dados[4]
    defesa = dados[5]
    crit = dados[6]
    hp = dados[7]

    msg = (
        f"📜 {nome}\n"
        f"Classe: {classe}\n"
        f"Lv {nivel}\n\n"
        f"⚔️ ATK {atk}\n"
        f"🛡️ DEF {defesa}\n"
        f"🎯 CRIT {crit}\n"
        f"❤️ HP {hp}"
    )

    await update.message.reply_text(msg)


def main():
    print("Bot iniciando...")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("ver", ver))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), salvar))

    app.run_polling()


if __name__ == "__main__":
    main()

