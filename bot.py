import os
import re
import random
import psycopg2
import pytz
from datetime import datetime
from telegram import Update
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

GRUPO_ID = -1003792787717

TOPICO_PRESENCA = 16325
TOPICO_LOOTS = 19

TOPICO_PILAR = 29992
TOPICO_GIBBY = 82230

conn = psycopg2.connect(DATABASE_URL)
tz = pytz.timezone("America/Sao_Paulo")

def comando_permitido(msg):

    if msg.chat.type == "private":

        return membro_cadastrado(
            msg.from_user.id
        )

    return (
        msg.chat.id == GRUPO_ID
        and msg.message_thread_id == TOPICO_PILAR
    )

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

    bonus_atk = 0
    bonus_def = 0
    bonus_crit = 0

    atk = None
    defesa = None
    crit = None

    for linha in texto.split("\n"):
        linha = linha.strip()

        # STATUS PRINCIPAIS
        if "ATK" in linha and "DEF" in linha and "CRIT" in linha and "+" not in linha:

            atk_match = re.search(r"ATK\s+(\d+\.?\d*)", linha)
            def_match = re.search(r"DEF\s+(\d+\.?\d*)", linha)
            crit_match = re.search(r"CRIT\s+(\d+\.?\d*)", linha)

            if atk_match:
                atk = float(atk_match.group(1))

            if def_match:
                defesa = float(def_match.group(1))

            if crit_match:
                crit = float(crit_match.group(1))

        # POÇÕES
        elif "+" in linha and "ATK" in linha and "DEF" in linha and "CRIT" in linha:

            atk_match = re.search(r"\+(\d+\.?\d*)\s*ATK", linha)
            def_match = re.search(r"\+(\d+\.?\d*)\s*DEF", linha)
            crit_match = re.search(r"\+(\d+\.?\d*)\s*%?\s*CRIT", linha)

            if atk_match:
                bonus_atk = float(atk_match.group(1))

            if def_match:
                bonus_def = float(def_match.group(1))

            if crit_match:
                bonus_crit = float(crit_match.group(1))

        # ===== HP =====
        elif "HP" in linha:

            hp_match = re.search(r"(\d+)\s*/\s*(\d+)", linha)

            if hp_match:
                dados["hp"] = int(hp_match.group(2))
            else:
                numeros = re.findall(r"\d+", linha)
                if numeros:
                    dados["hp"] = int(numeros[-1])

        # ===== GOLD =====
        elif "Gold:" in linha:

            numeros = re.findall(r"\d+", linha)

            if numeros:
                dados["gold"] = int(numeros[0])

        # ===== TOFUS =====
        elif "Tofus:" in linha:

            numeros = re.findall(r"\d+", linha)

            if numeros:
                dados["tofus"] = int(numeros[0])

    # ===== APLICA DESCONTO DAS POÇÕES =====

    if atk is not None:
        dados["atk"] = max(0, atk - bonus_atk)

    if defesa is not None:
        dados["def"] = max(0, defesa - bonus_def)

    if crit is not None:
        dados["crit"] = max(0, crit - bonus_crit)

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

    if xp is None:
        return

    cur = conn.cursor()

    cur.execute("""
        SELECT xp
        FROM xp_logs
        WHERE telegram_id=%s
        ORDER BY data_hora DESC
        LIMIT 1
    """, (tg_id,))

    ultimo = cur.fetchone()

    if ultimo and ultimo[0] == xp:
        return

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

def buscar_nome_por_id(tg_id):

    cur = conn.cursor()

    cur.execute(
        "SELECT nome FROM membros WHERE telegram_id=%s",
        (tg_id,)
    )

    row = cur.fetchone()

    return row[0] if row else None

MSG_GIBBY_SUCESSO_1 = [
    "🔨 O Gibby bateu torto, mas bateu certo. {item} alcançou +1.",
    "🍺 Gibby jurou que sabia o que estava fazendo. E funcionou.",
    "✨ O martelo cantou, as runas brilharam e {item} virou +1.",
    "🛠 Depois de muito barulho e pouca técnica, sucesso.",
    "🔥 Os espíritos da forja aprovaram a tentativa.",
    "🏹 O Rastreador anota mais uma vitória nos livros da forja."
]

