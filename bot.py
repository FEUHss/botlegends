import re
import sqlite3
import unicodedata
import os
from telegram.ext import Application, MessageHandler, CommandHandler, filters

TOKEN = os.getenv("TOKEN")
LIDER_ID = -1003806440152

print("👑 BOT INICIANDO...")

# =========================
# BANCO
# =========================
conn = sqlite3.connect("legends.db", check_same_thread=False)
cursor = conn.cursor()

cursor.executescript("""
CREATE TABLE IF NOT EXISTS players (
nome TEXT PRIMARY KEY,
classe TEXT,
nivel INTEGER,
atk INTEGER,
def INTEGER,
hp INTEGER,
crit INTEGER,
xp INTEGER,
last_xp INTEGER,
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

CREATE TABLE IF NOT EXISTS missao_info (
nome TEXT,
meta INTEGER,
data TEXT
);
""")

conn.commit()

# =========================
# FUNÇÃO NOME (CORRIGIDA)
# =========================
def nome(txt):
    linha = txt.split("\n")[0]
    linha = unicodedata.normalize("NFD", linha)
    linha = linha.encode("ascii", "ignore").decode()

    linha = re.sub(r"\[.*?\]", "", linha)
    linha = re.sub(r"\d+", "", linha)
    linha = re.sub(r"[^a-zA-Z\s]", "", linha)
    linha = re.sub(r"\s+", " ", linha)

    return linha.strip().upper()

# =========================
# DETECTAR MISSÃO (NOVO)
# =========================
def detectar_missao(txt):
    try:
        texto = txt.lower()

        if "tarefas da guilda legends" not in texto:
            return None
        if "diaria" not in texto and "diária" not in texto:
            return None

        nome_missao = re.search(r"diária (.+)", texto)
        if not nome_missao:
            return None

        nome_missao = nome_missao.group(1).strip().title()

        progresso = re.search(r"(\d+)/(\d+)", texto)
        if not progresso:
            return None

        total = int(progresso.group(2))

        return nome_missao, total

    except:
        return None

# =========================
# EXTRAIR PERFIL
# =========================
def extrair(txt):
    try:
        return {
            "nome": nome(txt),
            "classe": re.search(r"Classe:\s*(\w+)", txt).group(1).lower(),
            "nivel": int(re.search(r"Lv\s*(\d+)", txt).group(1)),
            "atk": int(re.search(r"ATK\s*(\d+)", txt).group(1)),
            "def": int(re.search(r"DEF\s*(\d+)", txt).group(1)),
            "hp": int(re.search(r"HP:\s*\d+/(\d+)", txt).group(1)),
            "crit": int(re.search(r"CRIT\s*(\d+)", txt).group(1)),
            "xp": int(re.search(r"XP:\s*(\d+)", txt).group(1))
        }
    except:
        return None

