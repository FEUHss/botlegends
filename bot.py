import os
# Biblioteca com Criptas separadas do Atlas (implantação 2026-08-26).
import re
import random
import hashlib
import statistics
import psycopg2
import pytz
from datetime import datetime, timedelta
from pathlib import Path
from loot_parser import (
    analisar_texto_loot,
    chave_origem_drop,
    correspondencia_aproximada,
    extrair_mapa_visual,
    extrair_masmorra_visual,
    extrair_monstro_combate,
    extrair_monstro_cripta,
    extrair_monstro_masmorra,
    normalizar,
)
from market_collector import start_market_collector, stop_market_collector
from photo_permissions import can_submit_photo
from catalog_photos import save_header_photo, rift_entrance_name
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
    "almas": BASE_DIR / "assets" / "souls" / "souls-cover.jpg",
    "almas_guerreiro": BASE_DIR / "assets" / "souls" / "warrior-souls.jpg",
    "almas_arqueiro": BASE_DIR / "assets" / "souls" / "archer-souls.jpg",
    "almas_mago": BASE_DIR / "assets" / "souls" / "mage-souls.jpg",
}
BIBLIOTECA_ASSET_URLS = {
    "biblioteca": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/library-cover.jpg",
    "atlas": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/atlas-cover.jpg",
    "itens": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/items-cover.jpg",
    "desconhecido": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/unknown-cover.jpg",
    "almas": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/souls/souls-cover.jpg",
    "almas_guerreiro": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/souls/warrior-souls.jpg",
    "almas_arqueiro": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/souls/archer-souls.jpg",
    "almas_mago": "https://raw.githubusercontent.com/FEUHss/botlegends/main/assets/souls/mage-souls.jpg",
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
        CREATE TABLE IF NOT EXISTS almas_legends (
            id BIGSERIAL PRIMARY KEY,
            nome TEXT UNIQUE NOT NULL,
            classe_base TEXT NOT NULL,
            especializacao TEXT NOT NULL,
            equipamento TEXT NOT NULL,
            recarga_turnos INTEGER,
            efeito TEXT,
            confirmado BOOLEAN NOT NULL DEFAULT FALSE,
            fonte TEXT NOT NULL DEFAULT 'Material da guilda',
            atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS catalogo_masmorras (
            id BIGSERIAL PRIMARY KEY,
            mapa_id BIGINT NOT NULL REFERENCES catalogo_mapas(id),
            ordem INTEGER NOT NULL,
            nome TEXT NOT NULL,
            nome_normalizado TEXT NOT NULL,
            confirmado BOOLEAN NOT NULL DEFAULT TRUE,
            atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapa_id, nome_normalizado),
            UNIQUE (mapa_id, ordem)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS catalogo_criptas (
            numero INTEGER PRIMARY KEY CHECK (numero BETWEEN 1 AND 3),
            nome TEXT UNIQUE NOT NULL,
            mapa_id BIGINT REFERENCES catalogo_mapas(id),
            nivel_minimo INTEGER,
            nivel_maximo INTEGER,
            confirmado BOOLEAN NOT NULL DEFAULT TRUE,
            atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cripta_xp_observacoes (
            id BIGSERIAL PRIMARY KEY,
            cripta_numero INTEGER NOT NULL REFERENCES catalogo_criptas(numero)
                ON DELETE CASCADE,
            andares_concluidos INTEGER NOT NULL CHECK (andares_concluidos >= 0),
            xp_acumulado BIGINT NOT NULL CHECK (xp_acumulado >= 0),
            confirmado BOOLEAN NOT NULL DEFAULT TRUE,
            fonte TEXT,
            observado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (cripta_numero, andares_concluidos)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS site_acessos (
            telegram_id BIGINT PRIMARY KEY,
            papel TEXT NOT NULL DEFAULT 'consulta'
                CHECK (papel IN ('consulta', 'editor', 'admin')),
            permitido BOOLEAN NOT NULL DEFAULT TRUE,
            ultimo_acesso TIMESTAMPTZ,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS site_login_codigos (
            codigo TEXT PRIMARY KEY,
            telegram_id BIGINT,
            proximo_caminho TEXT,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expira_em TIMESTAMPTZ NOT NULL,
            confirmado_em TIMESTAMPTZ,
            consumido_em TIMESTAMPTZ
        )
        """,
        """
        ALTER TABLE site_acessos
        ADD COLUMN IF NOT EXISTS pode_enviar_fotos BOOLEAN NOT NULL DEFAULT FALSE
        """,
        """
        CREATE TABLE IF NOT EXISTS masmorra_aliases (
            id BIGSERIAL PRIMARY KEY,
            masmorra_id BIGINT NOT NULL REFERENCES catalogo_masmorras(id)
                ON DELETE CASCADE,
            alias TEXT NOT NULL,
            alias_normalizado TEXT NOT NULL UNIQUE,
            criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS catalogo_monstros (
            id BIGSERIAL PRIMARY KEY,
            ordem INTEGER NOT NULL,
            nome TEXT NOT NULL,
            mapa_id BIGINT REFERENCES catalogo_mapas(id),
            tipo TEXT DEFAULT 'Monstro',
            masmorra_id BIGINT REFERENCES catalogo_masmorras(id),
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
            masmorra_id BIGINT REFERENCES catalogo_masmorras(id),
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
            masmorra_id BIGINT REFERENCES catalogo_masmorras(id),
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
        """,
        """
        CREATE TABLE IF NOT EXISTS catalogo_estado (
            chave TEXT PRIMARY KEY,
            inicializado BOOLEAN NOT NULL DEFAULT FALSE,
            atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """
    ]

    cur = conn.cursor()
    try:
        for ddl in tabelas:
            cur.execute(ddl)

        def estado_inicial_catalogo(chave, tabela):
            """Registra uma vez se uma área já existia antes desta versão."""
            cur.execute(f"SELECT EXISTS (SELECT 1 FROM {tabela} LIMIT 1)")
            ja_possuia_dados = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO catalogo_estado (chave, inicializado)
                VALUES (%s, %s)
                ON CONFLICT (chave) DO NOTHING
            """, (chave, ja_possuia_dados))
            cur.execute(
                "SELECT inicializado FROM catalogo_estado WHERE chave=%s",
                (chave,),
            )
            return cur.fetchone()[0]

        def concluir_carga_inicial(chave):
            cur.execute("""
                UPDATE catalogo_estado
                SET inicializado=TRUE, atualizado_em=CURRENT_TIMESTAMP
                WHERE chave=%s
            """, (chave,))

        mapas_ja_inicializados = estado_inicial_catalogo(
            "mapas_e_masmorras_v1", "catalogo_mapas"
        )
        monstros_ja_inicializados = estado_inicial_catalogo(
            "monstros_v1", "catalogo_monstros"
        )
        itens_ja_inicializados = estado_inicial_catalogo(
            "itens_v1", "itens_legends"
        )
        estado_inicial_catalogo("almas_v1", "almas_legends")
        cur.execute("""
            SELECT inicializado FROM catalogo_estado
            WHERE chave='capacidades_masmorras_v1'
        """)
        estado_capacidades = cur.fetchone()
        capacidades_masmorras_ja_inicializadas = bool(
            estado_capacidades and estado_capacidades[0]
        )
        if estado_capacidades is None:
            cur.execute("""
                INSERT INTO catalogo_estado (chave, inicializado)
                VALUES ('capacidades_masmorras_v1', FALSE)
            """)
        cur.execute("""
            ALTER TABLE almas_legends
            ADD COLUMN IF NOT EXISTS obtencao TEXT
        """)
        cur.execute("""
            ALTER TABLE catalogo_masmorras
            ADD COLUMN IF NOT EXISTS minimo_jogadores INTEGER,
            ADD COLUMN IF NOT EXISTS maximo_jogadores INTEGER,
            ADD COLUMN IF NOT EXISTS xp_por_equipe JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS tipo_sistema TEXT NOT NULL DEFAULT 'masmorra',
            ADD COLUMN IF NOT EXISTS requisitos_texto TEXT,
            ADD COLUMN IF NOT EXISTS observacoes TEXT
        """)
        cur.execute("""
            ALTER TABLE catalogo_monstros
            ADD COLUMN IF NOT EXISTS masmorra_nome TEXT
        """)
        cur.execute("""
            ALTER TABLE catalogo_monstros
            ADD COLUMN IF NOT EXISTS masmorra_id BIGINT
                REFERENCES catalogo_masmorras(id)
        """)
        cur.execute("""
            ALTER TABLE catalogo_monstros
            ADD COLUMN IF NOT EXISTS cripta_numero INTEGER,
            ADD COLUMN IF NOT EXISTS habilidade TEXT,
            ADD COLUMN IF NOT EXISTS sem_habilidade BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS risco TEXT
        """)
        cur.execute("""
            INSERT INTO catalogo_criptas
                (numero, nome, mapa_id, nivel_minimo, nivel_maximo)
            SELECT dados.numero, dados.nome, mp.id,
                   dados.nivel_minimo, dados.nivel_maximo
            FROM (VALUES
                (1, 'Cripta 1', 22, 27),
                (2, 'Cripta 2', NULL::INTEGER, NULL::INTEGER),
                (3, 'Cripta 3', NULL::INTEGER, NULL::INTEGER)
            ) AS dados(numero, nome, nivel_minimo, nivel_maximo)
            LEFT JOIN catalogo_mapas mp ON mp.nome='Cemitério Antigo'
            ON CONFLICT (numero) DO UPDATE SET
                nome=EXCLUDED.nome,
                mapa_id=COALESCE(catalogo_criptas.mapa_id, EXCLUDED.mapa_id),
                nivel_minimo=COALESCE(catalogo_criptas.nivel_minimo, EXCLUDED.nivel_minimo),
                nivel_maximo=COALESCE(catalogo_criptas.nivel_maximo, EXCLUDED.nivel_maximo),
                atualizado_em=CURRENT_TIMESTAMP
        """)
        cur.executemany("""
            INSERT INTO cripta_xp_observacoes
                (cripta_numero, andares_concluidos, xp_acumulado,
                 confirmado, fonte)
            VALUES (2, %s, %s, TRUE, 'Sequência observada pela guilda')
            ON CONFLICT (cripta_numero, andares_concluidos) DO NOTHING
        """, [
            (8, 14123), (9, 16743), (10, 19547),
            (11, 22548), (12, 25758), (13, 29193),
            (14, 32869), (15, 36802), (16, 41011),
        ])
        # Migração idempotente: reaproveita os sete registros já vinculados à
        # antiga "Cripta II" sem mudar id, ordem, imagem ou relacionamentos.
        cur.execute("""
            UPDATE catalogo_monstros cm
            SET tipo='Cripta', cripta_numero=2,
                masmorra_id=NULL, masmorra_nome=NULL,
                xp=NULL, gold=NULL,
                atualizado_em=CURRENT_TIMESTAMP
            FROM catalogo_masmorras d
            WHERE cm.masmorra_id=d.id
              AND d.tipo_sistema='cripta'
              AND cm.cripta_numero IS NULL
        """)
        cur.execute("""
            ALTER TABLE masmorra_imagens
            ADD COLUMN IF NOT EXISTS masmorra_id BIGINT
                REFERENCES catalogo_masmorras(id)
        """)
        cur.execute("""
            ALTER TABLE masmorra_monstro_observacoes
            ADD COLUMN IF NOT EXISTS masmorra_id BIGINT
                REFERENCES catalogo_masmorras(id)
        """)
        # Cópia única e recuperável do estado anterior à migração. O nome fixo
        # torna esta proteção idempotente: reinícios futuros não sobrescrevem
        # o retrato original que recebemos do banco em produção.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS
                backup_masmorra_20260822_catalogo_monstros
            AS TABLE catalogo_monstros
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS
                backup_masmorra_20260822_imagens
            AS TABLE masmorra_imagens
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS
                backup_masmorra_20260822_observacoes
            AS TABLE masmorra_monstro_observacoes
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
            ON catalogo_monstros (mapa_id, tipo, masmorra_id)
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
        if not mapas_ja_inicializados:
            cur.executemany("""
                INSERT INTO catalogo_mapas
                    (ordem, nome, nivel_minimo, dificuldade, tempo_masmorra,
                     xp_masmorra_4, xp_masmorra_5, descricao, fonte, confirmado)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (nome) DO NOTHING
            """, mapas_iniciais)

        masmorras_iniciais = [
            (mapa, ordem, nome)
            for mapa, nomes in MASMORRAS_POR_MAPA.items()
            for ordem, nome in enumerate(nomes, start=1)
        ]
        if not mapas_ja_inicializados:
            cur.executemany("""
                INSERT INTO catalogo_masmorras
                    (mapa_id, ordem, nome, nome_normalizado, confirmado)
                SELECT id, %s, %s, %s, TRUE
                FROM catalogo_mapas
                WHERE nome=%s
                ON CONFLICT DO NOTHING
            """, [
                (ordem, nome, normalizar(nome), mapa)
                for mapa, ordem, nome in masmorras_iniciais
            ])
            cur.execute("""
                INSERT INTO masmorra_aliases
                    (masmorra_id, alias, alias_normalizado)
                SELECT id, nome, nome_normalizado
                FROM catalogo_masmorras
                ON CONFLICT (alias_normalizado) DO NOTHING
            """)
            concluir_carga_inicial("mapas_e_masmorras_v1")

        if not capacidades_masmorras_ja_inicializadas:
            configuracoes_masmorras = [
                (1, 5, "masmorra", None, None, "Planície", "Masmorra da Planície"),
                (1, 5, "masmorra", "Pele de Orc (F) ou (M).", None, "Planície", "Covil de Zul'gor"),
                (1, 5, "masmorra", None, None, "Floresta Sombria", "Masmorra da Floresta"),
                (1, 5, "masmorra", "Culpa de Altheryn (F) ou (M).", None, "Floresta Sombria", "Santuário de Altheryn"),
                (1, 5, "masmorra", None, None, "Pântano", "Masmorra do Pântano"),
                (1, 5, "masmorra", "Hydra Slayer (Guerreiro), (Mago) ou (Arqueiro).", None, "Pântano", "Covil da Hydra Maior"),
                (1, 5, "masmorra", "Uma skin Hydra Slayer e uma skin Cavaleiro das Sombras, nas versões Guerreiro, Mago ou Arqueiro, juntas no mesmo time.", None, "Pântano", "Covil da Hydra de Ossos"),
                (1, 5, "masmorra", "Chave especial: Chave do Ossuário.", None, "Cemitério Antigo", "Covil do Lord"),
                (None, None, "cripta", None, "Sistema especial de criptas infinitas; será modelado separadamente.", "Cemitério Antigo", "Cripta II"),
                (1, 5, "masmorra", None, None, "Deserto Escaldante", "Pirâmide do Deserto"),
                (1, 1, "masmorra", None, None, "Oásis Perdido", "Fenda Solar"),
                (2, 2, "masmorra", None, None, "Oásis Perdido", "Templo do Oásis"),
                (1, 5, "masmorra", None, None, "Montanhas Gélidas", "Ruínas de Azulgor"),
                (1, 5, "masmorra", None, None, "Montanhas Gélidas", "Lago de Kryos"),
                (1, 5, "masmorra", None, None, "Montanhas Gélidas", "Túneis Proibidos"),
                (1, 5, "masmorra", None, None, "Fortaleza dos Orcs", "Fosso de Provas"),
                (1, 5, "masmorra", None, None, "Fortaleza dos Orcs", "Trono de Khar'gath"),
            ]
            cur.executemany("""
                UPDATE catalogo_masmorras d
                SET minimo_jogadores=%s,
                    maximo_jogadores=%s,
                    tipo_sistema=%s,
                    requisitos_texto=%s,
                    observacoes=%s,
                    atualizado_em=CURRENT_TIMESTAMP
                FROM catalogo_mapas mp
                WHERE d.mapa_id=mp.id AND mp.nome=%s AND d.nome=%s
            """, configuracoes_masmorras)
            concluir_carga_inicial("capacidades_masmorras_v1")

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
            (67, "Demônio Menor", "Abismo", "Caçada", "Raro", 380, 68, 20, 380, 280, None, "Wikia oficial", False),
            (68, "Cavaleiro Sombrio", "Abismo", "Caçada", "Raro", 420, 72, 22, 420, 300, None, "Wikia oficial", False),
            (69, "Cultista", "Abismo", "Caçada", "Raro", 390, 70, 21, 410, 290, None, "Wikia oficial", False),
            (70, "Cão do Inferno", "Abismo", "Caçada", "Raro", 400, 75, 21, 440, 310, None, "Wikia oficial", False),
            (71, "Cria do Vazio", "Abismo", "Caçada", "Raro", 430, 78, 23, 460, 330, None, "Wikia oficial", False),
            (72, "Lorde do Abismo", "Abismo", "Caçada", "Boss", 650, 95, 28, 620, 480, None, "Wikia oficial", False),
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
              AND NOT %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM catalogo_monstros AS existente
                  WHERE existente.mapa_id = cm.mapa_id
                    AND existente.tipo = cm.tipo
                    AND existente.nome = 'Orc Warmarshal'
              )
        """, (monstros_ja_inicializados,))
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
              AND NOT %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM catalogo_monstros AS existente
                  WHERE existente.mapa_id = cm.mapa_id
                    AND existente.tipo = cm.tipo
                    AND existente.nome = 'Orc Wolf Rider'
              )
        """, (monstros_ja_inicializados,))
        # Estes registros são apenas a carga inicial de um banco novo. Em um
        # catálogo já administrado, reinseri-los a cada reinício ressuscitava
        # monstros excluídos corretamente pelo painel.
        if not monstros_ja_inicializados:
            cur.executemany("""
                INSERT INTO catalogo_monstros
                    (ordem, nome, mapa_id, tipo, raridade, hp, atk, defesa,
                     xp, gold, drops, fonte, confirmado)
                SELECT %s, %s, id, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                FROM catalogo_mapas
                WHERE nome = %s
                ON CONFLICT DO NOTHING
            """, [
                (ordem, nome, tipo, raridade, hp, atk, defesa, xp, gold,
                 drops, fonte, confirmado, mapa)
                for ordem, nome, mapa, tipo, raridade, hp, atk, defesa,
                    xp, gold, drops, fonte, confirmado in monstros_iniciais
            ])
            concluir_carga_inicial("monstros_v1")

        # Nas masmorras comuns, XP pertence ao resumo da atividade.
        # Fendas preservam XP/Gold dos monstros para somar a recompensa.
        cur.execute("""
            UPDATE catalogo_monstros AS cm
            SET xp=NULL, gold=NULL, atualizado_em=CURRENT_TIMESTAMP
            WHERE LOWER(tipo)=LOWER('Masmorra')
              AND (xp IS NOT NULL OR gold IS NOT NULL)
              AND NOT EXISTS (
                  SELECT 1 FROM catalogo_masmorras d
                  WHERE d.id=cm.masmorra_id AND d.tipo_sistema='fenda'
              )
        """)

        # Vincula o catálogo legado às masmorras canônicas sem apagar imagens
        # ou observações. Nomes recebidos com caixa/acentuação diferentes são
        # normalizados antes da associação.
        if not monstros_ja_inicializados:
            cur.execute("""
                SELECT d.id, d.mapa_id, d.nome, d.nome_normalizado, mp.nome
                FROM catalogo_masmorras d
                JOIN catalogo_mapas mp ON mp.id=d.mapa_id
                ORDER BY d.mapa_id, d.ordem, d.id
            """)
            masmorras_catalogo = cur.fetchall()
        else:
            masmorras_catalogo = []
        por_mapa = {}
        for dungeon_id, mapa_id, nome, nome_normalizado, mapa_nome in masmorras_catalogo:
            por_mapa.setdefault(mapa_id, []).append(
                (dungeon_id, nome, nome_normalizado, mapa_nome)
            )

        def masmorra_backfill(mapa_id, nome_recebido, mapa_nome):
            candidatos = por_mapa.get(mapa_id, [])
            procurado = normalizar(nome_recebido or "")
            if procurado:
                exatos = [row for row in candidatos if row[2] == procurado]
                if len(exatos) == 1:
                    return exatos[0]
            nome_padrao = MASMORRA_DOS_MONSTROS.get(mapa_nome)
            if not procurado and nome_padrao:
                padrao = normalizar(nome_padrao)
                exatos = [row for row in candidatos if row[2] == padrao]
                if len(exatos) == 1:
                    return exatos[0]
            if procurado:
                return correspondencia_aproximada(
                    nome_recebido,
                    [(row, [row[1]]) for row in candidatos],
                )
            return None

        if not monstros_ja_inicializados:
            cur.execute("""
                SELECT cm.id, cm.mapa_id, cm.masmorra_nome, mp.nome
                FROM catalogo_monstros cm
                JOIN catalogo_mapas mp ON mp.id=cm.mapa_id
                WHERE LOWER(cm.tipo)=LOWER('Masmorra')
            """)
            monstros_para_backfill = cur.fetchall()
        else:
            monstros_para_backfill = []
        for monstro_id, mapa_id, nome_recebido, mapa_nome in monstros_para_backfill:
            masmorra = masmorra_backfill(
                mapa_id, nome_recebido, mapa_nome
            )
            if masmorra:
                cur.execute("""
                    UPDATE catalogo_monstros
                    SET masmorra_id=%s, masmorra_nome=%s,
                        atualizado_em=CURRENT_TIMESTAMP
                    WHERE id=%s
                """, (masmorra[0], masmorra[1], monstro_id))

        for tabela, coluna_nome in (
            ("masmorra_imagens", "nome_masmorra"),
            ("masmorra_monstro_observacoes", "masmorra"),
        ):
            if not monstros_ja_inicializados:
                cur.execute(f"""
                    SELECT registro.id, registro.mapa_id,
                           registro.{coluna_nome}, mp.nome
                    FROM {tabela} registro
                    JOIN catalogo_mapas mp ON mp.id=registro.mapa_id
                    WHERE registro.masmorra_id IS NULL
                """)
                registros_para_backfill = cur.fetchall()
            else:
                registros_para_backfill = []
            for registro_id, mapa_id, nome_recebido, mapa_nome in registros_para_backfill:
                masmorra = masmorra_backfill(
                    mapa_id, nome_recebido, mapa_nome
                )
                if masmorra:
                    cur.execute(f"""
                        UPDATE {tabela}
                        SET masmorra_id=%s, {coluna_nome}=%s
                        WHERE id=%s
                    """, (masmorra[0], masmorra[1], registro_id))

        # "ordem" é o número público mostrado no Atlas. Corrige apenas as
        # repetições, preservando o primeiro registro e enviando os demais ao
        # fim da sequência. O ID primário já é protegido pelo PostgreSQL.
        cur.execute("""
            WITH marcados AS (
                SELECT id, ordem,
                       ROW_NUMBER() OVER (PARTITION BY ordem ORDER BY id) AS repeticao
                FROM catalogo_monstros
            ), corrigir AS (
                SELECT id,
                       ROW_NUMBER() OVER (ORDER BY ordem, id) AS deslocamento
                FROM marcados
                WHERE repeticao > 1
            ), limite AS (
                SELECT COALESCE(MAX(ordem), 0) AS maior
                FROM catalogo_monstros
            )
            UPDATE catalogo_monstros cm
            SET ordem=limite.maior+corrigir.deslocamento,
                atualizado_em=CURRENT_TIMESTAMP
            FROM corrigir, limite
            WHERE cm.id=corrigir.id AND NOT %s
        """, (monstros_ja_inicializados,))
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_catalogo_monstros_ordem
            ON catalogo_monstros (ordem)
        """)
        cur.execute("""
            SELECT setval(
                pg_get_serial_sequence('catalogo_monstros', 'id'),
                GREATEST(COALESCE((SELECT MAX(id) FROM catalogo_monstros), 1), 1),
                TRUE
            )
        """)

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
        itens_para_carga = (
            [] if itens_ja_inicializados else itens_anuncio_ghurak
        )
        for item in itens_para_carga:
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
        if not itens_ja_inicializados:
            concluir_carga_inicial("itens_v1")

        # Corrige a grafia provisória sem criar uma segunda alma nem trocar seu ID.
        cur.execute("""
            UPDATE almas_legends
            SET nome='Bênção do Clã', atualizado_em=CURRENT_TIMESTAMP
            WHERE nome='Benção do Clã'
              AND NOT EXISTS (
                  SELECT 1 FROM almas_legends WHERE nome='Bênção do Clã'
              )
        """)

        catalogo_almas = [
            ("Fúria do Lobo", "Guerreiro", "Berserker", "Machado", 3,
             "Golpe 1,6× e recebe +30% de ataque por 2 turnos.", True),
            ("Golpe Sombrio", "Guerreiro", "Berserker", "Machado", 4,
             "Golpe 1,7× e recupera vida igual a 20% do dano causado.", True),
            ("Fúria do Titã", "Guerreiro", "Berserker", "Machado", 9,
             "Golpe que causa 2,0× de dano.", True),
            ("Fúria de Khar'Gath", "Guerreiro", "Berserker", "Machado", 7,
             "Golpe 2,2×. Contra alvos com menos de 30% de HP, causa 30% de dano adicional.", True),
            ("Rugido do Rochedo", "Guerreiro", "Tank", "Espada e Escudo", 4,
             "Reduz 50% do dano recebido por 2 turnos e provoca o alvo.", True),
            ("Escudo de Ossos", "Guerreiro", "Tank", "Espada e Escudo", 5,
             "Recupera 50% do HP máximo. No PvP, recupera 25%.", True),
            ("Golpe do Obelisco", "Guerreiro", "Tank", "Espada e Escudo", 6,
             "Golpe 1,4× com dano adicional igual a 50% da defesa total.", True),
            ("Muralha Orc", "Guerreiro", "Tank", "Espada e Escudo", 6,
             "Provoca por 2 turnos, recebe 40% menos dano por 2 turnos e recupera 15% do HP máximo.", True),
            ("Picada da Aranha", "Arqueiro", "Caçador", "Arco", 4,
             "Golpe 1,3× e aplica veneno equivalente a 20% do ataque por turno durante 2 turnos.", True),
            ("Precisão Élfica", "Arqueiro", "Caçador", "Arco", 6,
             "Golpe 1,7× com +20% de chance de crítico neste disparo.", True),
            ("Flecha do Djinn", "Arqueiro", "Caçador", "Arco", 6,
             "Golpe 1,8× que ignora 30% da defesa do alvo.", True),
            ("Presa do Rastreador", "Arqueiro", "Caçador", "Arco", 5,
             "Golpe 1,4× e aplica veneno pesado equivalente a 30% do seu ataque por turno durante 3 turnos.", True),
            ("Lança dos Ventos", "Arqueiro", "Lanceiro", "Lança", 3,
             "Golpe 1,5× e recupera 20% do HP máximo.", True),
            ("Lança do Guardião", "Arqueiro", "Lanceiro", "Lança", 4,
             "Reduz 20% do dano recebido por 2 turnos e provoca o alvo.", True),
            ("Lança Solar", "Arqueiro", "Lanceiro", "Lança", 6,
             "Golpe 1,5× com dano adicional igual a 5% do seu HP máximo.", True),
            ("Lança Xamânica", "Arqueiro", "Lanceiro", "Lança", 5,
             "Golpe 1,4× e recupera 15% do HP máximo de toda a equipe.", True),
            ("Maldição da Bruxa", "Mago", "Cajado", "Cajado", 4,
             "Golpe 1,4× e aplica maldição equivalente a 65% do ataque por turno durante 2 turnos.", True),
            ("Poder do Lich", "Mago", "Cajado", "Cajado", 5,
             "Golpe 1,7× e recebe +25% de ataque por 3 turnos.", True),
            ("Tempestade de Areia", "Mago", "Cajado", "Cajado", 6,
             "O próximo golpe causa 2,0× de dano.", True),
            ("Chama de Guerra", "Mago", "Cajado", "Cajado", 5,
             "Golpe 1,5× que reduz em 30% a defesa do alvo por 2 turnos.", True),
            ("Escudo Arcano", "Mago", "Suporte", "Varinha", 4,
             "Toda a equipe recebe 50% menos dano por 3 turnos.", True),
            ("Vontade do Lich", "Mago", "Suporte", "Varinha", 5,
             "Toda a equipe recupera 35% do HP máximo. No PvP, recupera 20%.", True),
            ("Orbe Solar", "Mago", "Suporte", "Varinha", 5,
             "Golpe 1,4× e concede +15% de ataque para toda a equipe por 2 turnos.", True),
            ("Bênção do Clã", "Mago", "Suporte", "Varinha", 6,
             "Recupera 25% do HP máximo da equipe e concede +10% de ataque por 2 turnos.", True),
        ]
        cur.executemany("""
            INSERT INTO almas_legends (
                nome, classe_base, especializacao, equipamento,
                recarga_turnos, efeito, confirmado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (nome) DO UPDATE SET
                classe_base=EXCLUDED.classe_base,
                especializacao=EXCLUDED.especializacao,
                equipamento=EXCLUDED.equipamento,
                recarga_turnos=EXCLUDED.recarga_turnos,
                efeito=EXCLUDED.efeito,
                confirmado=EXCLUDED.confirmado,
                fonte='Guia de habilidades do Teletofus',
                atualizado_em=CURRENT_TIMESTAMP
        """, catalogo_almas)
        cur.execute("""
            UPDATE almas_legends
            SET fonte='Guia de habilidades do Teletofus'
            WHERE nome = ANY(%s)
        """, ([alma[0] for alma in catalogo_almas],))
        concluir_carga_inicial("almas_v1")
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
            INSERT INTO membro_administracao
                (telegram_id, ativo, telegram_username, classe, atualizado_em)
            VALUES (%s, TRUE, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (telegram_id) DO UPDATE SET
                telegram_username=COALESCE(EXCLUDED.telegram_username,
                                           membro_administracao.telegram_username),
                classe=COALESCE(EXCLUDED.classe, membro_administracao.classe),
                atualizado_em=CURRENT_TIMESTAMP
        """, (tg_id, telegram_username, classe))

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
        """SELECT m.nome
           FROM membros m
           LEFT JOIN membro_administracao ma ON ma.telegram_id=m.telegram_id
           WHERE m.telegram_id=%s AND COALESCE(ma.ativo, TRUE)""",
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
    try:
        cur.execute(
            """
            SELECT 1
            FROM membros m
            LEFT JOIN membro_administracao ma ON ma.telegram_id=m.telegram_id
            WHERE m.telegram_id=%s
              AND COALESCE(ma.ativo, TRUE)
            """,
            (tg_id,)
        )
        return cur.fetchone() is not None
    finally:
        cur.close()

def membro_inativo(tg_id):
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 1 FROM membro_administracao
            WHERE telegram_id=%s AND NOT ativo
        """, (tg_id,))
        return cur.fetchone() is not None
    finally:
        cur.close()

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

    cur.execute("""
        SELECT m.nome
        FROM membros m
        LEFT JOIN membro_administracao ma ON ma.telegram_id=m.telegram_id
        WHERE COALESCE(ma.ativo, TRUE)
        ORDER BY m.nome
    """)
    membros = [x[0] for x in cur.fetchall()]

    cur.execute("""
        SELECT p.nome
        FROM presencas p
        JOIN membros m ON m.telegram_id=p.telegram_id
        LEFT JOIN membro_administracao ma ON ma.telegram_id=m.telegram_id
        WHERE p.data=%s AND COALESCE(ma.ativo, TRUE)
        ORDER BY p.nome
    """,(hoje(),))
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
    SELECT latest.nome, latest.nivel, latest.xp
    FROM (
        SELECT DISTINCT ON (telegram_id) telegram_id, nome, nivel, xp
        FROM xp_logs
        ORDER BY telegram_id,data_hora DESC
    ) latest
    JOIN membros m ON m.telegram_id=latest.telegram_id
    LEFT JOIN membro_administracao ma ON ma.telegram_id=m.telegram_id
    WHERE COALESCE(ma.ativo, TRUE)
    """)
    d = sorted(cur.fetchall(), key=lambda x: x[2], reverse=True)
    txt = "🏆 RANKING XP\n\n"
    for i,(n,l,xp) in enumerate(d,1):
        txt += f"{i}. {n} — Lv {l} - {xp}\n"
    return txt

def ranking_status(campo, titulo):
    cur = conn.cursor()

    cur.execute(f"""

        SELECT latest.nome, latest.valor
        FROM (
            SELECT DISTINCT ON (telegram_id)
                   telegram_id, nome, {campo} AS valor
            FROM status
            WHERE {campo} IS NOT NULL
            ORDER BY telegram_id, data_hora DESC
        ) latest
        JOIN membros m ON m.telegram_id=latest.telegram_id
        LEFT JOIN membro_administracao ma ON ma.telegram_id=m.telegram_id
        WHERE COALESCE(ma.ativo, TRUE)
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
        SELECT x.telegram_id, x.nome, x.xp, x.data_hora
        FROM xp_logs x
        JOIN membros m ON m.telegram_id=x.telegram_id
        LEFT JOIN membro_administracao ma ON ma.telegram_id=m.telegram_id
        WHERE COALESCE(ma.ativo, TRUE)
        ORDER BY x.telegram_id, x.data_hora ASC
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

def mensagem_encaminhada_pelo_teletofus(msg):
    origem = getattr(msg, "forward_origin", None)
    usuario_origem = getattr(origem, "sender_user", None)
    if usuario_origem:
        return usuario_origem.id == TELETOFUS_BOT_ID

    # Compatibilidade com versões anteriores da API do Telegram.
    usuario_origem = getattr(msg, "forward_from", None)
    return bool(usuario_origem and usuario_origem.id == TELETOFUS_BOT_ID)


def chave_relacao_drop(item_id, monstro_id, mapa_id, forma_obtencao):
    return chave_origem_drop(
        item_id,
        monstro_id=monstro_id,
        mapa_id=mapa_id,
        forma=forma_obtencao,
    )


def resolver_monstro_catalogo(cur, nome_detectado, mapa_id=None, tipo=None):
    if not nome_detectado:
        return None

    nome_normalizado = normalizar(nome_detectado)
    cur.execute("""
        SELECT cm.id, cm.nome, cm.mapa_id
        FROM catalogo_monstros cm
        WHERE (%s IS NULL OR LOWER(cm.tipo)=LOWER(%s))
        ORDER BY cm.ordem, cm.id
    """, (tipo, tipo))
    candidatos = [
        row for row in cur.fetchall()
        if normalizar(row[1]) == nome_normalizado
    ]

    if not candidatos:
        cur.execute("""
            SELECT cm.id, cm.nome, cm.mapa_id
            FROM monstro_aliases alias
            JOIN catalogo_monstros cm ON cm.id=alias.monstro_id
            WHERE alias.alias_normalizado=%s
              AND (%s IS NULL OR LOWER(cm.tipo)=LOWER(%s))
        """, (nome_normalizado, tipo, tipo))
        candidatos = cur.fetchall()

    if mapa_id:
        candidatos_mapa = [row for row in candidatos if row[2] == mapa_id]
        if len(candidatos_mapa) == 1:
            return candidatos_mapa[0]

    if len(candidatos) == 1:
        return candidatos[0]
    return None


def resolver_monstro_por_imagem(cur, msg):
    if not msg.photo:
        return None
    file_unique_id = msg.photo[-1].file_unique_id
    cur.execute("""
        SELECT cm.id, cm.nome, cm.mapa_id
        FROM monstro_imagens imagem
        JOIN catalogo_monstros cm ON cm.id=imagem.monstro_id
        WHERE imagem.telegram_file_unique_id=%s
        ORDER BY imagem.atualizado_em DESC
        LIMIT 1
    """, (file_unique_id,))
    return cur.fetchone()


def resolver_monstro_masmorra_catalogo(
    cur, nome_detectado, mapa_id, masmorra_id
):
    """Localiza um monstro já cadastrado e vinculado à masmorra."""
    procurado = normalizar(nome_detectado)
    cur.execute("""
        SELECT cm.id, cm.nome, cm.mapa_id,
               COALESCE(array_agg(a.alias_normalizado)
                        FILTER (WHERE a.alias_normalizado IS NOT NULL), '{}')
        FROM catalogo_monstros cm
        LEFT JOIN monstro_aliases a ON a.monstro_id=cm.id
        WHERE cm.mapa_id=%s
          AND cm.masmorra_id=%s
          AND LOWER(cm.tipo)=LOWER('Masmorra')
        GROUP BY cm.id, cm.nome, cm.mapa_id, cm.ordem
        ORDER BY cm.ordem, cm.id
    """, (mapa_id, masmorra_id))
    registros = cur.fetchall()
    exatos = [
        row for row in registros
        if procurado == normalizar(row[1]) or procurado in row[3]
    ]
    if len(exatos) == 1:
        return exatos[0][:3]

    aproximado = correspondencia_aproximada(
        nome_detectado,
        [(row, [row[1], *row[3]]) for row in registros],
    )
    return aproximado[:3] if aproximado else None


def candidatos_monstro_semelhante(cur, nome_detectado, tipo=None):
    procurado = normalizar(nome_detectado)
    cur.execute("""
        SELECT id, nome, mapa_id
        FROM catalogo_monstros
        WHERE (%s IS NULL OR LOWER(tipo)=LOWER(%s))
        ORDER BY ordem, id
    """, (tipo, tipo))
    return [
        row for row in cur.fetchall()
        if normalizar(row[1]) in procurado or procurado in normalizar(row[1])
    ]


def resolver_masmorra_catalogo(cur, nome_detectado, mapa_id=None):
    """Resolve caixa, acentos, aliases e pequenas variações sem criar dados."""
    procurado = normalizar(nome_detectado)
    if not procurado:
        return None

    cur.execute("""
        SELECT d.id, d.mapa_id, mp.nome, d.nome, d.nome_normalizado,
               COALESCE(array_agg(a.alias_normalizado)
                        FILTER (WHERE a.alias_normalizado IS NOT NULL), '{}')
        FROM catalogo_masmorras d
        JOIN catalogo_mapas mp ON mp.id=d.mapa_id
        LEFT JOIN masmorra_aliases a ON a.masmorra_id=d.id
        WHERE (%s IS NULL OR d.mapa_id=%s)
        GROUP BY d.id, d.mapa_id, mp.nome, mp.ordem, d.nome,
                 d.nome_normalizado, d.ordem
        ORDER BY mp.ordem, d.ordem, d.id
    """, (mapa_id, mapa_id))
    registros = cur.fetchall()

    exatos = [
        row for row in registros
        if procurado == row[4] or procurado in row[5]
    ]
    if len(exatos) == 1:
        row = exatos[0]
        return row[0], row[1], row[2], row[3]

    row = correspondencia_aproximada(
        nome_detectado,
        [(row, [row[4], *row[5]]) for row in registros],
    )
    if not row:
        return None
    return row[0], row[1], row[2], row[3]


def resolver_mapa_da_masmorra(cur, nome_masmorra):
    return resolver_masmorra_catalogo(cur, nome_masmorra)


def resolver_mapa_catalogo(cur, nome_detectado):
    cur.execute("SELECT id, nome FROM catalogo_mapas ORDER BY ordem, id")
    candidatos = [
        row for row in cur.fetchall()
        if normalizar(row[1]) == normalizar(nome_detectado)
    ]
    return candidatos[0] if len(candidatos) == 1 else None


def resolver_masmorra_conhecida(cur, nome_detectado, nome_mapa=None):
    mapa_id = None
    if nome_mapa:
        mapa = resolver_mapa_catalogo(cur, nome_mapa)
        if not mapa:
            return None
        mapa_id = mapa[0]
    return resolver_masmorra_catalogo(cur, nome_detectado, mapa_id)


async def processar_imagem_mapa_ou_masmorra(msg):
    if (
        msg.chat.type != "private"
        or not msg.from_user
        or not mensagem_encaminhada_pelo_teletofus(msg)
        or not msg.photo
        or not can_submit_photo(conn, msg.from_user.id, LOOT_REVIEWER_ID)
    ):
        return False

    texto = msg.caption or msg.text or ""
    dados_masmorra = extrair_masmorra_visual(texto)
    nome_fenda = rift_entrance_name(texto)
    if nome_fenda:
        dados_masmorra = {"nome": nome_fenda, "mapa": "Abismo"}
    dados_mapa = extrair_mapa_visual(texto) if not dados_masmorra else None
    if not dados_masmorra and not dados_mapa:
        return False

    cur = conn.cursor()
    try:
        foto = msg.photo[-1]
        if dados_mapa:
            mapa = resolver_mapa_catalogo(cur, dados_mapa["nome"])
            if not mapa:
                await msg.reply_text(
                    "⚠️ Não encontrei esse mapa no Atlas. A imagem não foi salva."
                )
                return True

            mapa_id, nome_mapa = mapa
            cur.execute("""
                INSERT INTO mapa_imagens
                    (mapa_id, telegram_file_id, telegram_file_unique_id,
                     nome_detectado)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (telegram_file_unique_id) DO UPDATE SET
                    mapa_id=EXCLUDED.mapa_id,
                    telegram_file_id=EXCLUDED.telegram_file_id,
                    nome_detectado=EXCLUDED.nome_detectado,
                    atualizado_em=CURRENT_TIMESTAMP
            """, (
                mapa_id,
                foto.file_id,
                foto.file_unique_id,
                dados_mapa["nome"],
            ))
            conn.commit()
            await msg.reply_text(
                f"✅ Imagem salva para o mapa {nome_mapa}.\n"
                f"⭐ Nível identificado: {dados_mapa['nivel']}"
            )
            return True

        masmorra = resolver_masmorra_conhecida(
            cur,
            dados_masmorra["nome"], dados_masmorra["mapa"]
        )
        if not masmorra:
            await msg.reply_text(
                "⚠️ Não encontrei uma única masmorra compatível no Atlas. "
                "A imagem não foi salva."
            )
            return True

        masmorra_id, mapa_id, nome_mapa, nome_masmorra = masmorra
        cur.execute("""
            INSERT INTO masmorra_imagens
                (mapa_id, masmorra_id, nome_masmorra, telegram_file_id,
                 telegram_file_unique_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (mapa_id, nome_masmorra) DO UPDATE SET
                masmorra_id=EXCLUDED.masmorra_id,
                telegram_file_id=EXCLUDED.telegram_file_id,
                telegram_file_unique_id=EXCLUDED.telegram_file_unique_id,
                atualizado_em=CURRENT_TIMESTAMP
        """, (
            mapa_id,
            masmorra_id,
            nome_masmorra,
            foto.file_id,
            foto.file_unique_id,
        ))
        conn.commit()
        await msg.reply_text(
            f"✅ Imagem salva para {nome_masmorra}.\n"
            f"🗺️ Mapa: {nome_mapa}"
        )
        return True
    except Exception as erro:
        conn.rollback()
        print(f"Erro ao salvar imagem de mapa/masmorra: {erro}")
        await msg.reply_text(
            "⚠️ Não consegui salvar esta imagem no Atlas."
        )
        return True
    finally:
        cur.close()


async def processar_imagem_monstro_masmorra(msg, dados):
    cur = conn.cursor()
    try:
        masmorra = resolver_mapa_da_masmorra(cur, dados["masmorra"])
        if not masmorra:
            await msg.reply_text(
                "⚠️ Esta masmorra ainda não está cadastrada no painel. "
                "A imagem e o HP não foram salvos."
            )
            return True

        masmorra_id, mapa_id, nome_mapa, nome_masmorra = masmorra
        cur.execute("SELECT tipo_sistema FROM catalogo_masmorras WHERE id=%s", (masmorra_id,))
        if cur.fetchone()[0] == "fenda" and "Sala:" in (msg.caption or msg.text or ""):
            return await save_header_photo(conn, msg, msg.caption or msg.text or "")
        monstro = resolver_monstro_masmorra_catalogo(
            cur, dados["nome"], mapa_id, masmorra_id
        )
        if not monstro:
            await msg.reply_text(
                "⚠️ O monstro desta mensagem ainda não está cadastrado "
                "nesta masmorra.\n\n"
                f"Masmorra reconhecida: {nome_masmorra}\n"
                f"Monstro recebido: {dados['nome']}\n\n"
                "Cadastre e vincule o monstro pelo painel antes de "
                "encaminhar a mensagem novamente."
            )
            return True

        monstro_id, nome_catalogo, _ = monstro
        nome_recebido = dados["nome"].strip()
        foto = msg.photo[-1]
        cur.execute("SELECT monstro_id FROM monstro_imagens WHERE telegram_file_unique_id=%s", (foto.file_unique_id,))
        imagem_existente = cur.fetchone()
        if imagem_existente and imagem_existente[0] != monstro_id:
            conn.rollback()
            await msg.reply_text(
                "⚠️ Esta imagem já está ligada a outro monstro. Revise o cadastro no painel."
            )
            return True
        cur.execute("""
            UPDATE catalogo_monstros
            SET masmorra_id=%s,
                masmorra_nome=%s,
                raridade=CASE
                    WHEN %s THEN 'Boss'
                    WHEN raridade IS NULL OR BTRIM(raridade)='' THEN 'Subboss'
                    ELSE raridade
                END,
                atualizado_em=CURRENT_TIMESTAMP
            WHERE id=%s
        """, (
            masmorra_id, nome_masmorra, dados["boss"], monstro_id
        ))
        if normalizar(nome_catalogo) != normalizar(nome_recebido):
            cur.execute("""
                INSERT INTO monstro_aliases
                    (alias_normalizado, alias, monstro_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (alias_normalizado) DO UPDATE SET
                    alias=EXCLUDED.alias,
                    monstro_id=EXCLUDED.monstro_id
            """, (normalizar(nome_recebido), nome_recebido, monstro_id))

        foto = msg.photo[-1]
        cur.execute("""
            INSERT INTO monstro_imagens
                (monstro_id, telegram_file_id, telegram_file_unique_id,
                 nome_detectado, hp_detectado)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (telegram_file_unique_id) DO UPDATE SET
                monstro_id=EXCLUDED.monstro_id,
                telegram_file_id=EXCLUDED.telegram_file_id,
                nome_detectado=EXCLUDED.nome_detectado,
                hp_detectado=EXCLUDED.hp_detectado,
                atualizado_em=CURRENT_TIMESTAMP
        """, (
            monstro_id,
            foto.file_id,
            foto.file_unique_id,
            nome_recebido,
            dados["hp_max"],
        ))

        partes_chave = (
            monstro_id,
            masmorra_id,
            dados["andar"],
            dados["hp_max"],
            dados["tamanho_grupo"],
            dados["codigo_execucao"],
            foto.file_unique_id,
        )
        chave = hashlib.sha256(
            "|".join(str(parte or "") for parte in partes_chave).encode()
        ).hexdigest()
        cur.execute("""
            INSERT INTO masmorra_monstro_observacoes
                (chave_unica, monstro_id, mapa_id, masmorra_id,
                 masmorra, andar,
                 total_andares, boss, hp_atual, hp_max, tamanho_grupo,
                 codigo_execucao, telegram_message_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chave_unica) DO NOTHING
        """, (
            chave,
            monstro_id,
            mapa_id,
            masmorra_id,
            nome_masmorra,
            dados["andar"],
            dados["total_andares"],
            dados["boss"],
            dados["hp_atual"],
            dados["hp_max"],
            dados["tamanho_grupo"],
            dados["codigo_execucao"],
            msg.message_id,
        ))

        cur.execute("""
            SELECT andar, MIN(hp_max), MAX(hp_max), COUNT(*)
            FROM masmorra_monstro_observacoes
            WHERE monstro_id=%s AND hp_max IS NOT NULL
            GROUP BY andar
            ORDER BY andar
        """, (monstro_id,))
        observacoes = cur.fetchall()
        conn.commit()

        hp_por_andar = {andar: (minimo, maximo, total)
                        for andar, minimo, maximo, total in observacoes}
        linhas_hp = []
        limite = dados["andar"] if dados["boss"] else min(3, dados["total_andares"])
        inicio = dados["andar"] if dados["boss"] else 1
        for andar in range(inicio, limite + 1):
            valores = hp_por_andar.get(andar)
            if not valores:
                valor = "ainda não observado"
            elif valores[0] == valores[1]:
                valor = str(valores[0])
            else:
                valor = f"{valores[0]}–{valores[1]}"
            rotulo = "Boss" if dados["boss"] else f"{andar}º andar"
            linhas_hp.append(f"• {rotulo}: {valor}")

        resposta = (
            f"✅ Imagem salva para {nome_recebido}.\n"
            f"🗺️ {nome_mapa} — {nome_masmorra}\n"
            f"🏰 Sala observada: {dados['andar']}/{dados['total_andares']}\n"
            "❤️ HP observado:\n" + "\n".join(linhas_hp)
        )
        # A observação já foi confirmada no banco. Uma falha temporária do
        # Telegram ao responder não pode ser apresentada como falha de gravação.
        try:
            await msg.reply_text(resposta)
        except Exception as erro_resposta:
            print(
                "Observação de masmorra salva, mas a confirmação no "
                f"Telegram falhou: {erro_resposta!r}",
                flush=True,
            )
        return True
    except Exception as erro:
        conn.rollback()
        codigo_erro = hashlib.sha256(
            f"{type(erro).__name__}:{erro}".encode("utf-8")
        ).hexdigest()[:8].upper()
        print(
            f"Erro ao cadastrar monstro de masmorra [{codigo_erro}]: "
            f"{erro!r}",
            flush=True,
        )
        await msg.reply_text(
            "⚠️ Não consegui salvar esta observação de masmorra.\n"
            f"Código para diagnóstico: {codigo_erro}"
        )
        return True
    finally:
        cur.close()


async def processar_imagem_monstro(msg):
    if (
        msg.chat.type != "private"
        or not msg.from_user
        or not mensagem_encaminhada_pelo_teletofus(msg)
        or not msg.photo
        or not can_submit_photo(conn, msg.from_user.id, LOOT_REVIEWER_ID)
    ):
        return False

    texto = msg.caption or msg.text or ""
    dados_cripta = extrair_monstro_cripta(texto)
    if dados_cripta:
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT cm.id, cm.nome, cm.mapa_id
                FROM catalogo_monstros cm
                WHERE cm.cripta_numero=%s
                  AND LOWER(cm.tipo)=LOWER('Cripta')
                ORDER BY cm.id
            """, (dados_cripta["cripta_numero"],))
            registros = cur.fetchall()
            procurado = normalizar(dados_cripta["nome"])
            exatos = [row for row in registros if normalizar(row[1]) == procurado]
            monstro = exatos[0] if len(exatos) == 1 else correspondencia_aproximada(
                dados_cripta["nome"], [(row, [row[1]]) for row in registros]
            )
            if not monstro:
                await msg.reply_text(
                    "⚠️ Este monstro ainda não está cadastrado na Cripta "
                    f"{dados_cripta['cripta_numero']}. A imagem não foi salva."
                )
                return True
            monstro_id, nome_catalogo, _ = monstro
            nome_recebido = dados_cripta["nome"].strip()
            if normalizar(nome_catalogo) != normalizar(nome_recebido):
                cur.execute("""
                    INSERT INTO monstro_aliases
                        (alias_normalizado, alias, monstro_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (alias_normalizado) DO UPDATE SET
                        alias=EXCLUDED.alias, monstro_id=EXCLUDED.monstro_id
                """, (normalizar(nome_recebido), nome_recebido, monstro_id))
            foto = msg.photo[-1]
            cur.execute("""
                INSERT INTO monstro_imagens
                    (monstro_id, telegram_file_id, telegram_file_unique_id,
                     nome_detectado, hp_detectado)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (telegram_file_unique_id) DO UPDATE SET
                    monstro_id=EXCLUDED.monstro_id,
                    telegram_file_id=EXCLUDED.telegram_file_id,
                    nome_detectado=EXCLUDED.nome_detectado,
                    hp_detectado=EXCLUDED.hp_detectado,
                    atualizado_em=CURRENT_TIMESTAMP
            """, (monstro_id, foto.file_id, foto.file_unique_id,
                  nome_recebido, dados_cripta["hp_max"]))
            conn.commit()
            await msg.reply_text(
                f"✅ Imagem salva para {nome_catalogo}.\n"
                f"🗝️ Cripta {dados_cripta['cripta_numero']}\n"
                "ℹ️ O HP não foi fixado, pois varia conforme o avanço na Cripta."
            )
            return True
        except Exception as erro:
            conn.rollback()
            print(f"Erro ao salvar imagem de monstro da cripta: {erro!r}", flush=True)
            await msg.reply_text("⚠️ Não consegui salvar esta imagem da Cripta.")
            return True
        finally:
            cur.close()

    dados_masmorra = extrair_monstro_masmorra(texto)
    if dados_masmorra:
        return await processar_imagem_monstro_masmorra(msg, dados_masmorra)

    try:
        return await save_header_photo(conn, msg, texto)
    except Exception as erro:
        conn.rollback()
        print(f"Erro ao salvar foto do catálogo: {erro!r}", flush=True)
        await msg.reply_text("⚠️ Não consegui salvar esta imagem do catálogo.")
        return True


async def processar_loot_para_revisao(msg, context):
    """Cria propostas silenciosas e as envia apenas ao revisor configurado."""
    if not mensagem_encaminhada_pelo_teletofus(msg):
        return

    texto = msg.text or msg.caption
    if not texto:
        return

    cur = conn.cursor()
    try:
        cur.execute("SELECT id, nome FROM itens_legends ORDER BY LENGTH(nome) DESC")
        itens = cur.fetchall()
        cur.execute("SELECT id, nome FROM catalogo_mapas ORDER BY ordem, id")
        mapas = cur.fetchall()

        propostas = analisar_texto_loot(texto, itens, mapas)
        for proposta in propostas:
            monstro = resolver_monstro_catalogo(
                cur,
                proposta["monstro_nome"],
                proposta["mapa_id"],
            )
            identificado_por_imagem = False
            if not monstro:
                monstro = resolver_monstro_por_imagem(cur, msg)
                identificado_por_imagem = monstro is not None
            monstro_id = monstro[0] if monstro else None
            mapa_id = proposta["mapa_id"]
            mapa_nome = proposta["mapa_nome"]

            # Quando o monstro é inequívoco, seu mapa cadastrado é a fonte
            # mais segura para completar a proposta.
            if monstro and not mapa_id:
                mapa_id = monstro[2]
                if mapa_id:
                    cur.execute("SELECT nome FROM catalogo_mapas WHERE id=%s", (mapa_id,))
                    row_mapa = cur.fetchone()
                    mapa_nome = row_mapa[0] if row_mapa else None

            relacao_chave = chave_relacao_drop(
                proposta["item_id"],
                monstro_id,
                mapa_id,
                proposta["forma_obtencao"],
            )

            cur.execute("""
                SELECT 1
                FROM item_drop_relacoes
                WHERE item_id=%s AND confirmado=TRUE
                  AND (
                    (%s IS NOT NULL AND monstro_id=%s)
                    OR (%s IS NULL AND %s IS NOT NULL
                        AND monstro_id IS NULL AND mapa_id=%s)
                    OR (%s IS NULL AND %s IS NULL
                        AND monstro_id IS NULL AND mapa_id IS NULL
                        AND LOWER(COALESCE(forma_obtencao, ''))=LOWER(%s))
                  )
                LIMIT 1
            """, (
                proposta["item_id"], monstro_id, monstro_id,
                monstro_id, mapa_id, mapa_id,
                monstro_id, mapa_id, proposta["forma_obtencao"] or "",
            ))
            if cur.fetchone():
                continue

            cur.execute("""
                SELECT 1
                FROM loot_evidencias
                WHERE item_id=%s
                  AND status IN ('pendente', 'aprovado', 'rejeitado')
                  AND (
                    (%s IS NOT NULL AND monstro_id=%s)
                    OR (%s IS NULL AND %s IS NOT NULL
                        AND monstro_id IS NULL AND mapa_id=%s)
                    OR (%s IS NULL AND %s IS NULL
                        AND monstro_id IS NULL AND mapa_id IS NULL
                        AND LOWER(COALESCE(forma_obtencao, ''))=LOWER(%s))
                  )
                LIMIT 1
            """, (
                proposta["item_id"], monstro_id, monstro_id,
                monstro_id, mapa_id, mapa_id,
                monstro_id, mapa_id, proposta["forma_obtencao"] or "",
            ))
            if cur.fetchone():
                continue

            evidencia_chave = (
                f"{msg.chat.id}:{msg.message_id}:{proposta['item_id']}:"
                f"{monstro_id or 0}:{mapa_id or 0}:"
                f"{normalizar(proposta['forma_obtencao'] or '')}"
            )
            cur.execute("""
                INSERT INTO loot_evidencias
                    (chave_unica, relacao_chave, chat_id, message_id,
                     remetente_id, item_id, item_nome_detectado, monstro_id,
                     monstro_nome_detectado, mapa_id, forma_obtencao,
                     texto_original)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chave_unica) DO NOTHING
                RETURNING id
            """, (
                evidencia_chave,
                relacao_chave,
                msg.chat.id,
                msg.message_id,
                msg.from_user.id if msg.from_user else None,
                proposta["item_id"],
                proposta["item_nome"],
                monstro_id,
                proposta["monstro_nome"],
                mapa_id,
                proposta["forma_obtencao"],
                texto,
            ))
            row = cur.fetchone()
            if not row:
                continue

            evidencia_id = row[0]
            conn.commit()

            monstro_texto = monstro[1] if identificado_por_imagem else (
                proposta["monstro_nome"] or "não identificado"
            )
            if proposta["monstro_nome"] and not monstro_id:
                monstro_texto += " (não cadastrado/ambíguo)"
            if identificado_por_imagem:
                monstro_texto += " (identificado pela imagem)"

            teclado = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅ SIM",
                    callback_data=f"loot_sim_{evidencia_id}",
                ),
                InlineKeyboardButton(
                    "❌ NÃO",
                    callback_data=f"loot_nao_{evidencia_id}",
                ),
            ]])
            texto_revisao = (
                "🔎 PROPOSTA DE LINKAGEM\n\n"
                f"🎁 Item: {proposta['item_nome']}\n"
                f"👹 Monstro: {monstro_texto}\n"
                f"🗺️ Mapa: {mapa_nome or 'não identificado'}\n"
                f"📍 Obtenção: {proposta['forma_obtencao'] or 'não identificada'}\n\n"
                "Deseja adicionar esta linkagem ao banco?"
            )

            try:
                await context.bot.send_message(
                    chat_id=LOOT_REVIEWER_ID,
                    text=texto_revisao,
                    reply_markup=teclado,
                )
            except Exception as erro:
                cur.execute("""
                    UPDATE loot_evidencias
                    SET status='erro_notificacao'
                    WHERE id=%s AND status='pendente'
                """, (evidencia_id,))
                conn.commit()
                print(f"Erro ao enviar revisão de loot {evidencia_id}: {erro}")

    except Exception as erro:
        conn.rollback()
        print(f"Erro ao analisar LOOTS: {erro}")
    finally:
        cur.close()


async def callback_revisao_loot(update, context):
    query = update.callback_query
    if not query:
        return

    if update.effective_user.id != LOOT_REVIEWER_ID:
        await query.answer("Somente o revisor pode decidir esta proposta.", show_alert=True)
        return

    match = re.fullmatch(r"loot_(sim|nao)_(\d+)", query.data or "")
    if not match:
        return

    await query.answer()
    decisao, evidencia_id = match.group(1), int(match.group(2))
    cur = conn.cursor()
    decisao_concluida = False
    try:
        cur.execute("""
            SELECT relacao_chave, item_id, monstro_id, mapa_id,
                   forma_obtencao, status
            FROM loot_evidencias
            WHERE id=%s
            FOR UPDATE
        """, (evidencia_id,))
        evidencia = cur.fetchone()

        if not evidencia:
            conn.rollback()
            await query.edit_message_text("⚠️ Esta proposta não existe mais.")
            return

        relacao_chave, item_id, monstro_id, mapa_id, forma, status = evidencia
        if status != "pendente":
            conn.rollback()
            await query.edit_message_text(
                f"Esta proposta já foi decidida: {status}."
            )
            return

        if decisao == "sim":
            cur.execute("""
                INSERT INTO item_drop_relacoes
                    (chave_unica, item_id, monstro_id, mapa_id,
                     forma_obtencao, primeira_evidencia_id,
                     ultima_evidencia_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chave_unica) DO UPDATE SET
                    ultima_evidencia_id=EXCLUDED.ultima_evidencia_id,
                    ultima_observacao=CURRENT_TIMESTAMP,
                    quantidade_observacoes=
                        item_drop_relacoes.quantidade_observacoes + 1,
                    confirmado=TRUE
            """, (
                relacao_chave,
                item_id,
                monstro_id,
                mapa_id,
                forma,
                evidencia_id,
                evidencia_id,
            ))
            novo_status = "aprovado"
        else:
            novo_status = "rejeitado"

        cur.execute("""
            UPDATE loot_evidencias
            SET status=%s, revisor_id=%s, decidido_em=CURRENT_TIMESTAMP
            WHERE id=%s
        """, (novo_status, update.effective_user.id, evidencia_id))
        conn.commit()
        decisao_concluida = True

        texto_original = query.message.text or "Proposta de linkagem"
        texto_original = re.sub(
            r"\n\nDeseja adicionar esta linkagem ao banco\?$",
            "",
            texto_original,
        )
        if decisao == "sim":
            resultado = "\n\n✅ Aprovado e vinculado ao banco."
        else:
            resultado = "\n\n❌ Rejeitado. Nenhuma linkagem foi adicionada."
        await query.edit_message_text(texto_original + resultado)

    except Exception as erro:
        print(f"Erro ao decidir loot {evidencia_id}: {erro}")
        if not decisao_concluida:
            conn.rollback()
            await query.edit_message_text(
                "⚠️ Não consegui concluir esta decisão. "
                "A proposta continua pendente."
            )
    finally:
        cur.close()


def codigo_area_monstro_atlas(tipo, masmorra_id=None):
    if (tipo or "").lower() != "masmorra":
        return "c"
    return f"r{masmorra_id}" if masmorra_id else "d0"


async def processar_busca_biblioteca(update, context):
    mensagem_id = context.user_data.get("biblioteca_busca_msg_id")
    if not mensagem_id or update.effective_chat.type != "private":
        return False

    termo = (update.message.text or "").strip()[:60]
    if len(termo) < 2:
        await update.message.reply_text(
            "Digite pelo menos duas letras para pesquisar."
        )
        return True

    cur = conn.cursor()
    try:
        padrao = f"%{termo}%"
        cur.execute("""
            SELECT id, nome, classe, categoria
            FROM itens_legends
            WHERE nome ILIKE %s
            ORDER BY nome
            LIMIT 6
        """, (padrao,))
        itens = cur.fetchall()

        cur.execute("""
            SELECT cm.id, cm.nome, cm.mapa_id, mp.nome, cm.tipo,
                   cm.masmorra_id, cm.cripta_numero
            FROM catalogo_monstros cm
            JOIN catalogo_mapas mp ON mp.id=cm.mapa_id
            WHERE cm.nome ILIKE %s
            ORDER BY cm.nome
            LIMIT 6
        """, (padrao,))
        monstros = cur.fetchall()

        cur.execute("""
            SELECT id, nome
            FROM catalogo_mapas
            WHERE nome ILIKE %s
            ORDER BY ordem, id
            LIMIT 4
        """, (padrao,))
        mapas = cur.fetchall()

        cur.execute("""
            SELECT id, nome, especializacao
            FROM almas_legends
            WHERE nome ILIKE %s
            ORDER BY nome
            LIMIT 6
        """, (padrao,))
        almas = cur.fetchall()
    finally:
        cur.close()

    linhas = []
    for item_id, nome, classe, categoria in itens:
        linhas.append([InlineKeyboardButton(
            f"🎒 {nome}",
            callback_data=f"item_{item_id}_{classe}_{categoria}",
        )])
    for monstro_id, nome, mapa_id, mapa, tipo, masmorra_id, cripta_numero in monstros:
        if (tipo or "").lower() == "cripta" and cripta_numero:
            destino = f"cripta_m_{monstro_id}"
            local = f"Cripta {cripta_numero}"
        else:
            area = codigo_area_monstro_atlas(tipo, masmorra_id)
            destino = f"atlas_x_{monstro_id}_{mapa_id}_{area}"
            local = mapa
        linhas.append([InlineKeyboardButton(
            f"👹 {nome} — {local}", callback_data=destino,
        )])
    for mapa_id, nome in mapas:
        linhas.append([InlineKeyboardButton(
            f"🗺️ {nome}", callback_data=f"atlas_m_{mapa_id}"
        )])
    for alma_id, nome, especializacao in almas:
        linhas.append([InlineKeyboardButton(
            f"✨ {nome} — {especializacao}",
            callback_data=f"alma_{alma_id}",
        )])
    linhas.append([InlineKeyboardButton(
        "⬅ Biblioteca", callback_data="lib_inicio"
    )])

    total = len(itens) + len(monstros) + len(mapas) + len(almas)
    texto = (
        f"🔎 BUSCA — {termo}\n\n"
        + (f"Encontrados: {total}" if total else "Nenhum resultado encontrado.")
    )
    context.user_data.pop("biblioteca_busca_msg_id", None)

    try:
        await context.bot.edit_message_caption(
            chat_id=update.effective_chat.id,
            message_id=mensagem_id,
            caption=texto,
            reply_markup=InlineKeyboardMarkup(linhas),
        )
    except Exception as erro:
        print(f"Erro ao atualizar resultado da busca: {erro}")
        await enviar_pagina_biblioteca(
            update.message,
            "biblioteca",
            texto,
            InlineKeyboardMarkup(linhas),
        )
    return True


async def detectar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = update.message

    if not msg:
        return

    texto = msg.text or msg.caption

    if not texto:
        return

    numero_cripta_xp = context.user_data.get("cripta_xp_aguardando")
    if numero_cripta_xp and msg.chat.type == "private":
        valor = texto.strip()
        if not valor.isdigit() or not 1 <= int(valor) <= 999:
            await msg.reply_text("Informe somente um andar entre 1 e 999.")
            return
        context.user_data.pop("cripta_xp_aguardando", None)
        await mostrar_resultado_run_cripta(msg, numero_cripta_xp, int(valor))
        return

    if await processar_busca_biblioteca(update, context):
        return

    if await processar_imagem_mapa_ou_masmorra(msg):
        return

    if await processar_imagem_monstro(msg):
        return

    # =========================
    # CAÇADA EM DUPLA
    # =========================

    eh_privado = msg.chat.type == "private"

    eh_loot = (
        msg.chat.id == GRUPO_ID
        and msg.message_thread_id == TOPICO_LOOTS
    )

    if eh_loot:
        await processar_loot_para_revisao(msg, context)

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
    classe = extrair_classe(texto)
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
    if membro_inativo(tg_id):
        await msg.reply_text(
            "⚪ Seu cadastro está inativo. Procure um administrador da guilda "
            "para reativá-lo; seu histórico continua preservado."
        )
        return

    if not registrar_membro(tg_id, nome, msg.from_user.username, classe):
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
            m.nome,
            SUM(c.pvps)
        FROM cacadas c
        JOIN membros m ON m.telegram_id=c.telegram_id
        LEFT JOIN membro_administracao ma ON ma.telegram_id=m.telegram_id
        WHERE COALESCE(ma.ativo, TRUE)
        GROUP BY m.telegram_id, m.nome
        HAVING SUM(c.pvps) > 0
        ORDER BY SUM(c.pvps) DESC
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
            m.nome,
            COUNT(*) AS martelos,
            SUM(
                CASE
                    WHEN g.resultado='SUCESSO'
                    THEN 1
                    ELSE 0
                END
            ) AS sucessos
        FROM gibby_logs g
        JOIN membros m ON m.telegram_id=g.telegram_id
        LEFT JOIN membro_administracao ma ON ma.telegram_id=m.telegram_id
        WHERE COALESCE(ma.ativo, TRUE)
        GROUP BY m.telegram_id, m.nome
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


def limitar_legenda_biblioteca(texto, limite=1000):
    """Mantém uma margem segura dentro do limite de legendas do Telegram."""
    if len(texto) <= limite:
        return texto

    aviso = "\n\nℹ️ Conteúdo resumido para caber nesta página."
    disponivel = limite - len(aviso)
    linhas = []
    tamanho = 0
    for linha in texto.splitlines():
        adicional = len(linha) + (1 if linhas else 0)
        if tamanho + adicional > disponivel:
            break
        linhas.append(linha)
        tamanho += adicional
    return "\n".join(linhas).rstrip() + aviso


def midia_biblioteca_salva(chave):
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT telegram_file_id, telegram_file_unique_id
            FROM biblioteca_midias
            WHERE chave=%s
        """, (chave,))
        return cur.fetchone()
    finally:
        cur.close()


def salvar_midia_biblioteca(chave, mensagem):
    if not mensagem or not getattr(mensagem, "photo", None):
        return

    foto = mensagem.photo[-1]
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO biblioteca_midias
                (chave, telegram_file_id, telegram_file_unique_id, atualizado_em)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (chave) DO UPDATE SET
                telegram_file_id=EXCLUDED.telegram_file_id,
                telegram_file_unique_id=EXCLUDED.telegram_file_unique_id,
                atualizado_em=CURRENT_TIMESTAMP
        """, (chave, foto.file_id, foto.file_unique_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


async def enviar_pagina_biblioteca(
    mensagem, chave_midia, texto, teclado=None,
    file_id=None, file_unique_id=None
):
    texto = limitar_legenda_biblioteca(texto)
    midia = (
        (file_id, file_unique_id)
        if file_id
        else midia_biblioteca_salva(chave_midia)
    )

    if midia:
        resposta = await mensagem.reply_photo(
            photo=midia[0], caption=texto, reply_markup=teclado
        )
    else:
        caminho = BIBLIOTECA_ASSETS[chave_midia]
        with caminho.open("rb") as arquivo:
            resposta = await mensagem.reply_photo(
                photo=InputFile(arquivo), caption=texto, reply_markup=teclado
            )
        salvar_midia_biblioteca(chave_midia, resposta)

    return resposta


async def editar_pagina_biblioteca(
    query, chave_midia, texto, teclado=None, file_id=None, file_unique_id=None
):
    """Navega sempre entre mensagens com foto, sem apagar a página atual."""
    texto = limitar_legenda_biblioteca(texto)
    mensagem = query.message

    if file_id:
        midia_id = file_id
        unica_id = file_unique_id
    else:
        midia = midia_biblioteca_salva(chave_midia)
        midia_id = midia[0] if midia else None
        unica_id = midia[1] if midia else None

    foto_atual = mensagem.photo[-1] if getattr(mensagem, "photo", None) else None
    if foto_atual and unica_id and foto_atual.file_unique_id == unica_id:
        return await query.edit_message_caption(
            caption=texto, reply_markup=teclado
        )

    if foto_atual:
        if midia_id:
            resposta = await query.edit_message_media(
                media=InputMediaPhoto(media=midia_id, caption=texto),
                reply_markup=teclado,
            )
        else:
            try:
                resposta = await query.edit_message_media(
                    media=InputMediaPhoto(
                        media=BIBLIOTECA_ASSET_URLS[chave_midia], caption=texto
                    ),
                    reply_markup=teclado,
                )
                salvar_midia_biblioteca(chave_midia, resposta)
            except Exception as erro:
                # O Telegram pode recusar temporariamente o download da capa.
                # A navegação continua funcional usando a foto atual.
                print(
                    f"Erro ao carregar capa {chave_midia} por URL: {erro}"
                )
                resposta = await query.edit_message_caption(
                    caption=texto, reply_markup=teclado
                )
        return resposta

    # Compatibilidade com botões de mensagens antigas, anteriores à navegação
    # unificada: cria a nova página antes de remover a mensagem de texto.
    resposta = await enviar_pagina_biblioteca(
        mensagem, chave_midia, texto, teclado
    )
    try:
        await mensagem.delete()
    except Exception as erro:
        print(f"Erro ao limpar página antiga da Biblioteca: {erro}")
    return resposta


def teclado_inicio_unificado():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗺️ Atlas", callback_data="lib_atlas")],
        [InlineKeyboardButton("🗝️ Criptas", callback_data="lib_criptas")],
        [InlineKeyboardButton("🎒 Itens", callback_data="lib_itens")],
        [InlineKeyboardButton("✨ Almas", callback_data="lib_almas")],
        [InlineKeyboardButton("🔎 Buscar", callback_data="lib_buscar")],
    ])


async def mostrar_inicio_unificado(alvo, editar=False):
    texto = (
        "📚 BIBLIOTECA LEGENDS\n\n"
        "Explore o Atlas, as Criptas, os itens e as almas catalogados pela guilda."
    )
    if editar:
        await editar_pagina_biblioteca(
            alvo, "biblioteca", texto, teclado_inicio_unificado()
        )
    else:
        await enviar_pagina_biblioteca(
            alvo, "biblioteca", texto, teclado_inicio_unificado()
        )


ESPECIALIZACOES_ALMAS = {
    "berserker": ("Berserker", "Guerreiro", "almas_guerreiro", "🪓"),
    "tank": ("Tank", "Guerreiro", "almas_guerreiro", "🛡️"),
    "cacador": ("Caçador", "Arqueiro", "almas_arqueiro", "🏹"),
    "lanceiro": ("Lanceiro", "Arqueiro", "almas_arqueiro", "🔱"),
    "cajado": ("Cajado", "Mago", "almas_mago", "🪄"),
    "suporte": ("Suporte", "Mago", "almas_mago", "✨"),
}


def teclado_especializacoes_almas():
    botoes = []
    pares = [
        ("berserker", "tank"),
        ("cacador", "lanceiro"),
        ("cajado", "suporte"),
    ]
    for esquerda, direita in pares:
        linha = []
        for slug in (esquerda, direita):
            nome, _, _, emoji = ESPECIALIZACOES_ALMAS[slug]
            linha.append(InlineKeyboardButton(
                f"{emoji} {nome}", callback_data=f"almas_{slug}"
            ))
        botoes.append(linha)
    botoes.append([InlineKeyboardButton(
        "⬅ Biblioteca", callback_data="lib_inicio"
    )])
    return InlineKeyboardMarkup(botoes)


async def mostrar_inicio_almas(query):
    await editar_pagina_biblioteca(
        query,
        "almas",
        "✨ ALMAS DE TELETOFUS\n\nEscolha uma das 6 especializações:",
        teclado_especializacoes_almas(),
    )


async def mostrar_almas_especializacao(query, slug):
    nome, classe, midia, emoji = ESPECIALIZACOES_ALMAS[slug]
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, nome
            FROM almas_legends
            WHERE LOWER(especializacao)=LOWER(%s)
            ORDER BY id
        """, (nome,))
        almas = cur.fetchall()
    finally:
        cur.close()
    botoes = [[InlineKeyboardButton(
        f"✨ {alma_nome}", callback_data=f"alma_{alma_id}"
    )] for alma_id, alma_nome in almas]
    botoes.append([InlineKeyboardButton("⬅ Almas", callback_data="lib_almas")])
    await editar_pagina_biblioteca(
        query,
        midia,
        f"{emoji} {nome.upper()} — {classe.upper()}\n\nEscolha uma alma:",
        InlineKeyboardMarkup(botoes),
    )


async def mostrar_alma(query, alma_id):
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT nome, classe_base, especializacao, equipamento,
                   recarga_turnos, efeito, confirmado, fonte, obtencao
            FROM almas_legends WHERE id=%s
        """, (alma_id,))
        alma = cur.fetchone()
    finally:
        cur.close()
    if not alma:
        await query.answer("Alma não encontrada.", show_alert=True)
        return
    nome, classe, especializacao, equipamento, recarga, efeito, confirmado, fonte, obtencao = alma
    slug = next((
        chave for chave, dados in ESPECIALIZACOES_ALMAS.items()
        if dados[0].casefold() == especializacao.casefold()
    ), "cajado")
    midia = ESPECIALIZACOES_ALMAS[slug][2]
    estado = "Confirmado" if confirmado else "Efeito em revisão"
    texto = (
        f"✨ {nome.upper()}\n\n"
        f"🏷️ {classe} — {especializacao}\n"
        f"⚔️ Equipamento: {equipamento}\n"
        f"⏳ Recarga: {recarga or 'a confirmar'} turnos\n\n"
        f"📖 {efeito or 'Efeito a confirmar.'}\n\n"
        f"📍 Obtenção: {obtencao or 'não informada'}\n\n"
        f"🔎 {estado}\n📚 Fonte: {fonte}"
    )
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "⬅ Voltar às almas", callback_data=f"almas_{slug}"
        )],
        [InlineKeyboardButton("📚 Biblioteca", callback_data="lib_inicio")],
    ])


