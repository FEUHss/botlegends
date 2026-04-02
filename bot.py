import os
import psycopg2
import random
import pytz
import re
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

GRUPO_ID = -1003792787717
TOPICO_PRESENCA = 16325

GRUPO_LIDERANCA = -1003806440152
TOPICO_PAINEL = 116

conn = psycopg2.connect(DATABASE_URL)
tz = pytz.timezone("America/Sao_Paulo")

painel_msg_id = None
painel_data = None

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

        if linha.startswith("+"):
            continue

        if "/" in linha and "HP" not in linha:
            continue

        if "ATK" in linha and "DEF" in linha and "CRIT" in linha:
            numeros = re.findall(r"\d+\.?\d*", linha.replace(",", "."))
            if len(numeros) >= 3:
                dados["atk"] = float(numeros[0])
                dados["def"] = float(numeros[1])
                dados["crit"] = float(numeros[2])

        elif "HP" in linha:
            match = re.search(r"(\d+)\s*/\s*(\d+)", linha)
            if match:
                dados["hp"] = int(match.group(2))
            else:
                numeros = re.findall(r"\d+", linha)
                if numeros:
                    dados["hp"] = int(numeros[-1])

        elif "Gold:" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros:
                dados["gold"] = int(numeros[0])

        elif "Tofus:" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros:
                dados["tofus"] = int(numeros[0])

    return dados

# ================= FRASES =================

def mensagem_pilar(nome):
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
        DO UPDATE SET xp = EXCLUDED.xp, nivel = EXCLUDED.nivel
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

# ================= WIKI =================

def salvar_monstro(nome, hp):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO monstros (nome, hp)
        VALUES (%s, %s)
        ON CONFLICT (nome)
        DO UPDATE SET hp = EXCLUDED.hp
    """, (nome, hp))
    conn.commit()

def atualizar_monstro(nome, xp, gold, tipo, mapa):
    cur = conn.cursor()
    cur.execute("""
        UPDATE monstros
        SET xp=%s, gold=%s, tipo=%s, mapa=%s
        WHERE nome=%s
    """, (xp, gold, tipo, mapa, nome))
    conn.commit()

def buscar_monstro(nome):
    cur = conn.cursor()
    cur.execute("""
        SELECT nome, hp, xp, gold, tipo, mapa
        FROM monstros
        WHERE nome=%s
    """, (nome,))
    return cur.fetchone()

# 🔥 CORREÇÃO AQUI (GENÉRICA)
def extrair_monstro(texto):
    nome = None
    hp = None

    for linha in texto.split("\n"):
        linha = linha.strip()

        # HP
        if "HP" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros:
                hp = int(numeros[-1])

        # Nome do monstro (linha limpa, sem números e sem palavras do player)
        if (
            not nome
            and len(linha) < 30
            and not any(p in linha.lower() for p in ["combate", "você", "energia", "turno"])
            and not re.search(r"\d", linha)
        ):
            nome = linha.upper()

    return nome, hp

async def detectar_privado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg:
        return

    texto = msg.text or msg.caption
    if not texto:
        return

    nome, hp = extrair_monstro(texto)

    if not nome or not hp:
        return

    salvar_monstro(nome, hp)

    await msg.reply_text(f"📚 Monstro salvo:\n{nome} — HP {hp}")

async def comando_addmob(update, context):
    try:
        nome = limpar_nome(context.args[0])
        xp = int(context.args[1])
        gold = int(context.args[2])
        tipo = context.args[3]
        mapa = context.args[4]

        atualizar_monstro(nome, xp, gold, tipo, mapa)

        await update.message.reply_text(f"✅ {nome} atualizado!")

    except:
        await update.message.reply_text("Uso:\n/addmob Nome XP GOLD tipo mapa")

async def comando_mob(update, context):
    nome = limpar_nome(" ".join(context.args))
    dados = buscar_monstro(nome)

    if not dados:
        await update.message.reply_text("❌ Monstro não encontrado.")
        return

    nome, hp, xp, gold, tipo, mapa = dados

    texto = f"📚 {nome}\n❤️ HP: {hp}\n"

    if xp:
        texto += f"✨ XP: {xp}\n"
    if gold:
        texto += f"💰 Gold: {gold}\n"
    if tipo:
        texto += f"⚔️ Tipo: {tipo}\n"
    if mapa:
        texto += f"🗺️ Mapa: {mapa}\n"

    await update.message.reply_text(texto)

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("addmob", comando_addmob))
    app.add_handler(CommandHandler("mob", comando_mob))

    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CaptionRegex(".*")) & filters.ChatType.PRIVATE,
            detectar_privado
        )
    )

    print("🚀 BOT COM WIKI FUNCIONANDO")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
