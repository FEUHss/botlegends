import os
import psycopg2
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

GRUPO_ID = -1003792787717
TOPICO_PRESENCA = 16325
GRUPO_LIDERANCA = -1003806440152

conn = psycopg2.connect(DATABASE_URL)


# ================= FUNÇÕES =================

def limpar_nome(nome):
    return nome.replace("[LG]", "").strip().upper()


def extrair_nome(texto):
    for linha in texto.split("\n"):
        if "📜" in linha:
            partes = linha.split()
            for i, p in enumerate(partes):
                if p.isdigit():
                    return limpar_nome(" ".join(partes[i + 1:]))
    return None


def salvar_presenca(nome):
    hoje = datetime.now().date()
    cur = conn.cursor()

    cur.execute(
        "SELECT 1 FROM presencas WHERE nome=%s AND data=%s",
        (nome, hoje),
    )

    if cur.fetchone():
        return False

    cur.execute(
        "INSERT INTO presencas (nome, data) VALUES (%s, %s)",
        (nome, hoje),
    )
    conn.commit()
    return True


# ================= DETECÇÃO =================

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg:
        return

    # grupo correto
    if msg.chat.id != GRUPO_ID:
        return

    # tópico correto
    if msg.message_thread_id != TOPICO_PRESENCA:
        return

    # ignora comandos
    if msg.text and msg.text.startswith("/"):
        return

    texto = msg.text or msg.caption
    if not texto:
        return

    nome = extrair_nome(texto)
    if not nome:
        return

    if salvar_presenca(nome):
        await msg.reply_text(f"✅ Presença: {nome}")


# ================= COMANDOS =================

async def presenca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.id != GRUPO_LIDERANCA:
        return

    hoje = datetime.now().date()
    cur = conn.cursor()

    cur.execute(
        "SELECT nome FROM presencas WHERE data=%s ORDER BY nome",
        (hoje,),
    )

    dados = cur.fetchall()

    if not dados:
        await update.message.reply_text("📋 Ninguém marcou presença hoje.")
        return

    texto = "📋 Presença de hoje:\n\n"
    texto += "\n".join([f"✅ {n[0]}" for n in dados])

    await update.message.reply_text(texto)


async def mensal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.id != GRUPO_LIDERANCA:
        return

    cur = conn.cursor()

    cur.execute(
        """
        SELECT nome, COUNT(*) 
        FROM presencas
        WHERE date_trunc('month', data) = date_trunc('month', CURRENT_DATE)
        GROUP BY nome
        ORDER BY nome
        """
    )

    dados = cur.fetchall()

    if not dados:
        await update.message.reply_text("📊 Sem dados esse mês.")
        return

    texto = "📊 Relatório mensal:\n\n"

    for nome, pres in dados:
        texto += f"{nome}: {pres} presenças\n"

    await update.message.reply_text(texto)


# ================= RELATÓRIO AUTOMÁTICO =================

async def relatorio_mensal_job(app):
    cur = conn.cursor()

    cur.execute(
        """
        SELECT nome, COUNT(*) 
        FROM presencas
        WHERE date_trunc('month', data) = date_trunc('month', CURRENT_DATE)
        GROUP BY nome
        ORDER BY nome
        """
    )

    dados = cur.fetchall()

    if not dados:
        return

    texto = "🏆 RELATÓRIO FINAL DO MÊS:\n\n"

    for nome, pres in dados:
        texto += f"{nome}: {pres} presenças\n"

    await app.bot.send_message(
        chat_id=GRUPO_LIDERANCA,
        text=texto
    )


# ================= RESET =================

def reset_diario():
    print("🕛 Reset diário executado")


# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # comandos
    app.add_handler(CommandHandler("presenca", presenca))
    app.add_handler(CommandHandler("mensal", mensal))

    # handler (corrigido)
    app.add_handler(MessageHandler(filters.ALL, detectar))

    scheduler = AsyncIOScheduler()

    scheduler.add_job(reset_diario, "cron", hour=0, minute=0)

    scheduler.add_job(
        lambda: app.create_task(relatorio_mensal_job(app)),
        "cron",
        day="last",
        hour=23,
        minute=59,
    )

    # 🔥 CORREÇÃO DO LOOP
    async def start_scheduler(app):
        scheduler.start()
        print("🧠 Scheduler iniciado")

    app.post_init = start_scheduler

    print("🚀 Bot presença FINAL rodando...")

    app.run_polling()


if __name__ == "__main__":
    main()
