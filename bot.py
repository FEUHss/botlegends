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
            (1, "Planície", 1, 1, 2, 1262, 1010, "Mapa inicial do jogo.", "Wikia oficial + Railway Archivus", False),
            (2, "Floresta Sombria", 8, None, 3, 2000, 1600, None, "Wikia oficial + Railway Archivus", False),
            (3, "Floresta Profunda", None, None, None, None, None, None, "Biblioteca restaurada + site oficial", False),
            (4, "Pântano", 15, None, 2, 2937, 2350, None, "Wikia oficial + Railway Archivus", False),
            (5, "Cemitério Antigo", 22, None, 5, 8537, 6930, "Chamado de Cemitério no Archivus.", "Wikia oficial + Railway Archivus", False),
            (6, "Deserto Escaldante", 32, None, 3, 9737, 7890, None, "Wikia oficial + Railway Archivus", False),
            (7, "Oásis Perdido", 35, 4, 5, None, None, "Chamado de Oásis no Archivus.", "Histórico do Teletofus + Railway Archivus", True),
            (8, "Montanhas Gélidas", 42, 4, None, None, None, None, "Wikia oficial + histórico do Teletofus", True),
            (9, "Fortaleza dos Orcs", 44, None, None, None, None, "Mapa de guerra entre as facções Goblin e Orc.", "Site oficial + histórico do Teletofus", True),
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
            # Planície — caçada
            (1, "Rato", "Planície", "Caçada", "Comum", 30, 3, 0, 8, 5, None, "Wikia oficial + Railway Archivus (Rato Gigante)", False),
            (2, "Lobo", "Planície", "Caçada", "Comum", 40, 5, 1, 12, 8, None, "Wikia oficial + Railway Archivus", False),
            (3, "Aranha", "Planície", "Caçada", "Comum", 50, 6, 2, 15, 10, None, "Wikia oficial + Railway Archivus", False),
            (4, "Bandido", "Planície", "Caçada", "Comum", 60, 8, 2, 20, 15, None, "Wikia oficial + Railway Archivus", False),
            (5, "Troll", "Planície", "Caçada", "Incomum", 80, 10, 3, 30, 20, None, "Wikia oficial + Railway Archivus (Troll Jovem)", False),
            (6, "Minotauro Batedor", "Planície", "Caçada", "Raro", 100, 12, 4, 50, 35, None, "Wikia oficial + Railway Archivus", False),
            (7, "Lobo Alfa", "Planície", "Masmorra", "Elite", 140, 16, 6, 400, 60, None, "Wikia oficial", False),
            (8, "Aranha Rochedo", "Planície", "Masmorra", "Elite", 160, 18, 7, 500, 70, None, "Wikia oficial", False),
            (9, "Batedor Goblin", "Planície", "Masmorra", "Elite", 170, 20, 7, 600, 80, None, "Wikia oficial", False),
            (10, "Senhor dos Rochedos", "Planície", "Masmorra", "Boss", 350, 30, 15, 900, 150, None, "Wikia oficial", False),

            # Floresta Sombria
            (11, "Goblin", "Floresta Sombria", "Caçada", "Comum", 90, 12, 3, 35, 25, None, "Wikia oficial + Railway Archivus", False),
            (12, "Vespa", "Floresta Sombria", "Caçada", "Comum", 100, 15, 3, 40, 28, None, "Wikia oficial + Railway Archivus (Vespa Gigante)", False),
            (13, "Javali", "Floresta Sombria", "Caçada", "Comum", 120, 18, 4, 45, 30, None, "Wikia oficial + Railway Archivus", False),
            (14, "Elfo Ladino", "Floresta Sombria", "Caçada", "Incomum", 140, 22, 5, 60, 45, None, "Wikia oficial + Railway Archivus (Elfo Saqueador)", False),
            (15, "Urso", "Floresta Sombria", "Caçada", "Incomum", 170, 24, 6, 70, 50, None, "Wikia oficial + Railway Archivus", False),
            (16, "Ent", "Floresta Sombria", "Caçada", "Boss", 260, 30, 10, 130, 90, None, "Wikia oficial", False),
            (17, "Ent Jovem", "Floresta Sombria", "Masmorra", "Elite", 300, 35, 12, 600, 85, None, "Wikia oficial", False),
            (18, "Aranha da Mata", "Floresta Sombria", "Masmorra", "Elite", 310, 38, 10, 800, 90, None, "Wikia oficial", False),
            (19, "Batedor Elfo", "Floresta Sombria", "Masmorra", "Elite", 330, 40, 11, 1000, 100, None, "Wikia oficial", False),
            (20, "Guardião do Bosque", "Floresta Sombria", "Masmorra", "Boss", 500, 55, 20, 1400, 200, None, "Wikia oficial", False),

            # Pântano
            (21, "Slime", "Pântano", "Caçada", "Comum", 160, 22, 5, 70, 60, None, "Wikia oficial + Railway Archivus", False),
            (22, "Sanguessuga", "Pântano", "Caçada", "Comum", 170, 24, 5, 75, 62, None, "Wikia oficial + Railway Archivus", False),
            (23, "Orc do Pântano", "Pântano", "Caçada", "Incomum", 190, 28, 6, 90, 70, None, "Wikia oficial + Railway Archivus", False),
            (24, "Bruxa", "Pântano", "Caçada", "Incomum", 210, 32, 8, 110, 80, None, "Wikia oficial + Railway Archivus", False),
            (25, "Carniçal", "Pântano", "Caçada", "Incomum", 230, 30, 7, 120, 85, None, "Wikia oficial + Railway Archivus", False),
            (26, "Filhote de Hidra", "Pântano", "Caçada", "Boss", 320, 38, 10, 200, 150, None, "Wikia oficial", False),
            (27, "Orc do Pântano", "Pântano", "Masmorra", "Elite", 350, 45, 14, 900, 110, None, "Wikia oficial", False),
            (28, "Bruxa do Brejo", "Pântano", "Masmorra", "Elite", 340, 50, 12, 1100, 120, None, "Wikia oficial", False),
            (29, "Sanguessuga Gigante", "Pântano", "Masmorra", "Elite", 380, 48, 15, 1300, 135, None, "Wikia oficial", False),
            (30, "Hidra Menor", "Pântano", "Masmorra", "Boss", 600, 70, 25, 2200, 250, None, "Wikia oficial", False),

            # Cemitério Antigo
            (31, "Esqueleto", "Cemitério Antigo", "Caçada", "Comum", 200, 28, 7, 110, 90, None, "Wikia oficial + Railway Archivus", False),
            (32, "Zumbi", "Cemitério Antigo", "Caçada", "Comum", 220, 30, 7, 120, 95, None, "Wikia oficial + Railway Archivus", False),
            (33, "Múmia", "Cemitério Antigo", "Caçada", "Incomum", 240, 32, 8, 135, 100, None, "Wikia oficial + Railway Archivus", False),
            (34, "Aprendiz de Necro", "Cemitério Antigo", "Caçada", "Incomum", 230, 36, 9, 150, 120, None, "Wikia oficial + Railway Archivus", False),
            (35, "Espectro", "Cemitério Antigo", "Caçada", "Raro", 260, 40, 12, 180, 150, None, "Wikia oficial + Railway Archivus", False),
            (36, "Lich", "Cemitério Antigo", "Caçada", "Boss", 350, 50, 15, 260, 220, None, "Wikia oficial", False),
            (37, "Cavaleiro Sombrio", "Cemitério Antigo", "Masmorra", "Elite", 600, 80, 30, 2000, 300, None, "Wikia oficial", False),
            (38, "Cultista Abissal", "Cemitério Antigo", "Masmorra", "Elite", 550, 90, 25, 2600, 310, None, "Wikia oficial", False),
            (39, "Golem de Osso", "Cemitério Antigo", "Masmorra", "Elite", 700, 85, 35, 3200, 330, None, "Wikia oficial", False),
            (40, "Arquilorde dos Ossos", "Cemitério Antigo", "Masmorra", "Raid Boss", 1200, 120, 50, 5500, 600, None, "Wikia oficial", False),

            # Deserto Escaldante
            (41, "Escorpião", "Deserto Escaldante", "Caçada", "Comum", 230, 35, 10, 160, 130, None, "Wikia oficial + Railway Archivus", False),
            (42, "Verme da Areia", "Deserto Escaldante", "Caçada", "Incomum", 260, 38, 10, 180, 140, None, "Wikia oficial + Railway Archivus (Verme de Areia)", False),
            (43, "Nômade", "Deserto Escaldante", "Caçada", "Incomum", 240, 42, 12, 190, 150, None, "Wikia oficial + Railway Archivus", False),
            (44, "Escaravelho", "Deserto Escaldante", "Caçada", "Raro", 280, 44, 13, 210, 170, None, "Wikia oficial + Railway Archivus", False),
            (45, "Diabrete de Fogo", "Deserto Escaldante", "Caçada", "Raro", 250, 48, 12, 230, 180, None, "Wikia oficial + Railway Archivus", False),
            (46, "Guardião Ancestral", "Deserto Escaldante", "Caçada", "Boss", 380, 55, 18, 320, 260, None, "Wikia oficial", False),
            (47, "Escorpião Titã", "Deserto Escaldante", "Masmorra", "Elite", 650, 90, 35, 2800, 320, None, "Wikia oficial", False),
            (48, "Verme Gigante", "Deserto Escaldante", "Masmorra", "Elite", 700, 95, 30, 3500, 340, None, "Wikia oficial", False),
            (49, "Elemental de Areia", "Deserto Escaldante", "Masmorra", "Elite", 680, 100, 32, 4200, 360, None, "Wikia oficial", False),
            (50, "Faraó Maldito", "Deserto Escaldante", "Masmorra", "Raid Boss", 1300, 130, 55, 7500, 650, None, "Wikia oficial", False),

            # Oásis Perdido — registros do Railway ainda sem ATK/DEF/Gold
            (51, "Karkto Feroz", "Oásis Perdido", "Caçada", None, 420, None, None, 245, None, None, "Railway Archivus", False),
            (52, "Cobra do Deserto", "Oásis Perdido", "Caçada", None, 360, None, None, 215, None, None, "Railway Archivus", False),
            (53, "Abutre de Fogo", "Oásis Perdido", "Caçada", None, 400, None, None, 230, None, None, "Railway Archivus", False),
            (54, "Lince Saqueadora", "Oásis Perdido", "Caçada", None, 440, None, None, 260, None, None, "Railway Archivus", False),
            (55, "Lagarto da Areia", "Oásis Perdido", "Caçada", None, 380, None, None, 210, None, None, "Railway Archivus", False),
            (56, "Guardião Raiz Profanado", "Oásis Perdido", "Masmorra", "Boss", 1211, None, None, None, None, None, "Histórico atual do Teletofus", True),

            # Montanhas Gélidas
            (57, "Golem de Gelo", "Montanhas Gélidas", "Caçada", "Incomum", 320, 50, 16, 260, 200, None, "Wikia oficial", False),
            (58, "Harpia", "Montanhas Gélidas", "Caçada", "Incomum", 300, 48, 14, 250, 190, None, "Wikia oficial", False),
            (59, "Orc do Gelo", "Montanhas Gélidas", "Caçada", "Incomum", 310, 52, 15, 260, 200, None, "Wikia oficial", False),
            (60, "Yeti", "Montanhas Gélidas", "Caçada", "Raro", 340, 54, 17, 280, 220, None, "Wikia oficial", False),
            (61, "Wyvern", "Montanhas Gélidas", "Caçada", "Raro", 360, 58, 18, 320, 240, None, "Wikia oficial", False),
            (62, "Dragão Jovem", "Montanhas Gélidas", "Caçada", "Boss", 480, 70, 22, 420, 320, None, "Wikia oficial", False),

            # Fortaleza dos Orcs — patch oficial; estatísticas ainda a confirmar
            (63, "Orc", "Fortaleza dos Orcs", "Caçada", None, None, None, None, None, None, "Pele de Goblin", "Notícia oficial do Teletofus", False),
            (64, "Goblin", "Fortaleza dos Orcs", "Caçada", None, None, None, None, None, None, "Pele de Orc", "Notícia oficial do Teletofus", False),

            # Abismo
            (65, "Demônio Menor", "Abismo", "Caçada", "Raro", 380, 68, 20, 380, 280, None, "Wikia oficial", False),
            (66, "Cavaleiro Sombrio", "Abismo", "Caçada", "Raro", 420, 72, 22, 420, 300, None, "Wikia oficial", False),
            (67, "Cultista", "Abismo", "Caçada", "Raro", 390, 70, 21, 410, 290, None, "Wikia oficial", False),
            (68, "Cão do Inferno", "Abismo", "Caçada", "Raro", 400, 75, 21, 440, 310, None, "Wikia oficial", False),
            (69, "Cria do Vazio", "Abismo", "Caçada", "Raro", 430, 78, 23, 460, 330, None, "Wikia oficial", False),
            (70, "Lorde do Abismo", "Abismo", "Caçada", "Boss", 650, 95, 28, 620, 480, None, "Wikia oficial", False),
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
    nome = re.sub(r"^[^\wÀ-ÿ]+", "", nome).strip()
    return nome.upper() or None

