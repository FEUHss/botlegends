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

    await update.message.reply_text("🔥 BOT ONLINE")

# =========================
# MAIN (FORMA CORRETA)
# =========================
async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    print("🚀 BOT INICIADO")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.stop()

# =========================
# START
# =========================
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
