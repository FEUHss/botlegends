import re
import sqlite3
import unicodedata
import random
from datetime import time
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters

import os
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

    cursor.execute("INSERT INTO historico VALUES (?, ?, datetime('now'))",
                   (d["nome"], d["xp"]))

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
    for i,(n,v) in enumerate(ranking[:10],1):
        txt += f"{i}. {n} — +{v} XP\n"

    if not ranking:
        txt += "Nenhuma evolução registrada hoje."

    await update.message.reply_text(txt)

# =========================
# RELATÓRIO AUTOMÁTICO
# =========================
async def relatorio_automatico(context):

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

    cursor.execute("SELECT nome FROM presenca WHERE data=date('now')")
    presentes = {x[0] for x in cursor.fetchall()}

    cursor.execute("SELECT nome FROM players")
    todos = {x[0] for x in cursor.fetchall()}

    faltantes = todos - presentes

    txt = "📊 Relatório Diário da Guilda\n\n"

    txt += "📈 Evolução XP\n"
    for i,(n,v) in enumerate(ranking[:5],1):
        txt += f"{i}. {n} — +{v} XP\n"

    txt += f"\n📅 Presença: {len(presentes)}/{len(todos)}\n"

    if faltantes:
        txt += "\n⚠️ Faltantes:\n"
        for n in list(faltantes)[:10]:
            txt += f"- {n}\n"

    await context.bot.send_message(chat_id=LIDER_ID, text=txt)

# =========================
# RANKS (resumido)
# =========================
def gerar_rank(campo):
    cursor.execute(f"SELECT nome,{campo} FROM players ORDER BY {campo} DESC")
    return cursor.fetchall()

async def rankatk(u,c): 
    if pode(u): await u.message.reply_text(str(gerar_rank("atk")))

# =========================
# MISSÃO + LOOT + LEITOR
# =========================
async def ler(update, context):
    global missao_ativa

    if not update.message:
        return

    msg = update.message
    texto = msg.text or msg.caption
    if not texto:
        return

    if str(msg.message_thread_id) == PRESENCA_ID and "XP:" in texto:
        d = extrair(texto)
        salvar(d)
        if registrar_presenca(d["nome"]):
            await msg.reply_text(f"📜 {d['nome']} registrado!")

    if str(msg.message_thread_id) == TASKS_ID:

        if "Tarefas da Guilda Legends" in texto and "Nenhuma tarefa ativa" not in texto:
            if not missao_ativa:
                missao_ativa = True
                await msg.reply_text("⚔️ Missão iniciada!\nA Guilda aguarda sua contribuição.")

        elif "Nenhuma tarefa ativa" in texto:
            if missao_ativa:
                cursor.execute("SELECT nome,SUM(pontos) FROM missoes GROUP BY nome ORDER BY SUM(pontos) DESC")
                dados = cursor.fetchall()

                txt = "🏹 Missão concluída!\n\n🏆 Ranking\n"
                for i,(n,p) in enumerate(dados,1):
                    txt += f"{i}. {n} — {p}\n"

                await msg.reply_text(txt)
                cursor.execute("DELETE FROM missoes")
                conn.commit()
                missao_ativa = False

        elif missao_ativa and "SEU TURNO" in texto:
            cursor.execute("INSERT INTO missoes VALUES (?,1)", (normalizar_nome(texto),))
            conn.commit()
            await msg.reply_text("Registrada.")

# =========================
# START
# =========================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("presenca", presenca_mensal))
app.add_handler(CommandHandler("xp", relatorio_xp))
app.add_handler(MessageHandler(filters.ALL, ler))

app.job_queue.run_daily(relatorio_automatico, time=time(23,0))
app.job_queue.run_daily(fechar_presenca, time=time(23,59))

print("👑 SISTEMA FINAL + AUTOMAÇÃO ATIVA")

app.run_polling()