MSG_GIBBY_SUCESSO_2 = [
    "⚡ O impossível aconteceu. {item} alcançou +2.",
    "🍀 Alguém claramente roubou sorte hoje.",
    "🔨 O velho Gibby tropeçou e acertou o golpe perfeito.",
    "📜 Mais um registro glorioso para os livros da forja.",
    "🔥 As chamas aceitaram o sacrifício.",
    "🏆 O martelo venceu a estatística."
]

MSG_GIBBY_SUCESSO_3 = [
    "👑 LENDA! {item} alcançou +3. Os livros da forja registrarão este feito por gerações."
]

MSG_GIBBY_FALHA = [
    "💀 Gibby cobrou o preço. Dois {item} viraram pó.",
    "🪦 Os espíritos da forja rejeitaram a tentativa.",
    "🔥 O martelo venceu. Os itens perderam.",
    "🍺 Gibby garante que da próxima vez funciona.",
    "⚰ Mais um par de itens tombou diante da estatística.",
    "📉 O ouro foi gasto. A tristeza foi gratuita."
]

def membro_cadastrado(tg_id):

    cur = conn.cursor()

    cur.execute(
        """
        SELECT 1
        FROM membros
        WHERE telegram_id=%s
        """,
        (tg_id,)
    )

    return cur.fetchone() is not None

async def avisar_tentativa_acesso(
    context,
    user,
    comando
):

    texto = (
        "🚨 TENTATIVA DE ACESSO\n\n"
        f"👤 Nome: {user.full_name}\n"
        f"📛 Username: @{user.username if user.username else 'sem username'}\n"
        f"🆔 ID: {user.id}\n"
        f"⌨ Comando: {comando}"
    )

    await context.bot.send_message(
        chat_id=5285053532,
        text=texto
    )

async def validar_acesso(
    update,
    context,
    comando
):

    if comando_permitido(
        update.message
    ):
        return True

    if update.message.chat.type == "private":

        await avisar_tentativa_acesso(
            context,
            update.effective_user,
            comando
        )

        await update.message.reply_text(
            "⚠ Você não possui um perfil cadastrado.\n\n"
            "Envie seu perfil no tópico de Presença da guilda e tente novamente."
        )

    return False

def extrair_cacada(texto):

    if "RESUMO DA CAÇADA EM DUPLA" not in texto:
        return None

    dados = {
        "xp": 0,
        "gold": 0,
        "lendarios": 0,
        "pvps": 0
    }

    xp_match = re.search(
        r"Total recebido:\s*([\d,.]+)\s*XP|XP recebido:\s*([\d,.]+)\s*XP",
        texto
    )

    if xp_match:

        valor = xp_match.group(1) or xp_match.group(2)

        dados["xp"] = int(
            valor.replace(",", "").replace(".", "")
        )

    gold_match = re.search(
        r"Gold recebido:\s*([\d,.]+)",
        texto
    )

    if gold_match:

        dados["gold"] = int(
            gold_match.group(1)
            .replace(",", "")
            .replace(".", "")
        )

    lendarios = 0

    for linha in texto.split("\n"):

        linha = linha.strip()

        if (
            "Tônico" not in linha
            and "Poção" not in linha
            and "Chave" not in linha
            and "XP" not in linha
            and "Gold" not in linha
            and linha
        ):

            if (
                "Drops:" not in linha
                and "Equipes eliminadas" not in linha
            ):
                pass

    lendarios = texto.count("🟠")

    if "Equipes eliminadas:" in texto:

        dados["pvps"] = len(
            re.findall(r"→", texto)
        )

    dados["lendarios"] = lendarios

    return dados

