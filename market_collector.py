import asyncio
import hashlib
import hmac
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import psycopg2
from telethon import TelegramClient, events
from telethon.sessions import StringSession


DEFAULT_MARKET_CHAT_ID = -1003529877508
DEFAULT_MARKET_TOPIC_ID = 67


@dataclass(frozen=True)
class MarketObservation:
    item_name: str
    item_normalized: str
    side: str
    price_amount: Decimal
    price_currency: str
    quantity: Decimal
    unit_price: Decimal
    upgrade: int | None
    confidence: Decimal


PRICE_RE = re.compile(
    r"(?P<amount>\d+(?:[.,]\d{1,3})?)\s*"
    r"(?P<scale>k|mil|m|milh(?:ao|ão|oes|ões)?)?\s*"
    r"(?P<currency>🧀|tf|tofu?s?|tufu?s?|gold|ouro|💵|💰|🪙)\s*"
    r"(?:cada)?",
    re.IGNORECASE,
)
BARE_PRICE_RE = re.compile(
    r"(?:^|[\s=»:\-]|\))(?P<amount>\d+(?:[.,]\d{1,3})?)\s*"
    r"(?P<scale>k|mil|m)?\s*(?:cada|\(?\s*s[oó]\s+tofu\s*\)?)?\s*$",
    re.IGNORECASE,
)
PRICE_LADDER_RE = re.compile(
    r"^\s*l\s*[-=]*>\s*(?P<tofu>\d+(?:[.,]\d+)?)\s*/\s*"
    r"\d+(?:[.,]\d+)?\s*/\s*"
    r"(?P<gold>\d+(?:[.,]\d+)?)\s*(?P<gold_scale>k|mil|m)?\s*$",
    re.IGNORECASE,
)
EXCHANGE_RE = re.compile(
    r"(?P<quantity>\d+)\s*tofu?s?.*?por\s*"
    r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<scale>k|mil|m)?\s*gold",
    re.IGNORECASE,
)
UPGRADE_RE = re.compile(r"(?<!\w)\+(?P<upgrade>\d+)\b")
QUANTITY_RE = re.compile(r"(?:\bx\s*(?P<after>\d+)\b|\b(?P<before>\d+)\s*x\b)", re.IGNORECASE)


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value).strip().lower()
    return re.sub(r"\s+", " ", value)


def _decimal_number(raw: str, scale: str | None) -> Decimal:
    normalized_scale = normalize_name(scale or "")
    raw = raw.strip()
    if normalized_scale:
        value = Decimal(raw.replace(",", "."))
    elif re.fullmatch(r"\d+[.,]\d{3}", raw):
        value = Decimal(raw.replace(".", "").replace(",", ""))
    else:
        value = Decimal(raw.replace(",", "."))

    if normalized_scale in {"k", "mil"}:
        value *= 1000
    elif normalized_scale in {"m", "milhao", "milhoes"}:
        value *= 1_000_000
    return value


def _currency(token: str) -> str:
    token_normalized = normalize_name(token)
    if token in {"🧀"} or token_normalized in {"tf", "tofu", "tofus", "tufu", "tufus"}:
        return "TOFU"
    return "GOLD"


def _side_from_text(text: str, fallback: str = "unknown") -> str:
    normalized = normalize_name(text)
    if re.search(r"\b(compro|comprando|procuro)\b", normalized):
        return "buy"
    if re.search(r"\b(troco|troca)\b", normalized):
        return "trade"
    if re.search(r"\b(vendo|venda|vendinha|negocio)\b", normalized):
        return "sell"
    return fallback


def _clean_item_name(raw: str) -> tuple[str, int | None, Decimal]:
    raw = re.sub(r"^[^\wÀ-ÿ]+", "", raw).strip()
    raw = re.sub(r"^(vendo|compro|troco|negocio)\s*[:~-]*\s*", "", raw, flags=re.IGNORECASE)
    upgrade_match = UPGRADE_RE.search(raw)
    upgrade = int(upgrade_match.group("upgrade")) if upgrade_match else None

    quantity_match = QUANTITY_RE.search(raw)
    quantity = Decimal(quantity_match.group("after") or quantity_match.group("before")) if quantity_match else Decimal(1)

    raw = QUANTITY_RE.sub("", raw)
    raw = re.sub(r"\[\s*lv\s*\d+[^\]]*\]", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\blv\s*\d+\b", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\((?!\+?\d+\))[^)]*(?:atk|def|hp|crit|lv)[^)]*\)", "", raw, flags=re.IGNORECASE)
    raw = UPGRADE_RE.sub("", raw)
    raw = re.sub(r"\s*[-–—:]\s*$", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" -–—:~")
    return raw, upgrade, quantity


