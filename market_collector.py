import asyncio
import hashlib
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
    r"(?P<currency>🧀|tf|tofu?s?|tufu?s?|gold|ouro|💵)\s*"
    r"(?:cada)?\s*$",
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
    if re.search(r"\b(troco|troca|negocio)\b", normalized):
        return "trade"
    if re.search(r"\b(vendo|venda|vendinha)\b", normalized):
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

        price = PRICE_RE.search(line)
        if not price:
            continue

        item_name, upgrade, quantity = _clean_item_name(line[: price.start()])
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

        try:
            amount = _decimal_number(price.group("amount"), price.group("scale"))
        except (InvalidOperation, ValueError):
            continue

        observations.append(
            MarketObservation(
                item_name=item_name,
                item_normalized=item_normalized,
                side=current_side,
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

CREATE TABLE IF NOT EXISTS market_price_observations (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    item_index INTEGER NOT NULL,
    item_id BIGINT,
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

CREATE INDEX IF NOT EXISTS idx_market_price_item
ON market_price_observations (item_normalized, upgrade, price_currency, message_date DESC);

CREATE INDEX IF NOT EXISTS idx_market_price_date
ON market_price_observations (message_date DESC);

CREATE INDEX IF NOT EXISTS idx_market_raw_text_expiry
ON market_messages (raw_text_expires_at)
WHERE raw_text IS NOT NULL;
"""


def _initialize_market_schema(database_url: str) -> None:
    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(MARKET_DDL)


def _persist_message(
    database_url: str,
    chat_id: int,
    topic_id: int,
    message_id: int,
    message_date: datetime,
    edited_at: datetime | None,
    text: str,
    observations: list[MarketObservation],
) -> None:
    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
    offer_kind = observations[0].side if observations else _side_from_text(text)
    parse_status = "parsed" if observations else "no_price"

    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO market_messages (
                    chat_id, message_id, topic_id, message_date, edited_at,
                    content_sha256, offer_kind, parse_status, parsed_items,
                    raw_text, raw_text_expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    raw_text_expires_at = EXCLUDED.raw_text_expires_at
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
                    len(observations),
                    text[:4000],
                    datetime.now(timezone.utc) + timedelta(days=7),
                ),
            )
            cursor.execute(
                "DELETE FROM market_price_observations WHERE chat_id = %s AND message_id = %s",
                (chat_id, message_id),
            )
            for index, observation in enumerate(observations):
                cursor.execute(
                    """
                    INSERT INTO market_price_observations (
                        chat_id, message_id, item_index, item_name,
                        item_normalized, upgrade, quantity, offer_side,
                        price_amount, price_currency, unit_price, confidence,
                        message_date
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chat_id,
                        message_id,
                        index,
                        observation.item_name,
                        observation.item_normalized,
                        observation.upgrade,
                        observation.quantity,
                        observation.side,
                        observation.price_amount,
                        observation.price_currency,
                        observation.unit_price,
                        observation.confidence,
                        message_date,
                    ),
                )
            cursor.execute(
                """UPDATE market_messages
                SET raw_text=NULL, raw_text_expires_at=NULL
                WHERE raw_text IS NOT NULL
                  AND raw_text_expires_at < CURRENT_TIMESTAMP"""
            )


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

        async def collect(event) -> None:
            try:
                message = event.message
                if message_topic_id(message) != topic_id:
                    return
                text = message.raw_text or ""
                observations = parse_market_message(text)
                message_date = message.date or datetime.now(timezone.utc)
                await asyncio.to_thread(
                    _persist_message,
                    database_url,
                    chat_id,
                    topic_id,
                    message.id,
                    message_date,
                    message.edit_date,
                    text,
                    observations,
                )
                print(
                    f"MARKET coletado message_id={message.id} "
                    f"itens={len(observations)} "
                    f"status={'parsed' if observations else 'no_price'}"
                )
            except Exception as error:
                print(
                    "MARKET falhou ao processar uma mensagem sem interromper o bot: "
                    f"{type(error).__name__}: {error}"
                )

        client.add_event_handler(collect, events.NewMessage(chats=chat_id))
        client.add_event_handler(collect, events.MessageEdited(chats=chat_id))
        application.bot_data["market_telethon_client"] = client
        print(f"5 - Coletor do Market ativo chat={chat_id} tópico={topic_id}")
    except Exception as error:
        print(f"5 - Coletor do Market falhou sem interromper o bot: {type(error).__name__}: {error}")


async def stop_market_collector(application) -> None:
    client = application.bot_data.pop("market_telethon_client", None)
    if client is not None:
        await client.disconnect()

