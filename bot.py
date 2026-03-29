import os
import psycopg2
from datetime import datetime, date
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

GRUPO_ID = -1003792787717
TOPICO_PRESENCA = 16325

GRUPO_LIDERANCA = -1003806440152
TOPICO_PAINEL = 116

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


# ================= BANCO =================

def registrar_membro(nome):
    cur = conn.cursor()
    cur.execute("INSERT INTO membros VALUES (%s) ON CONFLICT DO NOTHING", (nome,))
    conn.commit()


def salvar_presenca(nome):
    hoje = date.today()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM presencas WHERE nome=%s AND data=%s", (nome, hoje))
    if cur.fetchone():
        return False

    cur.execute("INSERT INTO presencas VALUES (%s,%s)", (nome, hoje))
    conn.commit()
    return True


# ================= PAINEL =================

def gerar_texto_painel():
    hoje = date.today()
    cur = conn.cursor()

    cur.execute("SELECT nome FROM membros")
    membros = [m[0] for m in cur.fetchall()]

    cur.execute("SELECT nome FROM presencas WHERE data=%s", (hoje,))
    presentes = [p[0] for p in cur.fetchall()]

    faltantes = sorted(set(membros) - set(presentes))
    presentes = sorted(presentes)

    texto = f"📋 PRESENÇA - {hoje.strftime('%d/%m')}\n\n"

    texto += "🟢 Presentes:\n"
    texto += "\n".join([f"✅ {n}" for n in presentes]) or "Ninguém ainda"

    texto += "\n\n🔴 Ausentes:\n"
    texto += "\n".join([f"❌ {n}" for n in faltantes]) or "Nenhum"

    texto += f"\n\n📊 {len(presentes)}/{len(membros)}"

    return texto


async def atualizar_painel(app):
    hoje = date.today()
    cur = conn.cursor()

    cur.execute("SELECT message_id FROM painel WHERE data=%s", (hoje,))
    result = cur.fetchone()

    if not result:
        return

    message_id = result[0]

    texto = gerar_texto_painel()

    await app.bot.edit_message_text(
        chat_id=GRUPO_LIDERANCA,
        message_id=message_id,
        text=texto,
        message_thread_id=TOPICO_PAINEL
    )


async def criar_painel(app):
    hoje = date.today()
    texto = gerar_texto_painel()

    msg = await app.bot.send_message(
        chat_id=GRUPO_LIDERANCA,
        text=texto,
        message_thread_id=TOPICO_PAINEL
    )

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO painel VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (hoje, msg.message_id)
    )
    conn.commit()


# ================= FALTAS =================

def marcar_faltas():
    hoje = date.today()
    cur = conn.cursor()

    cur.execute("SELECT nome FROM membros")
    membros = [m[0] for m in cur.fetchall()]

    cur.execute("SELECT nome FROM presencas WHERE data=%s", (hoje,))
    presentes = [p[0] for p in cur.fetchall()]

    faltantes = set(membros) - set(presentes)

    for nome in faltantes:
        cur.execute(
            "INSERT INTO faltas VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (nome, hoje)
        )

    conn.commit()


# ================= DETECÇÃO =================

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    if msg.chat.id != GRUPO_ID:
        return

    if msg.message_thread_id != TOPICO_PRESENCA:
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
        await atualizar_painel(context.application)


# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, detectar))

    scheduler = AsyncIOScheduler()

    # criar painel 00:00
    scheduler.add_job(
        lambda: app.create_task(criar_painel(app)),
        "cron",
        hour=0,
        minute=0
    )

    # finalizar dia 23:59
    scheduler.add_job(
        marcar_faltas,
        "cron",
        hour=23,
        minute=59
    )

    async def start_scheduler(app):
        scheduler.start()
        await criar_painel(app)
        print("🧠 Scheduler + painel iniciado")

    app.post_init = start_scheduler

    print("🚀 Bot com painel profissional rodando...")

    app.run_polling()


if __name__ == "__main__":
    main()