def parse_market_message(text: str) -> list[MarketObservation]:
    if not text or not text.strip():
        return []

    observations: list[MarketObservation] = []
    # O tipo acompanha cada bloco da mensagem. Não usamos o texto inteiro como
    # ponto de partida porque um mesmo anúncio pode conter VENDO e COMPRO.
    current_side = "unknown"

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        line_side = _side_from_text(line, current_side)
        if line_side != "unknown":
            current_side = line_side

        exchange = EXCHANGE_RE.search(line)
        if exchange:
            try:
                quantity = Decimal(exchange.group("quantity"))
                amount = _decimal_number(exchange.group("amount"), exchange.group("scale"))
            except (InvalidOperation, ValueError):
                continue
            observations.append(
                MarketObservation(
                    item_name="Tofu",
                    item_normalized="tofu",
                    side=current_side,
                    price_amount=amount,
                    price_currency="GOLD",
                    quantity=quantity,
                    unit_price=amount / quantity,
                    upgrade=None,
                    confidence=Decimal("0.98"),
                )
            )
            continue

        prices = list(PRICE_RE.finditer(line))
        if not prices:
            continue

        item_name, upgrade, quantity = _clean_item_name(line[: prices[0].start()])
        item_normalized = normalize_name(item_name)
        if len(item_normalized) < 3 or item_normalized in {
            "armas",
            "armaduras",
            "almas",
            "consumiveis",
            "joias",
            "cada",
        }:
            continue

        # Sem cabeçalho, item + preço é uma oferta de venda. Um cabeçalho
        # COMPRO/TROCO continua valendo até o próximo bloco explícito.
        effective_side = current_side if current_side != "unknown" else "sell"
        for price in prices:
            try:
                amount = _decimal_number(price.group("amount"), price.group("scale"))
            except (InvalidOperation, ValueError):
                continue

            observations.append(
                MarketObservation(
                    item_name=item_name,
                    item_normalized=item_normalized,
                    side=effective_side,
                    price_amount=amount,
                    price_currency=_currency(price.group("currency")),
                    quantity=quantity,
                    unit_price=amount / quantity,
                    upgrade=upgrade,
                    confidence=Decimal("0.95"),
                )
            )

    return observations


def message_topic_id(message) -> int | None:
    reply = getattr(message, "reply_to", None)
    if reply is None:
        return None
    return getattr(reply, "reply_to_top_id", None) or getattr(reply, "reply_to_msg_id", None)


MARKET_DDL = """
CREATE TABLE IF NOT EXISTS market_messages (
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    topic_id BIGINT NOT NULL,
    message_date TIMESTAMPTZ NOT NULL,
    edited_at TIMESTAMPTZ,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content_sha256 TEXT NOT NULL,
    offer_kind TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    parsed_items INTEGER NOT NULL DEFAULT 0,
    raw_text TEXT,
    raw_text_expires_at TIMESTAMPTZ,
    PRIMARY KEY (chat_id, message_id)
);

ALTER TABLE market_messages ADD COLUMN IF NOT EXISTS raw_text TEXT;
ALTER TABLE market_messages ADD COLUMN IF NOT EXISTS raw_text_expires_at TIMESTAMPTZ;
ALTER TABLE market_messages ADD COLUMN IF NOT EXISTS detected_items INTEGER NOT NULL DEFAULT 0;
ALTER TABLE market_messages ADD COLUMN IF NOT EXISTS unmatched_items INTEGER NOT NULL DEFAULT 0;
ALTER TABLE market_messages ADD COLUMN IF NOT EXISTS deduped_items INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS market_price_observations (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    item_index INTEGER NOT NULL,
    item_id BIGINT,
    soul_id BIGINT,
    catalog_type TEXT,
    item_name TEXT NOT NULL,
    item_normalized TEXT NOT NULL,
    upgrade INTEGER,
    quantity NUMERIC NOT NULL DEFAULT 1,
    offer_side TEXT NOT NULL,
    price_amount NUMERIC NOT NULL,
    price_currency TEXT NOT NULL,
    unit_price NUMERIC NOT NULL,
    confidence NUMERIC NOT NULL,
    message_date TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (chat_id, message_id, item_index),
    FOREIGN KEY (chat_id, message_id)
        REFERENCES market_messages(chat_id, message_id)
        ON DELETE CASCADE
);

ALTER TABLE market_price_observations ADD COLUMN IF NOT EXISTS soul_id BIGINT;
ALTER TABLE market_price_observations ADD COLUMN IF NOT EXISTS catalog_type TEXT;
ALTER TABLE market_price_observations ADD COLUMN IF NOT EXISTS dedupe_key TEXT;

CREATE INDEX IF NOT EXISTS idx_market_price_item
ON market_price_observations (item_normalized, upgrade, price_currency, message_date DESC);

CREATE INDEX IF NOT EXISTS idx_market_price_date
ON market_price_observations (message_date DESC);

CREATE INDEX IF NOT EXISTS idx_market_price_dedupe
ON market_price_observations (dedupe_key, message_date DESC)
WHERE dedupe_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_market_raw_text_expiry
ON market_messages (raw_text_expires_at)
WHERE raw_text IS NOT NULL;
"""


