import os
import re
import random
import psycopg2
import pytz
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

GRUPO_ID = -1003792787717

TOPICO_PRESENCA = 16325
TOPICO_LOOTS = 19

TOPICO_PILAR = 29992
TOPICO_GIBBY = 82230

conn = psycopg2.connect(DATABASE_URL)

def inicializar_banco():
    tabelas = [
        """
        CREATE TABLE IF NOT EXISTS membros (
            telegram_id BIGINT PRIMARY KEY,
            nome TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS membro_vinculos (
            telegram_id BIGINT NOT NULL,
            nome TEXT NOT NULL,
            primeira_vista TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            ultima_vista TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (telegram_id, nome)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS presencas (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            nome TEXT NOT NULL,
            data DATE NOT NULL,
            UNIQUE (telegram_id, data)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS xp_logs (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            nome TEXT NOT NULL,
            xp BIGINT,
            nivel INTEGER,
            data_hora TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS xp_progresso (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            nome TEXT NOT NULL,
            xp BIGINT NOT NULL,
            nivel INTEGER,
            xp_restante BIGINT NOT NULL,
            data_hora TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS status (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            nome TEXT NOT NULL,
            atk NUMERIC,
            def NUMERIC,
            crit NUMERIC,
            hp BIGINT,
            gold BIGINT,
            tofus BIGINT,
            data_hora TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cacadas (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            nome TEXT NOT NULL,
            xp BIGINT DEFAULT 0,
            gold BIGINT DEFAULT 0,
            lendarios INTEGER DEFAULT 0,
            pvps INTEGER DEFAULT 0,
            data_hora TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS gibby_logs (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            nome TEXT NOT NULL,
            item TEXT NOT NULL,
            nivel_origem INTEGER,
            nivel_destino INTEGER,
            resultado TEXT,
            itens_base_consumidos INTEGER DEFAULT 0,
            data_hora TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS itens_legends (
            id BIGSERIAL PRIMARY KEY,
            nome TEXT UNIQUE NOT NULL,
            classe TEXT NOT NULL,
            categoria TEXT NOT NULL,
            raridade TEXT NOT NULL,
            duas_maos BOOLEAN DEFAULT FALSE,
            nivel INTEGER,
            atk_min NUMERIC,
            atk_max NUMERIC,
            def_min NUMERIC,
            def_max NUMERIC,
            hp_min NUMERIC,
            hp_max NUMERIC,
            crit_min NUMERIC,
            crit_max NUMERIC,
            descricao TEXT,
            drop_1 TEXT,
            drop_2 TEXT,
            drop_3 TEXT,
            mapa TEXT,
            obtencao TEXT,
            chance_drop TEXT,
            passiva TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS catalogo_mapas (
            id BIGSERIAL PRIMARY KEY,
            ordem INTEGER NOT NULL,
            nome TEXT UNIQUE NOT NULL,
            nivel_minimo INTEGER,
            dificuldade INTEGER,
            tempo_masmorra INTEGER,
            xp_masmorra_4 BIGINT,
            xp_masmorra_5 BIGINT,
            descricao TEXT,
            fonte TEXT NOT NULL,
            confirmado BOOLEAN DEFAULT FALSE,
            atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS catalogo_monstros (
            id BIGSERIAL PRIMARY KEY,
            ordem INTEGER NOT NULL,
            nome TEXT NOT NULL,
            mapa_id BIGINT REFERENCES catalogo_mapas(id),
            tipo TEXT DEFAULT 'Monstro',
            raridade TEXT,
            hp BIGINT,
            atk NUMERIC,
            defesa NUMERIC,
            xp BIGINT,
            gold BIGINT,
            drops TEXT,
            fonte TEXT NOT NULL,
            confirmado BOOLEAN DEFAULT FALSE,
            atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (nome, mapa_id, tipo)
        )
        """
    ]

    cur = conn.cursor()
    try:
        for ddl in tabelas:
            cur.execute(ddl)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_xp_progresso_telegram_data
            ON xp_progresso (telegram_id, data_hora DESC)
        """)
        cur.execute("""
            INSERT INTO membro_vinculos (telegram_id, nome)
            SELECT telegram_id, nome FROM membros
            ON CONFLICT (telegram_id, nome) DO NOTHING
        """)

        mapas_iniciais = [
            (1, "PlanÃ­cie", 1, 1, 2, 1262, 1010, "Mapa inicial do jogo.", "Wikia oficial + Railway Archivus", False),
            (2, "Floresta Sombria", 8, None, 3, 2000, 1600, None, "Wikia oficial + Railway Archivus", False),
            (3, "Floresta Profunda", None, None, None, None, None, None, "Biblioteca restaurada + site oficial", False),
            (4, "PÃ¢ntano", 15, None, 2, 2937, 2350, None, "Wikia oficial + Railway Archivus", False),
            (5, "CemitÃ©rio Antigo", 22, None, 5, 8537, 6930, "Chamado de CemitÃ©rio no Archivus.", "Wikia oficial + Railway Archivus", False),
            (6, "Deserto Escaldante", 32, None, 3, 9737, 7890, None, "Wikia oficial + Railway Archivus", False),
            (7, "OÃ¡sis Perdido", 35, 4, 5, None, None, "Chamado de OÃ¡sis no Archivus.", "HistÃ³rico do Teletofus + Railway Archivus", True),
            (8, "Montanhas GÃ©lidas", 42, 4, None, None, None, None, "Wikia oficial + histÃ³rico do Teletofus", True),
            (9, "Fortaleza dos Orcs", 44, None, None, None, None, "Mapa de guerra entre as facÃ§Ãµes Goblin e Orc.", "Site oficial + histÃ³rico do Teletofus", True),
            (10, "Abismo", 52, None, None, None, None, None, "Wikia oficial", False),
        ]
        cur.executemany("""
            INSERT INTO catalogo_mapas
                (ordem, nome, nivel_minimo, dificuldade, tempo_masmorra,
                 xp_masmorra_4, xp_masmorra_5, descricao, fonte, confirmado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (nome) DO NOTHING
        """, mapas_iniciais)

        monstros_iniciais = [
            # PlanÃ­cie â€” caÃ§ada
            (1, "Rato", "PlanÃ­cie", "CaÃ§ada", "Comum", 30, 3, 0, 8, 5, None, "Wikia oficial + Railway Archivus (Rato Gigante)", False),
            (2, "Lobo", "PlanÃ­cie", "CaÃ§ada", "Comum", 40, 5, 1, 12, 8, None, "Wikia oficial + Railway Archivus", False),
            (3, "Aranha", "PlanÃ­cie", "CaÃ§ada", "Comum", 50, 6, 2, 15, 10, None, "Wikia oficial + Railway Archivus", False),
            (4, "Bandido", "PlanÃ­cie", "CaÃ§ada", "Comum", 60, 8, 2, 20, 15, None, "Wikia oficial + Railway Archivus", False),
            (5, "Troll", "PlanÃ­cie", "CaÃ§ada", "Incomum", 80, 10, 3, 30, 20, None, "Wikia oficial + Railway Archivus (Troll Jovem)", False),
            (6, "Minotauro Batedor", "PlanÃ­cie", "CaÃ§ada", "Raro", 100, 12, 4, 50, 35, None, "Wikia oficial + Railway Archivus", False),
            (7, "Lobo Alfa", "PlanÃ­cie", "Masmorra", "Elite", 140, 16, 6, 400, 60, None, "Wikia oficial", False),
            (8, "Aranha Rochedo", "PlanÃ­cie", "Masmorra", "Elite", 160, 18, 7, 500, 70, None, "Wikia oficial", False),
            (9, "Batedor Goblin", "PlanÃ­cie", "Masmorra", "Elite", 170, 20, 7, 600, 80, None, "Wikia oficial", False),
            (10, "Senhor dos Rochedos", "PlanÃ­cie", "Masmorra", "Boss", 350, 30, 15, 900, 150, None, "Wikia oficial", False),

            # Floresta Sombria
            (11, "Goblin", "Floresta Sombria", "CaÃ§ada", "Comum", 90, 12, 3, 35, 25, None, "Wikia oficial + Railway Archivus", False),
            (12, "Vespa", "Floresta Sombria", "CaÃ§ada", "Comum", 100, 15, 3, 40, 28, None, "Wikia oficial + Railway Archivus (Vespa Gigante)", False),
            (13, "Javali", "Floresta Sombria", "CaÃ§ada", "Comum", 120, 18, 4, 45, 30, None, "Wikia oficial + Railway Archivus", False),
            (14, "Elfo Ladino", "Floresta Sombria", "CaÃ§ada", "Incomum", 140, 22, 5, 60, 45, None, "Wikia oficial + Railway Archivus (Elfo Saqueador)", False),
            (15, "Urso", "Floresta Sombria", "CaÃ§ada", "Incomum", 170, 24, 6, 70, 50, None, "Wikia oficial + Railway Archivus", False),
            (16, "Ent", "Floresta Sombria", "CaÃ§ada", "Boss", 260, 30, 10, 130, 90, None, "Wikia oficial", False),
            (17, "Ent Jovem", "Floresta Sombria", "Masmorra", "Elite", 300, 35, 12, 600, 85, None, "Wikia oficial", False),
            (18, "Aranha da Mata", "Floresta Sombria", "Masmorra", "Elite", 310, 38, 10, 800, 90, None, "Wikia oficial", False),
            (19, "Batedor Elfo", "Floresta Sombria", "Masmorra", "Elite", 330, 40, 11, 1000, 100, None, "Wikia oficial", False),
            (20, "GuardiÃ£o do Bosque", "Floresta Sombria", "Masmorra", "Boss", 500, 55, 20, 1400, 200, None, "Wikia oficial", False),

            # PÃ¢ntano
            (21, "Slime", "PÃ¢ntano", "CaÃ§ada", "Comum", 160, 22, 5, 70, 60, None, "Wikia oficial + Railway Archivus", False),
            (22, "Sanguessuga", "PÃ¢ntano", "CaÃ§ada", "Comum", 170, 24, 5, 75, 62, None, "Wikia oficial + Railway Archivus", False),
            (23, "Orc do PÃ¢ntano", "PÃ¢ntano", "CaÃ§ada", "Incomum", 190, 28, 6, 90, 70, None, "Wikia oficial + Railway Archivus", False),
            (24, "Bruxa", "PÃ¢ntano", "CaÃ§ada", "Incomum", 210, 32, 8, 110, 80, None, "Wikia oficial + Railway Archivus", False),
            (25, "CarniÃ§al", "PÃ¢ntano", "CaÃ§ada", "Incomum", 230, 30, 7, 120, 85, None, "Wikia oficial + Railway Archivus", False),
            (26, "Filhote de Hidra", "PÃ¢ntano", "CaÃ§ada", "Boss", 320, 38, 10, 200, 150, None, "Wikia oficial", False),
            (27, "Orc do PÃ¢ntano", "PÃ¢ntano", "Masmorra", "Elite", 350, 45, 14, 900, 110, None, "Wikia oficial", False),
            (28, "Bruxa do Brejo", "PÃ¢ntano", "Masmorra", "Elite", 340, 50, 12, 1100, 120, None, "Wikia oficial", False),
            (29, "Sanguessuga Gigante", "PÃ¢ntano", "Masmorra", "Elite", 380, 48, 15, 1300, 135, None, "Wikia oficial", False),
            (30, "Hidra Menor", "PÃ¢ntano", "Masmorra", "Boss", 600, 70, 25, 2200, 250, None, "Wikia oficial", False),

            # CemitÃ©rio Antigo
            (31, "Esqueleto", "CemitÃ©rio Antigo", "CaÃ§ada", "Comum", 200, 28, 7, 110, 90, None, "Wikia oficial + Railway Archivus", False),
            (32, "Zumbi", "CemitÃ©rio Antigo", "CaÃ§ada", "Comum", 220, 30, 7, 120, 95, None, "Wikia oficial + Railway Archivus", False),
            (33, "MÃºmia", "CemitÃ©rio Antigo", "CaÃ§ada", "Incomum", 240, 32, 8, 135, 100, None, "Wikia oficial + Railway Archivus", False),
            (34, "Aprendiz de Necro", "CemitÃ©rio Antigo", "CaÃ§ada", "Incomum", 230, 36, 9, 150, 120, None, "Wikia oficial + Railway Archivus", False),
            (35, "Espectro", "CemitÃ©rio Antigo", "CaÃ§ada", "Raro", 260, 40, 12, 180, 150, None, "Wikia oficial + Railway Archivus", False),
            (36, "Lich", "CemitÃ©rio Antigo", "CaÃ§ada", "Boss", 350, 50, 15, 260, 220, None, "Wikia oficial", False),
            (37, "Cavaleiro Sombrio", "CemitÃ©rio Antigo", "Masmorra", "Elite", 600, 80, 30, 2000, 300, None, "Wikia oficial", False),
            (38, "Cultista Abissal", "CemitÃ©rio Antigo", "Masmorra", "Elite", 550, 90, 25, 2600, 310, None, "Wikia oficial", False),
            (39, "Golem de Osso", "CemitÃ©rio Antigo", "Masmorra", "Elite", 700, 85, 35, 3200, 330, None, "Wikia oficial", False),
            (40, "Arquilorde dos Ossos", "CemitÃ©rio Antigo", "Masmorra", "Raid Boss", 1200, 120, 50, 5500, 600, None, "Wikia oficial", False),

            # Deserto Escaldante
            (41, "EscorpiÃ£o", "Deserto Escaldante", "CaÃ§ada", "Comum", 230, 35, 10, 160, 130, None, "Wikia oficial + Railway Archivus", False),
            (42, "Verme da Areia", "Deserto Escaldante", "CaÃ§ada", "Incomum", 260, 38, 10, 180, 140, None, "Wikia oficial + Railway Archivus (Verme de Areia)", False),
            (43, "NÃ´made", "Deserto Escaldante", "CaÃ§ada", "Incomum", 240, 42, 12, 190, 150, None, "Wikia oficial + Railway Archivus", False),
            (44, "Escaravelho", "Deserto Escaldante", "CaÃ§ada", "Raro", 280, 44, 13, 210, 170, None, "Wikia oficial + Railway Archivus", False),
            (45, "Diabrete de Fogo", "Deserto Escaldante", "CaÃ§ada", "Raro", 250, 48, 12, 230, 180, None, "Wikia oficial + Railway Archivus", False),
            (46, "GuardiÃ£o Ancestral", "Deserto Escaldante", "CaÃ§ada", "Boss", 380, 55, 18, 320, 260, None, "Wikia oficial", False),
            (47, "EscorpiÃ£o TitÃ£", "Deserto Escaldante", "Masmorra", "Elite", 650, 90, 35, 2800, 320, None, "Wikia oficial", False),
            (48, "Verme Gigante", "Deserto Escaldante", "Masmorra", "Elite", 700, 95, 30, 3500, 340, None, "Wikia oficial", False),
            (49, "Elemental de Areia", "Deserto Escaldante", "Masmorra", "Elite", 680, 100, 32, 4200, 360, None, "Wikia oficial", False),
            (50, "FaraÃ³ Maldito", "Deserto Escaldante", "Masmorra", "Raid Boss", 1300, 130, 55, 7500, 650, None, "Wikia oficial", False),

            # OÃ¡sis Perdido â€” registros do Railway ainda sem ATK/DEF/Gold
            (51, "Karkto Feroz", "OÃ¡sis Perdido", "CaÃ§ada", None, 420, None, None, 245, None, None, "Railway Archivus", False),
            (52, "Cobra do Deserto", "OÃ¡sis Perdido", "CaÃ§ada", None, 360, None, None, 215, None, None, "Railway Archivus", False),
            (53, "Abutre de Fogo", "OÃ¡sis Perdido", "CaÃ§ada", None, 400, None, None, 230, None, None, "Railway Archivus", False),
            (54, "Lince Saqueadora", "OÃ¡sis Perdido", "CaÃ§ada", None, 440, None, None, 260, None, None, "Railway Archivus", False),
            (55, "Lagarto da Areia", "OÃ¡sis Perdido", "CaÃ§ada", None, 380, None, None, 210, None, None, "Railway Archivus", False),
            (56, "GuardiÃ£o Raiz Profanado", "OÃ¡sis Perdido", "Masmorra", "Boss", 1211, None, None, None, None, None, "HistÃ³rico atual do Teletofus", True),

            # Montanhas GÃ©lidas
            (57, "Golem de Gelo", "Montanhas GÃ©lidas", "CaÃ§ada", "Incomum", 320, 50, 16, 260, 200, None, "Wikia oficial", False),
            (58, "Harpia", "Montanhas GÃ©lidas", "CaÃ§ada", "Incomum", 300, 48, 14, 250, 190, None, "Wikia oficial", False),
            (59, "Orc do Gelo", "Montanhas GÃ©lidas", "CaÃ§ada", "Incomum", 310, 52, 15, 260, 200, None, "Wikia oficial", False),
            (60, "Yeti", "Montanhas GÃ©lidas", "CaÃ§ada", "Raro", 340, 54, 17, 280, 220, None, "Wikia oficial", False),
            (61, "Wyvern", "Montanhas GÃ©lidas", "CaÃ§ada", "Raro", 360, 58, 18, 320, 240, None, "Wikia oficial", False),
            (62, "DragÃ£o Jovem", "Montanhas GÃ©lidas", "CaÃ§ada", "Boss", 480, 70, 22, 420, 320, None, "Wikia oficial", False),

            # Fortaleza dos Orcs â€” patch oficial; estatÃ­sticas ainda a confirmar
            (63, "Orc", "Fortaleza dos Orcs", "CaÃ§ada", None, None, None, None, None, None, "Pele de Goblin", "NotÃ­cia oficial do Teletofus", False),
            (64, "Goblin", "Fortaleza dos Orcs", "CaÃ§ada", None, None, None, None, None, None, "Pele de Orc", "NotÃ­cia oficial do Teletofus", False),

            # Abismo
            (65, "DemÃ´nio Menor", "Abismo", "CaÃ§ada", "Raro", 380, 68, 20, 380, 280, None, "Wikia oficial", False),
            (66, "Cavaleiro Sombrio", "Abismo", "CaÃ§ada", "Raro", 420, 72, 22, 420, 300, None, "Wikia oficial", False),
            (67, "Cultista", "Abismo", "CaÃ§ada", "Raro", 390, 70, 21, 410, 290, None, "Wikia oficial", False),
            (68, "CÃ£o do Inferno", "Abismo", "CaÃ§ada", "Raro", 400, 75, 21, 440, 310, None, "Wikia oficial", False),
            (69, "Cria do Vazio", "Abismo", "CaÃ§ada", "Raro", 430, 78, 23, 460, 330, None, "Wikia oficial", False),
            (70, "Lorde do Abismo", "Abismo", "CaÃ§ada", "Boss", 650, 95, 28, 620, 480, None, "Wikia oficial", False),
        ]
        cur.executemany("""
            INSERT INTO catalogo_monstros
                (ordem, nome, mapa_id, tipo, raridade, hp, atk, defesa,
                 xp, gold, drops, fonte, confirmado)
            SELECT %s, %s, id, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            FROM catalogo_mapas
            WHERE nome = %s
            ON CONFLICT (nome, mapa_id, tipo) DO NOTHING
        """, [
            (ordem, nome, tipo, raridade, hp, atk, defesa, xp, gold,
             drops, fonte, confirmado, mapa)
            for ordem, nome, mapa, tipo, raridade, hp, atk, defesa,
                xp, gold, drops, fonte, confirmado in monstros_iniciais
        ])
        conn.commit()
        print("0 - Estrutura do banco verificada")
    finally:
        cur.close()

inicializar_banco()
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
    nome = nome.replace("[LG]", "").strip()
    nome = re.sub(r"^[^\wÃ€-Ã¿]+", "", nome).strip()
    return nome.upper() or None

def extrair_nome(texto):
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]

    # No formato atual, o nick fica imediatamente antes de "Classe:".
    for i, linha in enumerate(linhas):
        if re.match(r"^Classe\s*:", linha, re.IGNORECASE) and i > 0:
            return limpar_nome(linhas[i - 1])

    # Compatibilidade com perfis sem a linha de classe.
    ignorar = (
        "classe:", "tÃ­tulos:", "titulos:", "lv ", "xp:", "faltam:",
        "arena", "ranking:", "histÃ³rico:", "historico:", "energia:",
        "gold:", "tofus:", "mapa:", "renomear:", "mudar classe:"
    )
    for linha in linhas:
        candidato = re.sub(r"^[^\wÃ€-Ã¿]+", "", linha).strip()
        if candidato and not candidato.casefold().startswith(ignorar):
            if not re.search(r"\b(?:ATK|DEF|CRIT|HP)\b", candidato, re.IGNORECASE):
                return limpar_nome(candidato)

    return None

def extrair_xp(texto):
    match = re.search(r"\bXP\s*:\s*([\d.,]+)", texto, re.IGNORECASE)
    if not match:
        return None
    return int(re.sub(r"\D", "", match.group(1)))

def extrair_xp_restante(texto):
    match = re.search(r"\bFaltam\s*:\s*([\d.,]+)", texto, re.IGNORECASE)
    if not match:
        return None
    return int(re.sub(r"\D", "", match.group(1)))

def extrair_nivel(texto):
    match = re.search(r"\bLv\s*(\d+)", texto, re.IGNORECASE)
    return int(matc…10889 tokens truncated…nhas))

    except Exception as erro:
        conn.rollback()
        print(f"Erro bestiÃ¡rio: {erro}")
        await update.message.reply_text(
            "NÃ£o consegui consultar o bestiÃ¡rio agora. Tente novamente em instantes."
        )
    finally:
        cur.close()


async def cmd_start(update, context):

    if context.args and context.args[0] == "item":

        await update.message.reply_text(
            "ðŸ“š BIBLIOTECA LEGENDS\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_inicio_biblioteca()
        )

        return

    await update.message.reply_text(
        "OlÃ¡! Use os comandos disponÃ­veis."
    )

async def cmd_item(update, context):

    if not await validar_acesso(
        update,
        context,
        "/item"
    ):
        return

    if update.effective_chat.type != "private":

            bot_username = (
                await context.bot.get_me()
            ).username

            teclado = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "ðŸ“š Abrir Biblioteca",
                        url=f"https://t.me/{bot_username}?start=item"
                    )
                ]
            ])

            await update.message.reply_text(
                "ðŸ“š Para evitar spam nos tÃ³picos da guilda, "
                "a Biblioteca Legends funciona apenas no privado.\n\n"
                "Clique no botÃ£o abaixo para abrir a biblioteca.",
                reply_markup=teclado
            )

            return

    await update.message.reply_text(
        "ðŸ“š BIBLIOTECA LEGENDS\n\n"
        "Escolha uma categoria:",
        reply_markup=teclado_inicio_biblioteca()
    )

def teclado_inicio_biblioteca():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "âš” Guerreiro",
                callback_data="bib_guerreiro"
            )
        ],

        [
            InlineKeyboardButton(
                "ðŸ¹ Arqueiro",
                callback_data="bib_arqueiro"
            )
        ],

        [
            InlineKeyboardButton(
                "ðŸ”® Mago",
                callback_data="bib_mago"
            )
        ],

        [
            InlineKeyboardButton(
                "ðŸ§ª ConsumÃ­veis",
                callback_data="bib_consumiveis"
            )
        ],

        [
            InlineKeyboardButton(
                "âœ¨ Especiais",
                callback_data="bib_especiais"
            )
        ]

    ])

def teclado_categorias(classe):

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "âš” Armas",
                callback_data=f"cat_{classe}_arma"
            )
        ],

        [
            InlineKeyboardButton(
                "ðŸ›¡ Escudos",
                callback_data=f"cat_{classe}_escudo"
            )
        ],

        [
            InlineKeyboardButton(
                "ðŸ¥‹ Peitorais",
                callback_data=f"cat_{classe}_peitoral"
            )
        ],

        [
            InlineKeyboardButton(
                "ðŸ‘¢ Botas",
                callback_data=f"cat_{classe}_bota"
            )
        ],

        [
            InlineKeyboardButton(
                "ðŸ’ AnÃ©is",
                callback_data=f"cat_{classe}_anel"
            )
        ],

        [
            InlineKeyboardButton(
                "ðŸ“¿ Colares",
                callback_data=f"cat_{classe}_colar"
            )
        ],

        [
            InlineKeyboardButton(
                "â¬… Voltar",
                callback_data="voltar_inicio"
            )
        ]

    ])

def emoji_raridade(raridade):

    mapa = {

        "evento": "âšª",
        "comum": "ðŸŸ¢",
        "incomum": "ðŸ”µ",
        "raro": "ðŸŸ£",
        "lendario": "ðŸŸ ",
        "especial": "ðŸŸ¡"

    }

    return mapa.get(
        raridade,
        "â“"
    )

def teclado_itens(
    classe,
    categoria
):

    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id,
            nome,
            raridade,
            nivel,
            duas_maos
        FROM itens_legends
        WHERE categoria=%s
        AND (
            classe=%s
            OR classe='todas'
        )
        ORDER BY nivel, nome
        """,
        (
            categoria,
            classe
        )
    )

    rows = cur.fetchall()

    teclado = []

    for (
        item_id,
        nome,
        raridade,
        nivel,
        duas_maos
    ) in rows:

        emoji = emoji_raridade(
            raridade
        )

        sufixo = ""

        if duas_maos:
            sufixo = " (2M)"

        if nivel and nivel > 0:

            texto_botao = (
                f"{emoji} Lv{nivel} "
                f"{nome}{sufixo}"
            )

        else:

            texto_botao = (
                f"{emoji} "
                f"{nome}{sufixo}"
            )

        teclado.append(
            [
                InlineKeyboardButton(
                    texto_botao,
                    callback_data=
                    f"item_{item_id}_{classe}_{categoria}"
                )
            ]
        )

    teclado.append(
        [
            InlineKeyboardButton(
                "â¬… Voltar",
                callback_data=f"voltar_{classe}"
            )
        ]
    )

    return InlineKeyboardMarkup(
        teclado
    )

