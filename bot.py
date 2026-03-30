import os
import psycopg2
import random
import pytz
from datetime import datetime
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

tz = pytz.timezone("America/Sao_Paulo")

ultimo_texto_painel = {}


# ================= DATA =================

def hoje():
    return datetime.now(tz).date()


# ================= UTIL =================

def limpar_nome(nome):
    return nome.replace("[LG]", "").strip().upper()


def extrair_nome(texto):
    for linha in texto.split("\n"):
        partes = linha.strip().split()

        for i, p in enumerate(partes):
            if p.isdigit():
                nome = " ".join(partes[i + 1:])
                return limpar_nome(nome)

    return None


def mensagem_pilar(nome):
    frases = [
        f"📜 O Pilar registra: {nome} esteve presente.",
        f"🗿 O Pilar da Sabedoria reconhece {nome}.",
        f"✨ A presença de {nome} foi gravada no Pilar.",
        f"👑 O Pilar eterniza: {nome} marcou presença.",
        f"🔥 Feixes dourados registram a presença de {nome}.",
        f"🧠 O conhecimento do Pilar agora carrega o nome de {nome}.",
        f"⚡ Registrado: {nome}"
    ]
    return random.choice(frases)


# ================= BANCO =================

def registrar_membro(nome):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO membros (nome) VALUES (%s) ON CONFLICT DO NOTHING",
        (nome,)
    )
    conn.commit()


def salvar_presenca(nome):
    hoje_ = hoje()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM presencas WHERE nome=%s AND data=%s", (nome, hoje_))
    if cur.fetchone():
        return False

    cur.execute(
        "INSERT INTO presencas (nome, data) VALUES (%s,%s)",
        (nome, hoje_)
    )
    conn.commit()
    return True


# ================= PAINEL =================

def gerar_texto_painel():
    hoje_ = hoje()
    cur = conn.cursor()

    cur.execute("SELECT nome FROM membros")
    membros = [m[0] for m in cur.fetchall()]

    cur.execute("SELECT nome FROM presencas WHERE data=%s", (hoje_,))
    presentes = [p[0] for p in cur.fetchall()]

    faltantes = sorted(set(membros) - set(presentes))
    presentes = sorted(presentes)

    texto = f"📜 PRESENÇA DA GUILDA — {hoje_.strftime('%d/%m')}\n\n"

    texto += "🟢 Presentes:\n"
    texto += "\n".join([f"✅ {n}" for n in presentes]) if presentes else "Ninguém ainda"

    texto += "\n\n🔴 Ausentes:\n"
    texto += "\n".join([f"❌ {n}" for n in faltantes]) if faltantes else "Nenhum"

    texto += f"\n\n📊 Total: {len(presentes)}/{len(membros)} membros"

    return texto


# 🔥 CORREÇÃO FINAL
async def atualizar_painel(app):
    hoje_ = hoje()
    cur = conn.cursor()

    cur.execute("SELECT message_id FROM painel WHERE data=%s", (hoje_,))
    result = cur.fetchone()

    if not result:
        print("⚠️ Painel não encontrado")
        return

    message_id = result[0]
    texto = gerar_texto_painel()

    try:
        await app.bot.edit_message_text(
            chat_id=GRUPO_LIDERANCA,
            message_id=message_id,
            text=texto + f"\n\n🕒 Atualizado: {datetime.now(tz).strftime('%H:%M:%S')}"
        )
        print("🔄 Painel atualizado")

    except Exception as e:
        print("❌ Erro ao atualizar painel:", e)


async def criar_painel(app):
    hoje_ = hoje()
    texto = gerar_texto_painel()

    msg = await app.bot.send_message(
        chat_id=GRUPO_LIDERANCA,
        text=texto,
        message_thread_id=TOPICO_PAINEL
    )

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO painel (data, message_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (hoje_, msg.message_id)
    )
    conn.commit()


# ================= FALTAS =================

def marcar_faltas():
    hoje_ = hoje()
    cur = conn.cursor()

    cur.execute("SELECT nome FROM membros")
    membros = [m[0] for m in cur.fetchall()]

    cur.execute("SELECT nome FROM presencas WHERE data=%s", (hoje_,))
    presentes = [p[0] for p in cur.fetchall()]

    faltantes = set(membros) - set(presentes)

    for nome in faltantes:
        cur.execute(
            "INSERT INTO faltas (nome, data) VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (nome, hoje_)
        )

    conn.commit()
    print("📕 Faltas registradas")


async def fechar_e_novo_dia(app):
    print("🌙 Fechando dia...")

    marcar_faltas()
    await atualizar_painel(app)

    import asyncio
    await asyncio.sleep(2)

    await criar_painel(app)

    print("🌅 Novo painel criado")


# ================= COMANDO =================

async def comando_lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg:
        return

    if msg.chat.id not in [GRUPO_ID, GRUPO_LIDERANCA]:
        return

    texto = gerar_texto_painel()
    await msg.reply_text(texto)


# ================= DETECÇÃO =================

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg:
        return

    print("THREAD:", msg.message_thread_id)

    if msg.chat.id != GRUPO_ID:
        return

    if msg.message_thread_id != TOPICO_PRESENCA:
        return

    texto = msg.text or msg.caption
    if not texto:
        return

    print("📨 Mensagem recebida")

    nome = extrair_nome(texto)
    if not nome:
        print("⚠️ Nome não identificado")
        return

    print("👤 Nome detectado:", nome)

    registrar_membro(nome)

    if salvar_presenca(nome):
        await msg.reply_text(mensagem_pilar(nome))
        await atualizar_painel(context.application)


# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("lista", comando_lista))
    app.add_handler(MessageHandler(filters.TEXT | filters.CaptionRegex(".*"), detectar))

    scheduler = AsyncIOScheduler(timezone=tz)

    scheduler.add_job(
        lambda: app.create_task(fechar_e_novo_dia(app)),
        "cron",
        hour=23,
        minute=59
    )

    async def start_scheduler(app):
        scheduler.start()
        await criar_painel(app)
        print("🧠 Scheduler + painel iniciado")

    app.post_init = start_scheduler

    print("🚀 Bot rodando (FINAL PERFEITO)...")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