def extrair_nome(texto):
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]

    # No formato atual, o nick fica imediatamente antes de "Classe:".
    for i, linha in enumerate(linhas):
        if re.match(r"^Classe\s*:", linha, re.IGNORECASE) and i > 0:
            return limpar_nome(linhas[i - 1])

    # Compatibilidade com perfis sem a linha de classe.
    ignorar = (
        "classe:", "títulos:", "titulos:", "lv ", "xp:", "faltam:",
        "arena", "ranking:", "histórico:", "historico:", "energia:",
        "gold:", "tofus:", "mapa:", "renomear:", "mudar classe:"
    )
    for linha in linhas:
        candidato = re.sub(r"^[^\wÀ-ÿ]+", "", linha).strip()
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
    return int(match.group(1)) if match else None

def extrair_status(texto):
    dados = {}
    bonus_atk = 0
    bonus_def = 0
    bonus_crit = 0
    atk = None
    defesa = None
    crit = None

    for linha in texto.splitlines():
        linha = linha.strip()

        # Status principais e HP podem estar todos na mesma linha.
        if "+" not in linha:
            atk_match = re.search(r"\bATK\s*:?\s*(\d+(?:[.,]\d+)?)", linha, re.IGNORECASE)
            def_match = re.search(r"\bDEF\s*:?\s*(\d+(?:[.,]\d+)?)", linha, re.IGNORECASE)
            crit_match = re.search(r"\bCRIT\s*:?\s*(\d+(?:[.,]\d+)?)", linha, re.IGNORECASE)

            if atk_match:
                atk = float(atk_match.group(1).replace(",", "."))
            if def_match:
                defesa = float(def_match.group(1).replace(",", "."))
            if crit_match:
                crit = float(crit_match.group(1).replace(",", "."))

        if "+" in linha:
            atk_match = re.search(r"\+(\d+(?:[.,]\d+)?)\s*ATK", linha, re.IGNORECASE)
            def_match = re.search(r"\+(\d+(?:[.,]\d+)?)\s*DEF", linha, re.IGNORECASE)
            crit_match = re.search(r"\+(\d+(?:[.,]\d+)?)\s*%?\s*CRIT", linha, re.IGNORECASE)

            if atk_match:
                bonus_atk = float(atk_match.group(1).replace(",", "."))
            if def_match:
                bonus_def = float(def_match.group(1).replace(",", "."))
            if crit_match:
                bonus_crit = float(crit_match.group(1).replace(",", "."))

        hp_match = re.search(
            r"\bHP\s*:?\s*(\d[\d.,]*)(?:\s*/\s*(\d[\d.,]*))?",
            linha,
            re.IGNORECASE
        )
        if hp_match:
            valor_hp = hp_match.group(2) or hp_match.group(1)
            dados["hp"] = int(re.sub(r"\D", "", valor_hp))

        gold_match = re.search(r"\bGold\s*:\s*([\d.,]+)", linha, re.IGNORECASE)
        if gold_match:
            dados["gold"] = int(re.sub(r"\D", "", gold_match.group(1)))

        tofus_match = re.search(r"\bTofus\s*:\s*([\d.,]+)", linha, re.IGNORECASE)
        if tofus_match:
            dados["tofus"] = int(re.sub(r"\D", "", tofus_match.group(1)))

    if atk is not None:
        dados["atk"] = max(0, atk - bonus_atk)
    if defesa is not None:
        dados["def"] = max(0, defesa - bonus_def)
    if crit is not None:
        dados["crit"] = max(0, crit - bonus_crit)

    return dados

