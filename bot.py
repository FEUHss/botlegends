import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("❌ TOKEN não encontrado no Railway")

GRUPO_ID = -1003792787717
TOPICO_PRESENCA = 16325

# ==========================================

logging.basicConfig(level=logging.INFO)


# 🔹 LIMPAR NOME
def limpar_nome(nome):
    return (
        nome.replace("[LG]", "")
        .replace("*", "")
        .replace("_", "")
        .replace("`", "")
        .strip()
        .upper()
    )


# 🔹 EXTRAIR NOME (VERSÃO MELHORADA)
def extrair_nome(texto):
    try:
        linhas = texto.split("\n")

        for linha in linhas:
            if "📜" in linha:
                partes = linha.split()

                for i, parte in enumerate(partes):
                    if parte.isdigit():
                        nome = " ".join(partes[i + 1:])
                        return limpar_nome(nome)

        return
