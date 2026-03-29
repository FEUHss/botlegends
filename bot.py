import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("❌ TOKEN não encontrado no Railway")

GRUPO_ID = -1003792787717
TOPICO_PRESENCA = 16325
# ==========================================


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


# 🔹 EXTRAIR NOME (VERSÃO FINAL INTELIGENTE)
def extrair_nome(texto):
    linhas = texto.split("\n")

    for linha in linhas:
        if "📜" in linha:
            partes = linha.split()

            nome_partes = []
            encontrou_nivel = False

            for parte in partes:
                # Detecta nível (número)
                if parte.isdigit():
                    encontrou_nivel = True
                    continue

                # Depois do nível = nome
                if encontrou_nivel:
                    nome_partes.append(parte)

            if nome_partes:
                nome = " ".join(nome_partes)
                return limpar_nome(nome)

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

    # 🔒 FILTRO DO GRUPO + TÓPICO
    if chat_id == GRUPO_ID and thread_id != TOPICO_PRESENCA:
        return

    # 📥 TEXTO OU CAPTION
    texto = msg.text or msg.caption

    if not texto:
        print("❌ Sem texto")
        return

    print("📄 TEXTO:", texto[:100])

    # 🔍 EXTRAIR NOME
    nome = extrair_nome(texto)

    if not nome:
        print("❌ Não encontrou nome")
        return

    print("✅ Nome:", nome)

    # ✅ RESPOSTA
    await msg.reply_text(f"✅ Presença registrada: {nome}")


# 🔹 COMANDO START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot de presença ativo!")


# 🚀 MAIN
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    # 🔥 HANDLER CORRETO
    app.add_handler(
        MessageHandler(
            filters.TEXT | filters.PHOTO | filters.CaptionRegex(".*"),
            detectar_presenca,
        )
    )

    print("🚀 Bot presença inteligente rodando...")

    app.run_polling(
        drop_pending_updates=True,
        close_loop=False,
    )


if __name__ == "__main__":
    main()

