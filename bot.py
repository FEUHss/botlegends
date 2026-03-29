import os
import re
import asyncio
from datetime import datetime, date

import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# ================= CONFIG =================

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# 📥 GRUPO DO CLÃ (onde lê)
GRUPO_CLAN = -1003792787717
TOPICO_PRESENCA = 16325

# 📤 GRUPO LIDERANÇA (onde envia)
GRUPO_LIDER = -1003806440152
TOPICO_LISTA = 116

# ==========================================

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True


# ================= BANCO =================

def criar_tabelas():
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS membros (
            nome TEXT PRIMARY KEY
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS presencas (
            nome TEXT,
            data DATE,
            UNIQUE(nome, data)
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS faltas (
            nome TEXT,
            data DATE,
            UNIQUE(nome, data)
        );
        """)


# ================= FILTRO PERFIL =================

def eh_perfil(texto: str):
    texto = texto.lower()

    pontos = 0
    if "classe:" in texto: pontos += 1
    if "lv" in texto: pontos += 1
    if "hp:" in texto: pontos += 1
    if "energia:" in texto: pontos += 1

    return pontos >= 3


# ================= EXTRAIR NOME =================

def extrair_nome(texto):
    linhas = texto.split("\n")

    for linha in linhas:
        if "lv" in linha.lower():
            match = re.search(r"\]\s*(.+)", linha)
            if match:
                return match.group(1).strip().upper()

    return None


# ================= BANCO =================

def registrar_membro(nome):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO membros VALUES (%s) ON CONFLICT DO NOTHING",
            (nome,)
        )


def salvar_presenca(nome):
    hoje = date.today()

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO presencas VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (nome, hoje))


def ja_marcou(nome):
    hoje = date.today()

    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM presencas WHERE nome=%s AND data=%s
        """, (nome, hoje))
        return cur.fetchone() is not None


def gerar_faltas():
    hoje = date.today()

    with conn.cursor() as cur:
        cur.execute("SELECT nome FROM membros")
        membros = [x[0] for x in cur.fetchall()]

        cur.execute("SELECT nome FROM presencas WHERE data=%s", (hoje,))
        presentes = [x[0] for x in cur.fetchall()]

        faltantes = set(membros) - set(presentes)

        for nome in faltantes:
            cur.execute("""
                INSERT INTO faltas VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (nome, hoje))


def resumo_dia():
    hoje = date.today()

    with conn.cursor() as cur:
        cur.execute("SELECT nome FROM presencas WHERE data=%s", (hoje,))
        presentes = [x[0] for x in cur.fetchall()]

        cur.execute("SELECT nome FROM faltas WHERE data=%s", (hoje,))
        faltantes = [x[0] for x in cur.fetchall()]

    texto = "📊 PRESENÇA DO DIA\n\n"

    texto += "✅ Presentes:\n"
    for p in sorted(presentes):
        texto += f"✔ {p}\n"

    texto += "\n❌ Faltaram:\n"
    for f in sorted(faltantes):
        texto += f"✖ {f}\n"

    return texto


# ================= HANDLER =================

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    # 👇 FILTRO DE ORIGEM (CLÃ)
    if msg.chat.id != GRUPO_CLAN:
        return

    if msg.message_thread_id != TOPICO_PRESENCA:
        return

    texto = msg.text or ""

    if not eh_perfil(texto):
        return

    nome = extrair_nome(texto)
    if not nome:
        return

    registrar_membro(nome)

    if ja_marcou(nome):
        return

    salvar_presenca(nome)

    # 👇 ENVIA PARA LIDERANÇA
    await context.bot.send_message(
        chat_id=GRUPO_LIDER,
        message_thread_id=TOPICO_LISTA,
        text=f"✅ Presença: {nome}"
    )


# ================= AGENDAMENTO =================

async def tarefa_diaria(app):
    while True:
        agora = datetime.now()

        if agora.hour == 23 and agora.minute == 59:
            gerar_faltas()

            texto = resumo_dia()

            await app.bot.send_message(
                chat_id=GRUPO_LIDER,
                message_thread_id=TOPICO_LISTA,
                text=texto
            )

            await asyncio.sleep(60)

        await asyncio.sleep(20)


# ================= MAIN =================

async def main():
    criar_tabelas()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT, detectar))

    asyncio.create_task(tarefa_diaria(app))

    print("🚀 Bot rodando...")

    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
