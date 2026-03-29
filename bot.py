import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("❌ TOKEN não encontrado nas variáveis do Railway")

GRUPO_ID = -1003792787717
TOPICO_PRESENCA = 16325

# ==========================================

logging.basicConfig(level=logging.INFO)


# 🔹 LIMPAR NOME
def limpar_nome(nome):
    return (
        nome.replace("[LG]", "")
        .replace("*", "")
        .replace("_", "")
        .replace("`", "")
        .strip()
        .upper()
    )


# 🔹 EXTRAIR NOME DO PERFIL
def extrair_nome(texto):
    try:
        linhas = texto.split("\n")

        for linha in linhas:
            if "📜" in linha:
                partes = linha.split()

                for i, parte in enumerate(partes):
                    if parte.isdigit():
                        nome = " ".join(partes[i + 1:])
                        return limpar_nome(nome)

        return None

    except Exception as e:
        print("Erro ao extrair nome:", e)
        return None


# 🔥 HANDLER PRINCIPAL
async def detectar_presenca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg:
        return

    chat_id = msg.chat.id
    thread_id = msg.message_thread_id

    print("\n🔥 CHEGOU MENSAGEM")
    print("CHAT:", chat_id)
    print("THREAD:", thread_id)

    # 🔒 FILTRO DO GRUPO E TÓPICO
    if chat_id == GRUPO_ID:
        if thread_id != TOPICO_PRESENCA:
            return

    # 📥 TEXTO OU CAPTION (imagem encaminhada usa caption!)
    texto = msg.text or msg.caption

    if not texto:
        print("❌ Sem texto")
        return

    # 🔍 EXTRAIR NOME
    nome = extrair_nome(texto)

    if not nome:
        print("❌ Nome não encontrado")
        return

    print("✅ NOME DETECTADO:", nome)

    # ✅ RESPONDER
    await msg.reply_text(f"✅ Presença registrada: {nome}")


# 🔹 COMANDO START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot de presença ativo!")


# 🚀 MAIN
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL, detectar_presenca))

    print("🚀 Bot presença inteligente rodando...")

    app.run_polling()


if __name__ == "__main__":
    main()