async def mostrar_inicio_criptas(alvo):
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT c.numero, c.nome, c.nivel_minimo, c.nivel_maximo,
                   COUNT(cm.id)
            FROM catalogo_criptas c
            LEFT JOIN catalogo_monstros cm
              ON cm.cripta_numero=c.numero
             AND LOWER(cm.tipo)=LOWER('Cripta')
            GROUP BY c.numero, c.nome, c.nivel_minimo, c.nivel_maximo
            ORDER BY c.numero
        """)
        criptas = cur.fetchall()
    finally:
        cur.close()
    botoes = []
    for numero, nome, nivel_minimo, nivel_maximo, total in criptas:
        nivel = (
            f"Nv {nivel_minimo}–{nivel_maximo}"
            if nivel_minimo is not None and nivel_maximo is not None
            else "nível a confirmar"
        )
        botoes.append([InlineKeyboardButton(
            f"🗝️ {nome} · {nivel} ({total})", callback_data=f"cripta_{numero}"
        )])
    botoes.append([InlineKeyboardButton("⬅ Biblioteca", callback_data="lib_inicio")])
    await editar_pagina_biblioteca(
        alvo, "atlas", "🗝️ CRIPTAS LEGENDS\n\nEscolha uma Cripta:",
        InlineKeyboardMarkup(botoes),
    )


def formatar_xp(valor):
    return f"{int(valor):,}".replace(",", ".") if valor is not None else "indisponível"


def calcular_acumulado_cripta(numero, andares_concluidos):
    """Retorna (xp, confirmado) sem transformar projeções em dados salvos."""
    if andares_concluidos == 0:
        return 0, True
    if andares_concluidos < 0:
        return None, False
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT andares_concluidos, xp_acumulado
            FROM cripta_xp_observacoes
            WHERE cripta_numero=%s AND confirmado=TRUE
            ORDER BY andares_concluidos
        """, (numero,))
        observacoes = dict(cur.fetchall())
    finally:
        cur.close()
    if andares_concluidos in observacoes:
        return observacoes[andares_concluidos], True
    if not observacoes:
        return None, False
    ultimo_andar = max(observacoes)
    if andares_concluidos < ultimo_andar:
        return None, False

    deltas = {}
    for andar in sorted(observacoes):
        if andar - 1 in observacoes:
            deltas[andar] = observacoes[andar] - observacoes[andar - 1]
    if not deltas:
        return None, False
    ultimo_delta_andar = max(deltas)
    delta = deltas[ultimo_delta_andar]
    taxas = [
        deltas[andar] / deltas[andar - 1]
        for andar in sorted(deltas)
        if andar - 1 in deltas and deltas[andar - 1] > 0
    ]
    taxa = statistics.median(taxas) if taxas else 1.07
    acumulado = observacoes[ultimo_andar]
    for _andar in range(ultimo_andar + 1, andares_concluidos + 1):
        delta = int(delta * taxa + 0.5)
        acumulado += delta
    return acumulado, False