def _initialize_market_schema(database_url: str) -> None:
    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(MARKET_DDL)


def _catalog_candidates(cursor) -> list[tuple[str, int, str, str]]:
    """Retorna somente nomes administrados pela Biblioteca Legends."""
    candidates: list[tuple[str, int, str, str]] = []
    cursor.execute("SELECT id, nome FROM itens_legends")
    candidates.extend(
        ("item", row_id, name, normalize_name(name))
        for row_id, name in cursor.fetchall()
    )
    cursor.execute("SELECT id, nome FROM almas_legends")
    candidates.extend(
        ("soul", row_id, name, normalize_name(name))
        for row_id, name in cursor.fetchall()
    )
    return candidates


def resolve_catalog_name(
    detected_name: str,
    candidates: list[tuple[str, int, str, str]],
) -> tuple[str, int, str, str] | None:
    """Faz correspondência conservadora: exata ou nome canônico inteiro."""
    detected = normalize_name(detected_name)
    exact = [candidate for candidate in candidates if candidate[3] == detected]
    if len(exact) == 1:
        return exact[0]

    padded = f" {detected} "
    contained = [
        candidate for candidate in candidates
        if f" {candidate[3]} " in padded
    ]
    if not contained:
        ignored = {
            "vendo", "venda", "vendinha", "compro", "comprando", "procuro",
            "troco", "troca", "negocio", "promo", "promocao", "item", "itens",
            "alma", "almas", "cada", "por", "lv", "atk", "def", "hp", "crit",
            "tf", "tofu", "tofus", "gold", "ouro",
        }

        def token_key(token: str) -> str:
            token = {"hydra": "hidra"}.get(token, token)
            if len(token) > 4 and token.endswith("s"):
                token = token[:-1]
            return token

        detected_tokens = {
            token_key(token)
            for token in detected.split()
            if token not in ignored and not any(char.isdigit() for char in token)
        }
        if not detected_tokens:
            return None
        abbreviated = []
        for candidate in candidates:
            candidate_tokens = {token_key(token) for token in candidate[3].split()}
            if detected_tokens.issubset(candidate_tokens):
                abbreviated.append(candidate)
        return abbreviated[0] if len(abbreviated) == 1 else None
    longest = max(len(candidate[3]) for candidate in contained)
    winners = [candidate for candidate in contained if len(candidate[3]) == longest]
    return winners[0] if len(winners) == 1 else None


def _observations_for_prices(
    item_name: str,
    upgrade: int | None,
    quantity: Decimal,
    side: str,
    text: str,
) -> list[MarketObservation]:
    observations = []
    for price in PRICE_RE.finditer(text):
        try:
            amount = _decimal_number(price.group("amount"), price.group("scale"))
        except (InvalidOperation, ValueError):
            continue
        observations.append(MarketObservation(
            item_name=item_name,
            item_normalized=normalize_name(item_name),
            side=side if side != "unknown" else "sell",
            price_amount=amount,
            price_currency=_currency(price.group("currency")),
            quantity=quantity,
            unit_price=amount / quantity,
            upgrade=upgrade,
            confidence=Decimal("0.98"),
        ))
    return observations


