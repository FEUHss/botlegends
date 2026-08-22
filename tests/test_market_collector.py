import asyncio
from decimal import Decimal

from market_collector import normalize_name, parse_market_message, start_market_collector


def test_parses_multiple_tofu_prices_and_upgrades():
    observations = parse_market_message(
        """Vendo
🟠 Varinha de Ossos (+2) 100 🧀
🟠 Grimório das Almas Perdidas (+1) 15 🧀
🟡 Chave das Minas 3 🧀"""
    )

    assert len(observations) == 3
    assert observations[0].item_normalized == "varinha de ossos"
    assert observations[0].upgrade == 2
    assert observations[0].price_amount == Decimal("100")
    assert observations[0].price_currency == "TOFU"
    assert all(item.side == "sell" for item in observations)


def test_parses_gold_scales_and_exchange_unit_price():
    observations = parse_market_message(
        """VENDO TOFU por GOLD
1 TOFU (🧀) por 75k GOLD
50 TOFUs (🧀) por 3.5M GOLD"""
    )

    assert len(observations) == 2
    assert observations[0].price_amount == Decimal("75000")
    assert observations[0].unit_price == Decimal("75000")
    assert observations[1].price_amount == Decimal("3500000.0")
    assert observations[1].unit_price == Decimal("70000.0")


def test_parses_quantity_and_gold_symbol():
    observation = parse_market_message("Vendo\nElixir de Sabedoria x15 9.500 💵")[0]

    assert observation.quantity == Decimal("15")
    assert observation.price_currency == "GOLD"
    assert observation.price_amount == Decimal("9500")
    assert observation.unit_price == Decimal("633.3333333333333333333333333")


def test_ignores_lines_without_explicit_price():
    observations = parse_market_message(
        """Vendo
Machado do Dragão +1
Varinha de Ossos +2
Chama no privado"""
    )
    assert observations == []


def test_keeps_sell_and_buy_blocks_separate_in_same_message():
    observations = parse_market_message(
        """VENDO
Varinha de Ossos 100 🧀
COMPRO
Anel Arcano de Ghurak 80 🧀"""
    )

    assert [item.side for item in observations] == ["sell", "buy"]


def test_normalizes_accents_for_future_catalog_linking():
    assert normalize_name("Lâmina do Dragão Glacial") == "lamina do dragao glacial"


def test_collector_is_disabled_by_default_without_touching_database(monkeypatch):
    monkeypatch.delenv("MARKET_COLLECTOR_ENABLED", raising=False)

    class Application:
        bot_data = {}

    asyncio.run(start_market_collector(Application()))
    assert Application.bot_data == {}

