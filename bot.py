import os
import psycopg2
import random
import pytz
import re
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
                return limpar_nome(" ".join(partes[i + 1:]))
    return None

# 🔥 EXTRAÇÃO SEGURA DE XP
def extrair_xp(texto):
    match = re.search(r'XP:\s*([\d\.]+)', texto)
    if match:
        return int(match.group(1).replace(".", ""))
    return None

def extrair_status(texto):
    dados = {}

    for linha in texto.split("\n"):

        if "Classe:" in linha:
            dados["classe"] = linha.split(":")[1].strip()

        elif "Lv" in linha:
            partes = linha.split()
            for i, p in enumerate(partes):
                if p == "Lv":
                    dados["nivel"] = int(partes[i + 1])

        elif "ATK" in linha:
            nums = re.findall(r'[\d.]+', linha)
            if len(nums) >= 3:
                dados["atk"] = float(nums[0])
                dados["def"] = float(nums[1])
                dados["crit"] = float(nums[2])

        elif "HP:" in linha:
            dados["hp"] = int(re.findall(r'\d+', linha)[0])

        elif "Gold:" in linha:
            dados["gold"] = int(re.findall(r'\d+', linha)[0])

        elif "Tofus:" in linha:
            dados["tofus"] = int(re.findall(r'\d+', linha)[0])

    dados["xp"] = extrair_xp(texto)

    return dados

def mensagem_pilar(nome):
    return random.choice([
        f"📜 O Pilar registra: {nome} esteve presente.",
        f"🗿 O Pilar da Sabedoria reconhece {nome}.",
        f"✨ A presença de {nome} foi gravada no Pilar.",
        f"👑 O Pilar eterniza: {nome} marcou presença.",
        f"🔥 Feixes dourados registram a presença de {nome}.",
        f"🧠 O conhecimento do Pilar agora carrega o nome de {nome}.",
        f"⚡ Registrado: {nome}"
    ])

# ================= BANCO =================

def registrar_membro(nome):
    cur = conn.cursor()
    cur.execute("INSERT INTO membros (nome) VALUES (%s) ON CONFLICT DO NOTHING", (nome,))
    conn.commit()

def salvar_presenca(nome):
    cur = conn.cursor()
    if cur.execute("SELECT 1 FROM presencas WHERE nome=%s AND data=%s", (nome, hoje())):
        pass
    cur.execute("SELECT 1 FROM presencas WHERE nome=%s AND data=%s", (nome, hoje()))
    if cur.fetchone():
        return False

    cur.execute("INSERT INTO presencas (nome, data) VALUES (%s,%s)", (nome, hoje()))
    conn.commit()
    return True

def salvar_status(nome, dados):
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO status
        (nome, data, nivel, classe, atk, def, crit, hp, gold, tofus, xp)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (nome, data)
        DO UPDATE SET
            nivel=EXCLUDED.nivel,
            classe=EXCLUDED.classe,
            atk=EXCLUDED.atk,
            def=EXCLUDED.def,
            crit=EXCLUDED.crit,
            hp=EXCLUDED.hp,
            gold=EXCLUDED.gold,
            tofus=EXCLUDED.tofus,
            xp=EXCLUDED.xp
    """, (
        nome, hoje(),
        dados.get("nivel"),
        dados.get("classe"),
        dados.get("atk"),
        dados.get("def"),
        dados.get("crit"),
        dados.get("hp"),
        dados.get("gold"),
        dados.get("tofus"),
        dados.get("xp")
    ))

    # XP LOG
    if dados.get("xp"):
        cur.execute("""
            INSERT INTO xp_log (nome, data, xp)
            VALUES (%s,%s,%s)
            ON CONFLICT (nome, data)
            DO UPDATE SET xp=EXCLUDED.xp
        """, (nome, hoje(), dados["xp"]))

    conn.commit()

# ================= EVOLUÇÃO =================

def calcular_evolucao(nome):
    cur = conn.cursor()

    cur.execute("""
        SELECT data, xp FROM xp_log
        WHERE nome=%s
        ORDER BY data DESC
        LIMIT 2
    """, (nome,))

    dados = cur.fetchall()

    if len(dados) < 2:
        return "Sem histórico suficiente."

    hoje_xp = dados[0][1]
    ontem_xp = dados[1][1]

    diff = hoje_xp - ontem_xp

    simbolo = "📈" if diff > 0 else "💀" if diff < 0 else "😐"

    return f"{simbolo} {nome}\n\nHoje: {hoje_xp}\nAntes: {ontem_xp}\n\nDiferença: {diff}"

# ================= RANK =================

def gerar_rank(campo):
    cur = conn.cursor()

    cur.execute(f"""
        SELECT nome, {campo}
        FROM status
        WHERE data=%s
        ORDER BY {campo} DESC NULLS LAST
    """, (hoje(),))

    dados = cur.fetchall()

    texto = f"🏆 RANK {campo.upper()}\n\n"

    for i, (nome, valor) in enumerate(dados, 1):
        texto += f"{i}. {nome} — {valor}\n"

    return texto or "Sem dados"

# ================= XP =================

async def comando_evolucao(update, context):
    nome = " ".join(context.args).upper()
    await update.message.reply_text(calcular_evolucao(nome))

async def comando_xphistory(update, context):
    nome = " ".join(context.args).upper()
    cur = conn.cursor()

    cur.execute("""
        SELECT data, xp FROM xp_log
        WHERE nome=%s
        ORDER BY data DESC
        LIMIT 10
    """, (nome,))

    dados = cur.fetchall()

    if not dados:
        await update.message.reply_text("Sem histórico.")
        return

    texto = f"📜 XP HISTORY — {nome}\n\n"

    for d, xp in dados:
        texto += f"{d.strftime('%d/%m')} — {xp}\n"

    await update.message.reply_text(texto)

async def rank_xp(update, context):
    await update.message.reply_text(gerar_rank("xp"))

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
        dados = extrair_status(texto)
        salvar_status(nome, dados)

        await msg.reply_text(mensagem_pilar(nome))
        await atualizar_painel(context.application)

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("evolucao", comando_evolucao))
    app.add_handler(CommandHandler("xphistory", comando_xphistory))
    app.add_handler(CommandHandler("rankxp", rank_xp))

    app.add_handler(CommandHandler("level", lambda u,c: u.message.reply_text(gerar_rank("nivel"))))
    app.add_handler(CommandHandler("ataque", lambda u,c: u.message.reply_text(gerar_rank("atk"))))
    app.add_handler(CommandHandler("def", lambda u,c: u.message.reply_text(gerar_rank("def"))))
    app.add_handler(CommandHandler("hp", lambda u,c: u.message.reply_text(gerar_rank("hp"))))
    app.add_handler(CommandHandler("gold", lambda u,c: u.message.reply_text(gerar_rank("gold"))))
    app.add_handler(CommandHandler("tofu", lambda u,c: u.message.reply_text(gerar_rank("tofus"))))

    app.add_handler(MessageHandler(filters.TEXT | filters.CaptionRegex(".*"), detectar))

    print("🚀 BOT COM SISTEMA COMPLETO RODANDO")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