def extrair_gibby(texto):

    texto = texto.strip()

    # ===== SUCESSO =====

    if "SUCESSO!" in texto:

        match = re.search(
            r"SUCESSO!\s*🔥?\s*\n*\s*(.+?) foi forjado",
            texto,
            re.DOTALL
        )

        if not match:
            return None

        item = match.group(1).strip()

        nivel_match = re.search(
            r"evoluiu para \+(\d)",
            texto
        )

        if not nivel_match:
            return None

        nivel_destino = int(
            nivel_match.group(1)
        )

        nivel_origem = nivel_destino - 1

        itens_base = {
            1: 2,
            2: 4,
            3: 8
        }.get(nivel_destino, 0)

        return {
            "item": item,
            "nivel_origem": nivel_origem,
            "nivel_destino": nivel_destino,
            "resultado": "SUCESSO",
            "itens_base": itens_base
        }

    # ===== FALHA =====

    if "FALHA CATASTRÓFICA" in texto:

        match = re.search(
            r"Ambos os (.+?) \+(\d)",
            texto
        )

        if match:

            item = match.group(1).strip()

            nivel_origem = int(match.group(2))
            nivel_destino = nivel_origem + 1

        else:

            match = re.search(
                r"Ambos os (.+?) explodiram",
                texto
            )

            if not match:
                return None

            item = match.group(1).strip()

            nivel_origem = 0
            nivel_destino = 1

        itens_base = {
            1: 2,
            2: 4,
            3: 8
        }.get(nivel_destino, 0)

        return {
            "item": item,
            "nivel_origem": nivel_origem,
            "nivel_destino": nivel_destino,
            "resultado": "FALHA",
            "itens_base": itens_base
        }

    return None

def salvar_cacada(tg_id, nome, dados):

    if not dados:
        return

    cur = conn.cursor()

    cur.execute("""
        INSERT INTO cacadas
        (
            telegram_id,
            nome,
            xp,
            gold,
            lendarios,
            pvps
        )
        VALUES (%s,%s,%s,%s,%s,%s)
    """,
    (
        tg_id,
        nome,
        dados["xp"],
        dados["gold"],
        dados["lendarios"],
        dados["pvps"]
    ))

    conn.commit()

def salvar_gibby(
    tg_id,
    nome,
    item,
    nivel_origem,
    nivel_destino,
    resultado,
    itens_base
):

    cur = conn.cursor()

    cur.execute("""
        INSERT INTO gibby_logs
        (
            telegram_id,
            nome,
            item,
            nivel_origem,
            nivel_destino,
            resultado,
            itens_base_consumidos
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """,
    (
        tg_id,
        nome,
        item,
        nivel_origem,
        nivel_destino,
        resultado,
        itens_base
    ))

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

def ranking_status(campo, titulo):
    cur = conn.cursor()

    cur.execute(f"""
        SELECT DISTINCT ON (telegram_id)
               nome,
               {campo}
        FROM status
        WHERE {campo} IS NOT NULL
        ORDER BY telegram_id, data_hora DESC
    """)

    dados = cur.fetchall()

    dados.sort(
        key=lambda x: float(x[1]) if x[1] is not None else 0,
        reverse=True
    )

    texto = f"🏆 {titulo}\n\n"

    for i, (nome, valor) in enumerate(dados, 1):
        texto += f"{i}. {nome} — {valor}\n"

    return texto

def ranking_xpdif():
    cur = conn.cursor()

    cur.execute("""
        SELECT telegram_id, nome, xp, data_hora
        FROM xp_logs
        ORDER BY telegram_id, data_hora ASC
    """)

    rows = cur.fetchall()

    hoje_data = hoje()
    dados = {}

    for tg_id, nome, xp, data_hora in rows:

        data_registro = data_hora.astimezone(tz).date()

        if tg_id not in dados:
            dados[tg_id] = {
                "nome": nome,
                "base": None,
                "ultimo": xp,
                "ultimo_ontem": None
            }

        dados[tg_id]["ultimo"] = xp

        if data_registro < hoje_data:
            dados[tg_id]["ultimo_ontem"] = xp

        elif data_registro == hoje_data and dados[tg_id]["base"] is None:
            dados[tg_id]["base"] = xp

    resultado = []

    for jogador in dados.values():

        if jogador["ultimo_ontem"] is not None:
            base = jogador["ultimo_ontem"]
        else:
            base = jogador["base"]

        if base is None:
            continue

        ganho = jogador["ultimo"] - base

        resultado.append(
            (
                jogador["nome"],
                ganho
            )
        )

    resultado.sort(
        key=lambda x: x[1],
        reverse=True
    )

    texto = "📊 VARIAÇÃO XP (HOJE)\n\n"

    for pos, (nome, ganho) in enumerate(resultado, 1):

        emoji = "📈" if ganho > 0 else "➖"

        texto += f"{pos}. {nome} — {emoji} {ganho:+}\n"

    return texto

