import os
import re
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ==============================
# CONFIG
# ==============================

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

GRUPO_ID = -1003792787717
TOPICO_PERMITIDO = 16325

# ==============================
# CONEXÃO DB
# ==============================

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# ==============================
# FUNÇÕES DE EXTRAÇÃO
# ==============================

def extrair_nome(texto):
    try:
        # remove emojis do começo
        texto = re.sub(r"^[^\w\d]+", "", texto)

        match = re.search(r"\d+\s+(.+)", texto)
        if match:
            nome = match.group(1).strip()
            return nome

    except Exception as e:
        print("Erro ao extrair nome:", e)

    return None


def extrair_classe(texto):
    match = re.search(r"Classe:\s*(\w+)", texto)
    return match.group(1) if match else None


def extrair_nivel(texto):
    match = re.search(r"Lv\s*(\d+)", texto)
    return int(match.group(1)) if match else None


def extrair_stats(texto):
    try:
        atk = re.search(r"ATK\s*(\d+)", texto)
        defesa = re.search(r"DEF\s*([\d\.]+)", texto)
        crit = re.search(r"CRIT\s*(\d+)", texto)
        hp = re.search(r"HP:\s*(\d+)", texto)

        return (
            int(atk.group(1)) if atk else None,
            float(defesa.group(1)) if defesa else None,
            int(crit.group(1)) if crit else None,
            int(hp.group(1)) if hp else None,
        )
    except:
        return (None, None, None, None)

# ==============================
# SALVAR NO BANCO
# ==============================

def salvar_perfil(nome, classe, nivel, atk, defesa, crit, hp):
    try:
        cursor.execute("""
            INSERT INTO perfis (nome, classe, nivel, atk, defesa, crit, hp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (nome) DO UPDATE SET
                classe = EXCLUDED.classe,
                nivel = EXCLUDED.nivel,
                atk = EXCLUDED.atk,
                defesa = EXCLUDED.defesa,
                crit = EXCLUDED.crit,
                hp = EXCLUDED.hp;
        """, (nome, classe, nivel, atk, defesa, crit, hp))

        conn.commit()
        print(f"SALVO/ATUALIZADO: {nome}")

    except Exception as e:
        print("ERRO AO SALVAR:", e)

# ==============================
# HANDLER
# ==============================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message

        if not message or not message.text:
            return

        chat_id = message.chat.id
        topic_id = message.message_thread_id

        if chat_id != GRUPO_ID:
            return

        if topic_id != TOPICO_PERMITIDO:
            return

        texto = message.text

        print("\n---- NOVA MENSAGEM ----")
        print("CHAT ID:", chat_id)
        print("TOPIC ID:", topic_id)
        print("TEXTO:", texto)

        nome = extrair_nome(texto)
        classe = extrair_classe(texto)
        nivel = extrair_nivel(texto)
        atk, defesa, crit, hp = extrair_stats(texto)

        print("NOME EXTRAIDO:", nome)
        print("CLASSE:", classe)
        print("NIVEL:", nivel)
        print("STATS:", atk, defesa, crit, hp)

        if not nome:
            print("❌ Nome não encontrado, ignorando...")
            return

        salvar_perfil(nome, classe, nivel, atk, defesa, crit, hp)

    except Exception as e:
        print("ERRO NO HANDLER:", e)

# ==============================
# MAIN
# ==============================

def main():
    print("Bot rodando...")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    app.run_polling()

# ==============================

if __name__ == "__main__":
    main()
