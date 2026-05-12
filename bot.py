import os
import psycopg2
import psycopg2.pool
import random
import pytz
import re
import logging
from datetime import datetime, time as dt_time
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

TOPICO_LISTA = 116
GRUPO_LIDERANCA_ID = -1003806440153
GRUPO_ID = -1003792787717
TOPICO_PRESENCA = 16325
TOPICO_BANCO = 30933
ADMIN_ID = 5285053532

# ================= DATABASE CONNECTION POOL =================
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL)
    logger.info("✅ Pool de conexão de banco criado")
except Exception as e:
    logger.error(f"❌ Erro ao criar pool de banco: {e}")
    db_pool = None

def get_db_connection():
    """Obtém conexão do pool com tratamento de erro"""
    if db_pool is None:
        logger.error("❌ Pool de banco não inicializado")
        return None
    try:
        return db_pool.getconn()
    except Exception as e:
        logger.error(f"❌ Erro ao obter conexão: {e}")
        return None

def return_db_connection(conn):
    """Retorna conexão ao pool"""
    if db_pool and conn:
        db_pool.putconn(conn)

def execute_query(query, params=None, fetch=False, fetch_one=False):
    """Executa query com tratamento de erro centralizado"""
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Conexão com banco indisponível")
        return None if fetch or fetch_one else False
    
    try:
        cur = conn.cursor()
        cur.execute(query, params or ())
        
        if fetch:
            result = cur.fetchall()
        elif fetch_one:
            result = cur.fetchone()
        else:
            conn.commit()
            result = True
        
        cur.close()
        return result
    except Exception as e:
        logger.error(f"❌ Erro na query: {e}")
        conn.rollback()
        return None if fetch or fetch_one else False
    finally:
        return_db_connection(conn)

tz = pytz.timezone("America/Sao_Paulo")