def registrar_membro(tg_id, nome):
    cur = conn.cursor()
    try:
        # Impede que um perfil já vinculado seja apropriado por outro ID.
        cur.execute("""
            SELECT telegram_id
            FROM membros
            WHERE UPPER(nome)=UPPER(%s) AND telegram_id<>%s
            LIMIT 1
            FOR UPDATE
        """, (nome, tg_id))

        if cur.fetchone():
            conn.rollback()
            return False

        cur.execute("""
            INSERT INTO membros (telegram_id,nome)
            VALUES (%s,%s)
            ON CONFLICT (telegram_id)
            DO UPDATE SET nome=EXCLUDED.nome
        """, (tg_id, nome))

        # Mantém uma trilha de troca de nick sem apagar o vínculo anterior.
        cur.execute("""
            INSERT INTO membro_vinculos (telegram_id,nome)
            VALUES (%s,%s)
            ON CONFLICT (telegram_id,nome)
            DO UPDATE SET ultima_vista=CURRENT_TIMESTAMP
        """, (tg_id, nome))

        # O ID do Telegram é a identidade estável. Atualiza o nick de exibição
        # nos registros associados para rankings, presença, caçadas e Gibby.
        for tabela in (
            "presencas", "xp_logs", "xp_progresso", "status", "cacadas", "gibby_logs"
        ):
            cur.execute(
                f"UPDATE {tabela} SET nome=%s WHERE telegram_id=%s AND nome<>%s",
                (nome, tg_id, nome)
            )

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()

