import re
import sqlite3
import unicodedata
import random
import os
from datetime import time
from telegram.ext import Application, MessageHandler, CommandHandler, filters

# 🔥 TOKEN PELO RAILWAY
TOKEN = os.getenv("TOKEN")

GRUPO_ID = -1003792787717
LIDER_ID = -1003806440152

PRESENCA_ID = "16325"
TASKS_ID = "48"
LOOTS_ID = "19"

conn = sqlite3.connect("legends.db", check_same_thread=False)
cursor = conn.cursor()

# =========================
# BANCO
# =========================
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
# NORMALIZAR NOME
# =========================
def normalizar_nome(texto):
    linha = texto.split("\n")[0]
    linha = unicodedata.normalize("NFD", linha).encode("ascii","ignore").decode()
    linha = re.sub(r"\[.*?\]", "", linha)
    linha = re.sub(r"\d+", "", linha)
    linha = re.sub(r"[^\w\s]", "", linha)
    return linha.strip().upper()

def pode(update):
    return update.effective_chat.id == LIDER_ID or update.effective_chat.type == "private"

# =========================
# EXTRAIR PERFIL
# =========================
def extrair(texto):
    try:
        return {
            "nome": normalizar_nome(texto),
            "classe": re.search(r"Classe:\s*(\w+)", texto).group(1).lower(),
            "nivel": int(re.search(r"Lv\s*(\d+)", texto).group(1)),
            "atk": int(re.search(r"ATK\s*(\d+)", texto).group(1)),
            "def": int(re.search(r"DEF\s*(\d+)", texto).group(1)),
            "hp": int(re.search(r"HP:\s*\d+/(\d+)", texto).group(1)),
            "crit": int(re.search(r"CRIT\s*(\d+)", texto).group(1)),
            "xp": int(re.search(r"XP:\s*(\d+)", texto).group(1)),
        }
    except:
        return None

# =========================
# SALVAR PLAYER + HISTÓRICO
# =========================
def salvar(d):
    if not d:
        return

    cursor.execute("SELECT xp FROM players WHERE nome=?", (d["nome"],))
    r = cursor.fetchone()
    last = r[0] if r else d["xp"]

    cursor.execute("""
    INSERT INTO players VALUES (?,?,?,?,?,?,?,?,?)
    ON CONFLICT(nome) DO UPDATE SET
    classe=?,nivel=?,atk=?,def=?,hp=?,crit=?,xp=?,last_xp=?
    """, (
        d["nome"], d["classe"], d["nivel"], d["atk"], d["def"],
        d["hp"], d["crit"], d["xp"], last,
        d["classe"], d["nivel"], d["atk"], d["def"],
        d["hp"], d["crit"], d["xp"], last
    ))

    cursor.execute(
        "INSERT INTO historico VALUES (?, ?, datetime('now'))",
        (d["nome"], d["xp"])
    )

    conn.commit()

# =========================
# PRESENÇA
# =========================
def registrar_presenca(nome):
    cursor.execute("SELECT * FROM presenca WHERE nome=? AND data=date('now')", (nome,))
    if cursor.fetchone():
        return False

    cursor.execute("INSERT INTO presenca VALUES (?,date('now'),'P')", (nome,))
    conn.commit()
    return True

async def fechar_presenca(context):
    cursor.execute("SELECT nome FROM players")
    jogadores = [x[0] for x in cursor.fetchall()]

    cursor.execute("SELECT nome FROM presenca WHERE data=date('now')")
    presentes = {x[0] for x in cursor.fetchall()}

    faltantes = set(jogadores) - presentes

    for nome in faltantes:
        cursor.execute("INSERT INTO presenca VALUES (?,date('now'),'F')", (nome,))

    conn.commit()

# =========================
# RELATÓRIO MENSAL
# =========================
async def presenca_mensal(update, context):
    if not pode(update):
        return

    cursor.execute("""
    SELECT nome,
    SUM(CASE WHEN status='P' THEN 1 ELSE 0 END),
    SUM(CASE WHEN status='F' THEN 1 ELSE 0 END)
    FROM presenca
    WHERE strftime('%Y-%m', data)=strftime('%Y-%m','now')
    GROUP BY nome
    ORDER BY 2 DESC
    """)

    dados = cursor.fetchall()

    txt = "📊 Presença Mensal\n\n"

    for n,p,f in dados:
        txt += f"{n} — ✅ {p} | ❌ {f}\n"

    await update.message.reply_text(txt)

