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

# ================= LISTA =================  

def gerar_texto_painel():  
    cur = conn.cursor()  

    cur.execute("SELECT nome FROM membros")  
    membros = [m[0] for m in cur.fetchall()]  

    cur.execute("SELECT nome FROM presencas WHERE data=%s", (hoje(),))  
    presentes = [p[0] for p in cur.fetchall()]  

    faltantes = sorted(set(membros) - set(presentes))  
    presentes = sorted(presentes)  

    texto = f"📜 PRESENÇA — {hoje().strftime('%d/%m')}\n\n"  
    texto += "🟢 Presentes:\n"  
    texto += "\n".join([f"✅ {n}" for n in presentes]) if presentes else "Ninguém"  

    texto += "\n\n🔴 Ausentes:\n"  
    texto += "\n".join([f"❌ {n}" for n in faltantes]) if faltantes else "Nenhum"  

    texto += f"\n\n📊 {len(presentes)}/{len(membros)} membros"  

    return texto  

# 🔥 PAINEL CORRIGIDO  
async def atualizar_painel(app):  
    global painel_msg_id, painel_data  

    hoje_data = hoje()  
    texto = gerar_texto_painel()  

    hora = datetime.now(tz).strftime("%H:%M:%S")  
    texto += f"\n\n🕒 Atualizado: {hora}"  

    try:  
        if painel_data != hoje_data:  
            msg = await app.bot.send_message(  
                chat_id=GRUPO_LIDERANCA,  
                text=texto,  
                message_thread_id=TOPICO_PAINEL  
            )  
            painel_msg_id = msg.message_id  
            painel_data = hoje_data  
        else:  
            await app.bot.edit_message_text(  
                chat_id=GRUPO_LIDERANCA,  
                message_id=painel_msg_id,  
                text=texto,  
            )  

    except Exception as e:  
        print("Erro painel:", e)  

async def comando_lista(update, context):  
    await update.message.reply_text(gerar_texto_painel())  

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
        SELECT xp FROM xp_logs  
        WHERE nome=%s  
        ORDER BY data DESC  
        LIMIT 2  
    """, (nome,))  

    dados = cur.fetchall()  

    if len(dados) < 2:  
        return f"Dados insuficientes para evolução de {nome}"  

    diff = dados[0][0] - dados[1][0]  
    simbolo = "📈" if diff > 0 else "📉" if diff < 0 else "➖"  

    return f"{simbolo} {nome}\nXP atual: {dados[0][0]}\nVariação: {diff:+}"  

async def comando_xp(update, context):  
    args = context.args  

    if not args:  
        await update.message.reply_text(get_rank_xp())  
    else:  
        nome = limpar_nome(" ".join(args))  
        await update.message.reply_text(get_evolucao(nome))  

# ================= RANK (🔥 NOVO SISTEMA PERSISTENTE) =================  

def gerar_rank(campo, titulo):
    cur = conn.cursor()

    cur.execute(f"""
        SELECT DISTINCT ON (nome) nome, {campo}
        FROM status
        WHERE {campo} IS NOT NULL
        ORDER BY nome, data DESC
    """)

    dados = cur.fetchall()

    if not dados:
        return f"Sem dados de {titulo}."

    dados = sorted(dados, key=lambda x: x[1], reverse=True)

    texto = f"🏆 RANKING {titulo}\n\n"
    for i, (nome, valor) in enumerate(dados, 1):
        texto += f"{i}. {nome} — {valor}\n"

    return texto

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

    xp = extrair_xp(texto)  
    nivel = extrair_nivel(texto)  
    dados = extrair_status(texto)  

    registrar_membro(nome)  
    salvou = salvar_presenca(nome)  

    salvar_xp(nome, xp, nivel)  
    salvar_status(nome, dados)  

    if salvou:  
        await msg.reply_text(mensagem_pilar(nome))  
    else:  
        await msg.reply_text(f"⚠️ {nome} já marcou presença hoje")  

    await atualizar_painel(context.application)  

# ================= MAIN =================  

def main():  
    app = ApplicationBuilder().token(TOKEN).build()  

    app.add_handler(CommandHandler("xp", comando_xp))  
    app.add_handler(CommandHandler("lista", comando_lista))  

    app.add_handler(CommandHandler("atk", lambda u,c: u.message.reply_text(gerar_rank("atk","ATAQUE"))))  
    app.add_handler(CommandHandler("def", lambda u,c: u.message.reply_text(gerar_rank("def","DEFESA"))))  
    app.add_handler(CommandHandler("hp", lambda u,c: u.message.reply_text(gerar_rank("hp","HP"))))  
    app.add_handler(CommandHandler("crit", lambda u,c: u.message.reply_text(gerar_rank("crit","CRÍTICO"))))  
    app.add_handler(CommandHandler("gold", lambda u,c: u.message.reply_text(gerar_rank("gold","GOLD"))))  
    app.add_handler(CommandHandler("tofu", lambda u,c: u.message.reply_text(gerar_rank("tofus","TOFUS"))))  

    app.add_handler(MessageHandler(filters.TEXT | filters.CaptionRegex(".*"), detectar))  

    print("🚀 BOT FINAL COM PAINEL DIÁRIO + HORÁRIO")  

    app.run_polling(drop_pending_updates=True)  

if __name__ == "__main__":  
    main()
