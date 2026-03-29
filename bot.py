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


# ================= UTIL =================

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


def registrar_membro(nome):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO membros (nome) VALUES (%s) ON CONFLICT DO NOTHING",
        (nome,),
    )
    conn.commit()


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

    if msg.chat.id != GRUPO_ID:
        return

    if msg.message_thread_id != TOPICO_PRESENCA:
        return

    if msg.text and msg.text.startswith("/"):
        return

    texto = msg.text or msg.caption
    if not texto:
        return

    nome = extrair_nome(texto)
    if not nome:
        return

    registrar_membro(nome)

    if salvar_presenca(nome):
        await msg.reply_text(f"✅ Presença: {nome}")


# ================= COMANDOS =================

async def presenca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.id != GRUPO_LIDERANCA:
        return

    hoje = datetime.now().date()
    cur = conn.cursor()

    cur.execute("SELECT nome FROM presencas WHERE data=%s", (hoje,))
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

    cur.execute("""
    SELECT m.nome,
           COUNT(p.data) as presencas,
           COUNT(f.data) as faltas
    FROM membros m
    LEFT JOIN presencas p ON m.nome = p.nome
        AND date_trunc('month', p.data) = date_trunc('month', CURRENT_DATE)
    LEFT JOIN faltas f ON m.nome = f.nome
        AND date_trunc('month', f.data) = date_trunc('month', CURRENT_DATE)
    GROUP BY m.nome
    ORDER BY m.nome
    """)

    dados = cur.fetchall()

    texto = "📊 Relatório mensal:\n\n"

    for nome, pres, falt in dados:
        texto += f"{nome}: ✅ {pres} | ❌ {falt}\n"

    await update.message.reply_text(texto)


# ================= FALTAS AUTOMÁTICAS =================

def marcar_faltas():
    hoje = datetime.now().date()
    cur = conn.cursor()

    cur.execute("SELECT nome FROM membros")
    membros = [m[0] for m in cur.fetchall()]

    cur.execute("SELECT nome FROM presencas WHERE data=%s", (hoje,))
    presentes = [p[0] for p in cur.fetchall()]

    faltantes = set(membros) - set(presentes)

    for nome in faltantes:
        cur.execute(
            "INSERT INTO faltas (nome, data) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (nome, hoje),
        )

    conn.commit()
    print(f"🚫 Faltas registradas: {len(faltantes)}")


# ================= RELATÓRIO =================

async def relatorio_mensal_job(app):
    cur = conn.cursor()

    cur.execute("""
    SELECT m.nome,
           COUNT(p.data),
           COUNT(f.data)
    FROM membros m
    LEFT JOIN presencas p ON m.nome = p.nome
        AND date_trunc('month', p.data) = date_trunc('month', CURRENT_DATE)
    LEFT JOIN faltas f ON m.nome = f.nome
        AND date_trunc('month', f.data) = date_trunc('month', CURRENT_DATE)
    GROUP BY m.nome
    ORDER BY m.nome
    """)

    dados = cur.fetchall()

    texto = "🏆 RELATÓRIO FINAL DO MÊS:\n\n"

    for nome, pres, falt in dados:
        texto += f"{nome}: ✅ {pres} | ❌ {falt}\n"

    await app.bot.send_message(GRUPO_LIDERANCA, texto)


# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("presenca", presenca))
    app.add_handler(CommandHandler("mensal", mensal))

    app.add_handler(MessageHandler(filters.ALL, detectar))

    scheduler = AsyncIOScheduler()

    # 🔥 FALTAS AUTOMÁTICAS
    scheduler.add_job(marcar_faltas, "cron", hour=23, minute=59)

    # 🔥 RELATÓRIO MENSAL
    scheduler.add_job(
        lambda: app.create_task(relatorio_mensal_job(app)),
        "cron",
        day="last",
        hour=23,
        minute=59,
    )

    async def start_scheduler(app):
        scheduler.start()
        print("🧠 Scheduler iniciado")

    app.post_init = start_scheduler

    print("🚀 Bot com faltas automáticas rodando...")

    app.run_polling()


if __name__ == "__main__":
    main()