async def cmd_lista(update, context):

    if not await validar_acesso(
        update,
        context,
        "/lista"
    ):
        return

    await update.message.reply_text(
        gerar_lista()
    )

async def cmd_xp(update, context):

    if not await validar_acesso(
        update,
        context,
        "/xp"
    ):
        return

    await update.message.reply_text(
        ranking_xp()
    )

async def cmd_xpdif(update, context):

    if not await validar_acesso(
        update,
        context,
        "/xpdif"
    ):
        return

    await update.message.reply_text(
        ranking_xpdif()
    )

async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = update.message

    if not msg:
        return

    texto = msg.text or msg.caption

    if not texto:
        return

    # =========================
    # CAÇADA EM DUPLA
    # =========================

    eh_privado = msg.chat.type == "private"

    eh_loot = (
        msg.chat.id == GRUPO_ID
        and msg.message_thread_id == TOPICO_LOOTS
    )

    if eh_privado or eh_loot:

        dados_cacada = extrair_cacada(texto)

        if dados_cacada:

            tg_id = msg.from_user.id

            nome = buscar_nome_por_id(tg_id)

            if not nome:

                await msg.reply_text(
                    "⚠ Você ainda não possui perfil cadastrado."
                )

                return

            salvar_cacada(
                tg_id,
                nome,
                dados_cacada
            )

            await msg.reply_text(
                f"🏹 Boa {nome}! Dados da caçada salvos."
            )

            return

    # =========================
    # FORJA DO GIBBY
    # =========================

    eh_gibby = (
        msg.chat.id == GRUPO_ID
        and msg.message_thread_id == TOPICO_GIBBY
    )

    if eh_privado or eh_gibby:

        dados_gibby = extrair_gibby(texto)

        if dados_gibby:

            tg_id = msg.from_user.id

            nome = buscar_nome_por_id(tg_id)

            if not nome:

                await msg.reply_text(
                    "⚠ Você ainda não possui perfil cadastrado."
                )

                return

            salvar_gibby(
                tg_id,
                nome,
                dados_gibby["item"],
                dados_gibby["nivel_origem"],
                dados_gibby["nivel_destino"],
                dados_gibby["resultado"],
                dados_gibby["itens_base"]
            )

            if dados_gibby["resultado"] == "SUCESSO":

                if dados_gibby["nivel_destino"] == 1:

                    resposta = random.choice(
                        MSG_GIBBY_SUCESSO_1
                    )

                elif dados_gibby["nivel_destino"] == 2:

                    resposta = random.choice(
                        MSG_GIBBY_SUCESSO_2
                    )

                else:

                    resposta = random.choice(
                        MSG_GIBBY_SUCESSO_3
                    )

            else:

                resposta = random.choice(
                    MSG_GIBBY_FALHA
                )

            await msg.reply_text(
                resposta.format(
                    item=dados_gibby["item"]
                )
            )

            return

    # =========================
    # PRESENÇA
    # =========================

    if msg.chat.id != GRUPO_ID:
        return

    if msg.message_thread_id != TOPICO_PRESENCA:
        return

    nome = extrair_nome(texto)

    if not nome:
        return

    tg_id = msg.from_user.id
    xp = extrair_xp(texto)
    nivel = extrair_nivel(texto)
    status = extrair_status(texto)

    registrar_membro(tg_id, nome)

    novo = salvar_presenca(
        tg_id,
        nome
    )

    salvar_xp(
        tg_id,
        nome,
        xp,
        nivel
    )

    salvar_status(
        tg_id,
        nome,
        status
    )

    if novo:
        await msg.reply_text(
            f"✅ Primeiro perfil do dia registrado {nome}"
        )
    else:
        await msg.reply_text(
            f"{nome} Dados do dia atualizados"
        )

