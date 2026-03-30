import os
import re
import random
import psycopg2
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# ========================
# SEUS IDS
# ========================

GRUPO_PRESENCA_ID = -1003792787717
TOPICO_PRESENCA = 16325

GRUPO_LIDERANCA_ID = -1003806440152
TOPICO_LISTA = 116

# ========================
# BANCO
# ========================

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS jogadores (
    nome TEXT PRIMARY KEY
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS presencas (
    nome TEXT,
    data TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS controle (
    chave TEXT PRIMARY KEY,
    valor TEXT
)
""")

conn.commit()

# ========================
# LORE
# ========================

def mensagem_lore(nome):
    mensagens = [
        f"📜 O Pilar registra: {nome} respondeu ao chamado.",
        f"✨ Fragmento absorvido... {nome} agora ecoa no Pilar.",
        f"🌟 A luz dourada reconhece {nome}. Presença marcada.",
        f"🧠 O conhecimento de {nome} foi gravado.",
        f"🔮 Ecos antigos sussurram: {nome} está presente.",
        f"🏛️ O Pilar confirma: {nome} compareceu.",
        f"📖 {nome} agora faz parte da memória eterna."
    ]
    return random.choice(mensagens)

# ========================
# EXTRAIR NOME
# ========================

def extrair_nome(texto):
    match = re.search(r"\d+\s+\S+\s+(.+)", texto)
    if match:
        return match.group(1).strip()
    return None

# ========================
# GERAR LISTA
# ========================

def gerar_lista():
    hoje = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("SELECT nome FROM jogadores")
    todos = [x[0] for x in cursor.fetchall()]

    cursor.execute("SELECT nome FROM presencas WHERE data = %s", (hoje,))
    presentes = [x[0] for x in cursor.fetchall()]

    faltantes = [n for n in todos if n not in presentes]

    texto = "📋 PRESENÇA DIÁRIA\n\n"

    texto += "✅ PRESENTES:\n"
    for p in presentes:
        texto += f"✔️ {p}\n"

    texto += "\n❌ FALTANTES:\n"
    for f in faltantes:
        texto += f"❌ {f}\n"

    return texto

# ========================
# ATUALIZAR LISTA FIXA
# ========================

async def atualizar_lista(context):
    cursor.execute("SELECT valor FROM controle WHERE chave = 'mensagem_lista'")
    result = cursor.fetchone()

    if not result:
        return

    message_id = int(result[0])
    texto = gerar_lista()

    try:
        await context.bot.edit_message_text(
            chat_id=GRUPO_LIDERANCA_ID,
            message_id=message_id,
            text=texto
        )
    except:
        pass

# ========================
# COMANDO /lista
# ========================

async def comando_lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = gerar_lista()
    await update.message.reply_text(texto)

# ========================
# CRIAR LISTA FIXA
# ========================

async def criar_lista_inicial(context):
    texto = gerar_lista()

    msg = await context.bot.send_message(
        chat_id=GRUPO_LIDERANCA_ID,
        message_thread_id=TOPICO_LISTA,
        text=texto
    )

    cursor.execute("""
    INSERT INTO controle (chave, valor)
    VALUES ('mensagem_lista', %s)
    ON CONFLICT (chave) DO UPDATE SET valor = %s
    """, (str(msg.message_id), str(msg.message_id)))

    conn.commit()

# ========================
# HANDLER PRINCIPAL
# ========================

async def receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    # garantir que só leia no tópico certo
    if update.message.chat_id != GRUPO_PRESENCA_ID:
        return

    if update.message.message_thread_id != TOPICO_PRESENCA:
        return

    texto = update.message.text

    nome = extrair_nome(texto)
    if not nome:
        return

    hoje = datetime.now().strftime("%Y-%m-%d")

    # registrar jogador
    cursor.execute("INSERT INTO jogadores (nome) VALUES (%s) ON CONFLICT DO NOTHING", (nome,))

    # evitar duplicado
    cursor.execute("SELECT * FROM presencas WHERE nome=%s AND data=%s", (nome, hoje))
    if cursor.fetchone():
        return

    cursor.execute("INSERT INTO presencas (nome, data) VALUES (%s, %s)", (nome, hoje))
    conn.commit()

    # confirmação
    await update.message.reply_text(mensagem_lore(nome))

    # notificação liderança (no tópico)
    await context.bot.send_message(
        chat_id=GRUPO_LIDERANCA_ID,
        message_thread_id=TOPICO_LISTA,
        text=f"✅ Presença: {nome}"
    )

    # atualizar lista
    await atualizar_lista(context)

# ========================
# MAIN
# ========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT, receber))
    app.add_handler(CommandHandler("lista", comando_lista))

    async def on_start(app):
        await criar_lista_inicial(app)

    app.post_init = on_start

    print("🚀 Pilar da Sabedoria ativo...")
    app.run_polling()

if __name__ == "__main__":
    main()