# =========================
# RELATÓRIO XP
# =========================
async def relatorio_xp(update, context):
    if not pode(update):
        return

    cursor.execute("SELECT DISTINCT nome FROM historico")
    jogadores = [x[0] for x in cursor.fetchall()]

    ranking = []

    for nome in jogadores:
        cursor.execute("""
        SELECT xp FROM historico
        WHERE nome=?
        ORDER BY data DESC
        LIMIT 2
        """, (nome,))

        dados = cursor.fetchall()

        if len(dados) == 2:
            ganho = dados[0][0] - dados[1][0]
            if ganho > 0:
                ranking.append((nome, ganho))

    ranking.sort(key=lambda x: x[1], reverse=True)

    txt = "📊 Evolução diária de XP\n\n"

    for i, (n, v) in enumerate(ranking[:10], 1):
        txt += f"{i}. {n} — +{v} XP\n"

    if not ranking:
        txt += "Nenhuma evolução registrada hoje."

    await update.message.reply_text(txt)

# =========================
# RANKS (sem alteração)
# =========================
def gerar_rank(campo, classe=None):
    if classe:
        cursor.execute(f"SELECT nome,{campo} FROM players WHERE classe=? ORDER BY {campo} DESC",(classe,))
    else:
        cursor.execute(f"SELECT nome,{campo} FROM players ORDER BY {campo} DESC")
    return cursor.fetchall()

def montar(titulo, dados):
    if not dados:
        return "❌ Sem dados ainda."
    txt = f"🏆 {titulo}\n\n"
    for i,(n,v) in enumerate(dados,1):
        txt += f"{i}. {n} — {v}\n"
    return txt

async def rankatk(u,c): 
    if pode(u): await u.message.reply_text(montar("ATK", gerar_rank("atk")))

async def rankdef(u,c): 
    if pode(u): await u.message.reply_text(montar("DEF", gerar_rank("def")))

async def rankhp(u,c): 
    if pode(u): await u.message.reply_text(montar("HP", gerar_rank("hp")))

async def ranklevel(u,c): 
    if pode(u): await u.message.reply_text(montar("LEVEL", gerar_rank("nivel")))

async def rankcc(u,c): 
    if pode(u): await u.message.reply_text(montar("CRIT", gerar_rank("crit")))

def criar_rank_classe(campo, classe):
    async def cmd(u,c):
        if pode(u):
            await u.message.reply_text(montar(f"{campo.upper()} ({classe})", gerar_rank(campo, classe)))
    return cmd

rankatkguerreiro = criar_rank_classe("atk","guerreiro")
rankdefguerreiro = criar_rank_classe("def","guerreiro")
rankhpguerreiro = criar_rank_classe("hp","guerreiro")
rankccguerreiro = criar_rank_classe("crit","guerreiro")
ranklevelguerreiro = criar_rank_classe("nivel","guerreiro")

rankatkmago = criar_rank_classe("atk","mago")
rankdefmago = criar_rank_classe("def","mago")
rankhpmago = criar_rank_classe("hp","mago")
rankccmago = criar_rank_classe("crit","mago")
ranklevelmago = criar_rank_classe("nivel","mago")

rankatkarqueiro = criar_rank_classe("atk","arqueiro")
rankdefarqueiro = criar_rank_classe("def","arqueiro")
rankhparqueiro = criar_rank_classe("hp","arqueiro")
rankccarqueiro = criar_rank_classe("crit","arqueiro")
ranklevelarqueiro = criar_rank_classe("nivel","arqueiro")

# =========================
# LEITOR (sem alteração)
# =========================
async def ler(update, context):
    global missao_ativa

    if not update.message:
        return

    msg = update.message
    texto = msg.text or msg.caption
    if not texto:
        return

    if str(msg.message_thread_id) == PRESENCA_ID:
        if "XP:" in texto:
            d = extrair(texto)
            salvar(d)

            if registrar_presenca(d["nome"]):
                await msg.reply_text(f"📜 {d['nome']} registrado!")

# =========================
# START (CORRIGIDO)
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("rankatk", rankatk))
    app.add_handler(CommandHandler("rankdef", rankdef))
    app.add_handler(CommandHandler("rankhp", rankhp))
    app.add_handler(CommandHandler("ranklevel", ranklevel))
    app.add_handler(CommandHandler("rankcc", rankcc))

    app.add_handler(CommandHandler("presenca", presenca_mensal))
    app.add_handler(CommandHandler("xp", relatorio_xp))

    app.add_handler(MessageHandler(filters.ALL, ler))

    # 🔥 PROTEÇÃO JOB QUEUE
    if app.job_queue:
        app.job_queue.run_daily(fechar_presenca, time=time(23,59))

    print("👑 PILAR FINAL ABSOLUTO ATIVO")

    app.run_polling(
        drop_pending_updates=True,
        close_loop=False,
        stop_signals=None
    )

if __name__ == "__main__":
    main()
