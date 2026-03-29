import os
import re
import psycopg2
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler

TOKEN = os.getenv("TOKEN")

# IDs
GRUPO_PRESENCA = -1003792787717
TOPICO_PRESENCA = 16325

GRUPO_LIDERANCA = -1003806440152

# conexão banco
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()


# =========================
# BANCO
# =========================

def registrar_membro(nome):
    try:
        cur.execute(
            "INSERT INTO membros (nome) VALUES (%s) ON CONFLICT DO NOTHING",
            (nome,)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("ERRO registrar_membro:", e)


def salvar_presenca(nome):
    hoje = datetime.now().date()
    try:
        cur.execute(
            "INSERT INTO presencas (nome, data) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (nome, hoje)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print("ERRO salvar_presenca:", e)
        return False


# =========================
# FILTRO DE PERFIL
# =========================

def eh_perfil(texto: str):
    return (
        "Classe:" in texto and
        "Lv" in texto and
        "HP:" in texto
    )


# =========================
# EXTRAIR NOME (ROBUSTO)
# =========================

def extrair_nome(texto: str):
    try:
        linhas = texto.split("\n")[0]

        # remove emojis iniciais
        linhas = re.sub(r"^[^\w\[]+", "", linhas)

        # remove nível (ex: 37)
        linhas = re.sub(r"^\d+\s*", "", linhas)

        # remove classe emoji tipo 🏹 🛡️ 💫
        linhas = re.sub(r"[^\w\s\[\],]", "", linhas)

        # remove "Classe" se colado
        linhas = linhas.split("Classe")[0]

        nome = linhas.strip()

        # remove prefixos tipo [LG]
        nome = re.sub(r"\[.*?\]\s*", "", nome)

        return nome.upper()
    except:
        return None


# =========================
# DETECTOR DE MENSAGEM
# =========================

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg or not msg.text:
        return

    # 🔥 FILTRO DE GRUPO
    if msg.chat_id != GRUPO_PRESENCA:
        return

    # 🔥 FILTRO DE TÓPICO
    if msg.message_thread_id != TOPICO_PRESENCA:
        return

    texto = msg.text

    print("🔥 CHEGOU MENSAGEM")

    # 🔒 FILTRO DE PERFIL (ESSENCIAL)
    if not eh_perfil(texto):
        print("❌ Ignorado (não é perfil)")
        return

    nome = extrair_nome(texto)

    if not nome:
        print("❌ Não encontrou nome")
        return

    print(f"✅ Nome: {nome}")

    registrar_membro(nome)

    if salvar_presenca(nome):
        await msg.reply_text(f"✅ Presença: {nome}")
    else:
        print("⚠️ Já registrado hoje")


# =========================
# COMANDO PRESENÇA
# =========================

async def presenca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GRUPO_LIDERANCA:
        return

    hoje = datetime.now().date()

    cur.execute("SELECT nome FROM presencas WHERE data = %s ORDER BY nome", (hoje,))
    presentes = [r[0] for r in cur.fetchall()]

    if not presentes:
        await update.message.reply_text("📭 Ninguém marcou presença hoje.")
        return

    texto = "📋 Presença de hoje:\n\n"
    texto += "\n".join([f"✅ {n}" for n in presentes])

    await update.message.reply_text(texto)


# =========================
# COMANDO MENSAL
# =========================

async def mensal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GRUPO_LIDERANCA:
        return

    mes = datetime.now().month
    ano = datetime.now().year

    cur.execute("""
        SELECT nome, COUNT(*) 
        FROM presencas 
        WHERE EXTRACT(MONTH FROM data) = %s
        AND EXTRACT(YEAR FROM data) = %s
        GROUP BY nome
        ORDER BY COUNT(*) DESC
    """, (mes, ano))

    dados = cur.fetchall()

    if not dados:
        await update.message.reply_text("📭 Sem dados no mês.")
        return

    texto = "📊 Presença mensal:\n\n"

    for nome, total in dados:
        texto += f"👤 {nome} → {total} dias\n"

    await update.message.reply_text(texto)


# =========================
# MAIN
# =========================

def main():
    print("🚀 Bot presença inteligente rodando...")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT, detectar))
    app.add_handler(CommandHandler("presenca", presenca))
    app.add_handler(CommandHandler("mensal", mensal))

    app.run_polling()


if __name__ == "__main__":
    main()