def salvar_presenca(tg_id,nome):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO presencas (telegram_id,nome,data) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
        (tg_id,nome,hoje())
    )
    inseriu = cur.rowcount > 0
    conn.commit()
    return inseriu

def salvar_xp(tg_id,nome,xp,nivel,xp_restante=None):

    if xp is None:
        return

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT xp
            FROM xp_logs
            WHERE telegram_id=%s
            ORDER BY data_hora DESC
            LIMIT 1
        """, (tg_id,))

        ultimo = cur.fetchone()
        if not ultimo or ultimo[0] != xp:
            cur.execute(
                "INSERT INTO xp_logs (telegram_id,nome,xp,nivel) VALUES (%s,%s,%s,%s)",
                (tg_id,nome,xp,nivel)
            )

        if xp_restante is not None:
            cur.execute("""
                SELECT xp, nivel, xp_restante
                FROM xp_progresso
                WHERE telegram_id=%s
                ORDER BY data_hora DESC
                LIMIT 1
            """, (tg_id,))

            ultimo_progresso = cur.fetchone()
            if ultimo_progresso != (xp, nivel, xp_restante):
                cur.execute("""
                    INSERT INTO xp_progresso
                    (telegram_id,nome,xp,nivel,xp_restante)
                    VALUES (%s,%s,%s,%s,%s)
                """, (tg_id,nome,xp,nivel,xp_restante))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()

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

def formatar_numero(valor):
    return f"{int(valor):,}".replace(",", ".")

def faixa_previsao(dias):
    if dias <= 1:
        return "hoje ou amanhã"
    if dias < 3:
        return "em menos de 3 dias"
    if dias <= 7:
        return "entre 3 e 7 dias"
    if dias <= 14:
        return "entre 1 e 2 semanas"
    return "em mais de 2 semanas"

def gerar_up(tg_id):
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT nome, nivel, xp, xp_restante, data_hora
            FROM xp_progresso
            WHERE telegram_id=%s
            ORDER BY data_hora DESC
            LIMIT 1
        """, (tg_id,))

        ultimo = cur.fetchone()
        if not ultimo:
            return (
                "📈 EXP TRACKER\n\n"
                "Ainda não tenho o XP restante desse personagem. "
                "Encaminhe um perfil atualizado no tópico de presença."
            )

        nome, nivel, xp, xp_restante, data_ultimo = ultimo
        inicio = data_ultimo - timedelta(days=7)

        # Um snapshot por dia evita que vários perfis no mesmo dia distorçam
        # a média. XP total é cumulativo, inclusive após subir de nível.
        cur.execute("""
            SELECT dia, xp
            FROM (
                SELECT DISTINCT ON (
                    (data_hora AT TIME ZONE 'America/Sao_Paulo')::date
                )
                    (data_hora AT TIME ZONE 'America/Sao_Paulo')::date AS dia,
                    xp,
                    data_hora
                FROM xp_logs
                WHERE telegram_id=%s
                  AND data_hora BETWEEN %s AND %s
                ORDER BY
                    (data_hora AT TIME ZONE 'America/Sao_Paulo')::date,
                    data_hora DESC
            ) diarios
            ORDER BY dia
        """, (tg_id, inicio, data_ultimo))

        diarios = cur.fetchall()
        cabecalho = (
            f"📈 EXP TRACKER — {nome}\n\n"
            f"⭐ Nível: {nivel}\n"
            f"✨ XP total: {formatar_numero(xp)}\n"
            f"🎯 Faltam: {formatar_numero(xp_restante)} XP\n"
        )

        if len(diarios) < 2:
            return (
                cabecalho
                + "\n⏳ Ainda falta histórico diário para calcular o ritmo.\n"
                + "Envie outro perfil em um próximo dia e use /up novamente."
            )

        primeira_data, primeiro_xp = diarios[0]
        ultima_data, ultimo_xp = diarios[-1]
        dias_observados = (ultima_data - primeira_data).days
        ganho = ultimo_xp - primeiro_xp

        if dias_observados < 1 or ganho <= 0:
            return (
                cabecalho
                + "\n➖ Não houve ganho positivo suficiente no período "
                + "para projetar a subida de nível."
            )

        media = ganho / dias_observados
        dias_estimados = xp_restante / media if media > 0 else 0

        return (
            cabecalho
            + f"\n📊 Ganho em {dias_observados} dia(s): "
            + f"{formatar_numero(ganho)} XP\n"
            + f"⚡ Média: {formatar_numero(round(media))} XP/dia\n"
            + f"🗓 Previsão: {faixa_previsao(dias_estimados)} "
            + f"(~{dias_estimados:.1f} dia(s))\n\n"
            + "ℹ️ Estimativa baseada nos perfis dos últimos 7 dias."
        )
    finally:
        cur.close()

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