def _implicit_prices(
    item_name: str,
    upgrade: int | None,
    quantity: Decimal,
    side: str,
    text: str,
) -> list[MarketObservation]:
    """Fallback conservador para preço sem emoji após item canônico."""
    ladder = PRICE_LADDER_RE.match(text)
    values: list[tuple[Decimal, str]] = []
    if ladder:
        values = [
            (_decimal_number(ladder.group("tofu"), None), "TOFU"),
            (_decimal_number(ladder.group("gold"), ladder.group("gold_scale")), "GOLD"),
        ]
    else:
        match = BARE_PRICE_RE.search(text)
        if not match:
            return []
        scale = match.group("scale")
        amount = _decimal_number(match.group("amount"), scale)
        if amount <= 0:
            return []
        # No vocabulário do Market, "70k" significa 70.000 Gold.
        # Número nu após um item canônico é o fallback de preço em Tofu.
        values = [(amount, "GOLD" if scale else "TOFU")]

    effective_side = side if side != "unknown" else "sell"
    return [
        MarketObservation(
            item_name=item_name,
            item_normalized=normalize_name(item_name),
            side=effective_side,
            price_amount=amount,
            price_currency=currency,
            quantity=quantity,
            unit_price=amount / quantity,
            upgrade=upgrade,
            confidence=Decimal("0.90"),
        )
        for amount, currency in values
    ]


def parse_catalog_market_message(
    text: str,
    candidates: list[tuple[str, int, str, str]],
) -> list[tuple[MarketObservation, tuple[str, int, str, str]]]:
    """Usa nomes canônicos como delimitadores e aceita preços continuados."""
    results = []
    current_side = "unknown"
    pending_catalogs = []

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        line_side = _side_from_text(line, current_side)
        if line_side != "unknown":
            current_side = line_side

        catalog = resolve_catalog_name(line, candidates)
        prices = list(PRICE_RE.finditer(line))
        if catalog:
            prefix = line[:prices[0].start()] if prices else line
            _, upgrade, quantity = _clean_item_name(prefix)
            parsed = _observations_for_prices(
                catalog[2], upgrade, quantity, current_side, line
            )
            if not parsed:
                parsed = _implicit_prices(
                    catalog[2], upgrade, quantity, current_side, line
                )
            if parsed:
                pending_catalogs = []
                results.extend((observation, catalog) for observation in parsed)
            else:
                pending_catalogs.append((catalog, upgrade, quantity))
            continue

        if prices and pending_catalogs:
            prefix = line[:prices[0].start()]
            # Uma continuação válida contém apenas separadores/números antes
            # do preço. Texto desconhecido indica o começo de outro produto.
            prefix_words = normalize_name(prefix)
            if not prefix_words or prefix_words in {"ou", "por", "cada", "por apenas"}:
                for pending_catalog, upgrade, quantity in pending_catalogs:
                    parsed = _observations_for_prices(
                        pending_catalog[2], upgrade, quantity, current_side, line
                    )
                    results.extend((observation, pending_catalog) for observation in parsed)
                pending_catalogs = []
                continue
            pending_catalogs = []
            continue

        if pending_catalogs:
            implicit = []
            for pending_catalog, upgrade, quantity in pending_catalogs:
                parsed = _implicit_prices(
                    pending_catalog[2], upgrade, quantity, current_side, line
                )
                implicit.extend((observation, pending_catalog) for observation in parsed)
            if implicit:
                results.extend(implicit)
                pending_catalogs = []
                continue

        normalized_line = normalize_name(line)
        is_heading = normalized_line in {
            "venda", "vendo", "compro", "compra", "troco", "trocas",
            "almas", "itens", "consumiveis", "armas", "armaduras", "joias",
        }
        is_metadata = bool(re.search(r"\b(atk|def|hp|crit|nivel|lv)\b", normalized_line))
        if normalized_line and not is_heading and not is_metadata and not prices:
            # Não carregamos um item anterior através de um nome/descritivo
            # desconhecido: isso evita atribuições silenciosas incorretas.
            pending_catalogs = []

    return results


