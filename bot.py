import re
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters, CommandHandler
import os

# ================= CONFIG =================

TOKEN = os.getenv("BOT_TOKEN")

GROUP_ID = -1003792787717
TOPIC_ID = 16325  # presença diária

# ================= BANCO =================

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()

# ================= EXTRAÇÃO =================

def extrair_dados(texto):
    try:
        # Nome (remove emojis e nível do começo)
        nome_linha = texto.split("\n")[0]
        nome = re.sub(r"[^\w\s,\[\]]", "", nome_linha)
        nome = re.sub(r"\d+", "", nome).strip()

        # Classe + nível
        classe_match = re.search(r"Classe:\s*(\w+)\s*Lv\s*(\d+)", texto)
        if classe_match:
            classe = classe_match.group(1)
            nivel = int(classe_match.group(2))
        else:
            classe = None
            nivel = None

        # ATK
        atk_match = re.search(r"ATK\s*(\d+)", texto)
        atk = int(atk_match.group(1)) if atk_match else None

        # DEF
        def_match = re.search(r"DEF\s*([\d\.]+)", texto)
        defesa = float(def_match.group(1)) if def_match else None

        # CRIT
        crit_match = re.search(r"CRIT\s*(\d+)%", texto)
        crit = int(crit_match.group(1)) if crit_match else None

        # HP
        hp_match = re.search(r"HP:\s*(\d+)/", texto)
        hp = int(hp_match.group(1)) if hp_match else None

        return nome, classe, nivel, atk, defesa, crit, hp

    except Exception as e:
        print("Erro ao extrair:", e)
        return None

# ================= SALVAR =================

async def salvar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.chat.id != GROUP_ID:
            return

        if update.message.message_thread_id != TOPIC_ID:
            return

        texto = update.message.text

        if not texto:
            return

        if "Classe:" not in texto:
            return

        dados = extrair_dados(texto)

        if not dados:
            return

        nome, classe, nivel, atk, defesa, crit, hp = dados

        print("SALVANDO:", dados)

        cursor.execute("""
            INSERT INTO perfis (nome, classe, nivel, atk, defesa, crit, hp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (nome) DO UPDATE SET
            classe = EXCLUDED.classe,
            nivel = EXCLUDED.nivel,
            atk = EXCLUDED.atk,
            defesa = EXCLUDED.defesa,
            crit = EXCLUDED.crit,
            hp = EXCLUDED.hp
        """, (nome, classe, nivel, atk, defesa, crit, hp))

        conn.commit()

    except Exception as e:
        print("ERRO AO SALVAR:", e)

# ================= COMANDO /VER =================

async def ver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT nome, classe, nivel FROM perfis ORDER BY nivel DESC")
    dados = cursor.fetchall()

    if not dados:
        await update.message.reply_text("Nenhum perfil salvo.")
        return

    msg = "📜 Perfis salvos:\n\n"

    for nome, classe, nivel in dados:
        msg += f"{nome} - {classe} Lv {nivel}\n"

    await update.message.reply_text(msg)

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, salvar))
    app.add_handler(CommandHandler("ver", ver))

    print("Bot rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()