async def cmd_up(update, context):

    if not await validar_acesso(
        update,
        context,
        "/up"
    ):
        return

    await update.message.reply_text(
        gerar_up(update.effective_user.id)
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

    # Só perfis autênticos encaminhados pelo bot do jogo podem gravar dados.
    # Mensagens comuns, textos copiados e imagens sem o formato completo são ignorados.
    if not msg.photo or not msg.caption:
        return

    eh_encaminhada = any((
        getattr(msg, "forward_origin", None),
        getattr(msg, "forward_date", None),
        getattr(msg, "forward_from", None),
        getattr(msg, "forward_from_chat", None),
        getattr(msg, "forward_sender_name", None),
    ))

    if not eh_encaminhada:
        return

    marcadores_obrigatorios = (
        r"^Classe\s*:",
        r"\bLv\s*\d+",
        r"\bXP\s*:\s*[\d.,]+",
        r"\bATK\s*:?\s*\d+",
        r"\bDEF\s*:?\s*\d+",
        r"\bCRIT\s*:?\s*\d+",
        r"\bHP\s*:?\s*\d+",
        r"\bGold\s*:\s*[\d.,]+",
        r"\bTofus\s*:\s*[\d.,]+",
    )

    if not all(
        re.search(marcador, texto, re.IGNORECASE | re.MULTILINE)
        for marcador in marcadores_obrigatorios
    ):
        return

    nome = extrair_nome(texto)
    xp = extrair_xp(texto)
    xp_restante = extrair_xp_restante(texto)
    nivel = extrair_nivel(texto)
    status = extrair_status(texto)

    campos_status = {"atk", "def", "crit", "hp", "gold", "tofus"}
    if (
        not nome
        or xp is None
        or nivel is None
        or not campos_status.issubset(status)
    ):
        return

    tg_id = msg.from_user.id
    if not registrar_membro(tg_id, nome):
        await msg.reply_text(
            "⚠ Este personagem já está vinculado a outra conta do Telegram. "
            "Os dados não foram alterados. Procure um administrador para revisar o vínculo."
        )
        return

    novo = salvar_presenca(
        tg_id,
        nome
    )

    salvar_xp(
        tg_id,
        nome,
        xp,
        nivel,
        xp_restante
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

async def enviar_em_partes(update, texto, limite=3800):

    parte = ""

    for linha in texto.splitlines():
        candidato = f"{parte}\n{linha}" if parte else linha

        if len(candidato) > limite and parte:
            await update.message.reply_text(parte)
            parte = linha
        else:
            parte = candidato

    if parte:
        await update.message.reply_text(parte)


def argumento_numerico(context):

    if len(context.args) != 1 or not context.args[0].isdigit():
        return None

    numero = int(context.args[0])
    return numero if numero > 0 else None


def formatar_valor_catalogo(valor):

    if valor is None:
        return "a confirmar"

    if hasattr(valor, "to_integral_value") and valor == valor.to_integral_value():
        return str(int(valor))

    return str(valor)


async def cmd_mapa(update, context):

    # O catálogo fica silencioso nos grupos durante a fase de testes.
    if update.effective_chat.type != "private":
        return

    if not await validar_acesso(update, context, "/mapa"):
        return

    numero = argumento_numerico(context) if context.args else None

    if context.args and numero is None:
        await update.message.reply_text(
            "Use /mapa para listar ou /mapa NÚMERO para consultar."
        )
        return

    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, nome, nivel_minimo, dificuldade, tempo_masmorra,
                   xp_masmorra_4, xp_masmorra_5, descricao, fonte, confirmado
            FROM catalogo_mapas
            ORDER BY ordem, id
        """)
        mapas = cur.fetchall()

        if not numero:
            linhas = ["🗺️ MAPAS DO TELETOFUS", ""]

            for indice, mapa in enumerate(mapas, start=1):
                nivel = f"Lv {mapa[2]}" if mapa[2] is not None else "nível a confirmar"
                linhas.append(f"{indice}. {mapa[1]} — {nivel}")

            linhas.extend(["", "Consulte os detalhes com /mapa número."])
            await enviar_em_partes(update, "\n".join(linhas))
            return

        if numero > len(mapas):
            await update.message.reply_text(
                f"Mapa inexistente. Escolha um número entre 1 e {len(mapas)}."
            )
            return

        (mapa_id, nome, nivel, dificuldade, tempo_masmorra,
         xp_masmorra_4, xp_masmorra_5, descricao, fonte,
         confirmado) = mapas[numero - 1]

        cur.execute("""
            SELECT nome, tipo
            FROM catalogo_monstros
            WHERE mapa_id=%s
            ORDER BY ordem, id
        """, (mapa_id,))
        monstros = cur.fetchall()

        cur.execute("""
            SELECT nome
            FROM itens_legends
            WHERE mapa=%s
            ORDER BY nivel NULLS LAST, nome
            LIMIT 6
        """, (nome,))
        itens = [linha[0] for linha in cur.fetchall()]

        cur.execute("""
            SELECT COUNT(*)
            FROM itens_legends
            WHERE mapa=%s
        """, (nome,))
        total_itens = cur.fetchone()[0]

        linhas = [
            f"🗺️ MAPA {numero} — {nome}",
            "",
            f"⭐ Nível mínimo: {formatar_valor_catalogo(nivel)}",
            f"⚔️ Dificuldade: {formatar_valor_catalogo(dificuldade)}",
            f"🔎 Estado: {'confirmado' if confirmado else 'a confirmar/atualizar'}",
            f"📚 Fonte: {fonte}",
        ]

        if descricao:
            linhas.extend(["", descricao])

        if tempo_masmorra or xp_masmorra_4 or xp_masmorra_5:
            linhas.extend(["", "🏛️ Referência de masmorra do Archivus"])

            if tempo_masmorra:
                linhas.append(f"• Tempo ideal: {tempo_masmorra} min")

            if xp_masmorra_4:
                linhas.append(f"• 4 jogadores: {xp_masmorra_4:,} XP".replace(",", "."))

            if xp_masmorra_5:
                linhas.append(f"• 5 jogadores: {xp_masmorra_5:,} XP".replace(",", "."))

        linhas.extend(["", f"👹 Monstros cadastrados: {len(monstros)}"])
        linhas.extend(f"• {monstro} ({tipo})" for monstro, tipo in monstros)

        linhas.extend(["", f"🎁 Itens associados: {total_itens}"])
        linhas.extend(f"• {item}" for item in itens)

        if total_itens > len(itens):
            linhas.append(f"• e mais {total_itens - len(itens)} item(ns)")

        await enviar_em_partes(update, "\n".join(linhas))

    except Exception as erro:
        conn.rollback()
        print(f"Erro catálogo de mapas: {erro}")
        await update.message.reply_text(
            "Não consegui consultar os mapas agora. Tente novamente em instantes."
        )
    finally:
        cur.close()


async def cmd_monstro(update, context):

    # O bestiário fica silencioso nos grupos durante a fase de testes.
    if update.effective_chat.type != "private":
        return

    if not await validar_acesso(update, context, "/monstro"):
        return

    numero = argumento_numerico(context) if context.args else None

    if context.args and numero is None:
        await update.message.reply_text(
            "Use /monstro para listar ou /monstro NÚMERO para consultar."
        )
        return

    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT cm.nome, mp.nome, cm.tipo, cm.raridade, cm.hp,
                   cm.atk, cm.defesa, cm.xp, cm.gold, cm.drops,
                   cm.fonte, cm.confirmado
            FROM catalogo_monstros cm
            LEFT JOIN catalogo_mapas mp ON mp.id=cm.mapa_id
            ORDER BY cm.ordem, cm.id
        """)
        monstros = cur.fetchall()

        if not numero:
            linhas = ["👹 BESTIÁRIO DO TELETOFUS", ""]

            for indice, monstro in enumerate(monstros, start=1):
                linhas.append(f"{indice}. {monstro[0]} — {monstro[1] or 'mapa a confirmar'}")

            linhas.extend(["", "Consulte os detalhes com /monstro número."])
            await enviar_em_partes(update, "\n".join(linhas))
            return

        if numero > len(monstros):
            await update.message.reply_text(
                f"Monstro inexistente. Escolha um número entre 1 e {len(monstros)}."
            )
            return

        (nome, mapa, tipo, raridade, hp, atk, defesa, xp, gold,
         drops, fonte, confirmado) = monstros[numero - 1]

        linhas = [
            f"👹 MONSTRO {numero} — {nome}",
            "",
            f"🗺️ Mapa: {mapa or 'a confirmar'}",
            f"🏷️ Tipo: {tipo or 'a confirmar'}",
            f"💠 Raridade: {raridade or 'a confirmar'}",
            f"❤️ HP: {formatar_valor_catalogo(hp)}",
            f"⚔️ ATK: {formatar_valor_catalogo(atk)}",
            f"🛡️ DEF: {formatar_valor_catalogo(defesa)}",
            f"⭐ XP: {formatar_valor_catalogo(xp)}",
            f"💰 Gold: {formatar_valor_catalogo(gold)}",
            f"🎁 Drops: {drops or 'a confirmar'}",
            "",
            f"🔎 Estado: {'confirmado' if confirmado else 'a confirmar/atualizar'}",
            f"📚 Fonte: {fonte}",
        ]

        await update.message.reply_text("\n".join(linhas))

    except Exception as erro:
        conn.rollback()
        print(f"Erro bestiário: {erro}")
        await update.message.reply_text(
            "Não consegui consultar o bestiário agora. Tente novamente em instantes."
        )
    finally:
        cur.close()


async def cmd_start(update, context):

    if context.args and context.args[0] == "item":

        await update.message.reply_text(
            "📚 BIBLIOTECA LEGENDS\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_inicio_biblioteca()
        )

        return

    await update.message.reply_text(
        "Olá! Use os comandos disponíveis."
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
                        "📚 Abrir Biblioteca",
                        url=f"https://t.me/{bot_username}?start=item"
                    )
                ]
            ])

            await update.message.reply_text(
                "📚 Para evitar spam nos tópicos da guilda, "
                "a Biblioteca Legends funciona apenas no privado.\n\n"
                "Clique no botão abaixo para abrir a biblioteca.",
                reply_markup=teclado
            )

            return

    await update.message.reply_text(
        "📚 BIBLIOTECA LEGENDS\n\n"
        "Escolha uma categoria:",
        reply_markup=teclado_inicio_biblioteca()
    )