def resultado_run_cripta(numero, andar_alvo):
    antes, antes_confirmado = calcular_acumulado_cripta(numero, andar_alvo - 1)
    depois, depois_confirmado = calcular_acumulado_cripta(numero, andar_alvo)
    ganho = depois - antes if antes is not None and depois is not None else None
    return {
        "antes": antes, "depois": depois, "ganho": ganho,
        "antes_confirmado": antes_confirmado,
        "depois_confirmado": depois_confirmado,
    }


async def mostrar_cripta(alvo, numero):
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT c.nome, c.nivel_minimo, c.nivel_maximo, mp.nome,
                   COUNT(cm.id)
            FROM catalogo_criptas c
            LEFT JOIN catalogo_mapas mp ON mp.id=c.mapa_id
            LEFT JOIN catalogo_monstros cm ON cm.cripta_numero=c.numero
                AND LOWER(cm.tipo)=LOWER('Cripta')
            WHERE c.numero=%s
            GROUP BY c.numero, c.nome, c.nivel_minimo, c.nivel_maximo, mp.nome
        """, (numero,))
        cripta = cur.fetchone()
    finally:
        cur.close()
    if not cripta:
        await mostrar_inicio_criptas(alvo)
        return
    nome, nivel_minimo, nivel_maximo, mapa, total = cripta
    nivel = (
        f"{nivel_minimo}–{nivel_maximo}"
        if nivel_minimo is not None and nivel_maximo is not None
        else "a confirmar"
    )
    texto = (
        f"🗝️ {nome.upper()}\n\n📍 Local: {mapa or 'Cemitério Antigo'}\n"
        f"🎚️ Níveis permitidos: {nivel}\n👹 Monstros cadastrados: {total}\n\n"
        "Escolha o que deseja consultar:"
    )
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("👹 Monstros", callback_data=f"cripta_monstros_{numero}")],
        [InlineKeyboardButton("⭐ Consultar XP", callback_data=f"cripta_xp_{numero}")],
        [InlineKeyboardButton("⬅ Criptas", callback_data="lib_criptas")],
    ])
    await editar_pagina_biblioteca(alvo, "atlas", texto, teclado)


async def mostrar_consulta_xp_cripta(alvo, numero):
    cur = conn.cursor()
    try:
        cur.execute("SELECT nome FROM catalogo_criptas WHERE numero=%s", (numero,))
        row = cur.fetchone()
    finally:
        cur.close()
    if not row:
        await mostrar_inicio_criptas(alvo)
        return
    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1–10", callback_data=f"cripta_run_{numero}_10"),
            InlineKeyboardButton("1–20", callback_data=f"cripta_run_{numero}_20"),
        ],
        [
            InlineKeyboardButton("1–30", callback_data=f"cripta_run_{numero}_30"),
            InlineKeyboardButton("1–40", callback_data=f"cripta_run_{numero}_40"),
        ],
        [InlineKeyboardButton("🔢 Informar andar de saída", callback_data=f"cripta_custom_{numero}")],
        [InlineKeyboardButton("⬅ Voltar à Cripta", callback_data=f"cripta_{numero}")],
    ])
    await editar_pagina_biblioteca(
        alvo, "atlas",
        f"⭐ CALCULADORA — {row[0].upper()}\n\n"
        "Escolha uma run popular ou informe o andar em que pretende decidir se sai.\n\n"
        "O resultado mostra o XP ao sair durante esse andar e após concluí-lo.",
        teclado,
    )


async def mostrar_resultado_run_cripta(alvo, numero, andar_alvo):
    if andar_alvo < 1 or andar_alvo > 999:
        if hasattr(alvo, "answer"):
            await alvo.answer("Informe um andar entre 1 e 999.", show_alert=True)
        else:
            await alvo.reply_text("Informe um andar entre 1 e 999.")
        return
    cur = conn.cursor()
    try:
        cur.execute("SELECT nome FROM catalogo_criptas WHERE numero=%s", (numero,))
        row = cur.fetchone()
    finally:
        cur.close()
    if not row:
        await mostrar_inicio_criptas(alvo)
        return
    resultado = resultado_run_cripta(numero, andar_alvo)
    antes = resultado["antes"]
    depois = resultado["depois"]
    marca_antes = "✅ confirmado" if resultado["antes_confirmado"] else "🧮 estimado"
    marca_depois = "✅ confirmado" if resultado["depois_confirmado"] else "🧮 estimado"
    texto = (
        f"⭐ {row[0].upper()} — RUN 1–{andar_alvo}\n\n"
        f"🚪 Sair durante o andar {andar_alvo}:\n"
        f"📊 XP dos andares 1–{andar_alvo - 1}: {formatar_xp(antes)} "
        f"{marca_antes if antes is not None else ''}\n\n"
        f"⚔️ Concluir o andar {andar_alvo} e sair:\n"
        f"📊 XP dos andares 1–{andar_alvo}: {formatar_xp(depois)} "
        f"{marca_depois if depois is not None else ''}\n"
    )
    if resultado["ganho"] is not None:
        texto += f"\n➕ XP do andar {andar_alvo}: {formatar_xp(resultado['ganho'])}"
    if antes is None or depois is None:
        texto += "\n\n⚠️ Ainda faltam observações reais para calcular esta faixa."
    elif not (resultado["antes_confirmado"] and resultado["depois_confirmado"]):
        texto += "\n\n🧮 A estimativa usa a progressão observada e não substitui dados reais."
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Outras runs", callback_data=f"cripta_xp_{numero}")],
        [InlineKeyboardButton("🗝️ Voltar à Cripta", callback_data=f"cripta_{numero}")],
    ])
    if hasattr(alvo, "message"):
        await editar_pagina_biblioteca(alvo, "atlas", texto, teclado)
    else:
        await enviar_pagina_biblioteca(alvo, "atlas", texto, teclado)


async def mostrar_monstros_cripta(alvo, numero):
    cur = conn.cursor()
    try:
        cur.execute("SELECT nome, nivel_minimo, nivel_maximo FROM catalogo_criptas WHERE numero=%s", (numero,))
        cripta = cur.fetchone()
        if not cripta:
            await mostrar_inicio_criptas(alvo)
            return
        cur.execute("""
            SELECT id, nome FROM catalogo_monstros
            WHERE cripta_numero=%s AND LOWER(tipo)=LOWER('Cripta')
            ORDER BY ordem, id
        """, (numero,))
        monstros = cur.fetchall()
    finally:
        cur.close()
    nome, nivel_minimo, nivel_maximo = cripta
    nivel = (
        f"Nível recomendado: {nivel_minimo}–{nivel_maximo}"
        if nivel_minimo is not None and nivel_maximo is not None
        else "Nível recomendado: a confirmar"
    )
    botoes = [[InlineKeyboardButton(
        f"👹 {nome_monstro}", callback_data=f"cripta_m_{monstro_id}"
    )] for monstro_id, nome_monstro in monstros]
    botoes.append([InlineKeyboardButton("⬅ Voltar à Cripta", callback_data=f"cripta_{numero}")])
    instrucao = "Escolha um monstro:" if monstros else "Nenhum monstro cadastrado por enquanto."
    await editar_pagina_biblioteca(
        alvo, "atlas", f"🗝️ {nome.upper()}\n{nivel}\n\n{instrucao}",
        InlineKeyboardMarkup(botoes),
    )


async def mostrar_monstro_cripta(alvo, monstro_id):
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT cm.nome, cm.cripta_numero, c.nome, mp.nome,
                   cm.habilidade, cm.sem_habilidade, cm.risco,
                   mi.telegram_file_id, mi.telegram_file_unique_id
            FROM catalogo_monstros cm
            JOIN catalogo_criptas c ON c.numero=cm.cripta_numero
            LEFT JOIN catalogo_mapas mp ON mp.id=c.mapa_id
            LEFT JOIN LATERAL (
                SELECT telegram_file_id, telegram_file_unique_id
                FROM monstro_imagens WHERE monstro_id=cm.id
                ORDER BY atualizado_em DESC LIMIT 1
            ) mi ON TRUE
            WHERE cm.id=%s AND LOWER(cm.tipo)=LOWER('Cripta')
        """, (monstro_id,))
        monstro = cur.fetchone()
    finally:
        cur.close()
    if not monstro:
        await mostrar_inicio_criptas(alvo)
        return
    nome, numero, nome_cripta, mapa, habilidade, sem_habilidade, risco, file_id, unique_id = monstro
    habilidade_texto = "Sem habilidade" if sem_habilidade else (habilidade or "a confirmar")
    risco_texto = risco or "a confirmar"
    alerta = ""
    if risco and risco.casefold() == "alto":
        alerta = "\n\n⚠️ ALERTA: monstro de risco alto."
    texto = (
        f"👹 {nome.upper()}\n\n🗝️ {nome_cripta}\n"
        f"🗺️ Local: {mapa or 'Cemitério Antigo'}\n"
        f"✨ Habilidade: {habilidade_texto}\n"
        f"⚠️ Risco: {risco_texto}{alerta}"
    )
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Monstros da Cripta", callback_data=f"cripta_monstros_{numero}")],
        [InlineKeyboardButton("🗝️ Todas as Criptas", callback_data="lib_criptas")],
    ])
    await editar_pagina_biblioteca(
        alvo, "atlas", texto, teclado, file_id=file_id, file_unique_id=unique_id
    )


