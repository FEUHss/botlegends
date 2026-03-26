import re
import sqlite3
import unicodedata
import os
from datetime import time
from telegram.ext import Application, MessageHandler, CommandHandler, filters

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN não encontrado")

print("👑 BOT INICIANDO...")

LIDER_ID = -1003806440152

# =========================
# BANCO
# =========================
conn = sqlite3.connect("legends.db", check_same_thread=False)
cursor = conn.cursor()

cursor.executescript("""
CREATE TABLE IF NOT EXISTS players (
nome TEXT PRIMARY KEY,
xp INTEGER,
last_xp INTEGER,
classe TEXT,
last_seen TEXT
);

CREATE TABLE IF NOT EXISTS presenca (
nome TEXT,
data TEXT,
status TEXT
);

CREATE TABLE IF NOT EXISTS missoes (
nome TEXT,
pontos INTEGER
);

CREATE TABLE IF NOT EXISTS loots (
nome TEXT,
item TEXT,
raridade TEXT,
data TEXT
);

CREATE TABLE IF NOT EXISTS historico (
nome TEXT,
xp INTEGER,
data TEXT
);
""")

conn.commit()

missao_ativa = False

# =========================
# UTIL
# =========================
def nome(txt):
    linha = txt.split("\n")[0]
    linha = unicodedata.normalize("NFD", linha).encode("ascii","ignore").decode()
    return re.sub(r"[^\w\s]", "", linha).strip().upper()

# =========================
# PERFIL
# =========================
def extrair(txt):
    try:
        return {
            "nome": nome(txt),
            "xp": int(re.search(r"XP:\s*(\d+)", txt).group(1)),
            "classe": re.search(r"Classe:\s*(\w+)", txt).group(1).lower()
        }
    except:
        return None

def salvar(d):
    cursor.execute("SELECT xp FROM players WHERE nome=?", (d["nome"],))
    r = cursor.fetchone()
    last = r[0] if r else d["xp"]

    cursor.execute("""
    INSERT INTO players VALUES (?,?,?,?,datetime('now'))
    ON CONFLICT(nome) DO UPDATE SET
    xp=?, last_xp=?, classe=?, last_seen=datetime('now')
    """, (d["nome"], d["xp"], last, d["classe"],
          d["xp"], last, d["classe"]))

    cursor.execute("INSERT INTO historico VALUES (?, ?, datetime('now'))",
                   (d["nome"], d["xp"]))

    conn.commit()

def registrar_presenca(n):
    cursor.execute("SELECT * FROM presenca WHERE nome=? AND data=date('now')", (n,))
    if cursor.fetchone(): return False
    cursor.execute("INSERT INTO presenca VALUES (?,date('now'),'P')", (n,))
    conn.commit()
    return True

# =========================
# RANKINGS
# =========================
async def rank(update,_):
    cursor.execute("SELECT nome,xp FROM players ORDER BY xp DESC LIMIT 10")
    d=cursor.fetchall()
    txt="🏆 Ranking XP\n\n"
    for i,(n,v) in enumerate(d,1):
        txt+=f"{i}. {n} — {v}\n"
    await update.message.reply_text(txt or "Sem dados")

async def rankclasse(update,_):
    cursor.execute("SELECT classe,nome,xp FROM players ORDER BY classe,xp DESC")
    d=cursor.fetchall()
    txt="🏹 Ranking por Classe\n\n"
    for c,n,v in d:
        txt+=f"{c.upper()} → {n} ({v})\n"
    await update.message.reply_text(txt)

async def xpdia(update,_):
    res=[]
    cursor.execute("SELECT DISTINCT nome FROM historico")
    for n in [x[0] for x in cursor.fetchall()]:
        cursor.execute("SELECT xp FROM historico WHERE nome=? ORDER BY data DESC LIMIT 2",(n,))
        d=cursor.fetchall()
        if len(d)==2:
            g=d[0][0]-d[1][0]
            if g>0: res.append((n,g))
    res.sort(key=lambda x:x[1],reverse=True)
    txt="📊 XP Diário\n\n"
    for i,(n,v) in enumerate(res[:10],1):
        txt+=f"{i}. {n} +{v}\n"
    await update.message.reply_text(txt)