def teclado_inicio_biblioteca():

    return InlineKeyboardMarkup([

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

    ])

def teclado_categorias(classe):

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "⚔ Armas",
                callback_data=f"cat_{classe}_arma"
            )
        ],

        [
            InlineKeyboardButton(
                "🛡 Escudos",
                callback_data=f"cat_{classe}_escudo"
            )
        ],

        [
            InlineKeyboardButton(
                "🥋 Peitorais",
                callback_data=f"cat_{classe}_peitoral"
            )
        ],

        [
            InlineKeyboardButton(
                "👢 Botas",
                callback_data=f"cat_{classe}_bota"
            )
        ],

        [
            InlineKeyboardButton(
                "💍 Anéis",
                callback_data=f"cat_{classe}_anel"
            )
        ],

        [
            InlineKeyboardButton(
                "📿 Colares",
                callback_data=f"cat_{classe}_colar"
            )
        ],

        [
            InlineKeyboardButton(
                "⬅ Voltar",
                callback_data="voltar_inicio"
            )
        ]

    ])

def emoji_raridade(raridade):

    mapa = {

        "evento": "⚪",
        "comum": "🟢",
        "incomum": "🔵",
        "raro": "🟣",
        "lendario": "🟠",
        "especial": "🟡"

    }

    return mapa.get(
        raridade,
        "❓"
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
                "⬅ Voltar",
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
            "Item não encontrado."
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

        "guerreiro": "🛡 Guerreiro",
        "arqueiro": "🏹 Arqueiro",
        "mago": "🔮 Mago",
        "todas": "🌎 Todas as Classes"

    }

    texto += (
        f"{classe_map.get(item['classe'],'')}\n"
    )

    if item.get("nivel"):

        texto += (
            f"⭐ Lv {item['nivel']}\n"
        )

    if item.get("duas_maos"):

        texto += (
            "⚔ Arma de Duas Mãos\n"
        )

    stats = ""

    if item.get("atk_min"):

        stats += (
            f"⚔ {item['atk_min']}~"
            f"{item['atk_max']}\n"
        )

    if item.get("def_min"):

        stats += (
            f"🛡 {item['def_min']}~"
            f"{item['def_max']}\n"
        )

    if item.get("hp_min"):

        stats += (
            f"❤️ {item['hp_min']}~"
            f"{item['hp_max']}\n"
        )

    if item.get("crit_min"):

        stats += (
            f"🎯 {float(item['crit_min']):g}~"
            f"{float(item['crit_max']):g}%\n"
        )

    if stats:

        texto += "\n" + stats

    if item.get("descricao"):

        texto += (
            f"\n📖 {item['descricao']}\n"
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
            f"\n🗺️ {item['mapa']}\n"
        )

    if drops:

        texto += "\n📍 Obtenção\n"

        for drop in drops:

            texto += (
                f"• {drop}\n"
            )

    if item.get("obtencao"):

        texto += (
            f"\n📍 {item['obtencao']}\n"
        )

    if item.get("chance_drop"):

        texto += (
            f"\n🎁 Chance: "
            f"{item['chance_drop']}"
        )

    if item.get("passiva"):

        texto += (
            f"\n\n✨ Passiva\n"
            f"{item['passiva']}"
        )

    teclado = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "⬅ Voltar",
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
            "📚 BIBLIOTECA LEGENDS\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_inicio_biblioteca()
        )

        return

    if dados == "voltar_todas":

        await query.edit_message_text(
            "📚 BIBLIOTECA LEGENDS\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_inicio_biblioteca()
        )

        return

    # GUERREIRO

    if dados == "bib_guerreiro":

        await query.edit_message_text(
            "⚔ BIBLIOTECA GUERREIRO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "guerreiro"
            )
        )

        return

    if dados == "cat_guerreiro_arma":

        await query.edit_message_text(
            "⚔ ARMAS - GUERREIRO",
            reply_markup=teclado_itens(
                "guerreiro",
                "arma"
            )
        )

        return

    if dados == "cat_guerreiro_escudo":

        await query.edit_message_text(
            "🛡 ESCUDOS - GUERREIRO",
            reply_markup=teclado_itens(
                "guerreiro",
                "escudo"
            )
        )

        return


    if dados == "cat_guerreiro_peitoral":

        await query.edit_message_text(
            "🥋 PEITORAIS - GUERREIRO",
            reply_markup=teclado_itens(
                "guerreiro",
                "peitoral"
            )
        )

        return


    if dados == "cat_guerreiro_bota":

        await query.edit_message_text(
            "👢 BOTAS - GUERREIRO",
           reply_markup=teclado_itens(
                "guerreiro",
                "bota"
            )
        )

        return


    if dados == "cat_guerreiro_anel":

        await query.edit_message_text(
            "💍 ANÉIS - GUERREIRO",
            reply_markup=teclado_itens(
                "guerreiro",
                "anel"
            )
        )

        return


    if dados == "cat_guerreiro_colar":

        await query.edit_message_text(
            "📿 COLARES - GUERREIRO",
            reply_markup=teclado_itens(
                "guerreiro",
                "colar"
            )
        )

        return

    if dados == "voltar_guerreiro":

        await query.edit_message_text(
            "⚔ BIBLIOTECA GUERREIRO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "guerreiro"
            )
        )

        return

    # ARQUEIRO

    if dados == "bib_arqueiro":

        await query.edit_message_text(
            "🏹 BIBLIOTECA ARQUEIRO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "arqueiro"
            )
        )

        return

    if dados == "cat_arqueiro_arma":

        await query.edit_message_text(
            "⚔ ARMAS - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "arma"
            )
        )

        return

    if dados == "cat_arqueiro_escudo":

        await query.edit_message_text(
            "🛡 ESCUDOS - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "escudo"
            )
        )

        return

    if dados == "cat_arqueiro_peitoral":

        await query.edit_message_text(
            "🥋 PEITORAIS - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "peitoral"
            )
        )

        return

    if dados == "cat_arqueiro_bota":

        await query.edit_message_text(
            "👢 BOTAS - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "bota"
            )
        )

        return

    if dados == "cat_arqueiro_anel":

        await query.edit_message_text(
            "💍 ANÉIS - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "anel"
            )
        )

        return

    if dados == "cat_arqueiro_colar":

        await query.edit_message_text(
            "📿 COLARES - ARQUEIRO",
            reply_markup=teclado_itens(
                "arqueiro",
                "colar"
            )
        )

        return

    if dados == "voltar_arqueiro":

        await query.edit_message_text(
            "🏹 BIBLIOTECA ARQUEIRO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "arqueiro"
            )
        )

        return

    # MAGO

    if dados == "bib_mago":

        await query.edit_message_text(
            "🔮 BIBLIOTECA MAGO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "mago"
            )
        )

        return

    if dados == "voltar_mago":

        await query.edit_message_text(
            "🔮 BIBLIOTECA MAGO\n\n"
            "Escolha uma categoria:",
            reply_markup=teclado_categorias(
                "mago"
            )
        )

        return

    if dados == "cat_mago_arma":

        await query.edit_message_text(
            "⚔ ARMAS - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "arma"
            )
        )

        return

    if dados == "cat_mago_escudo":

        await query.edit_message_text(
            "🛡 ESCUDOS - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "escudo"
            )
        )

        return

    if dados == "cat_mago_peitoral":

        await query.edit_message_text(
            "🥋 PEITORAIS - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "peitoral"
            )
        )

        return


    if dados == "cat_mago_bota":

        await query.edit_message_text(
            "👢 BOTAS - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "bota"
            )
        )

        return

    if dados == "cat_mago_anel":

        await query.edit_message_text(
            "💍 ANÉIS - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "anel"
            )
        )

        return

    if dados == "cat_mago_colar":

        await query.edit_message_text(
            "📿 COLARES - MAGO",
            reply_markup=teclado_itens(
                "mago",
                "colar"
            )
        )

        return

    # CONSUMÍVEIS

    if dados == "bib_consumiveis":

        await query.edit_message_text(
            "🧪 CONSUMÍVEIS",
            reply_markup=teclado_itens(
                "todas",
                "consumivel"
            )
        )

        return

    # ESPECIAIS

    if dados == "bib_especiais":

        await query.edit_message_text(
            "✨ ESPECIAIS",
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
            "CRÍTICO"
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