async def cmd_mapa(update, context):
    if not await validar_acesso(update, context, "/mapa"):
        return

    if update.effective_chat.type != "private":
        bot_username = (await context.bot.get_me()).username
        teclado = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🗺️ Abrir Atlas Legends",
                url=f"https://t.me/{bot_username}?start=atlas"
            )
        ]])
        await update.message.reply_text(
            "🗺️ Pilar da Sabedoria:\n\n"
            "Para evitar spam nos tópicos da guilda, o Atlas Legends "
            "funciona apenas no privado.\n\n"
            "Clique no botão abaixo para abrir o Atlas.",
            reply_markup=teclado
        )
        return

    if context.args:
        numero = argumento_numerico(context)
        if numero is None:
            await update.message.reply_text(
                "Use apenas /mapa para abrir o Atlas Legends."
            )
            return

        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT id
                FROM catalogo_mapas
                ORDER BY ordem, id
                OFFSET %s LIMIT 1
            """, (numero - 1,))
            resultado = cur.fetchone()
        finally:
            cur.close()

        if not resultado:
            await update.message.reply_text("Esse mapa não existe no Atlas.")
            return

        await mostrar_mapa_atlas(update.message, resultado[0])
        return

    await mostrar_inicio_atlas(update.message)


def agrupar_botoes_atlas(botoes, colunas=2):
    return [botoes[i:i + colunas] for i in range(0, len(botoes), colunas)]


def masmorras_do_mapa_atlas(nome_mapa):
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT d.nome
            FROM catalogo_masmorras d
            JOIN catalogo_mapas mp ON mp.id=d.mapa_id
            WHERE mp.nome=%s
              AND COALESCE(d.tipo_sistema, 'masmorra') <> 'cripta'
            ORDER BY d.ordem, d.id
        """, (nome_mapa,))
        return [row[0] for row in cur.fetchall()]
    finally:
        cur.close()