async def cmd_cacada(update, context):

    if not await validar_acesso(
        update,
        context,
        "/cacada"
    ):
        return

    tg_id = update.effective_user.id

    cur = conn.cursor()

    cur.execute("""
        SELECT
            COALESCE(SUM(xp),0),
            COALESCE(SUM(gold),0),
            COALESCE(SUM(lendarios),0),
            COALESCE(SUM(pvps),0)
        FROM cacadas
        WHERE telegram_id=%s
    """,(tg_id,))

    xp,gold,lend,pvp = cur.fetchone()

    nome = buscar_nome_por_id(tg_id)

    texto = (
        f"🏹 RESUMO DE CAÇADA\n\n"
        f"👤 {nome}\n\n"
        f"📦 XP acumulado: {xp:,}\n"
        f"💰 Gold acumulado: {gold:,}\n"
        f"🟠 Lendários: {lend}\n"
        f"⚔ PvPs vencidos: {pvp}"
    )

    await update.message.reply_text(texto)

async def cmd_pvp(update, context):

    if not await validar_acesso(
        update,
        context,
        "/pvp"
    ):
        return

    cur = conn.cursor()

    cur.execute("""
        SELECT
            nome,
            SUM(pvps)
        FROM cacadas
        GROUP BY nome
        HAVING SUM(pvps) > 0
        ORDER BY SUM(pvps) DESC
        LIMIT 20
    """)

    rows = cur.fetchall()

    texto = "⚔ RANKING DE CAÇADORES\n\n"

    for i,(nome,pvps) in enumerate(rows,1):

        texto += (
            f"{i}. {nome} — {pvps} PvPs\n"
        )

    await update.message.reply_text(texto)

async def mostrar_item_gibby(
    update,
    tg_id,
    item
):

    cur = conn.cursor()

    cur.execute("""
        SELECT
            nivel_destino,
            resultado
        FROM gibby_logs
        WHERE telegram_id=%s
        AND item=%s
    """,
    (
        tg_id,
        item
    ))

    rows = cur.fetchall()

    usados = len(rows)

    itens_base = 0

    s1=f1=s2=f2=s3=f3=0

    for nivel, resultado in rows:

        if nivel == 1:

            itens_base += 2

            if resultado == "SUCESSO":
                s1 += 1
            else:
                f1 += 1

        elif nivel == 2:

            itens_base += 4

            if resultado == "SUCESSO":
                s2 += 1
            else:
                f2 += 1

        elif nivel == 3:

            itens_base += 8

            if resultado == "SUCESSO":
                s3 += 1
            else:
                f3 += 1

    def pct(s,f):

        total = s + f

        if total == 0:
            return 0

        return round(
            s * 100 / total,
            1
        )

    total_s = s1+s2+s3
    total_f = f1+f2+f3

    geral = pct(
        total_s,
        total_f
    )

    nome = buscar_nome_por_id(tg_id)

    texto = (
        f"👤 {nome}\n\n"
        f"📿 {item}\n\n"
        f"🔨 Martelos usados: {usados}\n"
        f"📦 Itens base consumidos: {itens_base}\n\n"
        f"⭐ +1\n"
        f"✅ {s1} sucessos\n"
        f"❌ {f1} falhas\n"
        f"🎯 {pct(s1,f1)}%\n\n"
        f"⭐⭐ +2\n"
        f"✅ {s2} sucessos\n"
        f"❌ {f2} falhas\n"
        f"🎯 {pct(s2,f2)}%\n\n"
        f"⭐⭐⭐ +3\n"
        f"✅ {s3} sucessos\n"
        f"❌ {f3} falhas\n"
        f"🎯 {pct(s3,f3)}%\n\n"
        f"🏆 Taxa geral\n"
        f"🎯 {geral}%"
    )

    await update.message.reply_text(texto)

