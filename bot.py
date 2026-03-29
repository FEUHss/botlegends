from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import re
import os

TOKEN = os.getenv("TOKEN")

GRUPO_ID = -1003792787717  # grupo da guilda

# Lista base de membros
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

    # remove [TAG]
    nome = re.sub(r"\[.*?\]", "", nome)

    # remove emojis/símbolos
    nome = re.sub(r"[^\w\s,]", "", nome)

    # remove espaços extras
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
            nome = match.group(1)
            return limpar_nome(nome)
    except:
        return None

# =========================
# CAPTURA DE PERFIL (SÓ GRUPO)
# =========================
async def capturar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg or not msg.text:
        return

    # 🔒 Só funciona no grupo
    if msg.chat.id != GRUPO_ID:
        return

    texto = msg.text

    # garante que é perfil
    if "Classe:" not in texto:
        return

    nome = extrair_nome(texto)

    print("NOME DETECTADO:", nome)

    if nome:
        presencas.add(nome)
        MEMBROS.add(nome)  # adiciona novos automaticamente
        print(f"✅ Presença registrada: {nome}")

# =========================
# COMANDO /presenca (FUNCIONA EM QUALQUER LUGAR)
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
    print("Bot presença inteligente rodando...")

    app = ApplicationBuilder().token(TOKEN).build()

    # captura mensagens (grupo)
    app.add_handler(MessageHandler(filters.TEXT, capturar))

    # comandos (funcionam em qualquer chat)
    app.add_handler(CommandHandler("presenca", ver_presenca))
    app.add_handler(CommandHandler("reset", reset))

    app.run_polling()

if __name__ == "__main__":
    main()
