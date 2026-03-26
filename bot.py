import os
import re
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL não encontrado")

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS perfis (user_id BIGINT PRIMARY KEY, nome TEXT, level INT, xp TEXT, atk TEXT, defesa TEXT, crit TEXT, hp TEXT, gold TEXT, tofu TEXT)")
conn.commit()

TOPICO_PRESENCA = 16325


def extrair_dados(texto):
    try:
        linhas = texto.split("\n")

        nome = linhas[0]

        level = re.search(r"Lv (\d+)", texto)
        xp = re.search(r"XP: ([\d]+)", texto)
        atk = re.search(r"ATK (\d+)", texto)
        defesa = re.search(r"DEF ([\d\.]+)", texto)
        crit = re.search(r"CRIT (\d+%)", texto)
        hp = re.search(r"
