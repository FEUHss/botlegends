Warning: truncated output (original token count: 40910)
Total output lines: 5321

import os
import re
import random
import hashlib
import psycopg2
import pytz
from datetime import datetime, timedelta
from pathlib import Path
from loot_parser import (
    analisar_texto_loot,
    chave_origem_drop,
    extrair_mapa_visual,
    extrair_masmorra_visual,
    extrair_monstro_combate,
    extrair_monstro_masmorra,
    normalizar,
)
from market_collector import start_market_collector, stop_market_collector
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto
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

BASE_DIR = Path(__file__).resolve().parent
BIBLIOTECA_ASSETS = {
    "biblioteca": BASE_DIR / "assets" / "library-cover.jpg",
    "atlas": BASE_DIR / "assets" / "atlas-cover.jpg",
    "itens": BASE_DIR / "assets" / "items-cover.jpg",
    "desconhecido": BASE_DIR / "assets" / "unknown-cover.jpg",
}
BIBLIOTECA_ASSET_URLS = {
    "biblioteca": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/library-cover.jpg",
    "atlas": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/atlas-cover.jpg",
    "itens": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/items-cover.jpg",
    "desconhecido": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/unknown-cover.jpg",
}

# Somente este usuário recebe e decide as propostas encontradas em LOOTS.
LOOT_REVIEWER_ID = int(os.getenv("LOOT_REVIEWER_ID", "5285053532"))
TELETOFUS_BOT_ID = int(os.getenv("TELETOFUS_BOT_ID", "8564509864"))

GRUPO_ID = -1003792787717

TOPICO_PRESENCA = 16325
TOPICO_LOOTS = 19

TOPICO_PILAR = 29992
TOPICO_GIBBY = 82230

# Nomes levantados diretamente nos menus do bot oficial. Um mapa pode ter
# várias masmorras; a ordem é apenas a ordem de exibição no Atlas.
MASMORRAS_POR_MAPA = {
    "Planície": ["Masmorra da Planície", "Covil de Zul'gor"],
    "Floresta Sombria": ["Masmorra da Floresta"],
    "Pântano": ["Masmorra do Pântano"],
    "Cemitério Antigo": ["Covil do Lord", "Cripta do Cemitério"],
    "Deserto Escaldante": ["Pirâmide do Deserto"],
    "Oásis Perdido": ["Fenda Solar", "Templo do Oásis"],
    "Montanhas Gélidas": [
        "Ruínas de Azulgor",
        "Lago de Kryos",
        "Túneis Proibidos",
    ],
    "Fortaleza dos Orcs": ["Fosso de Provas", "Trono de Khar'gath"],
}

