from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import re
import os

TOKEN = os.getenv("TOKEN")

GRUPO_ID = -1003792787717
TOPICO_PRESENCA = 16325

MEMBROS = set([
    "ARCHANGEL",
    "CHURO",
    "GROMATH, O URSO",
    "MARLON",
    "LINK",
    "HENRIQUE",
    "LUIZ CARLOS",
    "JOSHUA",
    "G.K",
    "JHON, O IMENSO",
    "ARTORIAS",
    "BIGSLOW",
    "GENERICO",
    "KVN",
    "KAZAN",
    "KAZUKKIDRAGNAK",
    "K"
])

presencas = set()

# =========================
# LIMPAR NOME
# =========================
def limpar_nome(nome):
    nome = nome.upper()
    nome = re.sub(r"\[.*?\]", "", nome)
    nome = re.sub(r"[^\w\s,]", "", nome)
    nome = re.sub(r"\s+", " ", nome).strip()
    return nome

# =========================
# EXTRAIR NOME
# =========================
def extrair_nome(texto):
    try:
        texto = re.sub(r"^[^\w\d]+", "", texto)
        match = re.search(r"\d+\s+(.+)", texto)
        if match:
            return limpar_nome(match.group(1))
    except:
        return None

# =========================
# CAPTURA (COM TÓPICO)
# =========================
async def capturar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg:
        return

    print("🔥 CHEGOU MENSAGEM")
    print("CHAT:", msg.chat.id)
    print("THREAD:", msg.message_thread_id)

    # 🔒 garante que é do grupo certo
    if msg.chat.id != GRUPO_ID:
        return

    # 🔒 garante que é da aba presença diária
    if msg.message_thread_id != TOPICO_PRESENCA:
        return

    if not msg.text:
        return

    texto = msg.text

    if "Classe:" not in texto:
        return

    nome = extrair_nome(texto)

    print("NOME DETECTADO:", nome)

    if nome:
        presencas.add(nome)
        MEMBROS.add(nome)
        print(f"✅ Presença registrada: {nome}")

# =========================
# COMANDO /presenca
# =========================
async def ver_presenca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resposta = "📋 PRESENÇA DO DIA\n\n"

    for membro in sorted(MEMBROS):
        if membro in presencas:
            resposta += f"✅ {membro}\n"
        else:
            resposta += f"❌ {membro}\n"

    await update.message.reply_text(resposta)

# =========================
# RESET
# =========================
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    presencas.clear()
    await update.message.reply_text("🔄 Presença resetada.")

# =========================
# MAIN
# =========================
def main():
    print("Bot presença com tópico rodando...")

    app = ApplicationBuilder().token(TOKEN).build()

    # 🔥 IMPORTANTE: usar ALL
    app.add_handler(MessageHandler(filters.ALL, capturar))

    app.add_handler(CommandHandler("presenca", ver_presenca))
    app.add_handler(CommandHandler("reset", reset))

    app.run_polling()

if __name__ == "__main__":
    main()
