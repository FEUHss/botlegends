import os
import re
import random
import psycopg2
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

GRUPO_PRESENCA = -1003792787717
TOPICO_PRESENCA = 16325

GRUPO_LIDER = -1003806440152
TOPICO_LISTA = 116

# ========================
# CONEXÃO SEGURA
# ========================

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# ========================
# DATA
# ========================

def hoje():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d")

# ========================
# LORE
# ========================

def lore(nome):
    frases = [
        f"📜 O Pilar registra: {nome}.",
        f"✨ Presença absorvida: {nome}.",
        f"🗿 {nome} foi reconhecido pelo Pilar.",
        f"🔥 Energia dourada envolve {nome}.",
        f"🧠 Conhecimento registrado: {nome}.",
        f"⚡ Presença confirmada: {nome}"
    ]
    return random.choice(frases)

# ========================
# EXTRAIR NOME
# ========================

def extrair_nome(texto):
    match = re.search(r"\d+\s+(.+)", texto)
    if match:
        nome = match.group(1)
        nome = re.split(r"\n|Classe:", nome)[0]
        return nome.strip()
    return None

# ========================
# GERAR LISTA
# ========================

def gerar_lista():
    try:
        conn = get_conn()
        cursor = conn.cursor()

        data = hoje()

        cursor.execute("SELECT nome FROM jogadores")
        todos = [x[0] for x in cursor.fetchall()]

        cursor.execute("SELECT nome FROM presencas WHERE data=%s", (data,))
        presentes = [x[0] for x in cursor.fetchall()]

        faltantes = [n for n in todos if n not in presentes]

        conn.close()

        texto = "📋 PRESENÇA DIÁRIA\n\n"

        texto += "✅ PRESENTES:\n"
        texto += "\n".join([f"✔️ {p}" for p in presentes]) if presentes else "Nenhum"

        texto += "\n\n❌ FALTANTES:\n"
        texto += "\n".join([f"❌ {f}" for f in faltantes]) if faltantes else "Nenhum"

        return texto

    except Exception as e:
        print("ERRO LISTA:", e)
        return "Erro ao gerar lista."

# ========================
# ATUALIZAR LISTA
# ========================

async def atualizar_lista(bot):
    try:
        conn = get_conn()
        cursor = conn.cursor()

        texto = gerar_lista()

        cursor.execute("SELECT valor FROM controle WHERE chave='msg_lista'")
        res = cursor.fetchone()

        if res:
            try:
                await bot.edit_message_text(
                    chat_id=GRUPO_LIDER,
                    message_id=int(res[0]),
                    text=texto
                )
                conn.close()
                return
            except:
                pass

        msg = await bot.send_message(
            chat_id=GRUPO_LIDER,
            message_thread_id=TOPICO_LISTA,
            text=texto
        )

        cursor.execute("""
        INSERT INTO controle (chave, valor)
        VALUES ('msg_lista', %s)
        ON CONFLICT (chave) DO UPDATE SET valor=%s
        """, (str(msg.message_id), str(msg.message_id)))

        conn.commit()
        conn.close()

    except Exception as e:
        print("ERRO UPDATE LISTA:", e)

# ========================
# COMANDO /lista
# ========================

async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_chat.id != GRUPO_LIDER:
            return

        texto = gerar_lista()

        await context.bot.send_message(
            chat_id=GRUPO_LIDER,
            message_thread_id=TOPICO_LISTA,
            text=texto
        )

    except Exception as e:
        print("ERRO /lista:", e)

# ========================
# DETECTAR
# ========================

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message:
            return

        if update.effective_chat.id != GRUPO_PRESENCA:
            return

        if update.message.message_thread_id:
            if update.message.message_thread_id != TOPICO_PRESENCA:
                return

        texto = update.message.text or ""
        nome = extrair_nome(texto)

        if not nome:
            return

        print("✅ Detectado:", nome)

        conn = get_conn()
        cursor = conn.cursor()

        data = hoje()

        cursor.execute(
            "INSERT INTO jogadores VALUES (%s) ON CONFLICT DO NOTHING",
            (nome,)
        )

        cursor.execute(
            "SELECT 1 FROM presencas WHERE nome=%s AND data=%s",
            (nome, data)
        )

        if cursor.fetchone():
            conn.close()
            return

        cursor.execute(
            "INSERT INTO presencas VALUES (%s, %s)",
            (nome, data)
        )

        conn.commit()
        conn.close()

        await update.message.reply_text(lore(nome))

        await context.bot.send_message(
            chat_id=GRUPO_LIDER,
            message_thread_id=TOPICO_LISTA,
            text=f"✅ Presença: {nome}"
        )

        await atualizar_lista(context.bot)

    except Exception as e:
        print("ERRO DETECTAR:", e)

# ========================
# MAIN
# ========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT, detectar))
    app.add_handler(CommandHandler("lista", lista))

    print("🚀 Pilar ativo (modo estável)...")
    app.run_polling()

if __name__ == "__main__":
    main()