async def cmd_gibby(update, context):

    if not await validar_acesso(
        update,
        context,
        "/gibby"
    ):
        return

    tg_id = update.effective_user.id

    # CONSULTA DE ITEM

    if context.args:

        try:
            numero = int(context.args[0])

        except:

            await update.message.reply_text(
                "Use /gibby <número>"
            )

            return

        cur = conn.cursor()

        cur.execute("""
            SELECT DISTINCT item
            FROM gibby_logs
            WHERE telegram_id=%s
            ORDER BY item
        """,(tg_id,))

        itens = [x[0] for x in cur.fetchall()]

        if numero < 1 or numero > len(itens):

            await update.message.reply_text(
                "❌ Item não encontrado."
            )

            return

        item = itens[numero - 1]

        await mostrar_item_gibby(
            update,
            tg_id,
            item
        )

        return

    cur = conn.cursor()

    # martelos usados
    cur.execute("""
        SELECT COUNT(*)
        FROM gibby_logs
        WHERE telegram_id=%s
    """,(tg_id,))

    martelos = cur.fetchone()[0]

    # itens base
    cur.execute("""
        SELECT COALESCE(
            SUM(itens_base_consumidos),
            0
        )
        FROM gibby_logs
        WHERE telegram_id=%s
    """,(tg_id,))

    itens_base = cur.fetchone()[0]

    # taxa geral
    cur.execute("""
        SELECT
            COUNT(*),
            SUM(
                CASE
                    WHEN resultado='SUCESSO'
                    THEN 1
                    ELSE 0
                END
            )
        FROM gibby_logs
        WHERE telegram_id=%s
    """,(tg_id,))

    total, sucessos = cur.fetchone()

    sucessos = sucessos or 0

    taxa_geral = (
        sucessos * 100 / total
        if total
        else 0
    )

    # itens registrados
    cur.execute("""
        SELECT DISTINCT item
        FROM gibby_logs
        WHERE telegram_id=%s
        ORDER BY item
    """,(tg_id,))

    itens = [x[0] for x in cur.fetchall()]

    nome = buscar_nome_por_id(tg_id)

    texto = (
        f"🔨 LIVRO DA FORJA DO GIBBY\n\n"
        f"👤 {nome}\n\n"
        f"🔨 Martelos usados: {martelos}\n\n"
        f"📦 Itens base consumidos: {itens_base}\n\n"
    )

    for nivel in [1,2,3]:

        cur.execute("""
            SELECT
                COUNT(*),
                SUM(
                    CASE
                        WHEN resultado='SUCESSO'
                        THEN 1
                        ELSE 0
                    END
                )
            FROM gibby_logs
            WHERE telegram_id=%s
            AND nivel_destino=%s
        """,(tg_id,nivel))

        total_nivel, sucesso_nivel = cur.fetchone()

        sucesso_nivel = sucesso_nivel or 0

        taxa = (
            sucesso_nivel * 100 / total_nivel
            if total_nivel
            else 0
        )

        estrelas = "⭐" * nivel

        texto += (
            f"{estrelas} - 🎯 {taxa:.1f}%\n\n"
        )

    texto += (
        f"🏆 Taxa geral\n"
        f"🎯 {taxa_geral:.1f}%\n\n"
        f"📜 ITENS REGISTRADOS\n\n"
    )

    for i,item in enumerate(itens,1):

        texto += f"{i}. {item}\n"

    texto += (
        "\nℹ️ Use /gibby <número> "
        "para consultar os detalhes de um item.\n"
        "Exemplo: /gibby 1"
    )

    await update.message.reply_text(texto)