# O catálogo legado só dizia "Masmorra". Esta tabela determina em qual das
# masmorras oficiais os registros antigos aparecem, sem duplicá-los nas demais.
MASMORRA_DOS_MONSTROS = {
    "Planície": "Masmorra da Planície",
    "Floresta Sombria": "Masmorra da Floresta",
    "Pântano": "Masmorra do Pântano",
    "Cemitério Antigo": "Covil do Lord",
    "Deserto Escaldante": "Pirâmide do Deserto",
    "Oásis Perdido": "Templo do Oásis",
}

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
        CREATE TABLE IF NOT EXISTS membro_administracao (
            telegram_id BIGINT PRIMARY KEY,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            telegram_username TEXT,
            classe TEXT,
            inativado_em TIMESTAMPTZ,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
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
            masmorra_nome TEXT,
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
        """,
        """
        CREATE TABLE IF NOT EXISTS loot_evidencias (
            id BIGSERIAL PRIMARY KEY,
            chave_unica TEXT UNIQUE NOT NULL,
            relacao_chave TEXT NOT NULL,
            chat_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            remetente_id BIGINT,
            item_id BIGINT NOT NULL,
            item_nome_detectado TEXT NOT NULL,
            monstro_id BIGINT,
            monstro_nome_detectado TEXT,
            mapa_id BIGINT,
            forma_obtencao TEXT,
            texto_original TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            revisor_id BIGINT,
            criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            decidido_em TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS item_drop_relacoes (
            id BIGSERIAL PRIMARY KEY,
            chave_unica TEXT UNIQUE NOT NULL,
            item_id BIGINT NOT NULL,
            monstro_id BIGINT,
            mapa_id BIGINT,
            forma_obtencao TEXT,
            primeira_evidencia_id BIGINT,
            ultima_evidencia_id BIGINT,
            quantidade_observacoes INTEGER NOT NULL DEFAULT 1,
            primeira_observacao TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            ultima_observacao TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            confirmado BOOLEAN NOT NULL DEFAULT TRUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS monstro_aliases (
            alias_normalizado TEXT PRIMARY KEY,
            alias TEXT NOT NULL,
            monstro_id BIGINT NOT NULL,
            criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS monstro_imagens (
            id BIGSERIAL PRIMARY KEY,
            monstro_id BIGINT NOT NULL,
            telegram_file_id TEXT NOT NULL,
            telegram_file_unique_id TEXT UNIQUE NOT NULL,
            nome_detectado TEXT NOT NULL,
            hp_detectado BIGINT,
            atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS item_imagens (
            id BIGSERIAL PRIMARY KEY,
            item_id BIGINT NOT NULL,
            telegram_file_id TEXT NOT NULL,
            telegram_file_unique_id TEXT UNIQUE NOT NULL,
            nome_detectado TEXT NOT NULL,
            atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS mapa_imagens (
            id BIGSERIAL PRIMARY KEY,
            mapa_id BIGINT NOT NULL,
            telegram_file_id TEXT NOT NULL,
            telegram_file_unique_id TEXT UNIQUE NOT NULL,
            nome_detectado TEXT NOT NULL,
            atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS masmorra_imagens (
            id BIGSERIAL PRIMARY KEY,
            mapa_id BIGINT NOT NULL,
            nome_masmorra TEXT NOT NULL,
            telegram_file_id TEXT NOT NULL,
            telegram_file_unique_id TEXT UNIQUE NOT NULL,
            atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapa_id, nome_masmorra)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS biblioteca_midias (
            chave TEXT PRIMARY KEY,
            telegram_file_id TEXT NOT NULL,
            telegram_file_unique_id TEXT UNIQUE NOT NULL,
            atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS masmorra_monstro_observacoes (
            id BIGSERIAL PRIMARY KEY,
            chave_unica TEXT UNIQUE NOT NULL,
            monstro_id BIGINT NOT NULL,
            mapa_id BIGINT NOT NULL,
            masmorra TEXT NOT NULL,
            andar INTEGER NOT NULL,
            total_andares INTEGER NOT NULL,
            boss BOOLEAN NOT NULL DEFAULT FALSE,
            hp_atual BIGINT,
            hp_max BIGINT,
            tamanho_grupo INTEGER,
            codigo_execucao TEXT,
            telegram_message_id BIGINT,
            observado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """
    ]

    cur = conn.cursor()
    try:
        for ddl in tabelas:
            cur.execute(ddl)
        cur.execute("""
            ALTER TABLE catalogo_monstros
            ADD COLUMN IF NOT EXISTS masmorra_nome TEXT
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_xp_progresso_telegram_data
            ON xp_progresso (telegram_id, data_hora DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_loot_evidencias_status
            ON loot_evidencias (status, criado_em DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_item_drop_item
            ON item_drop_relacoes (item_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_item_drop_monstro
            ON item_drop_relacoes (monstro_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_item_drop_mapa
            ON item_drop_relacoes (mapa_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_item_imagens_item
            ON item_imagens (item_id, atualizado_em DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mapa_imagens_mapa
            ON mapa_imagens (mapa_id, atualizado_em DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_masmorra_imagens_mapa
            ON masmorra_imagens (mapa_id, nome_masmorra)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_masmorra_monstro_andar
            ON masmorra_monstro_observacoes
                (monstro_id, andar, observado_em DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_catalogo_monstro_masmorra
            ON catalogo_monstros (mapa_id, tipo, masmorra_nome)
        """)
        cur.execute("""
            INSERT INTO membro_vinculos (telegram_id, nome)
            SELECT telegram_id, nome FROM membros
            ON CONFLICT (telegram_id, nome) DO NOTHING
        """)
        cur.execute("""
            INSERT INTO membro_administracao (telegram_id, ativo)
            SELECT telegram_id, TRUE FROM membros
            ON CONFLICT (telegram_id) DO NOTHING
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

            # Fortaleza dos Orcs — variantes confirmadas em caçadas no bot oficial.
            # O XP abaixo é o valor-base: a tela mostrou o total com +10% da guilda.
            # ATK/DEF ficam vazios porque dano recebido/causado depende do personagem.
            (63, "Orc Warmarshal", "Fortaleza dos Orcs", "Caçada", None, 1150, None, None, 4600, 380, None, "Teletofus oficial — caçada observada em 11/08/2026", True),
            (64, "Orc Wolf Rider", "Fortaleza dos Orcs", "Caçada", None, 800, None, None, 3200, 250, None, "Teletofus oficial — caçada observada em 11/08/2026", True),
            (65, "Orc Caçador", "Fortaleza dos Orcs", "Caçada", None, 850, None, None, 3400, 265, None, "Teletofus oficial — caçada observada em 11/08/2026", True),
            (66, "Orc Berserker", "Fortaleza dos Orcs", "Caçada", None, 950, None, None, None, None, None, "Teletofus oficial — HP confirmado em 11/08/2026; recompensas não obtidas", True),

            # Abismo
            (65, "Demônio Menor", "Abismo", "Caçada", "Raro", 380, 68, 20, 380, 280, None, "Wikia oficial", False),
            (66, "Cavaleiro Sombrio", "Abismo", "Caçada", "Raro", 420, 72, 22, 420, 300, None, "Wikia oficial", False),
            (67, "Cultista", "Abismo", "Caçada", "Raro", 390, 70, 21, 410, 290, None, "Wikia oficial", False),
            (68, "Cão do Inferno", "Abismo", "Caçada", "Raro", 400, 75, 21, 440, 310, None, "Wikia oficial", False),
            (69, "Cria do Vazio", "Abismo", "Caçada", "Raro", 430, 78, 23, 460, 330, None, "Wikia oficial", False),
            (70, "Lorde do Abismo", "Abismo", "Caçada", "Boss", 650, 95, 28, 620, 480, None, "Wikia oficial", False),
        ]

        # Preserva os IDs dos dois placeholders antigos da Fortaleza e os converte
        # nas primeiras variantes confirmadas. Assim, uma base já existente recebe
        # a correção sem apagar relações que possam apontar para esses registros.
        cur.execute("""
            UPDATE catalogo_monstros AS cm
            SET nome = 'Orc Warmarshal',
                raridade = NULL,
                hp = 1150,
                atk = NULL,
                defesa = NULL,
                xp = 4600,
                gold = 380,
                drops = NULL,
                fonte = 'Teletofus oficial — caçada observada em 11/08/2026',
                confirmado = TRUE,
                atualizado_em = CURRENT_TIMESTAMP
            FROM catalogo_mapas AS mapa
            WHERE cm.mapa_id = mapa.id
              AND mapa.nome = 'Fortaleza dos Orcs'
              AND cm.nome = 'Orc'
              AND cm.tipo = 'Caçada'
              AND NOT EXISTS (
                  SELECT 1
                  FROM catalogo_monstros AS existente
                  WHERE existente.mapa_id = cm.mapa_id
                    AND existente.tipo = cm.tipo
                    AND existente.nome = 'Orc Warmarshal'
              )
        """)
        cur.execute("""
            UPDATE catalogo_monstros AS cm
            SET nome = 'Orc Wolf Rider',
                raridade = NULL,
                hp = 800,
                atk = NULL,
                defesa = NULL,
                xp = 3200,
                gold = 250,
                drops = NULL,
                fonte = 'Teletofus oficial — caçada observada em 11/08/2026',
                confirmado = TRUE,
                atualizado_em = CURRENT_TIMESTAMP
            FROM catalogo_mapas AS mapa
            WHERE cm.mapa_id = mapa.id
              AND mapa.nome = 'Fortaleza dos Orcs'
              AND cm.nome = 'Goblin'
              AND cm.tipo = 'Caçada'
              AND NOT EXISTS (
                  SELECT 1
                  FROM catalogo_monstros AS existente
                  WHERE existente.mapa_id = cm.mapa_id
                    AND existente.tipo = cm.tipo
                    AND existente.nome = 'Orc Wolf Rider'
              )
        """)
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

        # Itens anunciados no jogo em 11/08/2026. O upsert mantém o ID dos
        # registros existentes (especialmente o Broquel de Varkrul) e, com
        # isso, preserva favoritos e relações de drop já cadastradas.
        itens_anuncio_ghurak = [
            (
                "Anel Certeiro de Ghurak", "arqueiro", "anel", "lendario",
                False, 46, 3, 7, 5, 8, 12, 18, 8, 12,
                None, None, None, None, None, None, None, None,
            ),
            (
                "Anel Arcano de Ghurak", "mago", "anel", "lendario",
                False, 46, 8, 13, 3, 5, 16, 22, 4, 8,
                None, None, None, None, None, None, None, None,
            ),
            (
                "Anel de Ferro de Ghurak", "guerreiro", "anel", "lendario",
                False, 46, 5, 9, 8, 12, 10, 15, 2, 4,
                None, None, None, None, None, None, None, None,
            ),
            (
                "Broquel da Floresta", "arqueiro", "escudo", "raro",
                False, 8, None, None, 2, 4, 3, 7, None, None,
                None, None, None, None, "Floresta Sombria",
                "Drop", None, None,
            ),
            (
                "Broquel do Escaravelho Dourado", "arqueiro", "escudo",
                "lendario", False, 32, None, None, 5, 7, 8, 12, None, None,
                None, None, None, None, "Deserto Escaldante",
                "Masmorra do Deserto",
                "Taxa de secundário", None,
            ),
            (
                "Broquel de Varkrul", "arqueiro", "escudo", "lendario",
                False, 42, None, None, 8, 12, 12, 18, None, None,
                None, None, None, None, None, None, None, None,
            ),
        ]
        for item in itens_anuncio_ghurak:
            (
                nome, classe, categoria, raridade, duas_maos, nivel,
                atk_min, atk_max, def_min, def_max, hp_min, hp_max,
                crit_min, crit_max, descricao, drop_1, drop_2, drop_3,
                mapa, obtencao, chance_drop, passiva,
            ) = item
            valores = (
                classe, categoria, raridade, duas_maos, nivel,
                atk_min, atk_max, def_min, def_max, hp_min, hp_max,
                crit_min, crit_max, descricao, drop_1, drop_2, drop_3,
                mapa, obtencao, chance_drop, passiva, nome,
            )
            cur.execute("""
                UPDATE itens_legends
                SET classe=%s,
                    categoria=%s,
                    raridade=%s,
                    duas_maos=%s,
                    nivel=COALESCE(%s, nivel),
                    atk_min=COALESCE(%s, atk_min),
                    atk_max=COALESCE(%s, atk_max),
                    def_min=COALESCE(%s, def_min),
                    def_max=COALESCE(%s, def_max),
                    hp_min=COALESCE(%s, hp_min),
                    hp_max=COALESCE(%s, hp_max),
                    crit_min=COALESCE(%s, crit_min),
                    crit_max=COALESCE(%s, crit_max),
                    descricao=COALESCE(%s, descricao),
                    drop_1=COALESCE(%s, drop_1),
                    drop_2=COALESCE(%s, drop_2),
                    drop_3=COALESCE(%s, drop_3),
                    mapa=COALESCE(%s, mapa),
                    obtencao=COALESCE(%s, obtencao),
                    chance_drop=COALESCE(%s, chance_drop),
                    passiva=COALESCE(%s, passiva)
                WHERE LOWER(nome)=LOWER(%s)
            """, valores)
            if cur.rowcount == 0:
                cur.execute("""
                    INSERT INTO itens_legends (
                        nome, classe, categoria, raridade, duas_maos, nivel,
                        atk_min, atk_max, def_min, def_max, hp_min, hp_max,
                        crit_min, crit_max, descricao, drop_1, drop_2, drop_3,
                        mapa, obtencao, chance_drop, passiva
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, item)
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

def extrair_classe(texto):
    match = re.search(r"^Classe\s*:\s*([^\n\r]+)", texto, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip()[:40] if match else None

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

def registrar_membro(tg_id, nome, telegram_username=None, classe=None):
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

        cur.execute("""
            INSERT INTO membro_administra…20910 tokens truncated…
                    quantidade += contagem_masmorras.get(None, 0)
                linhas.append([InlineKeyboardButton(
                    f"🗝️ {nome_masmorra} ({quantidade})",
                    callback_data=f"atlas_t_{mapa_id}_d{indice}"
                )])
            linhas.append([
                InlineKeyboardButton("⬅️ Mapas", callback_data="atlas_inicio")
            ])
            teclado = InlineKeyboardMarkup(linhas)

        if editar:
            if imagem_mapa:
                await editar_pagina_biblioteca(
                    alvo,
                    "atlas",
                    texto,
                    teclado,
                    file_id=imagem_mapa[0],
                    file_unique_id=imagem_mapa[1],
                )
            else:
                await editar_atlas_com_texto(alvo, texto, teclado)
        else:
            await enviar_pagina_biblioteca(
                alvo,
                "atlas",
                texto,
                teclado,
                file_id=imagem_mapa[0] if imagem_mapa else None,
                file_unique_id=imagem_mapa[1] if imagem_mapa else None,
            )
    finally:
        cur.close()


async def mostrar_monstros_atlas(alvo, mapa_id, codigo_area):
    cur = conn.cursor()
    try:
        cur.execute("SELECT nome FROM catalogo_mapas WHERE id=%s", (mapa_id,))
        resultado = cur.fetchone()
        if not resultado:
            await mostrar_inicio_atlas(alvo, editar=True)
            return
        nome_mapa = resultado[0]

        titulo_area = nome_area_atlas(nome_mapa, codigo_area)
        if not titulo_area:
            await mostrar_mapa_atlas(alvo, mapa_id, editar=True)
            return

        if codigo_area == "c":
            cur.execute("""
                SELECT telegram_file_id, telegram_file_unique_id
                FROM mapa_imagens
                WHERE mapa_id=%s
                ORDER BY atualizado_em DESC
                LIMIT 1
            """, (mapa_id,))
        else:
            cur.execute("""
                SELECT telegram_file_id, telegram_file_unique_id
                FROM masmorra_imagens
                WHERE mapa_id=%s AND nome_masmorra=%s
                ORDER BY atualizado_em DESC
                LIMIT 1
            """, (mapa_id, titulo_area))
        imagem_area = cur.fetchone()

        if codigo_area == "c":
            cur.execute("""
                SELECT ordem, id, nome
                FROM catalogo_monstros
                WHERE mapa_id=%s AND LOWER(tipo)=LOWER('Caçada')
                ORDER BY ordem, id
            """, (mapa_id,))
            monstros = cur.fetchall()
        else:
            masmorra_legada = MASMORRA_DOS_MONSTROS.get(nome_mapa)
            cur.execute("""
                SELECT ordem, id, nome
                FROM catalogo_monstros
                WHERE mapa_id=%s
                  AND LOWER(tipo)=LOWER('Masmorra')
                  AND (
                      masmorra_nome=%s
                      OR (masmorra_nome IS NULL AND %s=%s)
                  )
                ORDER BY ordem, id
            """, (
                mapa_id,
                titulo_area,
                titulo_area,
                masmorra_legada,
            ))
            monstros = cur.fetchall()

        botoes = [
            InlineKeyboardButton(
                f"{ordem}. {nome}",
                callback_data=f"atlas_x_{monstro_id}_{mapa_id}_{codigo_area}"
            )
            for ordem, monstro_id, nome in monstros
        ]
        linhas = agrupar_botoes_atlas(botoes)
        linhas.append([
            InlineKeyboardButton(
                f"⬅️ {nome_mapa}", callback_data=f"atlas_m_{mapa_id}"
            )
        ])
        instrucao = (
            "Escolha um monstro:"
            if monstros
            else "Nenhum monstro associado a esta área por enquanto."
        )
        texto = f"👹 {titulo_area.upper()} — {nome_mapa.upper()}\n\n{instrucao}"
        teclado = InlineKeyboardMarkup(linhas)
        if imagem_area:
            await editar_pagina_biblioteca(
                alvo,
                "atlas",
                texto,
                teclado,
                file_id=imagem_area[0],
                file_unique_id=imagem_area[1],
            )
        else:
            await editar_atlas_com_texto(alvo, texto, teclado)
    finally:
        cur.close()


async def mostrar_monstro_atlas(
    alvo, monstro_id, mapa_id, codigo_area
):
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT cm.ordem, cm.nome, mp.nome, cm.tipo, cm.raridade,
                   cm.hp, cm.atk, cm.defesa, cm.xp, cm.gold, cm.drops
            FROM catalogo_monstros cm
            JOIN catalogo_mapas mp ON mp.id=cm.mapa_id
            WHERE cm.id=%s AND cm.mapa_id=%s
        """, (monstro_id, mapa_id))
        monstro = cur.fetchone()
        if not monstro:
            await mostrar_monstros_atlas(alvo, mapa_id, codigo_area)
            return

        (ordem, nome, mapa, tipo, raridade, hp, atk, defesa, xp, gold,
         drops) = monstro
        cur.execute("""
            SELECT il.nome
            FROM item_drop_relacoes rel
            JOIN itens_legends il ON il.id=rel.item_id
            WHERE rel.monstro_id=%s AND rel.confirmado=TRUE
            ORDER BY il.nome
        """, (monstro_id,))
        drops_relacionados = [linha[0] for linha in cur.fetchall()]
        cur.execute("""
            SELECT telegram_file_id, telegram_file_unique_id
            FROM monstro_imagens
            WHERE monstro_id=%s
            ORDER BY atualizado_em DESC
            LIMIT 1
        """, (monstro_id,))
        row_imagem = cur.fetchone()

        observacoes_hp = []
        if (tipo or "").lower() == "masmorra":
            cur.execute("""
                SELECT andar, MIN(hp_max), MAX(hp_max), COUNT(*)
                FROM masmorra_monstro_observacoes
                WHERE monstro_id=%s AND hp_max IS NOT NULL
                GROUP BY andar
                ORDER BY andar
            """, (monstro_id,))
            observacoes_hp = cur.fetchall()

        hp_principal = (
            "varia por andar"
            if observacoes_hp
            else formatar_valor_catalogo(hp)
        )

        texto = (
            f"👹 MONSTRO {ordem} — {nome}\n\n"
            f"🗺️ {mapa}   🏷️ {tipo or 'a confirmar'}   "
            f"💠 {raridade or 'a confirmar'}\n"
            f"❤️ HP: {hp_principal}   "
            f"⚔️ ATK: {formatar_valor_catalogo(atk)}   "
            f"🛡️ DEF: {formatar_valor_catalogo(defesa)}\n"
            f"⭐ XP: {formatar_valor_catalogo(xp)}   "
            f"💰 Gold: {formatar_valor_catalogo(gold)}\n"
        )
        if (tipo or "").lower() == "masmorra":
            hp_por_andar = {
                andar: (minimo, maximo)
                for andar, minimo, maximo, _ in observacoes_hp
            }
            andares = [4] if (raridade or "").lower() == "boss" else [1, 2, 3]
            texto += "❤️ HP observado na masmorra:\n"
            for andar in andares:
                valores = hp_por_andar.get(andar)
                if not valores:
                    valor = "ainda não observado"
                elif valores[0] == valores[1]:
                    valor = str(valores[0])
                else:
                    valor = f"{valores[0]}–{valores[1]}"
                rotulo = "Boss" if andar == 4 else f"{andar}º andar"
                texto += f"• {rotulo}: {valor}\n"
        if drops_relacionados:
            texto += "🎁 Drops: " + ", ".join(drops_relacionados[:6])
            if len(drops_relacionados) > 6:
                texto += f" e mais {len(drops_relacionados) - 6}"
        else:
            texto += f"🎁 Drops: {drops or 'a confirmar'}"

        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "⬅️ Voltar aos monstros",
                callback_data=f"atlas_t_{mapa_id}_{codigo_area}"
            )],
            [InlineKeyboardButton(
                "🗺️ Todos os mapas", callback_data="atlas_inicio"
            )]
        ])

        if row_imagem:
            try:
                await editar_pagina_biblioteca(
                    alvo,
                    "desconhecido",
                    texto,
                    teclado,
                    file_id=row_imagem[0],
                    file_unique_id=row_imagem[1],
                )
                return
            except Exception as erro:
                print(f"Erro ao exibir imagem do monstro {monstro_id}: {erro}")

        await editar_pagina_biblioteca(
            alvo, "desconhecido", texto, teclado
        )
    finally:
        cur.close()


async def callback_atlas(update, context):
    query = update.callback_query

    if not membro_cadastrado(query.from_user.id):
        await query.answer(
            "Envie seu perfil no tópico de Presença primeiro.",
            show_alert=True
        )
        return

    await query.answer()

    dados = query.data
    try:
        if dados == "atlas_inicio":
            await mostrar_inicio_atlas(query, editar=True)
        elif dados.startswith("atlas_m_"):
            await mostrar_mapa_atlas(query, int(dados.split("_")[2]), editar=True)
        elif dados.startswith("atlas_t_"):
            _, _, mapa_id, codigo_area = dados.split("_")
            # Compatibilidade com botões da primeira versão do Atlas.
            if codigo_area == "d":
                cur = conn.cursor()
                try:
                    cur.execute(
                        "SELECT nome FROM catalogo_mapas WHERE id=%s",
                        (int(mapa_id),)
                    )
                    mapa = cur.fetchone()
                finally:
                    cur.close()
                if mapa:
                    nome_destino = MASMORRA_DOS_MONSTROS.get(mapa[0])
                    masmorras = masmorras_do_mapa_atlas(mapa[0])
                    if nome_destino in masmorras:
                        codigo_area = f"d{masmorras.index(nome_destino)}"
            await mostrar_monstros_atlas(query, int(mapa_id), codigo_area)
        elif dados.startswith("atlas_x_"):
            _, _, monstro_id, mapa_id, codigo_area = dados.split("_")
            await mostrar_monstro_atlas(
                query, int(monstro_id), int(mapa_id), codigo_area
            )
    except (ValueError, IndexError):
        await editar_atlas_com_texto(
            query,
            "Não consegui abrir essa página do Atlas. Use /mapa novamente.",
        )


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
            SELECT cm.id, cm.nome, mp.nome, cm.tipo, cm.raridade, cm.hp,
                   cm.atk, cm.defesa, cm.xp, cm.gold, cm.drops
            FROM catalogo_monstros cm
            LEFT JOIN catalogo_mapas mp ON mp.id=cm.mapa_id
            ORDER BY cm.ordem, cm.id
        """)
        monstros = cur.fetchall()

        if not numero:
            linhas = ["👹 BESTIÁRIO DO TELETOFUS", ""]

            for indice, monstro in enumerate(monstros, start=1):
                linhas.append(f"{indice}. {monstro[1]} — {monstro[2] or 'mapa a confirmar'}")

            linhas.extend(["", "Consulte os detalhes com /monstro número."])
            await enviar_em_partes(update, "\n".join(linhas))
            return

        if numero > len(monstros):
            await update.message.reply_text(
                f"Monstro inexistente. Escolha um número entre 1 e {len(monstros)}."
            )
            return

        (monstro_id, nome, mapa, tipo, raridade, hp, atk, defesa, xp, gold,
         drops) = monstros[numero - 1]

        cur.execute("""
            SELECT il.nome
            FROM item_drop_relacoes rel
            JOIN itens_legends il ON il.id=rel.item_id
            WHERE rel.monstro_id=%s AND rel.confirmado=TRUE
            ORDER BY il.nome
        """, (monstro_id,))
        drops_relacionados = [row[0] for row in cur.fetchall()]

        linhas = [
            f"👹 MONSTRO {numero} — {nome}",
            "",
            f"🗺️ Mapa: {mapa or 'a confirmar'}   🏷️ Tipo: {tipo or 'a confirmar'}   💠 Raridade: {raridade or 'a confirmar'}",
            f"❤️ HP: {formatar_valor_catalogo(hp)}   ⚔️ ATK: {formatar_valor_catalogo(atk)}   🛡️ DEF: {formatar_valor_catalogo(defesa)}",
            f"⭐ XP: {formatar_valor_catalogo(xp)}   💰 Gold: {formatar_valor_catalogo(gold)}",
        ]

        if drops_relacionados:
            linhas.append(f"🎁 Drops conhecidos: {len(drops_relacionados)}")
            linhas.extend(f"• {item}" for item in drops_relacionados[:8])
            if len(drops_relacionados) > 8:
                linhas.append(f"• e mais {len(drops_relacionados) - 8} item(ns)")
        else:
            linhas.append(f"🎁 Drops: {drops or 'a confirmar'}")

        linhas.extend(["", "📚 Fonte: Wikia oficial"])

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

    if context.args and context.args[0] in {"lib", "biblioteca"}:

        if not await validar_acesso(update, context, "/biblioteca"):
            return

        await mostrar_inicio_unificado(update.message)
        return

    if context.args and context.args[0] == "atlas":

        if not await validar_acesso(update, context, "/mapa"):
            return

        await mostrar_inicio_atlas(update.message)
        return

    if context.args and context.args[0] == "item":

        await enviar_pagina_biblioteca(
            update.message,
            "itens",
            "📚 BIBLIOTECA LEGENDS\n\n"
            "Escolha uma categoria:",
            teclado_inicio_biblioteca()
        )


        return

    await update.message.reply_text(
        "Olá! Use os comandos disponíveis."
    )


async def cmd_biblioteca(update, context):

    if not await validar_acesso(update, context, "/biblioteca"):
        return

    if update.effective_chat.type != "private":
        bot_username = (await context.bot.get_me()).username
        teclado = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📚 Abrir Biblioteca Legends",
                url=f"https://t.me/{bot_username}?start=lib"
            )
        ]])
        await update.message.reply_text(
            "📚 Pilar da Sabedoria:\n\n"
            "Para evitar spam nos tópicos da guilda, a Biblioteca Legends "
            "funciona apenas no privado.\n\n"
            "Clique no botão abaixo para abrir a biblioteca.",
            reply_markup=teclado,
        )
        return

    await mostrar_inicio_unificado(update.message)

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

    await enviar_pagina_biblioteca(
        update.message,
        "itens",
        "📚 BIBLIOTECA LEGENDS\n\n"
        "Escolha uma categoria:",
        teclado_inicio_biblioteca()
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
        ],

        [
            InlineKeyboardButton(
                "⬅ Biblioteca",
                callback_data="lib_inicio"
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


class ConsultaItensComMidia:
    """Adapta as páginas legadas de texto para a capa persistente de Itens."""

    def __init__(self, query):
        self._query = query

    def __getattr__(self, nome):
        return getattr(self._query, nome)

    async def edit_message_text(self, text, reply_markup=None, **kwargs):
        return await editar_pagina_biblioteca(
            self._query, "itens", text, reply_markup
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

        cur.close()

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


    cur.execute("""
        SELECT cm.nome,
               COALESCE(mp.nome, mp_monstro.nome) AS mapa,
               rel.forma_obtencao
        FROM item_drop_relacoes rel
        LEFT JOIN catalogo_monstros cm ON cm.id=rel.monstro_id
        LEFT JOIN catalogo_mapas mp ON mp.id=rel.mapa_id
        LEFT JOIN catalogo_mapas mp_monstro ON mp_monstro.id=cm.mapa_id
        WHERE rel.item_id=%s AND rel.confirmado=TRUE
        ORDER BY mapa NULLS LAST, cm.nome NULLS LAST, rel.forma_obtencao
    """, (item_id,))
    fontes_confirmadas = cur.fetchall()

    if fontes_confirmadas:
        texto += "\n\n🔗 Fontes confirmadas pela guilda\n"
        for monstro, mapa, forma in fontes_confirmadas[:6]:
            partes = []
            if monstro:
                partes.append(f"👹 {monstro}")
            if mapa:
                partes.append(f"🗺️ {mapa}")
            if forma:
                partes.append(f"📍 {forma}")
            texto += f"• {' — '.join(partes)}\n"
        if len(fontes_confirmadas) > 6:
            texto += f"• e mais {len(fontes_confirmadas) - 6} fonte(s)\n"

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

    cur.execute("""
        SELECT telegram_file_id, telegram_file_unique_id
        FROM item_imagens
        WHERE item_id=%s
        ORDER BY atualizado_em DESC
        LIMIT 1
    """, (item_id,))
    imagem_item = cur.fetchone()
    cur.close()

    if imagem_item:
        await editar_pagina_biblioteca(
            query,
            "desconhecido",
            texto,
            teclado,
            file_id=imagem_item[0],
            file_unique_id=imagem_item[1],
        )
    else:
        await editar_pagina_biblioteca(
            query, "desconhecido", texto, teclado
        )

async def callback_biblioteca(update, context):

    query = ConsultaItensComMidia(update.callback_query)

    await query.answer()

    dados = query.data

    if dados == "lib_inicio":
        context.user_data.pop("biblioteca_busca_msg_id", None)
        await mostrar_inicio_unificado(query, editar=True)
        return

    if dados == "lib_atlas":
        context.user_data.pop("biblioteca_busca_msg_id", None)
        await mostrar_inicio_atlas(query, editar=True)
        return

    if dados == "lib_itens":
        context.user_data.pop("biblioteca_busca_msg_id", None)
        await query.edit_message_text(
            "🎒 ITENS DA BIBLIOTECA\n\nEscolha uma categoria:",
            reply_markup=teclado_inicio_biblioteca(),
        )
        return

    if dados == "lib_buscar":
        context.user_data["biblioteca_busca_msg_id"] = query.message.message_id
        await editar_pagina_biblioteca(
            query,
            "biblioteca",
            "🔎 BUSCAR NA BIBLIOTECA\n\n"
            "Envie o nome de um item, mapa ou monstro.",
            InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "⬅ Biblioteca", callback_data="lib_inicio"
                )
            ]]),
        )
        return

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

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(start_market_collector)
        .post_shutdown(stop_market_collector)
        .build()
    )

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
            ["biblioteca", "lib"],
            cmd_biblioteca
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
            callback_revisao_loot,
            pattern=r"^loot_(?:sim|nao)_\d+$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            callback_atlas,
            pattern=r"^atlas_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            callback_biblioteca
        )
    )

    print("3 - Handlers registrados")

    # DETECTOR DE PERFIS, LOOTS E CADASTRO VISUAL DE MONSTROS

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
