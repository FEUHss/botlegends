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

TOPICO_BANCO = 30933
ADMIN_ID = 5285053532

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
        if linha.startswith("+"): continue
        if "/" in linha and "HP" not in linha: continue

        if "ATK" in linha and "DEF" in linha and "CRIT" in linha:
            numeros = re.findall(r"\d+\.?\d*", linha.replace(",", "."))
            if len(numeros) >= 3:
                dados["atk"] = float(numeros[0])
                dados["def"] = float(numeros[1])
                dados["crit"] = float(numeros[2])

        elif "HP" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros:
                dados["hp"] = int(numeros[-1])

        elif "Gold:" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros: dados["gold"] = int(numeros[0])

        elif "Tofus:" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros: dados["tofus"] = int(numeros[0])

    return dados

# ================= BANCO BASE =================
def registrar_membro(nome):
    cur = conn.cursor()
    cur.execute("INSERT INTO membros (nome) VALUES (%s) ON CONFLICT DO NOTHING", (nome,))
    conn.commit()

def salvar_presenca(nome):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM presencas WHERE nome=%s AND data=%s", (nome, hoje()))
    if cur.fetchone(): return False
    cur.execute("INSERT INTO presencas (nome,data) VALUES (%s,%s)", (nome, hoje()))
    conn.commit()
    return True

def salvar_xp(nome, xp, nivel):
    if xp is None: return
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO xp_logs (nome,xp,nivel,data)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (nome,data)
        DO UPDATE SET xp=EXCLUDED.xp,nivel=EXCLUDED.nivel
    """, (nome,xp,nivel,hoje()))
    conn.commit()

def salvar_status(nome, dados):
    if not dados: return
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO status (nome,data,atk,def,crit,hp,gold,tofus)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (nome,data)
        DO UPDATE SET atk=EXCLUDED.atk,def=EXCLUDED.def,crit=EXCLUDED.crit,
        hp=EXCLUDED.hp,gold=EXCLUDED.gold,tofus=EXCLUDED.tofus
    """, (nome,hoje(),dados.get("atk"),dados.get("def"),
          dados.get("crit"),dados.get("hp"),
          dados.get("gold"),dados.get("tofus")))
    conn.commit()

# ================= XP =================
def get_rank_xp():
    cur=conn.cursor()
    cur.execute("""
        SELECT x.nome,x.nivel,x.xp
        FROM xp_logs x
        INNER JOIN (
            SELECT nome, MAX(data) as data_ref
            FROM xp_logs GROUP BY nome
        ) ref
        ON x.nome=ref.nome AND x.data=ref.data_ref
        ORDER BY x.xp DESC
    """)
    d=cur.fetchall()
    txt="🏆 RANKING XP\n\n"
    for i,(n,l,xp) in enumerate(d,1):
        txt+=f"{i}. {n} — Lv {l} - {xp} XP\n"
    return txt

def get_rank_xp_dif():
    cur = conn.cursor()

    cur.execute("""
        WITH hoje AS (
            SELECT nome, xp
            FROM xp_logs
            WHERE data = CURRENT_DATE
        ),
        ontem AS (
            SELECT DISTINCT ON (nome) nome, xp
            FROM xp_logs
            WHERE data < CURRENT_DATE
            ORDER BY nome, data DESC
        )

        SELECT m.nome,
               CASE
                   WHEN hoje.xp IS NULL THEN 0
                   WHEN ontem.xp IS NULL THEN 0
                   ELSE hoje.xp - ontem.xp
               END AS diff

        FROM membros m
        LEFT JOIN hoje ON m.nome = hoje.nome
        LEFT JOIN ontem ON m.nome = ontem.nome

        ORDER BY diff DESC
    """)

    dados = cur.fetchall()

    texto = "📊 VARIAÇÃO XP (24h)\n\n"

    for i, (nome, diff) in enumerate(dados, 1):
        simbolo = "📈" if diff > 0 else "📉" if diff < 0 else "➖"
        texto += f"{i}. {nome} — {simbolo} {diff:+}\n"

    return texto

# ================= BANCO =================
def get_saldo():
    cur=conn.cursor()
    cur.execute("SELECT saldo FROM banco_guilda LIMIT 1")
    return cur.fetchone()[0]

