-- Additive extensions: never reseed or rewrite the curated catalog.
CREATE TABLE IF NOT EXISTS catalogo_skins (
 id BIGSERIAL PRIMARY KEY, nome TEXT NOT NULL,
 classe TEXT NOT NULL DEFAULT 'Todas', variante TEXT,
 obtencao TEXT, confirmado BOOLEAN NOT NULL DEFAULT FALSE,
 ativo BOOLEAN NOT NULL DEFAULT TRUE,
 telegram_file_id TEXT, telegram_file_unique_id TEXT,
 atualizado_por TEXT, atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS skins_nome_unique ON catalogo_skins(lower(nome));
CREATE UNIQUE INDEX IF NOT EXISTS skins_photo_unique ON catalogo_skins(telegram_file_unique_id)
 WHERE telegram_file_unique_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS skin_requisitos (
 masmorra_id BIGINT NOT NULL REFERENCES catalogo_masmorras(id) ON DELETE CASCADE,
 skin_id BIGINT NOT NULL REFERENCES catalogo_skins(id),
 grupo INTEGER NOT NULL CHECK(grupo BETWEEN 1 AND 10),
 confirmado BOOLEAN NOT NULL DEFAULT FALSE,
 PRIMARY KEY(masmorra_id,skin_id)
);
CREATE TABLE IF NOT EXISTS skin_photo_pending (
 token TEXT PRIMARY KEY, telegram_id BIGINT NOT NULL,
 file_id TEXT NOT NULL, file_unique_id TEXT NOT NULL,
 skin_id BIGINT REFERENCES catalogo_skins(id),
 expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '30 minutes',
 consumed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS library_saved (
 telegram_id BIGINT NOT NULL, target TEXT NOT NULL,
 favorite BOOLEAN NOT NULL DEFAULT FALSE,
 visited_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(telegram_id,target)
);
CREATE TABLE IF NOT EXISTS catalog_hp_review (
 -- Keep review history even if an administrator later deletes the monster.
 id BIGSERIAL PRIMARY KEY, monstro_id BIGINT NOT NULL,
 previous_hp INTEGER, observed_hp INTEGER NOT NULL CHECK(observed_hp>0),
 submitted_by BIGINT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), decided_at TIMESTAMPTZ,
 UNIQUE(monstro_id,observed_hp,status)
);
CREATE TABLE IF NOT EXISTS catalog_contributions (
 id BIGSERIAL PRIMARY KEY, entity TEXT NOT NULL, entity_id BIGINT NOT NULL,
 actor TEXT NOT NULL, action TEXT NOT NULL, details JSONB NOT NULL DEFAULT '{}',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