def nome_area_atlas(nome_mapa, codigo_area):
    if codigo_area == "c":
        return "Caçada"


    if not codigo_area.startswith("d"):
        return None

    try:
        indice = int(codigo_area[1:])
        return masmorras_do_mapa_atlas(nome_mapa)[indice]
    except (ValueError, IndexError):
        return None


def resolver_area_atlas(cur, mapa_id, codigo_area):
    if codigo_area == "c":
        return "Caçada", None
    if codigo_area.startswith("r"):
        try:
            masmorra_id = int(codigo_area[1:])
        except ValueError:
            return None, None
        cur.execute("""
            SELECT nome
            FROM catalogo_masmorras
            WHERE id=%s AND mapa_id=%s
              AND COALESCE(tipo_sistema, 'masmorra') <> 'cripta'
        """, (masmorra_id, mapa_id))
        row = cur.fetchone()
        return (row[0], masmorra_id) if row else (None, None)
    if codigo_area.startswith("d"):
        try:
            indice = int(codigo_area[1:])
        except ValueError:
            return None, None
        cur.execute("""
            SELECT id, nome
            FROM catalogo_masmorras
            WHERE mapa_id=%s
              AND COALESCE(tipo_sistema, 'masmorra') <> 'cripta'
            ORDER BY ordem, id
            OFFSET %s LIMIT 1
        """, (mapa_id, indice))
        row = cur.fetchone()
        return (row[1], row[0]) if row else (None, None)
    return None, None