# ================= MIGRATIONS =================
def run_migrations():
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Migration falhou: sem conexão")
        return
    try:
        cur = conn.cursor()
        cur.execute("ALTER TABLE membros ADD COLUMN IF NOT EXISTS telegram_id BIGINT")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                nome_mob VARCHAR NOT NULL,
                status VARCHAR DEFAULT 'ativa',
                data_inicio TIMESTAMP DEFAULT NOW(),
                data_fim TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS task_participantes (
                id SERIAL PRIMARY KEY,
                task_id INT REFERENCES tasks(id),
                telegram_id BIGINT NOT NULL,
                nome VARCHAR NOT NULL,
                kills INT DEFAULT 0,
                data DATE DEFAULT CURRENT_DATE,
                UNIQUE(task_id, telegram_id)
            )
        """)
        conn.commit()
        cur.close()
        logger.info("✅ Migrations executadas com sucesso")
    except Exception as e:
        logger.error(f"❌ Erro nas migrations: {e}")
        conn.rollback()
    finally:
        return_db_connection(conn)

# ================= DATA =================
def hoje():
    return datetime.now(tz).date()

# ================= UTIL =================
def limpar_nome(nome):
    if not nome:
        return None
    return nome.replace("[LG]", "").strip().upper()

def extrair_nome(texto):
    if not texto:
        return None
    for linha in texto.split("\n"):
        partes = linha.strip().split()
        for i, p in enumerate(partes):
            if p.isdigit():
                return limpar_nome(" ".join(partes[i + 1:]))
    return None

def extrair_xp(texto):
    if not texto:
        return None
    for linha in texto.split("\n"):
        if "XP" in linha:
            numeros = re.findall(r"\d+", linha.replace(".", "").replace(",", ""))
            if len(numeros) >= 2:
                return int(numeros[1])
    return None

def extrair_nivel(texto):
    if not texto:
        return None
    for linha in texto.split("\n"):
        if "Lv" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros:
                return int(numeros[0])
    return None

# ================= STATUS =================
def extrair_status(texto):
    dados = {}
    if not texto:
        return dados
    
    for linha in texto.split("\n"):
        linha = linha.strip()
        if linha.startswith("+"): continue
        if "/" in linha and "HP" not in linha: continue

        if "ATK" in linha and "DEF" in linha and "CRIT" in linha:
            numeros = re.findall(r"\d+\.?\d*", linha.replace(",", "."))
            if len(numeros) >= 3:
                try:
                    dados["atk"] = float(numeros[0])
                    dados["def"] = float(numeros[1])
                    dados["crit"] = float(numeros[2])
                except ValueError:
                    logger.warning(f"⚠️ Erro ao parsear ATK/DEF/CRIT: {numeros}")

        elif "HP" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros:
                try:
                    dados["hp"] = int(numeros[-1])
                except ValueError:
                    logger.warning(f"⚠️ Erro ao parsear HP: {numeros}")

        elif "Gold:" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros:
                try:
                    dados["gold"] = int(numeros[0])
                except ValueError:
                    logger.warning(f"⚠️ Erro ao parsear Gold: {numeros}")

        elif "Tofus:" in linha:
            numeros = re.findall(r"\d+", linha)
            if numeros:
                try:
                    dados["tofus"] = int(numeros[0])
                except ValueError:
                    logger.warning(f"⚠️ Erro ao parsear Tofus: {numeros}")

    return dados

# ================= BANCO BASE =================
def registrar_membro(nome):
    if not nome:
        return False
    query = "INSERT INTO membros (nome) VALUES (%s) ON CONFLICT DO NOTHING"
    return execute_query(query, (nome,))

def salvar_presenca(nome):
    if not nome:
        return False

    check_query = "SELECT 1 FROM presencas WHERE nome=%s AND data=%s"
    if execute_query(check_query, (nome, hoje()), fetch_one=True):
        return False

    insert_query = "INSERT INTO presencas (nome,data) VALUES (%s,%s)"
    execute_query(insert_query, (nome, hoje()))

    execute_query(
        "INSERT INTO tickets(nome,semanal,mensal) VALUES(%s,0,0) ON CONFLICT DO NOTHING",
        (nome,)
    )
    execute_query(
        "UPDATE tickets SET semanal=semanal+1, mensal=mensal+1 WHERE nome=%s",
        (nome,)
    )
    return True

def salvar_xp(nome, xp, nivel):
    if not nome or xp is None:
        return False
    
    query = """
        INSERT INTO xp_logs (nome,xp,nivel,data)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (nome,data)
        DO UPDATE SET xp=EXCLUDED.xp,nivel=EXCLUDED.nivel
    """
    return execute_query(query, (nome, xp, nivel, hoje()))

def salvar_status(nome, dados):
    if not nome or not dados:
        return False
    
    query = """
        INSERT INTO status (nome,data,atk,def,crit,hp,gold,tofus)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (nome,data)
        DO UPDATE SET atk=EXCLUDED.atk,def=EXCLUDED.def,crit=EXCLUDED.crit,
        hp=EXCLUDED.hp,gold=EXCLUDED.gold,tofus=EXCLUDED.tofus
    """
    return execute_query(query, (
        nome, hoje(), dados.get("atk"), dados.get("def"),
        dados.get("crit"), dados.get("hp"),
        dados.get("gold"), dados.get("tofus")
    ))

# ================= XP =================
def get_rank_xp():
    query = """
        SELECT x.nome,x.nivel,x.xp
        FROM xp_logs x
        INNER JOIN (
            SELECT nome, MAX(data) as data_ref
            FROM xp_logs GROUP BY nome
        ) ref
        ON x.nome=ref.nome AND x.data=ref.data_ref
        ORDER BY x.xp DESC
    """
    d = execute_query(query, fetch=True)
    if not d:
        return "❌ Sem dados de XP"

    medalhas = {1: "🥇", 2: "🥈", 3: "🥉"}
    txt = "🏆 RANKING GERAL DE XP\n\n"
    for i, (n, l, xp) in enumerate(d, 1):
        prefix = medalhas.get(i, f"{i}.")
        txt += f"{prefix} {n} — Lv {l} - {xp:,} XP\n"
    return txt

def get_rank_xp_dif():
    query = """
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
    """
    dados = execute_query(query, fetch=True)
    if not dados:
        return "❌ Sem dados de variação"
    
    texto = "📊 VARIAÇÃO XP (24h)\n\n"
    for i, (nome, diff) in enumerate(dados, 1):
        simbolo = "📈" if diff > 0 else "📉" if diff < 0 else "➖"
        texto += f"{i}. {nome} — {simbolo} {diff:+}\n"
    return texto

def get_rank_xp_diario():
    query = """
        WITH hoje AS (
            SELECT nome, xp, nivel
            FROM xp_logs
            WHERE data = CURRENT_DATE
        ),
        anterior AS (
            SELECT DISTINCT ON (nome) nome, xp, nivel
            FROM xp_logs
            WHERE data < CURRENT_DATE
            ORDER BY nome, data DESC
        )
        SELECT
            h.nome,
            h.nivel AS nivel_atual,
            COALESCE(a.nivel, h.nivel) AS nivel_anterior,
            COALESCE(h.xp - a.xp, 0) AS xp_ganho
        FROM hoje h
        LEFT JOIN anterior a ON h.nome = a.nome
        ORDER BY xp_ganho DESC
    """
    dados = execute_query(query, fetch=True)
    if not dados:
        return "❌ Nenhum jogador marcou presença hoje ainda"

    texto = "📅 RANKING XP DO DIA\n\n"
    for i, (nome, nivel_atual, nivel_anterior, xp_ganho) in enumerate(dados, 1):
        if nivel_atual > nivel_anterior:
            nivel_str = f"Lv {nivel_anterior}→{nivel_atual} 🆙"
        else:
            nivel_str = f"Lv {nivel_atual}"
        simbolo = "📈" if xp_ganho > 0 else "➖"
        texto += f"{i}. {nome} — {nivel_str} {simbolo} +{xp_ganho:,} XP\n"
    return texto

# ================= RANK STATUS =================
def gerar_rank(campo, titulo):
    # Validar campo para evitar SQL injection
    campos_validos = ["atk", "def", "crit", "hp", "gold", "tofus"]
    if campo not in campos_validos:
        return f"❌ Campo inválido: {campo}"
    
    query = f"""
        SELECT s.nome,s.{campo}
        FROM status s
        INNER JOIN (
            SELECT nome,MAX(data) as data_ref
            FROM status GROUP BY nome
        ) ref
        ON s.nome=ref.nome AND s.data=ref.data_ref
        ORDER BY s.{campo} DESC
    """
    d = execute_query(query, fetch=True)
    if not d:
        return f"❌ Sem dados de {titulo}"
    
    txt = f"🏆 {titulo}\n\n"
    for i, (n, v) in enumerate(d, 1):
        txt += f"{i}. {n} — {v}\n"
    return txt

# ================= BANCO =================
def get_saldo():
    query = "SELECT saldo FROM banco_guilda LIMIT 1"
    result = execute_query(query, fetch_one=True)
    return result[0] if result else 0

def registrar_doacao(nome, valor):
    if not nome or not isinstance(valor, int) or valor <= 0:
        return 0
    
    conn = get_db_connection()
    if not conn:
        return 0
    
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO doacoes(nome,valor,data) VALUES(%s,%s,CURRENT_DATE)", (nome, valor))
        cur.execute("UPDATE banco_guilda SET saldo=saldo+%s", (valor,))
        t = min(valor // 1000, 20)

        cur.execute("""
            INSERT INTO tickets(nome,semanal,mensal)
            VALUES(%s,0,0)
            ON CONFLICT DO NOTHING
        """, (nome,))

        cur.execute("""
            UPDATE tickets
            SET semanal=semanal+%s, mensal=mensal+%s
            WHERE nome=%s
        """, (t, t, nome))

        conn.commit()
        cur.close()
        return t
    except Exception as e:
        logger.error(f"❌ Erro ao registrar doação: {e}")
        conn.rollback()
        return 0
    finally:
        return_db_connection(conn)

def get_tickets(nome):
    if not nome:
        return None
    query = "SELECT semanal,mensal FROM tickets WHERE nome=%s"
    return execute_query(query, (nome,), fetch_one=True)

def rank_tickets(tipo):
    if tipo not in ["semanal", "mensal"]:
        return "❌ Tipo inválido"
    
    query = f"SELECT nome,{tipo} FROM tickets ORDER BY {tipo} DESC"
    d = execute_query(query, fetch=True)
    if not d:
        return f"❌ Sem dados de {tipo}"

    txt = f"🏆 RANK {tipo.upper()}\n\n"
    for i, (n, v) in enumerate(d, 1):
        txt += f"{i}. {n} — {v}\n"
    return txt

def rank_doacoes():
    query = "SELECT nome,SUM(valor) FROM doacoes GROUP BY nome ORDER BY SUM(valor) DESC"
    d = execute_query(query, fetch=True)
    if not d:
        return "❌ Sem dados de doações"

    txt = "🏆 RANK DOAÇÕES\n\n"
    for i, (n, v) in enumerate(d, 1):
        txt += f"{i}. {n} — {v}\n"
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
async def comando_doar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Acesso negado")
            return
        
        if update.message.chat.type != "private":
            await update.message.reply_text("❌ Use em chat privado")
            return
        
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("❌ Uso: /doar <nome> <valor>")
            return
        
        nome = limpar_nome(context.args[0])
        try:
            valor = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Valor deve ser um número")
            return

        if not nome:
            await update.message.reply_text("❌ Nome inválido")
            return

        t = registrar_doacao(nome, valor)
        s = get_saldo()

        await update.message.reply_text(f"✅ Doação registrada\nTickets: {t}")

        await context.bot.send_message(
            chat_id=GRUPO_ID,
            message_thread_id=TOPICO_BANCO,
            text=gerar_mensagem_doacao(nome, valor, t, s)
        )
    except Exception as e:
        logger.error(f"❌ Erro em comando_doar: {e}")
        await update.message.reply_text("❌ Erro ao processar comando")

async def comando_banco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(f"🏦 Saldo: {get_saldo()} gold")
    except Exception as e:
        logger.error(f"❌ Erro em comando_banco: {e}")
        await update.message.reply_text("❌ Erro ao buscar saldo")

async def comando_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Uso: /ticket <nome>")
            return
        
        nome = limpar_nome(" ".join(context.args))
        if not nome:
            await update.message.reply_text("❌ Nome inválido")
            return
        
        d = get_tickets(nome)

        if not d:
            await update.message.reply_text("❌ Sem tickets")
            return

        await update.message.reply_text(f"{nome}\n🎟 Total: {d[0]+d[1]}")
    except Exception as e:
        logger.error(f"❌ Erro em comando_ticket: {e}")
        await update.message.reply_text("❌ Erro ao buscar tickets")

async def comando_ticketS(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Uso: /ticketS <nome>")
            return
        
        nome = limpar_nome(" ".join(context.args))
        if not nome:
            await update.message.reply_text("❌ Nome inválido")
            return
        
        d = get_tickets(nome)
        if not d:
            await update.message.reply_text("❌ Sem tickets")
            return
        
        await update.message.reply_text(f"{nome}\n🎟 Semanal: {d[0]}")
    except Exception as e:
        logger.error(f"❌ Erro em comando_ticketS: {e}")
        await update.message.reply_text("❌ Erro ao buscar tickets")

async def comando_ticketM(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Uso: /ticketM <nome>")
            return
        
        nome = limpar_nome(" ".join(context.args))
        if not nome:
            await update.message.reply_text("❌ Nome inválido")
            return
        
        d = get_tickets(nome)
        if not d:
            await update.message.reply_text("❌ Sem tickets")
            return
        
        await update.message.reply_text(f"{nome}\n🎟 Mensal: {d[1]}")
    except Exception as e:
        logger.error(f"❌ Erro em comando_ticketM: {e}")
        await update.message.reply_text("❌ Erro ao buscar tickets")

async def comando_rank_semanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(rank_tickets("semanal"))
    except Exception as e:
        logger.error(f"❌ Erro em comando_rank_semanal: {e}")
        await update.message.reply_text("❌ Erro ao buscar ranking")

async def comando_rank_mensal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(rank_tickets("mensal"))
    except Exception as e:
        logger.error(f"❌ Erro em comando_rank_mensal: {e}")
        await update.message.reply_text("❌ Erro ao buscar ranking")

async def comando_rank_doacoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(rank_doacoes())
    except Exception as e:
        logger.error(f"❌ Erro em comando_rank_doacoes: {e}")
        await update.message.reply_text("❌ Erro ao buscar ranking")

async def comando_resetbanco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return
        execute_query("UPDATE banco_guilda SET saldo=0")
        await update.message.reply_text("✅ Banco resetado")
    except Exception as e:
        logger.error(f"❌ Erro em comando_resetbanco: {e}")
        await update.message.reply_text("❌ Erro ao resetar")

async def comando_resetsemanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return
        execute_query("UPDATE tickets SET semanal=0")
        await update.message.reply_text("✅ Tickets semanais resetados")
    except Exception as e:
        logger.error(f"❌ Erro em comando_resetsemanal: {e}")
        await update.message.reply_text("❌ Erro ao resetar")

async def comando_resetmensal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return
        execute_query("UPDATE tickets SET mensal=0")
        await update.message.reply_text("✅ Tickets mensais resetados")
    except Exception as e:
        logger.error(f"❌ Erro em comando_resetmensal: {e}")
        await update.message.reply_text("❌ Erro ao resetar")

# ================= GESTÃO DE TICKETS =================
async def comando_addticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Acesso negado")
            return
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("❌ Uso: /addticket <nome> <qtd>")
            return
        nome = limpar_nome(context.args[0])
        try:
            qtd = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Quantidade deve ser um número")
            return
        if qtd <= 0:
            await update.message.reply_text("❌ Quantidade deve ser positiva")
            return
        execute_query(
            "INSERT INTO tickets(nome,semanal,mensal) VALUES(%s,0,0) ON CONFLICT DO NOTHING",
            (nome,)
        )
        execute_query(
            "UPDATE tickets SET semanal=semanal+%s, mensal=mensal+%s WHERE nome=%s",
            (qtd, qtd, nome)
        )
        await update.message.reply_text(f"✅ +{qtd} tickets adicionados para {nome}")
    except Exception as e:
        logger.error(f"❌ Erro em comando_addticket: {e}")
        await update.message.reply_text("❌ Erro ao adicionar tickets")

async def comando_removeticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Acesso negado")
            return
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("❌ Uso: /removeticket <nome> <qtd>")
            return
        nome = limpar_nome(context.args[0])
        try:
            qtd = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Quantidade deve ser um número")
            return
        if qtd <= 0:
            await update.message.reply_text("❌ Quantidade deve ser positiva")
            return
        execute_query(
            "UPDATE tickets SET semanal=GREATEST(semanal-%s,0), mensal=GREATEST(mensal-%s,0) WHERE nome=%s",
            (qtd, qtd, nome)
        )
        await update.message.reply_text(f"✅ -{qtd} tickets removidos de {nome}")
    except Exception as e:
        logger.error(f"❌ Erro em comando_removeticket: {e}")
        await update.message.reply_text("❌ Erro ao remover tickets")

# ================= COFRE =================
def registrar_item(nome, item):
    if not nome or not item:
        return False
    query = "INSERT INTO cofre_itens (nome,item,data) VALUES (%s,%s,%s)"
    return execute_query(query, (nome, item.upper(), hoje()))

def remover_item(item):
    if not item:
        return None
    query = "DELETE FROM cofre_itens WHERE item=%s LIMIT 1 RETURNING item"
    return execute_query(query, (item.upper(),), fetch_one=True)

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

# ================= TASKS =================
def iniciar_task(nome_mob):
    if not nome_mob:
        return None
    ativa = execute_query("SELECT id FROM tasks WHERE status='ativa'", fetch_one=True)
    if ativa:
        return None
    execute_query("INSERT INTO tasks(nome_mob) VALUES(%s)", (nome_mob,))
    resultado = execute_query("SELECT id FROM tasks WHERE status='ativa'", fetch_one=True)
    return resultado[0] if resultado else None

def get_task_ativa():
    return execute_query("SELECT id, nome_mob FROM tasks WHERE status='ativa'", fetch_one=True)

def registrar_participacao(task_id, telegram_id, nome):
    return execute_query("""
        INSERT INTO task_participantes(task_id, telegram_id, nome, kills)
        VALUES(%s,%s,%s,0) ON CONFLICT DO NOTHING
    """, (task_id, telegram_id, nome))

def registrar_kill(task_id, telegram_id):
    return execute_query(
        "UPDATE task_participantes SET kills=kills+1 WHERE task_id=%s AND telegram_id=%s",
        (task_id, telegram_id)
    )

def finalizar_task(task_id):
    participantes = execute_query(
        "SELECT nome, kills FROM task_participantes WHERE task_id=%s ORDER BY kills DESC",
        (task_id,), fetch=True
    )
    for (nome, _kills) in (participantes or []):
        execute_query(
            "INSERT INTO tickets(nome,semanal,mensal) VALUES(%s,0,0) ON CONFLICT DO NOTHING",
            (nome,)
        )
        execute_query(
            "UPDATE tickets SET semanal=semanal+1, mensal=mensal+1 WHERE nome=%s",
            (nome,)
        )
    execute_query(
        "UPDATE tasks SET status='finalizada', data_fim=NOW() WHERE id=%s",
        (task_id,)
    )
    return participantes or []

async def comando_iniciar_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Acesso negado")
            return
        if not context.args:
            await update.message.reply_text("❌ Uso: /iniciar_task <nome_mob>")
            return
        nome_mob = " ".join(context.args).strip()[:50]
        task_id = iniciar_task(nome_mob)
        if task_id is None:
            ativa = get_task_ativa()
            await update.message.reply_text(
                f"⚠️ Já existe uma task ativa: {ativa[1]}\nFinalize com /finalizar_task primeiro."
            )
            return
        await update.message.reply_text(
            f"⚔️ Task iniciada!\n\n🦹 Mob: {nome_mob}\n\nUse /participar_task para entrar e envie fotos dos mobs mortos!"
        )
    except Exception as e:
        logger.error(f"❌ Erro em comando_iniciar_task: {e}")
        await update.message.reply_text("❌ Erro ao iniciar task")

async def comando_participar_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        telegram_id = update.effective_user.id
        task = get_task_ativa()
        if not task:
            await update.message.reply_text("❌ Nenhuma task ativa no momento")
            return
        task_id, nome_mob = task
        membro = execute_query(
            "SELECT nome FROM membros WHERE telegram_id=%s",
            (telegram_id,), fetch_one=True
        )
        if not membro:
            await update.message.reply_text(
                "❌ Você não está vinculado. Envie seu print de presença primeiro."
            )
            return
        nome = membro[0]
        registrar_participacao(task_id, telegram_id, nome)
        await update.message.reply_text(
            f"⚔️ {nome} entrou na task!\n\n"
            f"🦹 Mob: {nome_mob}\n\n"
            f"📸 Envie fotos dos mobs mortos para registrar seus kills!"
        )
    except Exception as e:
        logger.error(f"❌ Erro em comando_participar_task: {e}")
        await update.message.reply_text("❌ Erro ao registrar participação")

async def comando_finalizar_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Acesso negado")
            return
        task = get_task_ativa()
        if not task:
            await update.message.reply_text("❌ Nenhuma task ativa")
            return
        task_id, nome_mob = task
        participantes = finalizar_task(task_id)
        if not participantes:
            await update.message.reply_text(f"🏁 Task finalizada!\n⚔️ Mob: {nome_mob}\n\nNenhum participante.")
            return
        ranking = "\n".join(
            f"{i}. {nome} — {kills} kill{'s' if kills != 1 else ''} 🎟 +1"
            for i, (nome, kills) in enumerate(participantes, 1)
        )
        await update.message.reply_text(
            f"🏁 Task finalizada!\n⚔️ Mob: {nome_mob}\n\n"
            f"🏆 Ranking de kills:\n{ranking}"
        )
    except Exception as e:
        logger.error(f"❌ Erro em comando_finalizar_task: {e}")
        await update.message.reply_text("❌ Erro ao finalizar task")

async def detectar_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg or msg.chat.id != GRUPO_ID:
            return
        if not msg.photo:
            return
        task = get_task_ativa()
        if not task:
            return
        task_id, nome_mob = task
        telegram_id = update.effective_user.id
        participante = execute_query(
            "SELECT nome FROM task_participantes WHERE task_id=%s AND telegram_id=%s",
            (task_id, telegram_id), fetch_one=True
        )
        if not participante:
            return
        nome = participante[0]
        registrar_kill(task_id, telegram_id)
        kills = execute_query(
            "SELECT kills FROM task_participantes WHERE task_id=%s AND telegram_id=%s",
            (task_id, telegram_id), fetch_one=True
        )
        total = kills[0] if kills else 1
        await msg.reply_text(
            f"💀 Kill registrado!\n👤 {nome}\n⚔️ {nome_mob}\n🗡 Total: {total} kill{'s' if total != 1 else ''}"
        )
    except Exception as e:
        logger.error(f"❌ Erro em detectar_kill: {e}")

async def comando_task_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        task = get_task_ativa()
        if not task:
            await update.message.reply_text("📭 Nenhuma task ativa no momento.")
            return
        task_id, nome_mob = task
        participantes = execute_query(
            "SELECT nome, kills FROM task_participantes WHERE task_id=%s ORDER BY kills DESC",
            (task_id,), fetch=True
        )
        if not participantes:
            await update.message.reply_text(
                f"⚔️ Task ativa: {nome_mob}\n\nNenhum participante ainda. Use /participar_task!"
            )
            return
        ranking = "\n".join(
            f"{i}. {nome} — {kills} kill{'s' if kills != 1 else ''}"
            for i, (nome, kills) in enumerate(participantes, 1)
        )
        total_kills = sum(k for _, k in participantes)
        await update.message.reply_text(
            f"⚔️ Task ativa: {nome_mob}\n\n"
            f"🏆 Kills:\n{ranking}\n\n"
            f"💀 Total: {total_kills} kills"
        )
    except Exception as e:
        logger.error(f"❌ Erro em comando_task_status: {e}")
        await update.message.reply_text("❌ Erro ao buscar status da task")

async def detectar_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg or msg.chat.id != GRUPO_ID:
            return
        if update.effective_user.id != ADMIN_ID:
            return
        texto = msg.text or msg.caption
        if not texto:
            return
        # Extrai mob da linha com "Diária" (formato do jogo) ou usa primeira linha
        nome_mob = None
        for linha in texto.split("\n"):
            if "Diária" in linha or "Diario" in linha or "Semanal" in linha:
                nome_mob = re.sub(r"[^\w\s]", "", linha).replace("Diaria", "").replace("Diária", "").replace("Semanal", "").strip()[:50]
                break
        if not nome_mob:
            nome_mob = texto.split("\n")[0].strip()[:50]
        if not nome_mob:
            return
        task_id = iniciar_task(nome_mob)
        if task_id:
            await msg.reply_text(
                f"⚔️ Task iniciada!\n\n🦹 Mob: {nome_mob}\n\nUse /participar_task para entrar e envie fotos dos mobs mortos!"
            )
    except Exception as e:
        logger.error(f"❌ Erro em detectar_task: {e}")

# ================= SORTEIO =================
async def realizar_sorteio(context: ContextTypes.DEFAULT_TYPE):
    try:
        dados = execute_query(
            "SELECT nome, semanal FROM tickets WHERE semanal > 0",
            fetch=True
        )
        if not dados:
            await context.bot.send_message(
                chat_id=GRUPO_ID,
                text="🎲 Sorteio semanal: nenhum participante com tickets esta semana."
            )
            return

        nomes = [d[0] for d in dados]
        pesos = [d[1] for d in dados]
        vencedor = random.choices(nomes, weights=pesos, k=1)[0]

        saldo = get_saldo()
        premio = saldo // 2

        if premio > 0:
            execute_query("UPDATE banco_guilda SET saldo=saldo-%s", (premio,))

        execute_query("UPDATE tickets SET semanal=0")

        await context.bot.send_message(
            chat_id=GRUPO_ID,
            text=f"""🎲 SORTEIO SEMANAL — LEGENDS

