import os
import re
import psycopg2
import pytz
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

GRUPO_ID = -1003792787717
TOPICO_PRESENCA = 16325

conn = psycopg2.connect(DATABASE_URL)
tz = pytz.timezone("America/Sao_Paulo")

def hoje():
    return datetime.now(tz).date()

def limpar_nome(nome):
    return nome.replace("[LG]", "").strip().upper()

def extrair_nome(texto):
    for linha in texto.split("\n"):
        partes = linha.strip().split()
        for i, p in enumerate(partes):
            if p.isdigit():
                return limpar_nome(" ".join(partes[i+1:]))
    return None

def extrair_xp(texto):
    for linha in texto.split("\n"):
        if "XP" in linha:
            nums = re.findall(r"\d+", linha.replace(".","").replace(",",""))
            if len(nums) >= 2:
                return int(nums[1])
    return None

def extrair_nivel(texto):
    for linha in texto.split("\n"):
        if "Lv" in linha:
            nums = re.findall(r"\d+", linha)
            if nums:
                return int(nums[0])
    return None

def extrair_status(texto):
    dados = {}
    for linha in texto.split("\n"):
        linha = linha.strip()

        if "ATK" in linha and "DEF" in linha and "CRIT" in linha:
            n = re.findall(r"\d+\.?\d*", linha.replace(",", "."))
            if len(n) >= 3:
                dados["atk"] = float(n[0])
                dados["def"] = float(n[1])
                dados["crit"] = float(n[2])

        elif "HP" in linha:
            n = re.findall(r"\d+", linha)
            if n:
                dados["hp"] = int(n[-1])

        elif "Gold:" in linha:
            n = re.findall(r"\d+", linha)
            if n:
                dados["gold"] = int(n[0])

        elif "Tofus:" in linha:
            n = re.findall(r"\d+", linha)
            if n:
                dados["tofus"] = int(n[0])

    return dados

def registrar_membro(tg_id, nome):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO membros (telegram_id,nome)
        VALUES (%s,%s)
        ON CONFLICT (telegram_id)
        DO UPDATE SET nome=EXCLUDED.nome
    """,(tg_id,nome))
    conn.commit()

def salvar_presenca(tg_id,nome):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO presencas (telegram_id,nome,data) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
        (tg_id,nome,hoje())
    )
    inseriu = cur.rowcount > 0
    conn.commit()
    return inseriu

def salvar_xp(tg_id,nome,xp,nivel):
    if xp is None: return
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO xp_logs (telegram_id,nome,xp,nivel) VALUES (%s,%s,%s,%s)",
        (tg_id,nome,xp,nivel)
    )
    conn.commit()

def salvar_status(tg_id,nome,d):
    if not d: return
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO status
        (telegram_id,nome,atk,def,crit,hp,gold,tofus)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """,(tg_id,nome,d.get("atk"),d.get("def"),d.get("crit"),
         d.get("hp"),d.get("gold"),d.get("tofus")))
    conn.commit()

def gerar_lista():
    cur = conn.cursor()

    cur.execute("SELECT nome FROM membros ORDER BY nome")
    membros = [x[0] for x in cur.fetchall()]

    cur.execute("SELECT nome FROM presencas WHERE data=%s ORDER BY nome",(hoje(),))
    presentes = [x[0] for x in cur.fetchall()]

    ausentes = sorted(set(membros)-set(presentes))

    txt = f"📜 PRESENÇA {hoje().strftime('%d/%m')}\n\n🟢 Presentes\n"
    txt += "\n".join(f"✅ {x}" for x in presentes) if presentes else "Ninguém"
    txt += "\n\n🔴 Ausentes\n"
    txt += "\n".join(f"❌ {x}" for x in ausentes) if ausentes else "Nenhum"
    txt += f"\n\n📊 {len(presentes)}/{len(membros)} membros"
    return txt

