import asyncio
from unittest.mock import MagicMock,AsyncMock
from types import SimpleNamespace as NS
import library_extensions as lib


def test_legacy_context_match_accepts_accents_and_only_unique_names():
    rows=[(1,'Pântano'),(2,'Deserto Escaldante')]
    assert lib._unique_catalog_match('pantano',rows)==rows[0]
    assert lib._unique_catalog_match('Obtido no Deserto Escaldante',rows)==rows[1]


def test_legacy_context_match_rejects_ambiguous_partial_names():
    rows=[(1,'Hydra'),(2,'Hydra Maior')]
    assert lib._unique_catalog_match('Hydra Maior',rows)==rows[1]
    assert lib._unique_catalog_match('Hydra Maior e Hydra',rows) is None


def test_known_hp_creates_review_without_overwriting():
    cur=MagicMock();cur.fetchone.return_value=(100,)
    assert lib.observe_fixed_hp(cur,42,200,7)
    sql='\n'.join(c.args[0] for c in cur.execute.call_args_list)
    assert 'INSERT INTO catalog_hp_review' in sql and 'UPDATE catalogo_monstros' not in sql
    assert 'WHERE NOT EXISTS' in sql


def test_first_hp_is_filled_and_attributed():
    cur=MagicMock();cur.fetchone.return_value=(None,)
    assert not lib.observe_fixed_hp(cur,42,200,7)
    sql='\n'.join(c.args[0] for c in cur.execute.call_args_list)
    assert 'UPDATE catalogo_monstros' in sql and 'catalog_contributions' in sql


def test_callback_targets_use_internal_ids():
    assert lib.target_from_callback('atlas_m_7')=='map:7'
    assert lib.target_from_callback('atlas_x_2350_10_r48')=='monster:2350'
    assert lib.target_from_callback('atlas_d_10_48')=='dungeon:48'
    assert lib.target_from_callback('item_22_mago_arma')=='item:22'
    assert lib.target_from_callback('anything') is None


def test_unauthorized_photo_has_no_write(monkeypatch):
    monkeypatch.setattr(lib,'can_submit_photo',lambda *a:False)
    conn=MagicMock();msg=NS(chat=NS(type='private'),photo=[NS()],caption=None,from_user=NS(id=7))
    assert not asyncio.run(lib.receive_skin_photo(conn,msg,1))
    conn.cursor.assert_not_called()


def test_captionless_photo_only_creates_pending_choice(monkeypatch):
    monkeypatch.setattr(lib,'can_submit_photo',lambda *a:True)
    monkeypatch.setattr(lib,'B',lambda *a,**k:(a,k));monkeypatch.setattr(lib,'K',lambda a:a)
    conn=MagicMock();msg=NS(chat=NS(type='private'),photo=[NS(file_id='f',file_unique_id='u')],caption=None,from_user=NS(id=7),reply_text=AsyncMock())
    assert asyncio.run(lib.receive_skin_photo(conn,msg,1))
    sql='\n'.join(c.args[0] for c in conn.cursor.return_value.__enter__.return_value.execute.call_args_list)
    assert 'INSERT INTO skin_photo_pending' in sql and 'UPDATE catalogo_skins' not in sql
    assert 'ainda não vinculada' in msg.reply_text.call_args.args[0]


def test_expired_or_foreign_photo_cannot_be_confirmed(monkeypatch):
    monkeypatch.setattr(lib,'can_submit_photo',lambda *a:True)
    monkeypatch.setattr(lib,'B',lambda *a,**k:(a,k));monkeypatch.setattr(lib,'K',lambda a:a)
    conn=MagicMock();cur=conn.cursor.return_value.__enter__.return_value;cur.fetchone.return_value=None
    query=NS(data='ext_skinconfirm:abc:1',from_user=NS(id=7),message=NS(chat=NS(type='private'),reply_text=AsyncMock()))
    assert asyncio.run(lib.handle(conn,query,1,AsyncMock(),AsyncMock()))
    sql=cur.execute.call_args.args[0]
    assert 'telegram_id=%s' in sql and 'expires_at>now()' in sql and 'consumed_at IS NULL' in sql
    assert 'expirada' in query.message.reply_text.call_args.args[0]
    conn.commit.assert_not_called()


def test_revoked_contributor_cannot_confirm(monkeypatch):
    monkeypatch.setattr(lib,'can_submit_photo',lambda *a:False)
    monkeypatch.setattr(lib,'B',lambda *a,**k:(a,k))
    conn=MagicMock();q=NS(data='ext_skinconfirm:abc:1',from_user=NS(id=7),message=NS(chat=NS(type='private'),reply_text=AsyncMock()))
    asyncio.run(lib.handle(conn,q,1,AsyncMock(),AsyncMock()))
    conn.cursor.assert_not_called()


def test_selected_skin_photo_confirmed_once_and_audited(monkeypatch):
    monkeypatch.setattr(lib,'can_submit_photo',lambda *a:True)
    monkeypatch.setattr(lib,'B',lambda *a,**k:(a,k));monkeypatch.setattr(lib,'K',lambda a:a)
    conn=MagicMock();cur=conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect=[(2,'new-file','new-unique'),('Pele de Orc','old-unique','old-file'),None]
    q=NS(data='ext_skinconfirm:abc:2',from_user=NS(id=7),message=NS(chat=NS(type='private'),reply_text=AsyncMock()),edit_message_text=AsyncMock())
    assert asyncio.run(lib.handle(conn,q,1,AsyncMock(),AsyncMock()))
    sql='\n'.join(c.args[0] for c in cur.execute.call_args_list)
    assert 'UPDATE catalogo_skins' in sql and 'consumed_at=now()' in sql and 'catalog_contributions' in sql
    assert 'Foto vinculada' in q.edit_message_text.call_args.args[0]
    conn.commit.assert_called_once()


def test_confirmation_cannot_change_previously_selected_skin(monkeypatch):
    monkeypatch.setattr(lib,'can_submit_photo',lambda *a:True)
    monkeypatch.setattr(lib,'B',lambda *a,**k:(a,k));monkeypatch.setattr(lib,'K',lambda a:a)
    conn=MagicMock();cur=conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect=[(3,'new-file','new-unique'),('Pele de Orc',None,None)]
    q=NS(data='ext_skinconfirm:abc:2',from_user=NS(id=7),message=NS(chat=NS(type='private'),reply_text=AsyncMock()),edit_message_text=AsyncMock())
    asyncio.run(lib.handle(conn,q,1,AsyncMock(),AsyncMock()))
    assert not any('UPDATE catalogo_skins' in c.args[0] for c in cur.execute.call_args_list)
    conn.commit.assert_not_called()