🏆 Vencedor: {vencedor}
💰 Prêmio: {premio:,} gold (50% do banco)

━━━━━━━━━━━━━━━
🎟 Tickets semanais resetados
🏦 Saldo restante: {saldo - premio:,} gold
━━━━━━━━━━━━━━━"""
        )
    except Exception as e:
        logger.error(f"❌ Erro no sorteio: {e}")

async def comando_sorteio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Acesso negado")
            return
        await realizar_sorteio(context)
    except Exception as e:
        logger.error(f"❌ Erro em comando_sorteio: {e}")
        await update.message.reply_text("❌ Erro ao realizar sorteio")

# ================= LISTA PRESENÇA =================
def gerar_lista_texto():
    membros_query = "SELECT nome FROM membros ORDER BY nome"
    membros = execute_query(membros_query, fetch=True)
    if not membros:
        return "❌ Sem membros registrados"
    
    membros = [m[0] for m in membros]

    presentes_query = "SELECT nome FROM presencas WHERE data=%s"
    presentes_result = execute_query(presentes_query, (hoje(),), fetch=True)
    presentes = {p[0] for p in presentes_result} if presentes_result else set()

    texto = "📜 LISTA DE PRESENÇA — LEGENDS\n\n"

    for nome in membros:
        if nome in presentes:
            texto += f"✅ {nome}\n"
        else:
            texto += f"❌ {nome}\n"

    return texto

def get_mensagem_lista():
    query = "SELECT mensagem_id FROM lista_presenca WHERE data=%s"
    r = execute_query(query, (hoje(),), fetch_one=True)
    return r[0] if r else None

def salvar_mensagem_lista(msg_id):
    if not msg_id:
        return False
    query = """
        INSERT INTO lista_presenca (data,mensagem_id)
        VALUES (%s,%s)
        ON CONFLICT (data)
        DO UPDATE SET mensagem_id=EXCLUDED.mensagem_id
    """
    return execute_query(query, (hoje(), msg_id))

async def atualizar_lista(context):
    try:
        msg_id = get_mensagem_lista()
        texto = gerar_lista_texto()

        if msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=GRUPO_LIDERANCA_ID,
                    message_thread_id=TOPICO_LISTA,
                    message_id=msg_id,
                    text=texto
                )
            except Exception as e:
                logger.warning(f"⚠️ Erro ao editar mensagem: {e}")
        else:
            msg = await context.bot.send_message(
                chat_id=GRUPO_LIDERANCA_ID,
                message_thread_id=TOPICO_LISTA,
                text=texto
            )
            salvar_mensagem_lista(msg.message_id)
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar lista: {e}")

async def comando_lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(gerar_lista_texto())
    except Exception as e:
        logger.error(f"❌ Erro em comando_lista: {e}")
        await update.message.reply_text("❌ Erro ao gerar lista")

# ================= DETECÇÃO =================
async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg: return
        if msg.chat.id != GRUPO_ID: return
        if msg.message_thread_id != TOPICO_PRESENCA: return

        texto = msg.text or msg.caption
        if not texto: return

        nome = extrair_nome(texto)
        if not nome: return

        xp = extrair_xp(texto)
        nivel = extrair_nivel(texto)
        dados = extrair_status(texto)

        telegram_id = update.effective_user.id
        registrar_membro(nome)
        execute_query(
            "UPDATE membros SET telegram_id=%s WHERE nome=%s AND telegram_id IS NULL",
            (telegram_id, nome)
        )
        salvar_presenca(nome)
        salvar_xp(nome, xp, nivel)
        salvar_status(nome, dados)

        await msg.reply_text(f"""🧠 Pilar da Sabedoria reconhece presença

