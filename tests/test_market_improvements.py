from decimal import Decimal as D
from dataclasses import replace
from market_collector import (
    parse_catalog_market_message as parse, MarketObservation,
    _offer_dedupe_key, _looks_like_offer,
)

C=[('item',1,'Anel do Olho Solar','anel do olho solar'),
   ('item',2,'Colar do Eclipse Ritual','colar do eclipse ritual'),
   ('item',3,'Elixir de Sabedoria','elixir de sabedoria'),
   ('item',4,'Poeira Estelar','poeira estelar'),
   ('item',5,'Orbe do Eclipse','orbe do eclipse')]


def test_tier_prices_apply_to_group_not_next_item():
    result=parse('COMPRO\nANEL DO OLHO SOLAR\nCOLAR DO ECLIPSE RITUAL\n+0: 5🧀\n+1: 15🧀\n+2: 150🧀\nElixir de Sabedoria\n10🧀',C)
    assert [(o.upgrade,o.unit_price,c[1]) for o,c in result]==[(0,D(5),1),(0,D(5),2),(1,D(15),1),(1,D(15),2),(2,D(150),1),(2,D(150),2),(None,D(10),3)]
    assert all(o.side=='buy' for o,_ in result)


def test_unit_price_cada_is_not_divided_by_quantity():
    o,_=parse('Vendo Elixir de Sabedoria x15 4🧀 cada',C)[0]
    assert o.quantity==15 and o.unit_price==4


def test_same_line_products_have_independent_prices():
    result=parse('VENDO Anel do Olho Solar +1 20🧀; Orbe do Eclipse +2 100🧀',C)
    assert [(c[1],o.upgrade,o.unit_price) for o,c in result]==[(1,1,D(20)),(5,2,D(100))]


def test_section_change_does_not_leak_pending_item():
    assert parse('VENDO\nAnel do Olho Solar\nCOMPRO\n5🧀',C)==[]


def test_unknown_item_breaks_price_continuation():
    assert parse('VENDO\nAnel do Olho Solar\nSkin desconhecida\n40🧀',C)==[]


def test_gold_k_alias_and_tofu_are_separate():
    candidates=C+[('item',4,'Poeira Estelar','poeira')]
    result=parse('COMPRO POEIRA 70k\nVENDO\nOrbe do Eclipse 10🧀 / 150k 💰',candidates)
    assert [(o.side,o.price_currency,o.unit_price) for o,c in result]==[('buy','GOLD',D(70000)),('sell','TOFU',D(10)),('sell','GOLD',D(150000))]


def test_duplicate_seller_item_currency_upgrade_and_unit_value():
    o=MarketObservation('a','a','sell',D('10'), 'TOFU',D(1),D(10),None,D('.98'))
    key=_offer_dedupe_key(b'secret','123',o,C[0])
    assert key==_offer_dedupe_key(b'secret','123',replace(o,price_amount=D('20.0'),quantity=D(2),upgrade=0),C[0])
    assert key!=_offer_dedupe_key(b'secret','124',o,C[0])
    assert key!=_offer_dedupe_key(b'secret','123',replace(o,upgrade=1),C[0])
    assert key!=_offer_dedupe_key(b'secret','123',replace(o,price_currency='GOLD'),C[0])


def test_real_vendinha_stat_lines_and_other_currency():
    result=parse('VENDINHA\nOrbe do Eclipse [Lv32]\n| 10 ATK / 10% CRIT\nL-> 8🧀 / 32⚡ / 160k💰\nPoeira Estelar x1\nL-> 5🧀 /20⚡ /100k💰',C)
    assert [(c[1],o.unit_price,o.price_currency) for o,c in result]==[(5,D(8),'TOFU'),(5,D(160000),'GOLD'),(4,D(5),'TOFU'),(4,D(100000),'GOLD')]


def test_no_price_means_no_observation():
    assert parse('Vendo\nOrbe do Eclipse Lv32\nChama PV',C)==[]


def test_explicit_trailing_lot_price():
    catalog=[('item',20,'Chave de Masmorra','chave de masmorra')]
    result=parse('COMPRO CHAVE DE MASMORRA PAGO 1🧀 EM 4 CHAVES',catalog)
    assert len(result)==1
    assert result[0][0].quantity==4 and result[0][0].unit_price==D('0.25')


def test_old_dedupe_hash_remains_recognizable():
    from market_collector import _legacy_offer_dedupe_key
    import hashlib, hmac
    o=MarketObservation('a','a','sell',D('10'), 'TOFU',D(1),D(10),None,D('.98'))
    expected=hmac.new(b'secret',b'123|item|1||1|sell|10|TOFU',hashlib.sha256).hexdigest()
    assert _legacy_offer_dedupe_key(b'secret','123',o,C[0])==expected


def test_kk_is_one_million_gold_and_plural_catalog_name_resolves():
    result = parse('Vendo 11 poeiras por 1kk', C)
    assert len(result) == 1
    observation, catalog = result[0]
    assert catalog[1] == 4
    assert observation.price_currency == 'GOLD'
    assert observation.price_amount == D(1_000_000)
    assert observation.unit_price == D(1_000_000) / 11


def test_market_chatter_is_not_counted_as_failed_offer():
    assert not _looks_like_offer('No site', [], [])
    assert not _looks_like_offer('Vendo', [], [])
    assert _looks_like_offer('Vendo item raro, chamar no privado', [], [])