async def editar_atlas_com_texto(alvo, texto, teclado=None):
    await editar_pagina_biblioteca(alvo, "atlas", texto, teclado)


async def mostrar_inicio_atlas(alvo, editar=False):
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, nome
            FROM catalogo_mapas
            ORDER BY ordem, id
        """)
        mapas = cur.fetchall()
        botoes = [
            InlineKeyboardButton(
                f"🗺️ {nome}", callback_data=f"atlas_m_{mapa_id}"
            )
            for mapa_id, nome in mapas
        ]
        linhas = agrupar_botoes_atlas(botoes)
        linhas.append([
            InlineKeyboardButton(
                "⬅️ Biblioteca", callback_data="lib_inicio"
            )
        ])
        teclado = InlineKeyboardMarkup(linhas)
        texto = "🗺️ ATLAS LEGENDS\n\nEscolha um mapa:"

        if editar:
            await editar_atlas_com_texto(alvo, texto, teclado)
        else:
            await enviar_pagina_biblioteca(alvo, "atlas", texto, teclado)
    finally:
        cur.close()


async def mostrar_mapa_atlas(alvo, mapa_id, editar=False):
    cur = conn.cursor()
    try:
        imagem_mapa = None
        cur.execute("""
            SELECT nome, nivel_minimo, descricao
            FROM catalogo_mapas
            WHERE id=%s
        """, (mapa_id,))
        mapa = cur.fetchone()
        if not mapa:
            texto = "Esse mapa não está mais disponível no Atlas."
            teclado = InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Mapas", callback_data="atlas_inicio")
            ]])
        else:
            nome, nivel, descricao = mapa
            cur.execute("""
                SELECT telegram_file_id, telegram_file_unique_id
                FROM mapa_imagens
                WHERE mapa_id=%s
                ORDER BY atualizado_em DESC
                LIMIT 1
            """, (mapa_id,))
            imagem_mapa = cur.fetchone()
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE LOWER(tipo)=LOWER('Caçada')),
                    COUNT(*) FILTER (WHERE LOWER(tipo)=LOWER('Masmorra'))
                FROM catalogo_monstros
                WHERE mapa_id=%s
            """, (mapa_id,))
            total_cacada, total_masmorra = cur.fetchone()

            cur.execute("""
                SELECT d.id, d.nome, COUNT(cm.id), d.tipo_sistema
                FROM catalogo_masmorras d
                LEFT JOIN catalogo_monstros cm
                  ON cm.masmorra_id=d.id
                 AND LOWER(cm.tipo)=LOWER('Masmorra')
                WHERE d.mapa_id=%s
                  AND COALESCE(d.tipo_sistema, 'masmorra') <> 'cripta'
                GROUP BY d.id, d.nome, d.ordem, d.tipo_sistema
                ORDER BY d.ordem, d.id
            """, (mapa_id,))
            masmorras = cur.fetchall()

            cur.execute("""
                SELECT COUNT(DISTINCT item_id)
                FROM (
                    SELECT id AS item_id
                    FROM itens_legends
                    WHERE mapa=%s
                    UNION
                    SELECT rel.item_id
                    FROM item_drop_relacoes rel
                    LEFT JOIN catalogo_monstros cm ON cm.id=rel.monstro_id
                    WHERE rel.confirmado=TRUE
                      AND (rel.mapa_id=%s OR cm.mapa_id=%s)
                ) itens_do_mapa
            """, (nome, mapa_id, mapa_id))
            total_itens = cur.fetchone()[0]

            texto = (
                f"🗺️ {nome.upper()}\n\n"
                f"⭐ Nível mínimo: {formatar_valor_catalogo(nivel)}   "
                f"🎁 Itens: {total_itens}\n\n"
                "Escolha uma área:"
            )
            linhas = []
            if descricao:
                texto = texto.replace("Escolha uma área:", f"{descricao}\n\nEscolha uma área:")
            linhas.append([InlineKeyboardButton(
                f"⚔️ Caçada ({total_cacada})",
                callback_data=f"atlas_t_{mapa_id}_c"
            )])
            for masmorra_id, nome_masmorra, quantidade, sistema in masmorras:
                linhas.append([InlineKeyboardButton(
                    f"{'🌀' if sistema == 'fenda' else '🗝️'} {nome_masmorra} ({quantidade})",
                    callback_data=f"atlas_d_{mapa_id}_{masmorra_id}"
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


def texto_capacidade_masmorra(minimo, maximo):
    if minimo is None or maximo is None:
        return "a confirmar"
    if minimo == maximo == 1:
        return "1 jogador"
    if minimo == maximo:
        return f"{minimo} jogadores"
    return f"{minimo} a {maximo} jogadores"


async def mostrar_resumo_masmorra_atlas(alvo, mapa_id, masmorra_id):
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT d.nome, mp.nome, d.minimo_jogadores,
                   d.maximo_jogadores, d.xp_por_equipe,
                   d.tipo_sistema, d.requisitos_texto, d.observacoes,
                   COUNT(cm.id)
            FROM catalogo_masmorras d
            JOIN catalogo_mapas mp ON mp.id=d.mapa_id
            LEFT JOIN catalogo_monstros cm
              ON cm.masmorra_id=d.id
             AND LOWER(cm.tipo)=LOWER('Masmorra')
            WHERE d.id=%s AND d.mapa_id=%s
            GROUP BY d.id, mp.nome
        """, (masmorra_id, mapa_id))
        masmorra = cur.fetchone()
        if not masmorra:
            await mostrar_mapa_atlas(alvo, mapa_id, editar=True)
            return

        (nome, mapa, minimo, maximo, xp_por_equipe, tipo_sistema,
         requisitos, observacoes, total_monstros) = masmorra
        cur.execute("""
            SELECT telegram_file_id, telegram_file_unique_id
            FROM masmorra_imagens
            WHERE mapa_id=%s
              AND (masmorra_id=%s OR
                   (masmorra_id IS NULL AND nome_masmorra=%s))
            ORDER BY atualizado_em DESC
            LIMIT 1
        """, (mapa_id, masmorra_id, nome))
        imagem = cur.fetchone()

        xp_por_equipe = xp_por_equipe or {}
        linhas_xp = []
        for quantidade in range(1, 6):
            valor = xp_por_equipe.get(str(quantidade))
            if valor is None:
                valor = xp_por_equipe.get(quantidade)
            if valor is not None:
                linhas_xp.append(
                    f"• {quantidade} jogador{'es' if quantidade != 1 else ''}: "
                    f"{formatar_valor_catalogo(valor)} XP"
                )

        titulo_xp = "XP POR TAMANHO DA EQUIPE"
        if tipo_sistema == "fenda":
            titulo_xp = "XP por completar a Fenda"
            # A recompensa da fenda vem dos monstros vinculados a ela.
            # NULL é desconhecido, enquanto zero é um XP informado válido.
            cur.execute("""
                SELECT COUNT(*), COUNT(xp), SUM(xp)
                FROM catalogo_monstros
                WHERE masmorra_id=%s AND mapa_id=%s
                  AND LOWER(tipo)=LOWER('Masmorra')
            """, (masmorra_id, mapa_id))
            cadastrados, com_xp, soma_xp = cur.fetchone()
            linhas_xp = []
            if com_xp:
                linhas_xp.append(f"• {formatar_valor_catalogo(soma_xp)} XP")
                if com_xp < cadastrados:
                    linhas_xp.append(
                        f"⚠️ Soma parcial: {cadastrados - com_xp} monstro(s) sem XP informado."
                    )

        tipo = {"cripta": "Cripta — sistema especial", "fenda": "Fendas"}.get(tipo_sistema, "Masmorra")
        texto = (
            f"🗝️ {nome.upper()}\n\n"
            f"🗺️ Mapa: {mapa}\n"
            f"🏛️ Tipo: {tipo}\n"
            f"👥 Grupo permitido: {texto_capacidade_masmorra(minimo, maximo)}\n\n"
            f"⭐ {titulo_xp}\n"
            f"{chr(10).join(linhas_xp) if linhas_xp else '• Valores ainda não informados'}"
        )
        if requisitos:
            texto += f"\n\n🔐 Requisito de entrada: {requisitos}"
        if observacoes:
            texto += f"\n\n📝 {observacoes}"

        rotulo_monstros = (
            f"📜 Ver registros atuais ({total_monstros})"
            if tipo_sistema == "cripta"
            else f"👹 Ver monstros ({total_monstros})"
        )
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                rotulo_monstros,
                callback_data=f"atlas_t_{mapa_id}_r{masmorra_id}",
            )],
            [InlineKeyboardButton(
                f"⬅️ {mapa}", callback_data=f"atlas_m_{mapa_id}"
            )],
        ])
        await editar_pagina_biblioteca(
            alvo,
            "atlas",
            texto,
            teclado,
            file_id=imagem[0] if imagem else None,
            file_unique_id=imagem[1] if imagem else None,
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

        titulo_area, masmorra_id = resolver_area_atlas(
            cur, mapa_id, codigo_area
        )
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
                WHERE mapa_id=%s
                  AND (masmorra_id=%s OR
                       (masmorra_id IS NULL AND nome_masmorra=%s))
                ORDER BY atualizado_em DESC
                LIMIT 1
            """, (mapa_id, masmorra_id, titulo_area))
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
            cur.execute("""
                SELECT ordem, id, nome
                FROM catalogo_monstros
                WHERE mapa_id=%s
                  AND LOWER(tipo)=LOWER('Masmorra')
                  AND masmorra_id=%s
                ORDER BY ordem, id
            """, (mapa_id, masmorra_id))
            monstros = cur.fetchall()

        botoes = [
            InlineKeyboardButton(
                nome,
                callback_data=f"atlas_x_{monstro_id}_{mapa_id}_{codigo_area}"
            )
            for ordem, monstro_id, nome in monstros
        ]
        linhas = agrupar_botoes_atlas(botoes)
        if masmorra_id:
            linhas.append([InlineKeyboardButton(
                "⬅️ Resumo da área",
                callback_data=f"atlas_d_{mapa_id}_{masmorra_id}",
            )])
        else:
            linhas.append([InlineKeyboardButton(
                f"⬅️ {nome_mapa}", callback_data=f"atlas_m_{mapa_id}"
            )])
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
                   cm.hp, cm.atk, cm.defesa, cm.xp, cm.gold, cm.drops,
                   d.tipo_sistema, cm.habilidade, cm.sem_habilidade
            FROM catalogo_monstros cm
            JOIN catalogo_mapas mp ON mp.id=cm.mapa_id
            LEFT JOIN catalogo_masmorras d ON d.id=cm.masmorra_id
            WHERE cm.id=%s AND cm.mapa_id=%s
        """, (monstro_id, mapa_id))
        monstro = cur.fetchone()
        if not monstro:
            await mostrar_monstros_atlas(alvo, mapa_id, codigo_area)
            return

        (ordem, nome, mapa, tipo, raridade, hp, atk, defesa, xp, gold,
         drops, sistema, habilidade, sem_habilidade) = monstro
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
        if (tipo or "").lower() == "masmorra" and sistema != "fenda":
            cur.execute("""
                SELECT CASE WHEN boss THEN 0 ELSE andar END AS etapa,
                       MIN(hp_max), MAX(hp_max), COUNT(*)
                FROM masmorra_monstro_observacoes
                WHERE monstro_id=%s AND hp_max IS NOT NULL
                GROUP BY CASE WHEN boss THEN 0 ELSE andar END
                ORDER BY etapa
            """, (monstro_id,))
            observacoes_hp = cur.fetchall()

        hp_principal = (
            "varia por andar"
            if observacoes_hp
            else formatar_valor_catalogo(hp)
        )

        if (raridade or "").lower() == "boss":
            hp_boss = next((row for row in observacoes_hp if row[0] == 0), None)
            if hp_boss:
                hp_principal = str(hp_boss[1]) if hp_boss[1] == hp_boss[2] else f"{hp_boss[1]}–{hp_boss[2]}"
        eh_masmorra = (tipo or "").lower() in {"masmorra", "cripta"}
        texto = (
            f"👹 {nome}\n\n"
            f"🗺️ {mapa}   🏷️ {'Fenda' if sistema == 'fenda' else (tipo or 'a confirmar')}   "
            f"💠 {raridade or 'a confirmar'}\n"
            f"❤️ HP: {hp_principal}   "
            f"⚔️ ATK: {formatar_valor_catalogo(atk)}   "
            f"🛡️ DEF: {formatar_valor_catalogo(defesa)}\n"
        )
        if not eh_masmorra:
            texto += (
                f"⭐ XP: {formatar_valor_catalogo(xp)}   "
                f"💰 Gold: {formatar_valor_catalogo(gold)}\n"
            )
        if eh_masmorra and sistema != "fenda":
            hp_por_andar = {
                andar: (minimo, maximo)
                for andar, minimo, maximo, _ in observacoes_hp
            }
            andares = [0] if (raridade or "").lower() == "boss" else sorted({1, 2, 3, *hp_por_andar})
            texto += "❤️ HP observado na masmorra:\n"
            for andar in andares:
                valores = hp_por_andar.get(andar)
                if not valores:
                    valor = "ainda não observado"
                elif valores[0] == valores[1]:
                    valor = str(valores[0])
                else:
                    valor = f"{valores[0]}–{valores[1]}"
                rotulo = "Boss" if andar == 0 else f"{andar}º andar"
                texto += f"• {rotulo}: {valor}\n"
        if sistema == "fenda" or habilidade or sem_habilidade:
            texto += f"✨ Habilidade: {'Sem habilidade' if sem_habilidade else (habilidade or 'a confirmar')}\n"
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
        elif dados.startswith("atlas_d_"):
            _, _, mapa_id, masmorra_id = dados.split("_")
            await mostrar_resumo_masmorra_atlas(
                query, int(mapa_id), int(masmorra_id)
            )
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
                    cur = conn.cursor()
                    try:
                        masmorra = resolver_masmorra_catalogo(
                            cur, nome_destino, int(mapa_id)
                        ) if nome_destino else None
                    finally:
                        cur.close()
                    if masmorra:
                        codigo_area = f"r{masmorra[0]}"
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

            for monstro in monstros:
                linhas.append(f"• {monstro[1]} — {monstro[2] or 'mapa a confirmar'}")

            linhas.extend(["", "Consulte os detalhes pelos botões em /lib → Atlas ou Criptas."])
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

        eh_masmorra = (tipo or "").lower() in {"masmorra", "cripta"}
        linhas = [
            f"👹 {nome}",
            "",
            f"🗺️ Mapa: {mapa or 'a confirmar'}   🏷️ Tipo: {tipo or 'a confirmar'}   💠 Raridade: {raridade or 'a confirmar'}",
            f"❤️ HP: {formatar_valor_catalogo(hp)}   ⚔️ ATK: {formatar_valor_catalogo(atk)}   🛡️ DEF: {formatar_valor_catalogo(defesa)}",
        ]

        if not eh_masmorra:
            linhas.append(
                f"⭐ XP: {formatar_valor_catalogo(xp)}   "
                f"💰 Gold: {formatar_valor_catalogo(gold)}"
            )

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


async def cmd_site(update, context):
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "Por segurança, confirme o acesso ao site somente no privado."
        )
        return
    if len(context.args) != 1 or not re.fullmatch(r"[A-Z0-9]{8}", context.args[0].upper()):
        await update.message.reply_text(
            "Use /site seguido do código de 8 caracteres mostrado no painel."
        )
        return
    telegram_id = update.effective_user.id
    if not membro_cadastrado(telegram_id):
        await update.message.reply_text(
            "⚠️ O acesso ao site é permitido somente para membros ativos cadastrados."
        )
        return
    codigo = context.args[0].upper()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT permitido, papel FROM site_acessos WHERE telegram_id=%s
        """, (telegram_id,))
        acesso = cur.fetchone()
        if acesso and not acesso[0]:
            await update.message.reply_text(
                "⚠️ Seu acesso ao site está desativado. Fale com a liderança."
            )
            return
        if not acesso:
            cur.execute("""
                INSERT INTO site_acessos (telegram_id, papel, permitido)
                VALUES (%s, 'consulta', TRUE)
                ON CONFLICT (telegram_id) DO NOTHING
            """, (telegram_id,))
        cur.execute("""
            UPDATE site_login_codigos
            SET telegram_id=%s, confirmado_em=CURRENT_TIMESTAMP
            WHERE codigo=%s AND expira_em>CURRENT_TIMESTAMP
              AND confirmado_em IS NULL AND consumido_em IS NULL
        """, (telegram_id, codigo))
        if cur.rowcount != 1:
            conn.rollback()
            await update.message.reply_text(
                "⚠️ Código inválido ou expirado. Gere um novo código no site."
            )
            return
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
    await update.message.reply_text(
        "✅ Identidade confirmada! Volte ao site e clique em ‘Já confirmei’."
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

    cabecalho = [classe_map.get(item['classe'], '')]

    if item.get("nivel"):

        cabecalho.append(f"⭐ Lv {item['nivel']}")

    texto += " · ".join(parte for parte in cabecalho if parte) + "\n"

    if item.get("duas_maos"):

        texto += (
            "⚔ Arma de Duas Mãos\n"
        )

    stats = []

    if item.get("atk_min"):

        stats.append(f"⚔ {item['atk_min']}~{item['atk_max']}")

    if item.get("def_min"):

        stats.append(f"🛡 {item['def_min']}~{item['def_max']}")

    if item.get("hp_min"):

        stats.append(f"❤️ {item['hp_min']}~{item['hp_max']}")

    if item.get("crit_min"):

        stats.append(f"🎯 {float(item['crit_min']):g}~{float(item['crit_max']):g}%")

    if stats:

        texto += "\n" + " · ".join(stats) + "\n"

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

    cur.execute("SELECT to_regclass('public.market_price_observations')")
    if cur.fetchone()[0]:
        cur.execute("""
            SELECT upgrade, COUNT(*) AS anuncios,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
                         (ORDER BY unit_price)::numeric, 2) AS mediana
            FROM market_price_observations
            WHERE catalog_type='item' AND item_id=%s
              AND offer_side='sell' AND price_currency='TOFU'
              AND message_date >= CURRENT_TIMESTAMP - INTERVAL '7 days'
            GROUP BY upgrade
            ORDER BY upgrade NULLS FIRST
        """, (item_id,))
        tendencias = cur.fetchall()
        if tendencias:
            texto += "\n\n📈 Tendência de mercado — 7 dias\n"
            for aprimoramento, anuncios, mediana in tendencias:
                rotulo = "Base" if aprimoramento is None else f"+{aprimoramento}"
                preco = f"{float(mediana):g}"
                texto += f"• {rotulo}: {anuncios} anúncio(s) · mediana {preco} 🧀\n"
            texto += "⚠️ Referência de anúncios; não é preço oficial."


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

    if dados == "lib_criptas":
        context.user_data.pop("biblioteca_busca_msg_id", None)
        await mostrar_inicio_criptas(query)
        return

    if dados.startswith("cripta_monstros_"):
        try:
            numero = int(dados.removeprefix("cripta_monstros_"))
        except ValueError:
            return
        await mostrar_monstros_cripta(query, numero)
        return

    if dados.startswith("cripta_xp_"):
        try:
            numero = int(dados.removeprefix("cripta_xp_"))
        except ValueError:
            return
        await mostrar_consulta_xp_cripta(query, numero)
        return

    if dados.startswith("cripta_run_"):
        try:
            _prefixo, _run, numero, andar = dados.split("_")
            numero, andar = int(numero), int(andar)
        except (ValueError, TypeError):
            return
        await mostrar_resultado_run_cripta(query, numero, andar)
        return

    if dados.startswith("cripta_custom_"):
        try:
            numero = int(dados.removeprefix("cripta_custom_"))
        except ValueError:
            return
        context.user_data["cripta_xp_aguardando"] = numero
        await editar_pagina_biblioteca(
            query, "atlas",
            "🔢 INFORMAR ANDAR DE SAÍDA\n\n"
            "Envie somente o número do andar em que pretende decidir se sai.\n\n"
            "Exemplo: 35",
            InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅ Cancelar", callback_data=f"cripta_xp_{numero}")
            ]]),
        )
        return

    if dados.startswith("cripta_m_"):
        try:
            monstro_id = int(dados.removeprefix("cripta_m_"))
        except ValueError:
            return
        await mostrar_monstro_cripta(query, monstro_id)
        return

    if dados.startswith("cripta_"):
        try:
            numero = int(dados.removeprefix("cripta_"))
        except ValueError:
            return
        await mostrar_cripta(query, numero)
        return

    if dados == "lib_almas":
        context.user_data.pop("biblioteca_busca_msg_id", None)
        await mostrar_inicio_almas(query)
        return

    if dados.startswith("almas_"):
        slug = dados.removeprefix("almas_")
        if slug in ESPECIALIZACOES_ALMAS:
            await mostrar_almas_especializacao(query, slug)
        return

    if dados.startswith("alma_"):
        try:
            alma_id = int(dados.removeprefix("alma_"))
        except ValueError:
            return
        await mostrar_alma(query, alma_id)
        return

    if dados == "lib_buscar":
        context.user_data["biblioteca_busca_msg_id"] = query.message.message_id
        await editar_pagina_biblioteca(
            query,
            "biblioteca",
            "🔎 BUSCAR NA BIBLIOTECA\n\n"
            "Envie o nome de um item, alma, mapa ou monstro.",
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
        CommandHandler("site", cmd_site)
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

