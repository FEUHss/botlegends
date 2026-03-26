import re
import sqlite3
import unicodedata
import os
import asyncio
from datetime import time
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN não encontrado")

print("👑 BOT INICIANDO...")

# =========================
# CONFIG
# =========================
LIDER_ID = -1003806440152
PRESENCA_ID = "16325"
TASKS_ID = "48"
LOOTS_ID = "19"

# =========================
# BANCO
# =========================
conn = sqlite3.connect("legends.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
nome TEXT PRIMARY KEY,
classe TEXT,
nivel INTEGER,
atk INTEGER,
def INTEGER,
hp INTEGER,
crit INTEGER,
xp INTEGER,
last_xp INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS presenca (
nome TEXT,
data TEXT,
status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS missoes (
nome TEXT,
pontos INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS historico (
nome TEXT,
xp INTEGER,
data TEXT
)
""")

conn.commit()

missao_ativa = False

# =========================
# FUNÇÕES
# =========================
def normalizar_nome(texto):
    linha = texto.split("\n")[0]
