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

# Lista em memória (temporária)
presencas = set()
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


# 🔹 EXTRAIR NOME
def extrair_nome(texto):
    linhas = texto.split("\n")

    for linha in linhas:
        if "📜" in linha:
            partes = linha.split()

            nome_partes = []
            encontrou_nivel = False

            for parte in partes:
                if parte.isdigit():
                    encontrou_nivel = True
                    continue

                if encontrou_nivel:
                    nome_partes.append(parte)

            if nome_partes:
                nome = " ".join(nome_partes)
                return limpar_nome(nome)

    return None


# 🔥 HANDLER PRINCIPAL (IGNORA COMANDOS)
async def detectar_presenca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg:
        return

    # ❗ IGNORA COMANDOS
    if msg.text and msg.text.startswith("/"):
        return

    chat_id = msg.chat.id
    thread_id = msg.message_thread_id

    print("\n🔥 CHEGOU MENSAGEM")
    print("CHAT:", chat_id)
    print("THREAD:", thread_id)

    # 🔒 FILTRO GRUPO + TÓPICO
    if chat_id == GRUPO_ID and thread_id != TOPICO_PRESENCA:
        return

    texto = msg.text or msg.caption

    if not texto:
        print("❌ Sem texto")
        return

    nome = extrair_nome(texto)

    if not nome:
        print("❌ Não encontrou nome")
        return

    print("✅ Nome:", nome)

    # Salva presença
    presencas.add(nome)

    await msg.reply_text(f"✅ Presença registrada: {nome}")


# 🔹 COMANDO START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot de presença ativo!")


# 🔥 COMANDO /PRESENCA (AGORA FUNCIONA)
async def ver_presenca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not presencas:
        await update.message.reply_text("📋 Ninguém marcou presença ainda.")
        return

    lista = "\n".join([f"✅ {nome}" for nome in sorted(presencas)])

    texto = f"📋 Presenças do dia:\n\n{lista}"

    await update.message.reply_text(texto)


# 🚀 MAIN
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # 🔥 COMANDOS PRIMEIRO
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("presenca", ver_presenca))

    # 🔥 MENSAGENS DEPOIS
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
