import os
import re
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise Exception("TOKEN não encontrado")

# =========================
# HANDLER
# =========================
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message:
            return

        texto = update.message.text or update.message.caption

        print("------ NOVA MSG ------")
        print(texto)

        if not texto:
            return

        if "XP:" not in texto:
            return

        # =========================
        # EXTRAÇÃO ROBUSTA
        # =========================
        xp = int(re.search(r"XP:\s*(\d+)", texto).group(1))

        atk = int(re.search(r"ATK\s*(\d+)", texto).group(1))

        defesa = float(re.search(r"DEF\s*([\d\.]+)", texto).group(1))

        crit = int(re.search(r"CRIT\s*(\d+)", texto).group(1))

        hp = int(re.search(r"HP:\s*\d+/(\d+)", texto).group(1))

        print(f"XP: {xp} | ATK: {atk} | DEF: {defesa} | CRIT: {crit} | HP: {hp}")

        await update.message.reply_text("📜 O Pilar grava a sua jornada.")

    except Exception as e:
        print("ERRO:", e)

# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, responder))

    print("🚀 BOT INICIANDO...")

    app.run_polling(
        drop_pending_updates=True,
        close_loop=False,
        allowed_updates=["message"],
        poll_interval=2
    )

# =========================
# START
# =========================
if __name__ == "__main__":
    main()