# =========================
# SALVAR PLAYER
# =========================
def salvar(d):
    cursor.execute("SELECT xp FROM players WHERE nome=?", (d["nome"],))
    r = cursor.fetchone()
    last = r[0] if r else d["xp"]

    cursor.execute("""
    INSERT INTO players VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
    ON CONFLICT(nome) DO UPDATE SET
    classe=?,nivel=?,atk=?,def=?,hp=?,crit=?,xp=?,last_xp=?,last_seen=datetime('now')
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
def presenca(n):
    cursor.execute("SELECT * FROM presenca WHERE nome=? AND data=date('now')", (n,))
    if cursor.fetchone(): return False
    cursor.execute("INSERT INTO presenca VALUES (?,date('now'),'P')", (n,))
    conn.commit()
    return True

# =========================
# RANK GENÉRICO
# =========================
def gerar_rank(campo, classe=None):
    if classe:
        cursor.execute(f"SELECT nome,{campo} FROM players WHERE classe=? ORDER BY {campo} DESC LIMIT 10",(classe,))
    else:
        cursor.execute(f"SELECT nome,{campo} FROM players ORDER BY {campo} DESC LIMIT 10")
    return cursor.fetchall()

async def rank_cmd(update, _, campo, titulo, classe=None):
    dados = gerar_rank(campo, classe)
    txt = f"{titulo}\n\n"
    for i,(n,v) in enumerate(dados,1):
        txt += f"{i}. {n} — {v}\n"
    await update.message.reply_text(txt or "Sem dados")

# =========================
# RELATÓRIO
# =========================
async def relatorio(update,_):
    txt="📜 RELATÓRIO\n\n"

    cursor.execute("SELECT nome,xp FROM players ORDER BY xp DESC LIMIT 5")
    for i,(n,v) in enumerate(cursor.fetchall(),1):
        txt+=f"{i}. {n} — {v} XP\n"

    txt+="\n📦 Drops:\n"
    cursor.execute("SELECT nome,item FROM loots WHERE data=date('now')")
    for n,i in cursor.fetchall():
        txt+=f"{n} → {i}\n"

    await update.message.reply_text(txt)

# =========================
# LOOTS
# =========================
def salvar_loot(n,item):
    rar="lendario" if "lend" in item.lower() else "comum"
    cursor.execute("INSERT INTO loots VALUES (?,?,?,date('now'))",(n,item,rar))
    conn.commit()

async def dropslg(update,_):
    cursor.execute("""
    SELECT item,COUNT(*) FROM loots 
    WHERE raridade='lendario'
    GROUP BY item ORDER BY COUNT(*) DESC
    """)
    txt="💎 Lendários\n\n"
    for i,(item,q) in enumerate(cursor.fetchall(),1):
        txt+=f"{i}. {item} — {q}\n"
    await update.message.reply_text(txt or "Sem lendários")

# =========================
# MISSÃO
# =========================
async def missao(update,_):
    cursor.execute("SELECT nome,SUM(pontos) FROM missoes GROUP BY nome ORDER BY SUM(pontos) DESC")
    txt="⚔️ Missão\n\n"
    for i,(n,v) in enumerate(cursor.fetchall(),1):
        txt+=f"{i}. {n} — {v}\n"
    await update.message.reply_text(txt or "Sem dados")

# =========================
# LEITOR
# =========================
async def ler(update,_):
    if not update.message: return
    txt=update.message.text or update.message.caption
    if not txt: return

    # MISSÃO INTELIGENTE
    dados_missao = detectar_missao(txt)
    if dados_missao:
        nome_missao, meta = dados_missao

        cursor.execute("DELETE FROM missoes")
        cursor.execute("DELETE FROM missao_info")

        cursor.execute(
            "INSERT INTO missao_info VALUES (?,?,date('now'))",
            (nome_missao, meta)
        )
        conn.commit()

        await update.message.reply_text(
            f"⚔️ Nova missão iniciada!\n\n📌 {nome_missao}\n🎯 Meta: {meta}"
        )
        return

    if "XP:" in txt:
        d=extrair(txt)
        if d:
            salvar(d)
            if presenca(d["nome"]):
                await update.message.reply_text(f"📜 {d['nome']} registrado")

    if "SEU TURNO" in txt:
        n=nome(txt)
        cursor.execute("INSERT INTO missoes VALUES (?,1)",(n,))
        conn.commit()
        await update.message.reply_text("Registrada")

    if "Nenhuma tarefa ativa" in txt:
        cursor.execute("""
        SELECT nome,SUM(pontos)
        FROM missoes
        GROUP BY nome
        ORDER BY SUM(pontos) DESC
        """)
        ranking = cursor.fetchall()

        cursor.execute("SELECT nome FROM missao_info")
        info = cursor.fetchone()
        nome_missao = info[0] if info else "Missão"

        texto = f"🏁 Missão encerrada!\n\n📜 {nome_missao}\n\n🏆 Ranking:\n"

        for i,(n,v) in enumerate(ranking,1):
            texto += f"{i}. {n} — {v}\n"

        await update.message.reply_text(texto)

    if "drop" in txt.lower():
        n=nome(txt)
        salvar_loot(n,txt)
        await update.message.reply_text("Drop registrado")

# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("relatorio", relatorio))
    app.add_handler(CommandHandler("dropslg", dropslg))
    app.add_handler(CommandHandler("missao", missao))

    app.add_handler(CommandHandler("ranklevel", lambda u,c: rank_cmd(u,c,"nivel","🏆 Level")))
    app.add_handler(CommandHandler("rankatk", lambda u,c: rank_cmd(u,c,"atk","⚔️ ATK")))
    app.add_handler(CommandHandler("rankdef", lambda u,c: rank_cmd(u,c,"def","🛡 DEF")))
    app.add_handler(CommandHandler("rankhp", lambda u,c: rank_cmd(u,c,"hp","❤️ HP")))
    app.add_handler(CommandHandler("rankcc", lambda u,c: rank_cmd(u,c,"crit","🎯 CRIT")))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ler))

    print("👑 BOT ONLINE")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
