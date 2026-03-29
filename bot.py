import os
import re
import random
import psycopg2
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ================== CONFIG ==================

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

GRUPO_ORIGEM = -1003792787717
TOPICO_PRESENCA = 16325

GRUPO_DESTINO = -1003806440152
TOPICO_LISTA = 116

# ================== BANCO ==================

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS presencas (
    nome TEXT,
    data DATE,
    PRIMARY KEY (nome, data)
)
""")
conn.commit()

# ================== FRASES DO PILAR ==================

def gerar_confirmacao(nome):
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

# ================== FUNÇÕES ==================

def extrair_nome(texto):
    if not texto:
        return None

    # pega padrões comuns do Teletofus
    padrao = re.search(r"\d+\s+LG\s*([A-Za-zÀ-ÿ0-9_ ]+)", texto)
    if padrao:
        return padrao.group(1).strip()

    # fallback mais flexível
    padrao2 = re.search(r"\d+\s+([A-Za-zÀ-ÿ0-9_ ]+)", texto)
    if padrao2:
        return padrao2.group(1).strip()

    return None


def salvar_presenca(nome):
    hoje = datetime.utcnow().date()

    try:
        cur.execute(
            "INSERT INTO presencas (nome, data) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (nome, hoje)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print("ERRO AO SALVAR:", e)
        return False


# ================== HANDLER ==================

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    # 🔒 filtra grupo correto
    if update.effective_chat.id != GRUPO_ORIGEM:
        return

    # 🔒 filtra tópico correto
    if update.message.message_thread_id != TOPICO_PRESENCA:
        return

    texto = update.message.text or update.message.caption or ""
