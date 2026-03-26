import os
import re
import sqlite3
import unicodedata
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise Exception("TOKEN não encontrado")

# 🔥 ID DO TÓPICO PRESENÇA
TOPICO_PRESENCA_ID = 16325

# =========================
# BANCO
# =========================
conn = sqlite3.connect("legends.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
nome TEXT PRIMARY KEY,
nivel INTEGER,
xp INTEGER,
atk INTEGER,
def REAL,
crit INTEGER,
hp INTEGER,
gold INTEGER,
tofu INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS presenca (
nome TEXT,
data TEXT,
PRIMARY KEY(nome, data)
)
""")

conn.commit()

# =========================
# LIMPAR NOME
# =========================
def limpar_nome(texto):
    linha = texto.split("\n")[0]

    linha = unicodedata.normalize("NFD", linha)
    linha = linha.encode("ascii","ignore").decode()

    linha = re.sub(r".*?", "", linha)
    linha = re.sub(r"\d+", "", linha)
    linha = re.sub(r"[^\w\s]", "", linha)

    return linha.strip().upper()

# =========================
# EXTRAIR PERFIL
# =========================
def extrair(texto):
    try:
        return {
            "nome": limpar_nome(texto),
            "nivel": int(re.search(r"Lv\s*(\d+)", texto).group(1)),
            "xp": int(re.search(r"XP:\s*(\d+)", texto).group(1)),
            "atk": int(re.search(r"ATK\s*(\d+)", texto).group(1)),
            "def": float(re.search(r"DEF\s*([\d\.]+)", texto).group(1)),
            "crit": int(re.search(r"CRIT\s*(\d+)", texto).group(1)),
            "hp": int(re.search(r"HP:\s*\d+/(\d+)", texto).group(1)),
            "gold": int(re.search(r"Gold:\s*(\d+)", texto).group(1)),
            "tofu": int(re.search(r"Tofus:\s*(\d+)", texto).group(1))
        }
    except:
        return None

# =========================
# SALVAR PLAYER
# =========================
def salvar_player(d):
    cursor.execute("""
    INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(nome)