👤 {nome}

━━━━━━━━━━━━━━━
📜 Registro gravado com sucesso
━━━━━━━━━━━━━━━""")

        await atualizar_lista(context)
    except Exception as e:
        logger.error(f"❌ Erro ao detectar: {e}")

# ================= MAIN =================
def main():
    try:
        run_migrations()
        app = ApplicationBuilder().token(TOKEN).build()

        # XP
        app.add_handler(CommandHandler("xp", lambda u, c: u.message.reply_text(get_rank_xp())))
        app.add_handler(CommandHandler("xpdif", lambda u, c: u.message.reply_text(get_rank_xp_dif())))
        app.add_handler(CommandHandler("xp_rank", lambda u, c: u.message.reply_text(get_rank_xp())))
        app.add_handler(CommandHandler("xp_rank_diario", lambda u, c: u.message.reply_text(get_rank_xp_diario())))

        # STATUS
        app.add_handler(CommandHandler("atk", lambda u, c: u.message.reply_text(gerar_rank("atk", "ATAQUE"))))
        app.add_handler(CommandHandler("def", lambda u, c: u.message.reply_text(gerar_rank("def", "DEFESA"))))
        app.add_handler(CommandHandler("hp", lambda u, c: u.message.reply_text(gerar_rank("hp", "HP"))))
        app.add_handler(CommandHandler("crit", lambda u, c: u.message.reply_text(gerar_rank("crit", "CRÍTICO"))))
        app.add_handler(CommandHandler("gold", lambda u, c: u.message.reply_text(gerar_rank("gold", "GOLD"))))
        app.add_handler(CommandHandler("tofu", lambda u, c: u.message.reply_text(gerar_rank("tofus", "TOFUS"))))

        # BANCO
        app.add_handler(CommandHandler("doar", comando_doar))
        app.add_handler(CommandHandler("banco", comando_banco))
        app.add_handler(CommandHandler("ticket", comando_ticket))
        app.add_handler(CommandHandler("ticketS", comando_ticketS))
        app.add_handler(CommandHandler("ticketM", comando_ticketM))
        app.add_handler(CommandHandler("ranksemanal", comando_rank_semanal))
        app.add_handler(CommandHandler("rankmensal", comando_rank_mensal))
        app.add_handler(CommandHandler("rankdoacoes", comando_rank_doacoes))

        app.add_handler(CommandHandler("resetbanco", comando_resetbanco))
        app.add_handler(CommandHandler("resetsemanal", comando_resetsemanal))
        app.add_handler(CommandHandler("resetmensal", comando_resetmensal))

        # LISTA
        app.add_handler(CommandHandler("lista", comando_lista))

        # TASKS
        app.add_handler(CommandHandler("iniciar_task", comando_iniciar_task))
        app.add_handler(CommandHandler("participar_task", comando_participar_task))
        app.add_handler(CommandHandler("finalizar_task", comando_finalizar_task))

        # TICKETS ADMIN
        app.add_handler(CommandHandler("addticket", comando_addticket))
        app.add_handler(CommandHandler("removeticket", comando_removeticket))

        # SORTEIO
        app.add_handler(CommandHandler("sorteio", comando_sorteio))

        # STATUS DA TASK
        app.add_handler(CommandHandler("task_status", comando_task_status))

        # DETECÇÃO DE FORWARDS (tasks) — antes do handler geral
        app.add_handler(MessageHandler(filters.FORWARDED & filters.TEXT & ~filters.COMMAND, detectar_task))

        # KILLS POR FOTO durante task ativa
        app.add_handler(MessageHandler(filters.PHOTO, detectar_kill))

        # DETECÇÃO GERAL (presença)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, detectar))

        # SORTEIO AUTOMÁTICO — todo domingo às 21h (horário de SP)
        app.job_queue.run_daily(
            realizar_sorteio,
            time=dt_time(21, 0, 0, tzinfo=tz),
            days=(6,)
        )

        logger.info("🚀 BOT INICIADO COM SUCESSO")
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
        raise

if __name__ == "__main__":
    main()