async def mostrar_item(
    query,
    item_id,
    classe,
    categoria
):

    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM itens_legends
        WHERE id=%s
    """,(item_id,))

    row = cur.fetchone()

    if not row:

        await query.answer(
            "Item nÃ£o encontrado."
        )

        return

    colunas = [
        desc[0]
        for desc in cur.description
    ]

    item = dict(
        zip(
            colunas,
            row
        )
    )

    emoji = emoji_raridade(
        item["raridade"]
    )

    texto = (
        f"{emoji} {item['nome'].upper()}\n\n"
    )

    classe_map = {

        "guerreiro": "ðŸ›¡ Guerreiro",
        "arqueiro": "ðŸ¹ Arqueiro",
        "mago": "ðŸ”® Mago",
        "todas": "ðŸŒŽ Todas as Classes"

    }

    texto += (
        f"{classe_map.get(item['classe'],'')}\n"
    )

    if item.get("nivel"):

        texto += (
            f"â­ Lv {item['nivel']}\n"
        )

    if item.get("duas_maos"):

        texto += (
            "âš” Arma de Duas MÃ£os\n"
        )

    stats = ""

    if item.get("atk_min"):

        stats += (
            f"âš” {item['atk_min']}~"
            f"{item['atk_max']}\n"
        )

    if item.get("def_min"):

        stats += (
            f"ðŸ›¡ {item['def_min']}~"
            f"{item['def_max']}\n"
        )

    if item.get("hp_min"):

        stats += (
            f"â¤ï¸ {item['hp_min']}~"
            f"{item['hp_max']}\n"
        )

    if item.get("crit_min"):

        stats += (
            f"ðŸŽ¯ {float(item['crit_min']):g}~"
            f"{float(item['crit_max']):g}%\n"
        )

    if stats:

        texto += "\n" + stats

    if item.get("descricao"):

        texto += (
            f"\nðŸ“– {item['descricao']}\n"
        )

    drops = []

    for campo in [
        "drop_1",
        "drop_2",
        "drop_3"
    ]:

        valor = item.get(campo)

        if valor:

            drops.append(valor)

    if item.get("mapa"):

        texto += (
            f"\nðŸ—ºï¸ {item['mapa']}\n"
        )

    if drops:

        texto += "\nðŸ“ ObtenÃ§Ã£o\n"

        for drop in drops:

            texto += (
                f"â€¢ {drop}\n"
            )

    if item.get("obtencao"):

        texto += (
            f"\nðŸ“ {item['obtencao']}\n"
        )

    if item.get("chance_drop"):

        texto += (
            f"\nðŸŽ Chance: "
            f"{item['chance_drop']}"
        )

    if item.get("passiva"):

        texto += (
            f"\n\nâœ¨ Passiva\n"
            f"{item['passiva']}"
        )

    teclado = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "â¬… Voltar",
                callback_data=
                f"lista_{classe}_{categoria}"
            )
        ]

    ])

    await query.edit_message_text(
        texto,
        reply_markup=teclado
    )

async def callback_biblioteca(update, context):

    query = update.callback_query

    await query.answer()

    dados = query.data

    if dados.startswith(
        "item_"
    ):

        partes = dados.split("_")

        item_id = int(
            partes[1]
        )

        classe = partes[2]

        categoria = partes[3]

        await mostrar_item(
            query,
            item_id,
            classe,
            categoria
        )

        return
    if dados.startswith(
        "lista_"
    ):

        partes = dados.split("_")

        classe = partes[1]

        categoria = partes[2]

        titulo = (
            f"{categoria.upper()} - "
            f"{classe.upper()}"
        )

        await query.edit_message_text(
            titulo,
            reply_markup=teclado_itens(
                classe,
                categoria
            )
        )

        return

    # VOLTAR

    if dados == "voltar_inicio":

        await query.edit_message_text(
            "ðŸ“š BIBLIOTECA LEGENDS\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_inicio_biblioteca()
        )

        return

    if dados == "voltar_todas":

        await query.edit_message_text(
            "ðŸ“š BIBLIOTECA LEGENDS\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_inicio_biblioteca()
        )

        return

    # GUERREIRO

    if dados == "bib_guerreiro":

        await query.edit_message_text(
            "âš” BIBLIOTECA GUERREIRO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "guerreiro"
            )
        )

        return

    if dados == "cat_guerreiro_arma":

        await query.edit_message_text(
            "âš” ARMAS - GUERREIRO",
            reply_markup=teclado_itens(
                "guerreiro",
                "arma"
            )
        )

        return

    if dados == "cat_guerreiro_escudo":

        await query.edit_message_text(
            "ðŸ›¡ ESCUDOS - GUERREIRO",
            reply_markup=teclado_itens(
                "guerreiro",
                "escudo"
            )
        )

        return


    if dados == "cat_guerreiro_peitoral":

        await query.edit_message_text(
            "ðŸ¥‹ PEITORAIS - GUERREIRO",
            reply_markup=teclado_itens(
                "guerreiro",
                "peitoral"
            )
        )

        return


    if dados == "cat_guerreiro_bota":

        await query.edit_message_text(
            "ðŸ‘¢ BOTAS - GUERREIRO",
           reply_markup=teclado_itens(
                "guerreiro",
                "bota"
            )
        )

        return


    if dados == "cat_guerreiro_anel":

        await query.edit_message_text(
            "ðŸ’ ANÃ‰IS - GUERREIRO",
            reply_markup=teclado_itens(
                "guerreiro",
                "anel"
            )
        )

        return


    if dados == "cat_guerreiro_colar":

        await query.edit_message_text(
            "ðŸ“¿ COLARES - GUERREIRO",
            reply_markup=teclado_itens(
                "guerreiro",
                "colar"
            )
        )

        return

    if dados == "voltar_guerreiro":

        await query.edit_message_text(
            "âš” BIBLIOTECA GUERREIRO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "guerreiro"
            )
        )

        return

    # ARQUEIRO

    if dados == "bib_arqueiro":

        await query.edit_message_text(
            "ðŸ¹ BIBLIOTECA ARQUEIRO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "arqueiro"
            )
        )

        return

    if dados == "cat_arqueiro_arma":

        await query.edit_message_text(
            "âš” ARMAS - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "arma"
            )
        )

        return

    if dados == "cat_arqueiro_escudo":

        await query.edit_message_text(
            "ðŸ›¡ ESCUDOS - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "escudo"
            )
        )

        return

    if dados == "cat_arqueiro_peitoral":

        await query.edit_message_text(
            "ðŸ¥‹ PEITORAIS - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "peitoral"
            )
        )

        return

    if dados == "cat_arqueiro_bota":

        await query.edit_message_text(
            "ðŸ‘¢ BOTAS - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "bota"
            )
        )

        return

    if dados == "cat_arqueiro_anel":

        await query.edit_message_text(
            "ðŸ’ ANÃ‰IS - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "anel"
            )
        )

        return

    if dados == "cat_arqueiro_colar":

        await query.edit_message_text(
            "ðŸ“¿ COLARES - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "colar"
            )
        )

        return

    if dados == "voltar_arqueiro":

        await query.edit_message_text(
            "ðŸ¹ BIBLIOTECA ARQUEIRO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "arqueiro"
            )
        )

        return

    # MAGO

    if dados == "bib_mago":

        await query.edit_message_text(
            "ðŸ”® BIBLIOTECA MAGO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "mago"
            )
        )

        return

    if dados == "voltar_mago":

        await query.edit_message_text(
            "ðŸ”® BIBLIOTECA MAGO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "mago"
            )
        )

        return

    if dados == "cat_mago_arma":

        await query.edit_message_text(
            "âš” ARMAS - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "arma"
            )
        )

        return

    if dados == "cat_mago_escudo":

        await query.edit_message_text(
            "ðŸ›¡ ESCUDOS - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "escudo"
            )
        )

        return

    if dados == "cat_mago_peitoral":

        await query.edit_message_text(
            "ðŸ¥‹ PEITORAIS - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "peitoral"
            )
        )

        return


    if dados == "cat_mago_bota":

        await query.edit_message_text(
            "ðŸ‘¢ BOTAS - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "bota"
            )
        )

        return

    if dados == "cat_mago_anel":

        await query.edit_message_text(
            "ðŸ’ ANÃ‰IS - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "anel"
            )
        )

        return

    if dados == "cat_mago_colar":

        await query.edit_message_text(
            "ðŸ“¿ COLARES - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "colar"
            )
        )

        return

    # CONSUMÃVEIS

    if dados == "bib_consumiveis":

        await query.edit_message_text(
            "ðŸ§ª CONSUMÃVEIS",
            reply_markup=teclado_itens(
                "todas",
                "consumivel"
            )
        )

        return

    # ESPECIAIS

    if dados == "bib_especiais":

        await query.edit_message_text(
            "âœ¨ ESPECIAIS",
            reply_markup=teclado_itens(
                "todas",
                "especial"
            )
        )

        return

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
            "CRÃTICO"
        )
    )

def main():
    print("1 - Entrou no main")

    app = ApplicationBuilder().token(TOKEN).build()

    print("2 - Application criada")

    # COMANDOS

    app.add_handler(
        CommandHandler("lista", cmd_lista)
    )

    app.add_handler(
        CommandHandler("xp", cmd_xp)
    )

    app.add_handler(
        CommandHandler("xpdif", cmd_xpdif)
    )

    app.add_handler(
        CommandHandler("up", cmd_up)
    )

    app.add_handler(
        CommandHandler("cacada", cmd_cacada)
    )

    app.add_handler(
        CommandHandler("pvp", cmd_pvp)
    )

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
            "start",
            cmd_start
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
            "mapa",
            cmd_mapa
        )
    )

    app.add_handler(
        CommandHandler(
            "monstro",
            cmd_monstro
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

    # CALLBACKS DA BIBLIOTECA

    app.add_handler(
        CallbackQueryHandler(
            callback_biblioteca
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