# =========================
# MISSÕES
# =========================
async def missao(update,_):
    cursor.execute("SELECT nome,SUM(pontos) FROM missoes GROUP BY nome ORDER BY SUM(pontos) DESC")
    d=cursor.fetchall()
    txt="⚔️ Missão\n\n"
    for i,(n,v) in enumerate(d,1):
        txt+=f"{i}. {n} — {v}\n"
    await update.message.reply_text(txt or "Sem dados")

# =========================
# LOOTS
# =========================
def salvar_loot(n,item):
    raridade="lendario" if "lend" in item.lower() else "comum"
    cursor.execute("INSERT INTO loots VALUES (?,?,?,date('now'))",(n,item,raridade))
    conn.commit()

async def dropslg(update,_):
    cursor.execute("SELECT nome,item FROM loots WHERE data=date('now')")
    d=cursor.fetchall()
    txt="📦 Drops do dia\n\n"
    for n,i in d:
        txt+=f"{n} → {i}\n"
    await update.message.reply_text(txt or "Sem drops")

# =========================
# RELATÓRIO
# =========================
async def relatorio(context):
    cursor.execute("SELECT COUNT(*) FROM players")
    total=cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT nome) FROM presenca WHERE data=date('now')")
    pres=cursor.fetchone()[0]

    txt=f"📊 Relatório\nPresença: {pres}/{total}"
    await context.bot.send_message(chat_id=LIDER_ID,text=txt)

# =========================
# INATIVIDADE
# =========================
async def inatividade(context):
    cursor.execute("SELECT nome FROM players WHERE last_seen < datetime('now','-3 day')")
    for n in cursor.fetchall():
        await context.bot.send_message(chat_id=LIDER_ID,text=f"⚠️ {n[0]} inativo 3 dias")

# =========================
# LEITOR
# =========================
async def ler(update,_):
    global missao_ativa

    if not update.message: return
    txt=update.message.text or update.message.caption
    if not txt: return

    if "XP:" in txt:
        d=extrair(txt)
        if d:
            salvar(d)
            if registrar_presenca(d["nome"]):
                await update.message.reply_text(f"📜 {d['nome']} registrado")

    if "Tarefas da Guilda" in txt:
        cursor.execute("DELETE FROM missoes")
        conn.commit()
        await update.message.reply_text("⚔️ Nova missão iniciada!")

    if "SEU TURNO" in txt:
        n=nome(txt)
        cursor.execute("INSERT INTO missoes VALUES (?,1)",(n,))
        conn.commit()
        await update.message.reply_text("Registrada.")

    if "Nenhuma tarefa ativa" in txt:
        cursor.execute("SELECT nome,SUM(pontos) FROM missoes GROUP BY nome ORDER BY SUM(pontos) DESC")
        d=cursor.fetchall()
        txt="🏆 Resultado da Missão\n\n"
        for i,(n,v) in enumerate(d,1):
            txt+=f"{i}. {n} — {v}\n"
        await update.message.reply_text("🏁 Missão encerrada!\n"+txt)

    if "drop" in txt.lower():
        n=nome(txt)
        salvar_loot(n,txt)
        await update.message.reply_text("Drop registrado")

# =========================
# MAIN COM DEBUG
# =========================
def main():
    try:
        print("🚀 Criando aplicação...")
        app = Application.builder().token(TOKEN).build()

        print("✅ Adicionando comandos...")
        app.add_handler(CommandHandler("rank", rank))
        app.add_handler(CommandHandler("rankclasse", rankclasse))
        app.add_handler(CommandHandler("xpdia", xpdia))
        app.add_handler(CommandHandler("missao", missao))
        app.add_handler(CommandHandler("dropslg", dropslg))

        print("✅ Adicionando leitor...")
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ler))

        if app.job_queue:
            print("✅ Ativando jobs...")
            app.job_queue.run_daily(relatorio, time=time(23,0))
            app.job_queue.run_daily(inatividade, time=time(12,0))
        else:
            print("⚠️ JobQueue não disponível")

        print("👑 BOT ONLINE")

        app.run_polling(close_loop=False)

    except Exception as e:
        print("💥 ERRO:", e)

if __name__ == "__main__":
    main()
