import os
import re
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")

print("TOKEN LIDO:", TOKEN)

if not TOKEN:
    raise Exception("TOKEN não encontrado")

# 🔥 ID esperado (mas não bloqueia mais)
TOPICO_PRESENCA_ID = 16325

# =========================
# HAND
