import os
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise Exception("TOKEN não encontrado")

# =========================
# HANDLER
# =========================
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not update.message.text:
        return

    print("Mensagem recebida:", update.message.text)

    await update.message.reply_text("🔥 BOT ONLINE")

# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    print("🚀 BOT INICIADO")

    app.run_polling(
        drop_pending_updates=True,
        close_loop=False
    )

# =========================
# START
# =========================
if __name__ == "__main__":
    main()