def ranking_xp():
    cur = conn.cursor()
    cur.execute("""
    SELECT DISTINCT ON (telegram_id) nome,nivel,xp
    FROM xp_logs
    ORDER BY telegram_id,data_hora DESC
    """)
    d = sorted(cur.fetchall(), key=lambda x: x[2], reverse=True)
    txt = "🏆 RANKING XP\n\n"
    for i,(n,l,xp) in enumerate(d,1):
        txt += f"{i}. {n} — Lv {l} - {xp}\n"
    return txt

def ranking_status(campo,titulo):
    cur = conn.cursor()
    cur.execute(f"""
    SELECT DISTINCT ON (telegram_id) nome,{campo}
    FROM status
    ORDER BY telegram_id,data_hora DESC
    """)
    d = sorted(cur.fetchall(), key=lambda x: (x[1] or 0), reverse=True)
    txt = f"🏆 {titulo}\n\n"
    for i,(n,v) in enumerate(d,1):
        txt += f"{i}. {n} — {v}\n"
    return txt

def ranking_xpdif():
    cur = conn.cursor()
    cur.execute("""
    SELECT telegram_id,nome,xp,
           ROW_NUMBER() OVER(PARTITION BY telegram_id ORDER BY data_hora DESC) rn
    FROM xp_logs
    """)
    rows = cur.fetchall()

    dados = {}
    for tg,n,xp,rn in rows:
        dados.setdefault(tg, {"nome":n})
        if rn == 1: dados[tg]["ult"] = xp
        if rn == 2: dados[tg]["pen"] = xp

    res = []
    for v in dados.values():
        diff = v.get("ult",0) - v.get("pen",v.get("ult",0))
        res.append((v["nome"], diff))

    res.sort(key=lambda x:x[1], reverse=True)

    txt = "📊 VARIAÇÃO XP\n\n"
    for i,(n,d) in enumerate(res,1):
        s = "📈" if d>0 else "➖"
        txt += f"{i}. {n} — {s} {d:+}\n"
    return txt

async def cmd_lista(update, context):
    await update.message.reply_text(gerar_lista())

async def cmd_xp(update, context):
    await update.message.reply_text(ranking_xp())

async def cmd_xpdif(update, context):
    await update.message.reply_text(ranking_xpdif())

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    if msg.chat.id != GRUPO_ID: return
    if msg.message_thread_id != TOPICO_PRESENCA: return

    texto = msg.text or msg.caption
    if not texto: return

    nome = extrair_nome(texto)
    if not nome: return

    tg_id = msg.from_user.id
    xp = extrair_xp(texto)
    nivel = extrair_nivel(texto)
    status = extrair_status(texto)

    registrar_membro(tg_id,nome)
    novo = salvar_presenca(tg_id,nome)
    salvar_xp(tg_id,nome,xp,nivel)
    salvar_status(tg_id,nome,status)

    if novo:
        await msg.reply_text(f"✅ Presença registrada: {nome}")
    else:
        await msg.reply_text(f"⚠️ {nome} já marcou presença hoje")

def main():
    print("1 - Entrou no main")

    app = ApplicationBuilder().token(TOKEN).build()

    print("2 - Application criada")

    app.add_handler(CommandHandler("lista", cmd_lista))
    app.add_handler(CommandHandler("xp", cmd_xp))
    app.add_handler(CommandHandler("xpdif", cmd_xpdif))

    app.add_handler(CommandHandler("atk", lambda u,c: u.message.reply_text(ranking_status("atk","ATAQUE"))))
    app.add_handler(CommandHandler("def", lambda u,c: u.message.reply_text(ranking_status("def","DEFESA"))))
    app.add_handler(CommandHandler("hp", lambda u,c: u.message.reply_text(ranking_status("hp","HP"))))
    app.add_handler(CommandHandler("crit", lambda u,c: u.message.reply_text(ranking_status("crit","CRÍTICO"))))

    print("3 - Handlers registrados")

    app.add_handler(
        MessageHandler(
            filters.TEXT | filters.CaptionRegex(".*"),
            detectar
        )
    )

    print("4 - Iniciando polling")

    app.run_polling(
        drop_pending_updates=True,
        timeout=30,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=30,
        pool_timeout=30
    )

if __name__ == "__main__":
    main()
