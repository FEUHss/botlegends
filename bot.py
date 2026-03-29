import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# CONFIG
TOKEN = os.getenv("TOKEN")
GRUPO_ID = -1003792787717
TOPICO_PRESENCA = 16325


# LIMPAR NOME
def limpar_nome(nome):
    return (
        nome.replace("[LG]", "")
        .replace("*", "")
        .strip()
        .upper()
    )


# EXTRAIR NOME (SEM TRY = SEM ERRO)
def extrair_nome(texto):
    linhas = texto.split("\n")

    for linha in linhas:
        if "📜" in linha:
            partes = linha.split()

            for i, parte in enumerate(partes):
                if parte.isdigit():
                    nome = " ".join(partes[i + 1:])
                    return limpar_nome(nome)

    return None


# HANDLER
async def detectar_presenca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    chat_id = msg.chat.id
    thread_id = msg.message_thread_id

    print("CHAT:", chat_id)
    print("THREAD:", thread_id)

    # FILTRO DO TÓPICO
    if chat_id == GRUPO_ID and thread_id != TOPICO_PRESENCA:
        return

    texto = msg.text or msg.caption
    if not texto:
        return

    nome = extrair_nome(texto)

    if not nome:
        print("❌ Não encontrou nome")
        return

    print("✅ Nome:", nome)

    await msg.reply_text(f"✅ Presença registrada: {nome}")


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot ativo!")


# MAIN
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT | filters.PHOTO | filters.CaptionRegex(".*"),
            detectar_presenca,
        )
    )

    print("🚀 Rodando...")

    app.run_polling(drop_pending_updates=True, close_loop=False)


if __name__ == "__main__":
    main()
