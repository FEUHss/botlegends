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

def extrair_xp(texto):
    for linha in texto.split("\n"):
        if "XP" in linha:
            numeros = re.findall(r"\d+", linha.replace(".", "").replace(",", ""))
            if len(numeros) >= 2:
                return int(numeros[1])
    return None

def extrair_nivel(texto):
    for linha in texto.split("\n"):
        if "Lv" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros:
                return int(numeros[0])
    return None

# ================= STATUS =================

def extrair_status(texto):
    dados = {}

    for linha in texto.split("\n"):
        linha = linha.strip()

        if "/" in linha:
            continue

        if "ATK" in linha and "DEF" in linha and "CRIT" in linha:
            numeros = re.findall(r"\d+\.?\d*", linha.replace(",", "."))
            if len(numeros) >= 3:
                dados["atk"] = float(numeros[0])
                dados["def"] = float(numeros[1])
                dados["crit"] = float(numeros[2])

        elif "HP:" in linha:
            match = re.search(r"(\d+)\s*/\s*(\d+)", linha)
            if match:
                dados["hp"] = int(match.group(2))

        elif "Gold:" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros:
                dados["gold"] = int(numeros[0])

        elif "Tofus:" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros:
                dados["tofus"] = int(numeros[0])

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
    cur.execute("SELECT 1 FROM presencas WHERE nome=%s AND data=%s", (nome, hoje()))
    if cur.fetchone():
        return False

    cur.execute("INSERT INTO presencas (nome, data) VALUES (%s,%s)", (nome, hoje()))
    conn.commit()
    return True

def salvar_xp(nome, xp, nivel):
    if xp is None:
        return

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO xp_logs (nome, xp, nivel, data)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (nome, data)
        DO UPDATE SET 
            xp = EXCLUDED.xp,
            nivel = EXCLUDED.nivel
    """, (nome, xp, nivel, hoje()))
    conn.commit()

def salvar_status(nome, dados):
    if not dados:
        return

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO status
        (nome, data, atk, def, crit, hp, gold, tofus)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (nome, data)
        DO UPDATE SET
            atk=EXCLUDED.atk,
            def=EXCLUDED.def,
            crit=EXCLUDED.crit,
            hp=EXCLUDED.hp,
            gold=EXCLUDED.gold,
            tofus=EXCLUDED.tofus
    """, (
        nome,
        hoje(),
        dados.get("atk"),
        dados.get("def"),
        dados.get("crit"),
        dados.get("hp"),
        dados.get("gold"),
        dados.get("tofus"),
    ))
    conn.commit()

# ================= XP =================

def get_rank_xp():
    cur = conn.cursor()
    cur.execute("""
        SELECT nome, nivel, xp FROM xp_logs
        WHERE data=%s
        ORDER BY xp DESC
    """, (hoje(),))

    dados = cur.fetchall()

    if not dados:
        return "Sem dados de XP hoje."

    texto = "🏆 RANKING XP\n\n"
    for i, (nome, nivel, xp) in enumerate(dados, 1):
        texto += f"{i}. {nome} — Lv {nivel} - {xp} XP\n"

    return texto

def get_evolucao(nome):
    cur = conn.cursor()
    cur.execute("""
        SELECT xp, data FROM xp_logs
        WHERE nome=%s
        ORDER BY data DESC
        LIMIT 2
    """, (nome,))

    dados = cur.fetchall()

    if len(dados) < 2:
        return f"Dados insuficientes para evolução de {nome}"

    xp_hoje, _ = dados[0]
    xp_ontem, _ = dados[1]

    diff = xp_hoje - xp_ontem
    simbolo = "📈" if diff > 0 else "📉" if diff < 0 else "➖"

    return f"{simbolo} {nome}\nXP: {xp_hoje}\nVariação: {diff:+}"

# ================= RANK (CORRIGIDO) =================

def gerar_rank(campo, titulo):
    cur = conn.cursor()

    cur.execute(f"""
        SELECT nome, {campo}
        FROM status
        WHERE data=%s
        AND {campo} IS NOT NULL
        ORDER BY {campo} DESC
    """, (hoje(),))

    dados = cur.fetchall()

    if not dados:
        return f"Sem dados de {titulo} hoje."

    texto = f"🏆 RANKING {titulo}\n\n"
    for i, (nome, valor) in enumerate(dados, 1):
        texto += f"{i}. {nome} — {valor}\n"

    return texto

# ================= COMANDOS =================

async def comando_lista(update, context):
    await update.message.reply_text(gerar_texto_painel())

async def comando_xp(update, context):
    args = context.args
    if not args:
        await update.message.reply_text(get_rank_xp())
    else:
        nome = limpar_nome(" ".join(args))
        await update.message.reply_text(get_evolucao(nome))

async def rank_atk(update, context):
    await update.message.reply_text(gerar_rank("atk", "ATAQUE"))

async def rank_def(update, context):
    await update.message.reply_text(gerar_rank("def", "DEFESA"))

async def rank_hp(update, context):
    await update.message.reply_text(gerar_rank("hp", "HP"))

async def rank_crit(update, context):
    await update.message.reply_text(gerar_rank("crit", "CRÍTICO"))

async def rank_gold(update, context):
    await update.message.reply_text(gerar_rank("gold", "GOLD"))

async def rank_tofus(update, context):
    await update.message.reply_text(gerar_rank("tofus", "TOFUS"))

async def rank_nivel(update, context):
    await update.message.reply_text(gerar_rank("nivel", "NÍVEL"))

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("lista", comando_lista))
    app.add_handler(CommandHandler("xp", comando_xp))

    app.add_handler(CommandHandler("atk", rank_atk))
    app.add_handler(CommandHandler("def", rank_def))
    app.add_handler(CommandHandler("hp", rank_hp))
    app.add_handler(CommandHandler("crit", rank_crit))
    app.add_handler(CommandHandler("gold", rank_gold))
    app.add_handler(CommandHandler("tofu", rank_tofus))
    app.add_handler(CommandHandler("level", rank_nivel))

    app.add_handler(MessageHandler(filters.TEXT | filters.CaptionRegex(".*"), detectar))

    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.start()

    print("🚀 BOT FINAL COMPLETO (RANK LIMPO + SEM NONE)")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