def _offer_dedupe_key(
    secret: bytes,
    seller_key: str | None,
    observation: MarketObservation,
    catalog: tuple[str, int, str, str],
) -> str | None:
    if not seller_key:
        return None
    payload = "|".join((
        seller_key,
        catalog[0],
        str(catalog[1]),
        str(observation.upgrade if observation.upgrade is not None else ""),
        str(observation.quantity),
        observation.side,
        str(observation.price_amount),
        observation.price_currency,
    ))
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _persist_message(
    database_url: str,
    chat_id: int,
    topic_id: int,
    message_id: int,
    message_date: datetime,
    edited_at: datetime | None,
    text: str,
    observations: list[MarketObservation],
    seller_key: str | None = None,
    dedupe_secret: bytes = b"",
) -> tuple[int, int]:
    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
    offer_kind = observations[0].side if observations else _side_from_text(text)
    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            candidates = _catalog_candidates(cursor)
            matched = []
            unmatched_generic = 0
            for observation in observations:
                catalog = resolve_catalog_name(observation.item_name, candidates)
                if catalog:
                    matched.append((observation, catalog))
                else:
                    unmatched_generic += 1

            matched.extend(parse_catalog_market_message(text, candidates))
            unique_matched = []
            seen = set()
            for observation, catalog in matched:
                key = (
                    catalog[0], catalog[1], observation.upgrade,
                    observation.quantity, observation.side,
                    observation.price_amount, observation.price_currency,
                )
                if key not in seen:
                    seen.add(key)
                    unique_matched.append((observation, catalog))
            matched = unique_matched

            unmatched_count = unmatched_generic
            detected_count = max(len(observations), len(matched) + unmatched_count)
            if not detected_count:
                parse_status = "no_price"
            elif not matched:
                parse_status = "unmatched_item"
            elif unmatched_count:
                parse_status = "partial"
            else:
                parse_status = "parsed"

            cursor.execute(
                """
                INSERT INTO market_messages (
                    chat_id, message_id, topic_id, message_date, edited_at,
                    content_sha256, offer_kind, parse_status, parsed_items,
                    raw_text, raw_text_expires_at, detected_items, unmatched_items
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chat_id, message_id) DO UPDATE SET
                    topic_id = EXCLUDED.topic_id,
                    message_date = EXCLUDED.message_date,
                    edited_at = EXCLUDED.edited_at,
                    observed_at = CURRENT_TIMESTAMP,
                    content_sha256 = EXCLUDED.content_sha256,
                    offer_kind = EXCLUDED.offer_kind,
                    parse_status = EXCLUDED.parse_status,
                    parsed_items = EXCLUDED.parsed_items,
                    raw_text = EXCLUDED.raw_text,
                    raw_text_expires_at = EXCLUDED.raw_text_expires_at,
                    detected_items = EXCLUDED.detected_items,
                    unmatched_items = EXCLUDED.unmatched_items
                """,
                (
                    chat_id,
                    message_id,
                    topic_id,
                    message_date,
                    edited_at,
                    fingerprint,
                    offer_kind,
                    parse_status,
                    len(matched),
                    text[:4000],
                    datetime.now(timezone.utc) + timedelta(days=7),
                    detected_count,
                    unmatched_count,
                ),
            )
            cursor.execute(
                "DELETE FROM market_price_observations WHERE chat_id = %s AND message_id = %s",
                (chat_id, message_id),
            )
            accepted = []
            deduped_count = 0
            for observation, catalog in matched:
                dedupe_key = _offer_dedupe_key(
                    dedupe_secret, seller_key, observation, catalog
                ) if dedupe_secret else None
                if dedupe_key:
                    cursor.execute(
                        """SELECT 1 FROM market_price_observations
                        WHERE dedupe_key=%s
                          AND message_date >= %s - INTERVAL '7 days'
                        LIMIT 1""",
                        (dedupe_key, message_date),
                    )
                    if cursor.fetchone():
                        deduped_count += 1
                        continue
                accepted.append((observation, catalog, dedupe_key))

            if matched and not accepted:
                parse_status = "duplicate"
            elif accepted and unmatched_count:
                parse_status = "partial"
            elif accepted:
                parse_status = "parsed"

            cursor.execute(
                """UPDATE market_messages
                SET parse_status=%s, parsed_items=%s, deduped_items=%s
                WHERE chat_id=%s AND message_id=%s""",
                (parse_status, len(accepted), deduped_count, chat_id, message_id),
            )

            for index, (observation, catalog, dedupe_key) in enumerate(accepted):
                catalog_type, catalog_id, canonical_name, canonical_normalized = catalog
                item_id = catalog_id if catalog_type == "item" else None
                soul_id = catalog_id if catalog_type == "soul" else None
                cursor.execute(
                    """
                    INSERT INTO market_price_observations (
                        chat_id, message_id, item_index, item_id, soul_id,
                        catalog_type, item_name,
                        item_normalized, upgrade, quantity, offer_side,
                        price_amount, price_currency, unit_price, confidence,
                        message_date, dedupe_key
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        chat_id,
                        message_id,
                        index,
                        item_id,
                        soul_id,
                        catalog_type,
                        canonical_name,
                        canonical_normalized,
                        observation.upgrade,
                        observation.quantity,
                        observation.side,
                        observation.price_amount,
                        observation.price_currency,
                        observation.unit_price,
                        observation.confidence,
                        message_date,
                        dedupe_key,
                    ),
                )
            cursor.execute(
                """UPDATE market_messages
                SET raw_text=NULL, raw_text_expires_at=NULL
                WHERE raw_text IS NOT NULL
                  AND raw_text_expires_at < CURRENT_TIMESTAMP"""
            )
            return len(accepted), deduped_count


async def start_market_collector(application) -> None:
    enabled = os.getenv("MARKET_COLLECTOR_ENABLED", "false").lower() in {"1", "true", "yes"}
    if not enabled:
        print("5 - Coletor do Market desativado")
        return

    database_url = os.getenv("DATABASE_URL")
    api_id = os.getenv("TELETHON_API_ID")
    api_hash = os.getenv("TELETHON_API_HASH")
    session = os.getenv("TELETHON_SESSION")
    if not all((database_url, api_id, api_hash, session)):
        print("5 - Coletor do Market sem credenciais; bot continuará normalmente")
        return

    try:
        client = TelegramClient(StringSession(session), int(api_id), api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            print("5 - Sessão Telethon não autorizada; bot continuará normalmente")
            await client.disconnect()
            return

        await asyncio.to_thread(_initialize_market_schema, database_url)
        chat_id = int(os.getenv("MARKET_CHAT_ID", str(DEFAULT_MARKET_CHAT_ID)))
        topic_id = int(os.getenv("MARKET_TOPIC_ID", str(DEFAULT_MARKET_TOPIC_ID)))
        dedupe_seed = os.getenv("MARKET_DEDUPE_SECRET") or api_hash
        dedupe_secret = hashlib.sha256(
            f"market-dedupe:{dedupe_seed}".encode("utf-8")
        ).digest()

        async def persist_telegram_message(message) -> None:
            try:
                if message_topic_id(message) != topic_id:
                    return
                text = message.raw_text or ""
                observations = parse_market_message(text)
                message_date = message.date or datetime.now(timezone.utc)
                accepted_count, deduped_count = await asyncio.to_thread(
                    _persist_message,
                    database_url,
                    chat_id,
                    topic_id,
                    message.id,
                    message_date,
                    message.edit_date,
                    text,
                    observations,
                    str(getattr(message, "sender_id", "") or "") or None,
                    dedupe_secret,
                )
                print(
                    f"MARKET coletado message_id={message.id} "
                    f"precos_aceitos={accepted_count} "
                    f"repetidos_ignorados={deduped_count}"
                )
            except Exception as error:
                print(
                    "MARKET falhou ao processar uma mensagem sem interromper o bot: "
                    f"{type(error).__name__}: {error}"
                )

        async def collect(event) -> None:
            await persist_telegram_message(event.message)

        async def backfill_recent_market() -> None:
            limit = max(0, min(int(os.getenv("MARKET_BACKFILL_LIMIT", "500")), 2000))
            if not limit:
                return
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            processed = 0
            try:
                async for message in client.iter_messages(
                    chat_id, reply_to=topic_id, limit=limit
                ):
                    message_date = message.date or datetime.now(timezone.utc)
                    if message_date < cutoff:
                        break
                    await persist_telegram_message(message)
                    processed += 1
                print(f"5 - Backfill do Market concluído mensagens={processed}")
            except Exception as error:
                print(
                    "5 - Backfill do Market falhou sem interromper o monitoramento: "
                    f"{type(error).__name__}: {error}"
                )

        client.add_event_handler(collect, events.NewMessage(chats=chat_id))
        client.add_event_handler(collect, events.MessageEdited(chats=chat_id))
        application.bot_data["market_telethon_client"] = client
        application.bot_data["market_backfill_task"] = asyncio.create_task(
            backfill_recent_market()
        )
        print(f"5 - Coletor do Market ativo chat={chat_id} tópico={topic_id}")
    except Exception as error:
        print(f"5 - Coletor do Market falhou sem interromper o bot: {type(error).__name__}: {error}")


async def stop_market_collector(application) -> None:
    backfill_task = application.bot_data.pop("market_backfill_task", None)
    if backfill_task is not None and not backfill_task.done():
        backfill_task.cancel()
    client = application.bot_data.pop("market_telethon_client", None)
    if client is not None:
        await client.disconnect()

