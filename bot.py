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

# 🔥 BANCO
TOPICO_BANCO = 30933
ADMIN_ID = 5285053532

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
    return random.choice([
        f"📜 O Pilar registra: {nome} esteve presente.",
        f"🗿 O Pilar reconhece {nome}.",
        f"✨ Presença registrada: {nome}",
        f"👑 {nome} marcou presença.",
        f"🔥 Presença de {nome} confirmada.",
        f"🧠 {nome} foi registrado.",
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
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (nome,data)
        DO UPDATE SET xp=EXCLUDED.xp, nivel=EXCLUDED.nivel
    """, (nome, xp, nivel, hoje()))  
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
    cur = conn.cursor()
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
    dados = cur.fetchall()

    texto = "🏆 RANKING XP\n\n"
    for i,(n,l,xp) in enumerate(dados,1):
        texto += f"{i}. {n} — Lv {l} - {xp} XP\n"
    return texto

def get_evolucao(nome):
    cur = conn.cursor()
    cur.execute("""
        SELECT xp FROM xp_logs
        WHERE nome=%s ORDER BY data DESC LIMIT 2
    """,(nome,))
    d=cur.fetchall()
    if len(d)<2: return "Dados insuficientes"
    diff=d[0][0]-d[1][0]
    return f"{nome}\nXP atual: {d[0][0]}\nVariação: {diff:+}"

# ================= RANK =================  

def gerar_rank(campo,titulo):
    cur=conn.cursor()
    cur.execute(f"""
        SELECT s.nome,s.{campo}
        FROM status s
        INNER JOIN (
            SELECT nome,MAX(data) as data_ref
            FROM status GROUP BY nome
        ) ref
        ON s.nome=ref.nome AND s.data=ref.data_ref
        ORDER BY s.{campo} DESC
    """)
    dados=cur.fetchall()
    txt=f"🏆 {titulo}\n\n"
    for i,(n,v) in enumerate(dados,1):
        txt+=f"{i}. {n} — {v}\n"
    return txt

# ================= XPDIF =================  

def get_rank_xp_dif():
    cur=conn.cursor()
    cur.execute("""
        SELECT m.nome,
        CASE WHEN h.xp IS NULL THEN 0
        ELSE h.xp-COALESCE(o.xp,h.xp) END diff
        FROM membros m
        LEFT JOIN xp_logs h ON m.nome=h.nome AND h.data=CURRENT_DATE
        LEFT JOIN xp_logs o ON m.nome=o.nome
        AND o.data=(SELECT MAX(data) FROM xp_logs WHERE nome=m.nome AND data<CURRENT_DATE)
        ORDER BY diff DESC
    """)
    dados=cur.fetchall()
    txt="📊 VARIAÇÃO XP\n\n"
    for i,(n,d) in enumerate(dados,1):
        s="📈" if d>0 else "📉" if d<0 else "➖"
        txt+=f"{i}. {n} — {s} {d:+}\n"
    return txt

# ================= BANCO GUILD =================  

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

async def comando_doar(update,context):
    if update.effective_user.id!=ADMIN_ID: return
    if update.message.chat.type!="private": return
    try:
        nome=limpar_nome(context.args[0])
        valor=int(context.args[1])
        t=registrar_doacao(nome,valor)
        s=get_saldo()
        await update.message.reply_text(f"Doação registrada\nTickets: {t}")
        await context.bot.send_message(chat_id=GRUPO_ID,message_thread_id=TOPICO_BANCO,
            text=f"{nome} doou {valor} gold\nTickets: {t}\nSaldo: {s}")
    except:
        await update.message.reply_text("Uso: /doar Nome Valor")

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
    salvou=salvar_presenca(nome)

    salvar_xp(nome,xp,nivel)
    salvar_status(nome,dados)

    if salvou:
        await msg.reply_text(mensagem_pilar(nome))
    else:
        await msg.reply_text(f"{nome} já marcou")

# ================= MAIN =================  

def main():
    app=ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("xp",lambda u,c: u.message.reply_text(get_rank_xp())))
    app.add_handler(CommandHandler("xpdif",lambda u,c: u.message.reply_text(get_rank_xp_dif())))
    app.add_handler(CommandHandler("doar",comando_doar))

    app.add_handler(CommandHandler("atk",lambda u,c: u.message.reply_text(gerar_rank("atk","ATAQUE"))))
    app.add_handler(CommandHandler("def",lambda u,c: u.message.reply_text(gerar_rank("def","DEFESA"))))
    app.add_handler(CommandHandler("hp",lambda u,c: u.message.reply_text(gerar_rank("hp","HP"))))
    app.add_handler(CommandHandler("crit",lambda u,c: u.message.reply_text(gerar_rank("crit","CRÍTICO"))))
    app.add_handler(CommandHandler("gold",lambda u,c: u.message.reply_text(gerar_rank("gold","GOLD"))))
    app.add_handler(CommandHandler("tofu",lambda u,c: u.message.reply_text(gerar_rank("tofus","TOFUS"))))

    app.add_handler(MessageHandler(filters.TEXT | filters.CaptionRegex(".*"), detectar))

    print("🚀 BOT FINAL 100% OK")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
