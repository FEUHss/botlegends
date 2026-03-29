import os
import re
import random
import psycopg2
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

print("🔥 INICIANDO BOT...")

# ================== CONFIG ==================

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

GRUPO_ORIGEM = -1003792787717
TOPICO_PRESENCA = 16325

GRUPO_DESTINO = -1003806440152
TOPICO_LISTA = 116

# ================== BANCO ==================

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS presencas (
    nome TEXT,
    data DATE,
    PRIMARY KEY (nome, data)
)
""")
conn.commit()

# ================== UTIL ==================

def limpar_nome(nome):
    return re.sub(r"[^\w\s]", "", nome).strip()

def gerar_confirmacao(nome):
    frases = [
        f"📜 O Pilar registra: {nome} esteve presente.",
        f"🗿 O Pilar da Sabedoria reconhece {nome}.",
        f"✨ A presença de {nome} foi gravada no Pilar.",
        f"👑 O Pilar eterniza: {nome} marcou presença.",
        f"🔥 Feixes dourados registram a presença de {nome}.",
        f"🧠 O conhecimento do Pilar agora carrega o nome de {nome}.",
        f"⚡ Registrado: {nome}"
    ]
    return random.choice(frases)

def extrair_nome(texto):
    if not texto:
        return None

    match = re.search(r"\d+\s+\[LG\]\s*([^\n]+)", texto)
    if match:
        nome = match.group(1).strip()
        return limpar_nome(nome)

    match2 = re.search(r"\d+\s+([^\n]+)", texto)
    if match2:
        nome = match2.group(1).strip()
        return limpar_nome(nome)

    return None

def salvar_presenca(nome):
    hoje = datetime.utcnow().date()
    try:
        cur.execute(
            "INSERT INTO presencas (nome, data) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (nome, hoje)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print("❌ ERRO BANCO:", e)
        return False

# ================== HANDLER ==================

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message:
            return

        if update.effective_chat.id != GRUPO_ORIGEM:
            return

        if update.message.message_thread_id != TOPICO_PRESENCA:
            return

        texto = update.message.text or update.message.caption or ""
        print("\n📩 NOVA MENSAGEM")
        print("DEBUG TEXTO:", texto)

        nome = extrair_nome(texto)

        if not nome:
            print("❌ Nome não detectado")
            return

        print("✅ NOME:", nome)

        if salvar_presenca(nome):

            # 🔥 confirmação
            try:
                confirmacao = gerar_confirmacao(nome)
                await update.message.reply_text(confirmacao)
            except Exception as e:
                print("❌ ERRO AO RESPONDER:", e)

            # 🔥 envio liderança
            try:
                await context.bot.send_message(
                    chat_id=GRUPO_DESTINO,
                    message_thread_id=TOPICO_LISTA,
                    text=f"✅ Presença: {nome}"
                )
            except Exception as e:
                print("❌ ERRO AO ENVIAR PRA LIDERANÇA:", e)

    except Exception as e:
        print("❌ ERRO GERAL:", e)

# ================== MAIN ==================

def main():
    print("🚀 Bot rodando...")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, detectar))
    app.run_polling()

if __name__ == "__main__":
    main()