async def cmd_gibbyazar(update, context):

    if not await validar_acesso(
        update,
        context,
        "/gibbyazar"
    ):
        return

    cur = conn.cursor()

    cur.execute("""
        SELECT
            nome,
            COUNT(*) AS martelos,
            SUM(
                CASE
                    WHEN resultado='SUCESSO'
                    THEN 1
                    ELSE 0
                END
            ) AS sucessos
        FROM gibby_logs
        GROUP BY nome
        HAVING COUNT(*) >= 10
    """)

    rows = cur.fetchall()

    ranking = []

    for nome, martelos, sucessos in rows:

        sucessos = sucessos or 0

        taxa = (
            sucessos * 100 / martelos
        )

        ranking.append(
            (
                taxa,
                nome,
                martelos
            )
        )

    ranking.sort(key=lambda x: x[0])

    texto = (
        "💀 AMALDIÇOADOS PELO GOBLIN GIBBY\n\n"
    )

    if not ranking:

        texto += (
            "Ainda não há registros suficientes."
        )

    else:

        for pos, (taxa, nome, martelos) in enumerate(ranking[:10], 1):

            texto += (
                f"{pos}. {nome}\n"
                f"🎯 {taxa:.1f}% de sucesso\n"
                f"🔨 {martelos} martelos\n\n"
            )

        texto += (
            "🍺 O Gibby agradece "
            "as contribuições para a ciência."
        )

    await update.message.reply_text(texto)

async def cmd_gibbygeral(update, context):

    if not await validar_acesso(
        update,
        context,
        "/gibbygeral"
    ):
        return

    cur = conn.cursor()

    # Ferreiros registrados

    cur.execute("""
        SELECT COUNT(DISTINCT telegram_id)
        FROM gibby_logs
    """)

    ferreiros = cur.fetchone()[0]

    # Martelos utilizados

    cur.execute("""
        SELECT COUNT(*)
        FROM gibby_logs
    """)

    martelos = cur.fetchone()[0]

    # Itens base consumidos

    cur.execute("""
        SELECT COALESCE(
            SUM(itens_base_consumidos),
            0
        )
        FROM gibby_logs
    """)

    itens_base = cur.fetchone()[0]

    # +3 criados

    cur.execute("""
        SELECT COUNT(*)
        FROM gibby_logs
        WHERE resultado='SUCESSO'
        AND nivel_destino=3
    """)

    mais3 = cur.fetchone()[0]

    # Contadores

    dados = {}

    for nivel in [1,2,3]:

        cur.execute("""
            SELECT
                SUM(
                    CASE
                        WHEN resultado='SUCESSO'
                        THEN 1
                        ELSE 0
                    END
                ),
                SUM(
                    CASE
                        WHEN resultado='FALHA'
                        THEN 1
                        ELSE 0
                    END
                )
            FROM gibby_logs
            WHERE nivel_destino=%s
        """,(nivel,))

        sucesso, falha = cur.fetchone()

        sucesso = sucesso or 0
        falha = falha or 0

        dados[nivel] = (
            sucesso,
            falha
        )

    total_sucesso = (
        dados[1][0]
        + dados[2][0]
        + dados[3][0]
    )

    total_falha = (
        dados[1][1]
        + dados[2][1]
        + dados[3][1]
    )

    total = total_sucesso + total_falha

    taxa_geral = (
        total_sucesso * 100 / total
        if total
        else 0
    )

    itens_destruidos = (
        itens_base
        - (
            dados[1][0] * 1
            + dados[2][0] * 2
            + dados[3][0] * 4
        )
    )

    texto = (
        f"🔨 GRANDES LIVROS DA FORJA DO GIBBY\n\n"
        f"📊 Dados gerais da Legends\n\n"
        f"👥 Ferreiros registrados: {ferreiros}\n\n"
        f"🔨 Martelos utilizados: {martelos}\n\n"
        f"📦 Itens base consumidos: {itens_base}\n\n"
        f"💀 Itens destruídos: {itens_destruidos}\n\n"
        f"👑 Itens +3 criados: {mais3}\n\n"
        f"━━━━━━━━━━━━\n\n"
        f"⭐ +1\n"
        f"✅ {dados[1][0]}\n"
        f"❌ {dados[1][1]}\n"
        f"🎯 {(dados[1][0]*100/(dados[1][0]+dados[1][1])) if (dados[1][0]+dados[1][1]) else 0:.1f}%\n\n"
        f"⭐⭐ +2\n"
        f"✅ {dados[2][0]}\n"
        f"❌ {dados[2][1]}\n"
        f"🎯 {(dados[2][0]*100/(dados[2][0]+dados[2][1])) if (dados[2][0]+dados[2][1]) else 0:.1f}%\n\n"
        f"⭐⭐⭐ +3\n"
        f"✅ {dados[3][0]}\n"
        f"❌ {dados[3][1]}\n"
        f"🎯 {(dados[3][0]*100/(dados[3][0]+dados[3][1])) if (dados[3][0]+dados[3][1]) else 0:.1f}%\n\n"
        f"━━━━━━━━━━━━\n\n"
        f"🏆 Taxa geral\n"
        f"🎯 {taxa_geral:.1f}%\n\n"
        f"📜 Os livros da forja continuam crescendo a cada martelo utilizado."
    )

    await update.message.reply_text(texto)

