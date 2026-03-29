import os
import re
import random
import asyncio
from datetime import datetime, date

import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

CHAT_ID_ORIGEM = -1003792787717
TOPICO_PRESENCA = 16325

CHAT_ID_LIDER = -1003806440152
TOPICO_LISTA = 116

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True

# =========================
# BANCO
# =========================

def get_lista_msg_id():
    cur = conn.cursor()
    cur.execute("SELECT valor FROM config WHERE chave='lista_msg_id'")
    res = cur.fetchone()
    return int(res[0]) if res else None

def set_lista_msg_id(msg_id):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO config (chave, valor)
        VALUES ('lista_msg_id', %s)
        ON CONFLICT (chave)
        DO UPDATE SET valor = EXCLUDED.valor
    """, (str(msg_id),))

def registrar_membro(nome):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO membros VALUES (%s)
        ON CONFLICT DO NOTHING
    """, (nome,))

def salvar_presenca(nome):
    hoje = date.today()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO presencas VALUES (%s, %s)
        ON CONFLICT DO NOTHING
    """, (nome, hoje))

def get_presentes():
    hoje = date.today()
    cur = conn.cursor()
    cur.execute("SELECT nome FROM presencas WHERE data=%s", (hoje,))
    return [r[0] for r in cur.fetchall()]

def get_membros():
    cur = conn.cursor()
    cur.execute("SELECT nome FROM membros")
    return [r[0] for r in cur.fetchall()]

# =========================
# LISTA
# =========================

def gerar_lista():
    presentes = sorted(get_presentes())
    membros = sorted(get_membros())

    faltantes = [m for m in membros if m not in presentes]

    texto = "📋 PRESENÇA DIÁRIA\n\n"

    texto += "✅ PRESENTES:\n"
    for p in presentes:
        texto += f"✔ {p}\n"

    texto += "\n❌ FALTANTES:\n"
    for f in faltantes:
        texto += f"✖ {f}\n"

    return texto

# =========================
# ATUALIZAR LISTA
# =========================

async def atualizar_lista(bot):
    texto = gerar_lista()
    msg_id = get_lista_msg_id()

    try:
        if msg_id:
            await bot.edit_message_text(
                chat_id=CHAT_ID_LIDER,
                message_id=msg_id,
                text=texto
            )
        else:
            raise Exception("sem msg")
    except:
        msg = await bot.send_message(
            chat_id=CHAT_ID_LIDER,
            message_thread_id=TOPICO_LISTA,
            text=texto
        )
        set_lista_msg_id(msg.message_id)

# =========================
# CONFIRMAÇÃO LORE
# =========================

frases = [
    "📜 O Pilar registra {nome}.",
    "✨ A presença de {nome} ecoa na eternidade.",
    "📖 {nome} foi gravado no conhecimento da guilda.",
    "🜂 O Pilar reconhece {nome}.",
    "🔮 Registro confirmado: {nome}.",
    "📚 O saber eterno agora guarda {nome}.",
]

def resposta(nome):
    return random.choice(frases).format(nome=nome)

# =========================
# DETECTOR DE PERFIL
# =========================

def extrair_nome(texto):
    match = re.search(r"\d+\s+(.+)", texto)
    if match:
        nome = match.group(1)
        nome = re.split(r"\n|Classe:", nome)[0]
        return nome.strip()
    return None

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID_ORIGEM:
        return

    if update.message.message_thread_id != TOPICO_PRESENCA:
        return

    texto = update.message.text or ""
    nome = extrair_nome(texto)

    if not nome:
        return

    registrar_membro(nome)
    salvar_presenca(nome)

    await update.message.reply_text(resposta(nome))

    await atualizar_lista(context.bot)

# =========================
# FECHAMENTO 23:59
# =========================

async def fechar_dia(bot):
    texto = "📊 RELATÓRIO FINAL DO DIA\n\n"
    texto += gerar_lista()

    await bot.send_message(
        chat_id=CHAT_ID_LIDER,
        message_thread_id=TOPICO_LISTA,
        text=texto
    )

    # limpa presenças do dia
    cur = conn.cursor()
    cur.execute("DELETE FROM presencas WHERE data=%s", (date.today(),))

    # reseta lista
    set_lista_msg_id(None)

async def scheduler(app):
    while True:
        agora = datetime.now()
        if agora.hour == 23 and agora.minute == 59:
            await fechar_dia(app.bot)
            await asyncio.sleep(60)
        await asyncio.sleep(30)

# =========================
# MAIN
# =========================

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT, detectar))

    asyncio.create_task(scheduler(app))

    print("🚀 Bot rodando...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
