import os
from telegram.ext import Application, MessageHandler, filters

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise Exception("TOKEN não encontrado")

async def responder(update, context):
    try:
        if not update:
            return

        if not update.message:
            return

        texto = update.message.text

        if not texto:
            return

        await update.message.reply_text("🔥 BOT ONLINE")

    except Exception as e:
        print("ERRO HANDLER:", e)

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, responder))

    print("🚀 BOT INICIADO")

    app.run_polling(
        drop_pending_updates=True,
        close_loop=False,
        stop_signals=None
    )

if __name__ == "__main__":
    main()