async def cmd_item(update, context):

    if not await validar_acesso(
        update,
        context,
        "/item"
    ):
        return

    teclado = [

        [
            InlineKeyboardButton(
                "⚔ Guerreiro",
                callback_data="bib_guerreiro"
            )
        ],

        [
            InlineKeyboardButton(
                "🏹 Arqueiro",
                callback_data="bib_arqueiro"
            )
        ],

        [
            InlineKeyboardButton(
                "🔮 Mago",
                callback_data="bib_mago"
            )
        ],

        [
            InlineKeyboardButton(
                "🧪 Consumíveis",
                callback_data="bib_consumiveis"
            )
        ],

        [
            InlineKeyboardButton(
                "✨ Especiais",
                callback_data="bib_especiais"
            )
        ]

    ]

    await update.message.reply_text(
        "📚 BIBLIOTECA LEGENDS\n\n"
        "Escolha uma categoria:",
        reply_markup=InlineKeyboardMarkup(
            teclado
        )
    )

async def cmd_atk(update, context):

    if not await validar_acesso(
        update,
        context,
        "/atk"
    ):
        return

    await update.message.reply_text(
        ranking_status(
            "atk",
            "ATAQUE"
        )
    )

async def cmd_def(update, context):

    if not await validar_acesso(
        update,
        context,
        "/def"
    ):
        return

    await update.message.reply_text(
        ranking_status(
            "def",
            "DEFESA"
        )
    )

async def cmd_hp(update, context):

    if not await validar_acesso(
        update,
        context,
        "/hp"
    ):
        return

    await update.message.reply_text(
        ranking_status(
            "hp",
            "HP"
        )
    )

async def cmd_crit(update, context):

    if not await validar_acesso(
        update,
        context,
        "/crit"
    ):
        return

    await update.message.reply_text(
        ranking_status(
            "crit",
            "CRÍTICO"
        )
    )

def main():
    print("1 - Entrou no main")

    app = ApplicationBuilder().token(TOKEN).build()

    print("2 - Application criada")

    # COMANDOS
    app.add_handler(CommandHandler("lista", cmd_lista))
    app.add_handler(CommandHandler("xp", cmd_xp))
    app.add_handler(CommandHandler("xpdif", cmd_xpdif))

    app.add_handler(CommandHandler("cacada", cmd_cacada))
    app.add_handler(CommandHandler("pvp", cmd_pvp))

    app.add_handler(
        CommandHandler(
            "gibby",
            cmd_gibby
        )
    )

    app.add_handler(
        CommandHandler(
            "gibbyazar",
            cmd_gibbyazar
        )
    )

    app.add_handler(
        CommandHandler(
            "gibbygeral",
            cmd_gibbygeral
        )
    )

    app.add_handler(
        CommandHandler(
            "item",
            cmd_item
        )
    )

    app.add_handler(
        CommandHandler(
            "atk",
            cmd_atk
        )
    )

    app.add_handler(
        CommandHandler(
            "def",
            cmd_def
        )
    )

    app.add_handler(
        CommandHandler(
            "hp",
            cmd_hp
        )
    )

    app.add_handler(
        CommandHandler(
            "crit",
            cmd_crit
        )
    )

    print("3 - Handlers registrados")

    # DETECTOR DE PERFIS
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

