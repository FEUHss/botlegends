import os
import psycopg2
import random
import pytz
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
            partes = linha.replace("%", "").split()
            dados["atk"] = float(partes[1])
            dados["def"] = float(partes[3])
            dados["crit"] = float(partes[5])

        elif "HP:" in linha:
            dados["hp"] = int(linha.split()[1].split("/")[0])

        elif "Gold:" in linha:
            dados["gold"] = int(linha.split()[1])

        elif "Tofus:" in linha:
            dados["tofus"] = int(linha.split()[1])

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
    hoje_ = hoje()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM presencas WHERE nome=%s AND data=%s", (nome, hoje_))
    if cur.fetchone():
        return False

    cur.execute("INSERT INTO presencas (nome, data) VALUES (%s,%s)", (nome, hoje_))
    conn.commit()
    return True

def salvar_status(nome, dados):
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO status 
        (nome, nivel, classe, atk, def, crit, hp, gold, tofus, data)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (nome, data)
        DO UPDATE SET
            nivel=EXCLUDED.nivel,
            classe=EXCLUDED.classe,
            atk=EXCLUDED.atk,
            def=EXCLUDED.def,
            crit=EXCLUDED.crit,
            hp=EXCLUDED.hp,
            gold=EXCLUDED.gold,
            tofus=EXCLUDED.tofus
    """, (
        nome,
        dados.get("nivel"),
        dados.get("classe"),
        dados.get("atk"),
        dados.get("def"),
        dados.get("crit"),
        dados.get("hp"),
        dados.get("gold"),
        dados.get("tofus"),
        hoje()
    ))

    conn.commit()

# ================= RANK =================

def gerar_rank(campo):
    cur = conn.cursor()

    cur.execute(f"""
        SELECT nome, {campo}
        FROM status
        WHERE data=%s
        ORDER BY {campo} DESC
        LIMIT 10
    """, (hoje(),))

    resultados = cur.fetchall()

    if not resultados:
        return "Sem dados ainda."

    texto = f"🏆 RANKING {campo.upper()}\n\n"

    for i, (nome, valor) in enumerate(resultados, 1):
        texto += f"{i}. {nome} — {valor}\n"

    return texto

# ================= PAINEL =================

def gerar_texto_painel():
    hoje_ = hoje()
    cur = conn.cursor()

    cur.execute("SELECT nome FROM membros")
    membros = [m[0] for m in cur.fetchall()]

    cur.execute("SELECT nome FROM presencas WHERE data=%s", (hoje_,))
    presentes = [p[0] for p in cur.fetchall()]

    faltantes = sorted(set(membros) - set(presentes))
    presentes = sorted(presentes)

    texto = f"📜 PRESENÇA — {hoje_.strftime('%d/%m')}\n\n"

    texto += "🟢 Presentes:\n"
    texto += "\n".join([f"✅ {n}" for n in presentes]) if presentes else "Ninguém ainda"

    texto += "\n\n🔴 Ausentes:\n"
    texto += "\n".join([f"❌ {n}" for n in faltantes]) if faltantes else "Nenhum"

    texto += f"\n\n📊 {len(presentes)}/{len(membros)}"

    return texto

async def atualizar_painel(app):
    hoje_ = hoje()
    cur = conn.cursor()

    cur.execute("SELECT message_id FROM painel WHERE data=%s", (hoje_,))
    result = cur.fetchone()

    if not result:
        await criar_painel(app)
        return

    message_id = result[0]
    texto = gerar_texto_painel()

    try:
        await app.bot.edit_message_text(
            chat_id=GRUPO_LIDERANCA,
            message_id=message_id,
            text=texto
        )
    except Exception as e:
        print("Erro painel:", e)

async def criar_painel(app):
    msg = await app.bot.send_message(
        chat_id=GRUPO_LIDERANCA,
        text=gerar_texto_painel(),
        message_thread_id=TOPICO_PAINEL
    )

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO painel (data, message_id)
        VALUES (%s, %s)
        ON CONFLICT (data)
        DO UPDATE SET message_id = EXCLUDED.message_id
    """, (hoje(), msg.message_id))
    conn.commit()

# ================= COMANDOS =================

async def comando_lista(update, context):
    await update.message.reply_text(gerar_texto_painel())

async def rank_atk(update, context):
    await update.message.reply_text(gerar_rank("atk"))

async def rank_def(update, context):
    await update.message.reply_text(gerar_rank("def"))

async def rank_crit(update, context):
    await update.message.reply_text(gerar_rank("crit"))

async def rank_lvl(update, context):
    await update.message.reply_text(gerar_rank("nivel"))

async def rank_gold(update, context):
    await update.message.reply_text(gerar_rank("gold"))

async def rank_tofus(update, context):
    await update.message.reply_text(gerar_rank("tofus"))

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

    app.add_handler(CommandHandler("lista", comando_lista))

    app.add_handler(CommandHandler("rank_atk", rank_atk))
    app.add_handler(CommandHandler("rank_def", rank_def))
    app.add_handler(CommandHandler("rank_crit", rank_crit))
    app.add_handler(CommandHandler("rank_lvl", rank_lvl))
    app.add_handler(CommandHandler("rank_gold", rank_gold))
    app.add_handler(CommandHandler("rank_tofus", rank_tofus))

    app.add_handler(MessageHandler(filters.TEXT | filters.CaptionRegex(".*"), detectar))

    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.start()

    print("🚀 Bot com ranking rodando")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
