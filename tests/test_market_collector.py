import asyncio
from decimal import Decimal

from market_collector import (
    normalize_name,
    parse_catalog_market_message,
    parse_market_message,
    resolve_catalog_name,
    start_market_collector,
)


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


def test_parses_multiple_payment_options_and_ignores_energy_potions():
    observations = parse_market_message(
        "🟡 Passos do Sol (+1) Lv32 (DEF+7, HP+5) » 20🧀 / 60🧪 / 300k 💰"
    )
    assert len(observations) == 2
    assert observations[0].item_normalized == "passos do sol"
    assert observations[0].upgrade == 1
    assert observations[0].price_currency == "TOFU"
    assert observations[0].price_amount == Decimal("20")
    assert observations[1].price_currency == "GOLD"
    assert observations[1].price_amount == Decimal("300000")
    assert all(item.side == "sell" for item in observations)


def test_keeps_large_sell_and_buy_sections_separate_with_alternative_prices():
    observations = parse_market_message(
        """VENDA
Maldição da Bruxa » 4🧀 / 12🧪 / 60k 💵
Golpe do Obelisco » 4🧀

COMPRO
Lança Solar » 3🧀 / 200k GOLD"""
    )
    assert [item.side for item in observations] == [
        "sell", "sell", "sell", "buy", "buy"
    ]


def test_normalizes_accents_for_future_catalog_linking():
    assert normalize_name("Lâmina do Dragão Glacial") == "lamina do dragao glacial"


def test_catalog_linking_removes_market_prefixes_without_changing_canonical_name():
    candidates = [
        ("soul", 7, "Fúria do Lobo", "furia do lobo"),
        ("item", 8, "Anel Arcano de Ghurak", "anel arcano de ghurak"),
    ]
    match = resolve_catalog_name(
        "promoção vendo FURIA DO LOBO barato", candidates
    )
    assert match == ("soul", 7, "Fúria do Lobo", "furia do lobo")


def test_catalog_linking_rejects_unknown_product():
    candidates = [("soul", 7, "Fúria do Lobo", "furia do lobo")]
    assert resolve_catalog_name("alma misteriosa nova", candidates) is None


def test_catalog_parser_carries_wrapped_price_until_next_known_item():
    candidates = [
        ("item", 1, "Passos do Sol", "passos do sol"),
        ("soul", 2, "Lança Solar", "lanca solar"),
    ]
    matched = parse_catalog_market_message(
        """VENDA
Passos do Sol (+1) Lv32 (DEF+7, HP+5)
20🧀 / 60🧪 / 300k GOLD
Lança Solar » 4🧀 / 12🧪 / 60k GOLD""",
        candidates,
    )
    assert [(entry[1][2], entry[0].price_currency) for entry in matched] == [
        ("Passos do Sol", "TOFU"),
        ("Passos do Sol", "GOLD"),
        ("Lança Solar", "TOFU"),
        ("Lança Solar", "GOLD"),
    ]


def test_catalog_parser_does_not_attach_price_after_unknown_product_name():
    candidates = [("soul", 2, "Lança Solar", "lanca solar")]
    matched = parse_catalog_market_message(
        "Lança Solar\nItem Desconhecido\n50🧀", candidates
    )
    assert matched == []


def test_catalog_parser_reads_cheese_prices_from_common_sales_list():
    candidates = [
        ("item", 1, "Boots of Haste", "boots of haste"),
        ("item", 2, "Machado do Colosso Solar", "machado do colosso solar"),
        ("item", 3, "Orbe do Eclipse", "orbe do eclipse"),
    ]
    matched = parse_catalog_market_message(
        """VENDO
Boots of Haste Lv22 +0 6🧀
Machado do Colosso Solar +0 5🧀
Orbe do Eclipse Lv32 +0 10🧀""",
        candidates,
    )
    assert [(entry[1][2], entry[0].price_amount, entry[0].price_currency) for entry in matched] == [
        ("Boots of Haste", Decimal("6"), "TOFU"),
        ("Machado do Colosso Solar", Decimal("5"), "TOFU"),
        ("Orbe do Eclipse", Decimal("10"), "TOFU"),
    ]


def test_catalog_parser_interprets_k_without_currency_as_gold():
    candidates = [("item", 1, "Poeira Estelar", "poeira estelar")]
    matched = parse_catalog_market_message("COMPRO POEIRA 70k", candidates)
    observation = matched[0][0]
    assert observation.side == "buy"
    assert observation.price_amount == Decimal("70000")
    assert observation.price_currency == "GOLD"


def test_catalog_parser_shares_each_price_between_pending_souls():
    candidates = [
        ("soul", 1, "Lança Xamânica", "lanca xamanica"),
        ("soul", 2, "Benção do Clã", "bencao do cla"),
        ("soul", 3, "Chama de Guerra", "chama de guerra"),
    ]
    matched = parse_catalog_market_message(
        """VENDO novas almas
Lança Xamânica (lanceiro)
Benção do Clã (mago varinha)
Chama de Guerra (mago cajado)
700🧀 cada""",
        candidates,
    )
    assert len(matched) == 3
    assert all(entry[0].price_amount == Decimal("700") for entry in matched)
    assert all(entry[0].price_currency == "TOFU" for entry in matched)


def test_catalog_parser_accepts_ladder_prefix_after_attribute_line():
    candidates = [("item", 1, "Arco do Ossuário", "arco do ossuario")]
    matched = parse_catalog_market_message(
        """VENDINHA
Arco do Ossuário [Lv28]
10 ATK / 10% CRIT
L-> 8🧀 / 32⚡ / 160k💰""",
        candidates,
    )
    assert [(entry[0].price_amount, entry[0].price_currency) for entry in matched] == [
        (Decimal("8"), "TOFU"),
        (Decimal("160000"), "GOLD"),
    ]


def test_collector_is_disabled_by_default_without_touching_database(monkeypatch):
    monkeypatch.delenv("MARKET_COLLECTOR_ENABLED", raising=False)

    class Application:
        bot_data = {}

    asyncio.run(start_market_collector(Application()))
    assert Application.bot_data == {}

