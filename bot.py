import os
from telegram.ext import Application, MessageHandler, filters

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise Exception("TOKEN não encontrado")

async def responder(update, context):
    if update.message:
        await update.message.reply_text("🔥 BOT ONLINE")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT, responder))

    print("🚀 BOT INICIADO")

    app.run_polling(
        drop_pending_updates=True,
        close_loop=False,
        stop_signals=None
    )

if __name__ == "__main__":
    main()