def registrar_doacao(nome,valor):
    cur=conn.cursor()
    cur.execute("INSERT INTO doacoes(nome,valor,data) VALUES(%s,%s,CURRENT_DATE)",(nome,valor))
    cur.execute("UPDATE banco_guilda SET saldo=saldo+%s",(valor,))
    t=(valor//500)+(valor//5000)
    cur.execute("INSERT INTO tickets(nome,semanal,mensal) VALUES(%s,0,0) ON CONFLICT DO NOTHING",(nome,))
    cur.execute("UPDATE tickets SET semanal=semanal+%s,mensal=mensal+%s WHERE nome=%s",(t,t,nome))
    conn.commit()
    return t

def get_tickets(nome):
    cur=conn.cursor()
    cur.execute("SELECT semanal,mensal FROM tickets WHERE nome=%s",(nome,))
    return cur.fetchone()

def rank_tickets(tipo):
    cur=conn.cursor()
    cur.execute(f"SELECT nome,{tipo} FROM tickets ORDER BY {tipo} DESC")
    d=cur.fetchall()
    txt=f"🏆 RANK {tipo.upper()}\n\n"
    for i,(n,v) in enumerate(d,1):
        txt+=f"{i}. {n} — {v}\n"
    return txt

def rank_doacoes():
    cur=conn.cursor()
    cur.execute("SELECT nome,SUM(valor) FROM doacoes GROUP BY nome ORDER BY SUM(valor) DESC")
    d=cur.fetchall()
    txt="🏆 RANK DOAÇÕES\n\n"
    for i,(n,v) in enumerate(d,1):
        txt+=f"{i}. {n} — {v}\n"
    return txt

# ================= MENSAGEM BANCO =================
def gerar_mensagem_doacao(nome, valor, tickets, saldo):

    if valor < 5000:
        return f"""🏛️ Nova contribuição registrada

👤 Doador: {nome}
💰 Valor: +{valor} gold
🎟 Tickets: {tickets}

━━━━━━━━━━━━━━━
🏦 Saldo atual: {saldo} gold
━━━━━━━━━━━━━━━"""

    bonus_msgs = [
        "🔥 O Pilar reage à grande oferta!\n🎁 Entrada bônus concedida",
        "⚡ O cofre vibra com poder!\n🎟 Ticket extra ativado",
        "👑 Oferta digna de lenda!\n🎁 Recompensa bônus recebida",
        "🌟 Energia dourada detectada!\n🎟 Entrada extra liberada"
    ]

    bonus = random.choice(bonus_msgs)

    return f"""🏛️ ✨ DOAÇÃO ÉPICA ✨

👤 Doador: {nome}
💰 Valor: +{valor} gold
🎟 Tickets: {tickets}

{bonus}

━━━━━━━━━━━━━━━
🏦 Saldo atual: {saldo} gold
━━━━━━━━━━━━━━━"""

# ================= COMANDOS BANCO =================
async def comando_doar(update,context):
    if update.effective_user.id!=ADMIN_ID: return
    if update.message.chat.type!="private": return

    nome=limpar_nome(context.args[0])
    valor=int(context.args[1])

    t=registrar_doacao(nome,valor)
    s=get_saldo()

    await update.message.reply_text(f"Doação registrada\nTickets: {t}")

    await context.bot.send_message(
        chat_id=GRUPO_ID,
        message_thread_id=TOPICO_BANCO,
        text=gerar_mensagem_doacao(nome,valor,t,s)
    )

async def comando_banco(update,context):
    await update.message.reply_text(f"🏦 Saldo: {get_saldo()} gold")

async def comando_ticket(update,context):
    nome=limpar_nome(" ".join(context.args))
    d=get_tickets(nome)
    if not d:
        await update.message.reply_text("Sem tickets.")
        return
    await update.message.reply_text(f"{nome}\n🎟 Total: {d[0]+d[1]}")

async def comando_ticketS(update,context):
    nome=limpar_nome(" ".join(context.args))
    d=get_tickets(nome)
    await update.message.reply_text(f"{nome}\n🎟 Semanal: {d[0]}")

async def comando_ticketM(update,context):
    nome=limpar_nome(" ".join(context.args))
    d=get_tickets(nome)
    await update.message.reply_text(f"{nome}\n🎟 Mensal: {d[1]}")

async def comando_rank_semanal(update,context):
    await update.message.reply_text(rank_tickets("semanal"))

async def comando_rank_mensal(update,context):
    await update.message.reply_text(rank_tickets("mensal"))

async def comando_rank_doacoes(update,context):
    await update.message.reply_text(rank_doacoes())

async def comando_resetbanco(update,context):
    if update.effective_user.id!=ADMIN_ID: return
    conn.cursor().execute("UPDATE banco_guilda SET saldo=0")
    conn.commit()
    await update.message.reply_text("Banco resetado.")

async def comando_resetsemanal(update,context):
    if update.effective_user.id!=ADMIN_ID: return
    conn.cursor().execute("UPDATE tickets SET semanal=0")
    conn.commit()
    await update.message.reply_text("Tickets semanais resetados.")

async def comando_resetmensal(update,context):
    if update.effective_user.id!=ADMIN_ID: return
    conn.cursor().execute("UPDATE tickets SET mensal=0")
    conn.commit()
    await update.message.reply_text("Tickets mensais resetados.")

# ================= COFRE =================
def registrar_item(nome, item):
    cur = conn.cursor()
    cur.execute("INSERT INTO cofre_itens (nome,item,data) VALUES (%s,%s,%s)",
                (nome, item.upper(), hoje()))
    conn.commit()

def remover_item(item):
    cur = conn.cursor()
    cur.execute("DELETE FROM cofre_itens WHERE item=%s LIMIT 1 RETURNING item",
                (item.upper(),))
    r = cur.fetchone()
    conn.commit()
    return r

def gerar_msg_item(nome, item):
    return f"""🏛️ Cofre da Sabedoria

✨ Um artefato foi entregue ao Pilar

👤 Guardião: {nome}
📦 Item: {item}

━━━━━━━━━━━━━━━
🔐 O cofre absorve seu poder
━━━━━━━━━━━━━━━"""

def gerar_msg_remocao(item):
    return f"""🏛️ Cofre da Sabedoria

⚠️ Um item foi removido

📦 Item: {item}

━━━━━━━━━━━━━━━
🗝️ O selo foi temporariamente quebrado
━━━━━━━━━━━━━━━"""

async def comando_doaritem(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if update.message.chat.type != "private": return

    nome = limpar_nome(context.args[0])
    item = " ".join(context.args[1:])

    registrar_item(nome, item)

    await update.message.reply_text(f"Item registrado: {item}")

    await context.bot.send_message(
        chat_id=GRUPO_ID,
        message_thread_id=TOPICO_BANCO,
        text=gerar_msg_item(nome, item)
    )

async def comando_removeritem(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if update.message.chat.type != "private": return

    item = " ".join(context.args)

    r = remover_item(item)

    if not r:
        await update.message.reply_text("Item não encontrado.")
        return

    await update.message.reply_text(f"Item removido: {item}")

    await context.bot.send_message(
        chat_id=GRUPO_ID,
        message_thread_id=TOPICO_BANCO,
        text=gerar_msg_remocao(item)
    )

# ================= DETECÇÃO =================
async def detectar(update,context):
    msg=update.message
    if not msg: return
    if msg.chat.id!=GRUPO_ID: return
    if msg.message_thread_id!=TOPICO_PRESENCA: return

    texto=msg.text or msg.caption
    if not texto: return

    nome=extrair_nome(texto)
    if not nome: return

    xp=extrair_xp(texto)
    nivel=extrair_nivel(texto)
    dados=extrair_status(texto)

    registrar_membro(nome)
    salvar_presenca(nome)
    salvar_xp(nome,xp,nivel)
    salvar_status(nome,dados)

    await msg.reply_text(f"""🧠 Pilar da Sabedoria reconhece presença

👤 {nome}

━━━━━━━━━━━━━━━
📜 Registro gravado com sucesso
━━━━━━━━━━━━━━━""")

# ================= MAIN =================
def main():
    app=ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("xp",lambda u,c: u.message.reply_text(get_rank_xp())))
    app.add_handler(CommandHandler("xpdif",lambda u,c: u.message.reply_text(get_rank_xp_dif())))

    app.add_handler(CommandHandler("doar",comando_doar))
    app.add_handler(CommandHandler("banco",comando_banco))
    app.add_handler(CommandHandler("ticket",comando_ticket))
    app.add_handler(CommandHandler("ticketS",comando_ticketS))
    app.add_handler(CommandHandler("ticketM",comando_ticketM))
    app.add_handler(CommandHandler("ranksemanal",comando_rank_semanal))
    app.add_handler(CommandHandler("rankmensal",comando_rank_mensal))
    app.add_handler(CommandHandler("rankdoacoes",comando_rank_doacoes))

    app.add_handler(CommandHandler("resetbanco",comando_resetbanco))
    app.add_handler(CommandHandler("resetsemanal",comando_resetsemanal))
    app.add_handler(CommandHandler("resetmensal",comando_resetmensal))

    app.add_handler(CommandHandler("atk",lambda u,c: u.message.reply_text(gerar_rank("atk","ATAQUE"))))
    app.add_handler(CommandHandler("def",lambda u,c: u.message.reply_text(gerar_rank("def","DEFESA"))))
    app.add_handler(CommandHandler("hp",lambda u,c: u.message.reply_text(gerar_rank("hp","HP"))))
    app.add_handler(CommandHandler("crit",lambda u,c: u.message.reply_text(gerar_rank("crit","CRÍTICO"))))
    app.add_handler(CommandHandler("gold",lambda u,c: u.message.reply_text(gerar_rank("gold","GOLD"))))
    app.add_handler(CommandHandler("tofu",lambda u,c: u.message.reply_text(gerar_rank("tofus","TOFUS"))))

    app.add_handler(CommandHandler("doaritem",comando_doaritem))
    app.add_handler(CommandHandler("removeritem",comando_removeritem))

    app.add_handler(MessageHandler(filters.TEXT | filters.CaptionRegex(".*"), detectar))

    print("🚀 BOT FINAL COMPLETO + COFRE ATIVO")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
