"""Library conveniences. No Telegram polling or database work at import time."""
import json
import re
import secrets
from pathlib import Path
from psycopg2.extras import Json
from photo_permissions import can_submit_photo


def B(*args, **kwargs):
    from telegram import InlineKeyboardButton
    return InlineKeyboardButton(*args, **kwargs)


def K(*args, **kwargs):
    from telegram import InlineKeyboardMarkup
    return InlineKeyboardMarkup(*args, **kwargs)


def initialize(connection):
    with connection.cursor() as cur:
        cur.execute(Path(__file__).with_name('library_schema.sql').read_text(encoding='utf-8'))
    connection.commit()


def audit(cur, entity, entity_id, actor, action, details):
    cur.execute('''INSERT INTO catalog_contributions(entity,entity_id,actor,action,details)
        VALUES (%s,%s,%s,%s,%s)''', (entity, entity_id, str(actor), action, Json(details)))


def observe_fixed_hp(cur, monster_id, hp, actor):
    """Existing HP is curated data: changes require an explicit review."""
    cur.execute('SELECT hp FROM catalogo_monstros WHERE id=%s FOR UPDATE', (monster_id,))
    row = cur.fetchone()
    if not row or hp is None:
        return False
    if row[0] is not None and row[0] != hp:
        cur.execute('''INSERT INTO catalog_hp_review(monstro_id,previous_hp,observed_hp,submitted_by)
            SELECT %s,%s,%s,%s WHERE NOT EXISTS(SELECT 1 FROM catalog_hp_review
            WHERE monstro_id=%s AND observed_hp=%s) ON CONFLICT DO NOTHING''', (monster_id, row[0], hp, actor, monster_id, hp))
        return True
    if row[0] is None:
        cur.execute('UPDATE catalogo_monstros SET hp=%s, atualizado_em=now() WHERE id=%s', (hp,monster_id))
        audit(cur, 'monster', monster_id, actor, 'first_hp', {'hp': hp})
    return False


async def receive_skin_photo(connection, msg, owner):
    if msg.chat.type != 'private' or not msg.photo or (msg.caption or '').strip():
        return False
    if not msg.from_user or not can_submit_photo(connection, msg.from_user.id, owner):
        return False
    token = secrets.token_hex(6)
    photo = msg.photo[-1]
    with connection.cursor() as cur:
        cur.execute("DELETE FROM skin_photo_pending WHERE expires_at < now()")
        cur.execute('''INSERT INTO skin_photo_pending(token,telegram_id,file_id,file_unique_id)
            VALUES(%s,%s,%s,%s)''', (token,msg.from_user.id,photo.file_id,photo.file_unique_id))
    connection.commit()
    await msg.reply_text('📸 Foto recebida, ainda não vinculada. Escolha a skin cadastrada e confirme. '
                         'A seleção expira em 30 minutos.', reply_markup=K([
        [B('Escolher skin', callback_data=f'ext_skinpick:{token}:0')],
        [B('Cancelar', callback_data=f'ext_skincancel:{token}')]]))
    return True


def entry(connection, target):
    spec = {
        'item': ('itens_legends','id'), 'monster': ('catalogo_monstros','id'),
        'map': ('catalogo_mapas','id'), 'dungeon': ('catalogo_masmorras','id'),
        'soul': ('almas_legends','id'), 'crypt': ('catalogo_criptas','numero'),
        'skin': ('catalogo_skins','id')}
    kind, value = target.split(':')
    if kind not in spec or not value.isdigit():
        raise ValueError('Destino inválido')
    table, pk = spec[kind]
    with connection.cursor() as cur:
        cur.execute(f'SELECT nome FROM {table} WHERE {pk}=%s', (int(value),))
        row = cur.fetchone()
    return row[0] if row else None


def target_from_callback(data):
    patterns = [(r'item_(\d+)_.*','item'), (r'alma_(\d+)','soul'),
                (r'cripta_(\d+)','crypt'), (r'cripta_m_(\d+)','monster'),
                (r'atlas_x_(\d+)_\d+_.*','monster'), (r'atlas_m_(\d+)','map')]
    for pattern, kind in patterns:
        match = re.fullmatch(pattern, data or '')
        if match:
            return f'{kind}:{match[1]}'
    match = re.fullmatch(r'atlas_d_\d+_(\d+)', data or '')
    return f'dungeon:{match[1]}' if match else None


def remember(connection, user, target):
    if not entry(connection,target):
        return
    with connection.cursor() as cur:
        cur.execute('''INSERT INTO library_saved(telegram_id,target) VALUES(%s,%s)
            ON CONFLICT(telegram_id,target) DO UPDATE SET visited_at=now()''',(user,target))
        cur.execute('''DELETE FROM library_saved WHERE telegram_id=%s AND NOT favorite
            AND target NOT IN(SELECT target FROM library_saved WHERE telegram_id=%s
            ORDER BY visited_at DESC LIMIT 20)''', (user,user))
    connection.commit()


async def handle(connection, query, owner, render, open_target):
    """Caller checks ordinary library access; photo permission is rechecked here."""
    data, user = query.data, query.from_user.id
    if not data.startswith('ext_'):
        return False
    if query.message.chat.type != 'private':
        return True
    parts = data.split(':')
    home = [B('📚 Biblioteca', callback_data='lib_inicio')]
    if parts[0] in ('ext_skinpick','ext_skinselect','ext_skinconfirm','ext_skincancel'):
        if not can_submit_photo(connection,user,owner):
            await query.message.reply_text('Você não possui permissão para enviar fotos.')
            return True
        token = parts[1]
        with connection.cursor() as cur:
            cur.execute('''SELECT skin_id,file_id,file_unique_id FROM skin_photo_pending
                WHERE token=%s AND telegram_id=%s AND expires_at>now() AND consumed_at IS NULL FOR UPDATE''',(token,user))
            pending = cur.fetchone()
            if not pending:
                connection.rollback()
                await query.message.reply_text('Seleção expirada ou já concluída. Envie a foto novamente.')
                return True
            if parts[0]=='ext_skincancel':
                cur.execute('UPDATE skin_photo_pending SET consumed_at=now() WHERE token=%s',(token,))
                connection.commit()
                await query.edit_message_text('Seleção cancelada. Nenhuma imagem foi vinculada.')
                return True
            if parts[0]=='ext_skinpick':
                page = max(0,min(int(parts[2]),1000))
                cur.execute('SELECT id,nome FROM catalogo_skins WHERE ativo ORDER BY nome LIMIT 9 OFFSET %s',(page*8,))
                rows = cur.fetchall()
                connection.commit()
                buttons = [[B(name[:60],callback_data=f'ext_skinselect:{token}:{sid}')] for sid,name in rows[:8]]
                nav = []
                if page: nav.append(B('Anterior',callback_data=f'ext_skinpick:{token}:{page-1}'))
                if len(rows)>8: nav.append(B('Próxima',callback_data=f'ext_skinpick:{token}:{page+1}'))
                if nav: buttons.append(nav)
                buttons.append([B('Cancelar',callback_data=f'ext_skincancel:{token}')])
                await query.edit_message_text('Escolha a skin desta foto:' if rows else 'Cadastre primeiro a skin no site. Nenhuma foi criada automaticamente.',reply_markup=K(buttons))
                return True
            sid = int(parts[2])
            cur.execute('SELECT nome,telegram_file_unique_id,telegram_file_id FROM catalogo_skins WHERE id=%s AND ativo FOR UPDATE',(sid,))
            skin = cur.fetchone()
            if not skin:
                connection.rollback()
                await query.message.reply_text('Skin indisponível. Atualize a seleção.')
                return True
            if parts[0]=='ext_skinselect':
                cur.execute('UPDATE skin_photo_pending SET skin_id=%s WHERE token=%s',(sid,token))
                connection.commit()
                await query.edit_message_text(f'Vincular a foto a {skin[0]}?'+('\nA imagem atual será substituída; o histórico será preservado.' if skin[1] else ''),reply_markup=K([
                    [B('SIM — salvar',callback_data=f'ext_skinconfirm:{token}:{sid}')],
                    [B('NÃO — escolher outra',callback_data=f'ext_skinpick:{token}:0')],
                    [B('Cancelar',callback_data=f'ext_skincancel:{token}')]]))
                return True
            if pending[0] != sid:
                connection.rollback()
                return True
            cur.execute('SELECT id FROM catalogo_skins WHERE telegram_file_unique_id=%s AND id<>%s',(pending[2],sid))
            if cur.fetchone():
                connection.rollback()
                await query.message.reply_text('Esta foto já está ligada a outra skin. Revise no painel.')
                return True
            audit(cur,'skin',sid,user,'photo',{'before_unique_id':skin[1],'after_unique_id':pending[2],
                'before_file_id':skin[2],'after_file_id':pending[1]})
            cur.execute('''UPDATE catalogo_skins SET telegram_file_id=%s,telegram_file_unique_id=%s,
                atualizado_por=%s,atualizado_em=now() WHERE id=%s''',(pending[1],pending[2],str(user),sid))
            cur.execute('UPDATE skin_photo_pending SET consumed_at=now() WHERE token=%s',(token,))
        connection.commit()
        await query.edit_message_text(f'✅ Foto vinculada a {skin[0]}.')
        return True
    if parts[0] in ('ext_recent','ext_favorites'):
        with connection.cursor() as cur:
            cur.execute('''SELECT target,favorite FROM library_saved WHERE telegram_id=%s
                AND (%s=FALSE OR favorite) ORDER BY visited_at DESC LIMIT 20''',(user,parts[0]=='ext_favorites'))
            rows = cur.fetchall()
        buttons=[]
        for target,favorite in rows:
            name=entry(connection,target)
            if name:
                buttons.append([B(name[:46],callback_data=f'ext_open:{target}'),B('★' if favorite else '☆',callback_data=f'ext_fav:{target}')])
        await render(query,'biblioteca','⭐ FAVORITOS E RECENTES\n\nToque no nome para abrir ou na estrela para favoritar.',K(buttons+[home]))
    elif parts[0]=='ext_fav':
        target=':'.join(parts[1:])
        if not entry(connection,target): return True
        with connection.cursor() as cur:
            cur.execute('''SELECT COUNT(*),BOOL_OR(target=%s) FROM library_saved
                WHERE telegram_id=%s AND favorite''',(target,user))
            count, already = cur.fetchone()
            if count>=50 and not already:
                await query.message.reply_text('Limite de 50 favoritos. Remova um favorito antes de adicionar outro.')
                return True
            cur.execute('''INSERT INTO library_saved(telegram_id,target,favorite) VALUES(%s,%s,TRUE)
                ON CONFLICT(telegram_id,target) DO UPDATE SET favorite=NOT library_saved.favorite''',(user,target))
        connection.commit()
        await query.message.reply_text('⭐ Favorito atualizado. Reabra Favoritos/Recentes para ver a lista.')
    elif parts[0]=='ext_open':
        target=':'.join(parts[1:])
        if entry(connection,target):
            remember(connection,user,target)
            await open_target(query,target)
        else: await query.message.reply_text('Este cadastro não está mais disponível.')
    elif parts[0]=='ext_skins':
        page=max(0,min(int(parts[1]) if len(parts)>1 else 0,1000))
        with connection.cursor() as cur:
            cur.execute('SELECT id,nome FROM catalogo_skins WHERE ativo ORDER BY nome LIMIT 9 OFFSET %s',(page*8,))
            rows=cur.fetchall()
        buttons=[[B(name[:60],callback_data=f'ext_open:skin:{sid}')] for sid,name in rows[:8]]
        if page: buttons.append([B('Anterior',callback_data=f'ext_skins:{page-1}')])
        if len(rows)>8: buttons.append([B('Próxima',callback_data=f'ext_skins:{page+1}')])
        await render(query,'biblioteca','🎭 SKINS\n\n'+('Escolha uma skin:' if rows else 'Catálogo em preparação. Os cadastros serão feitos pelo painel.'),K(buttons+[home]))
    elif parts[0]=='ext_runs':
        page=max(0,min(int(parts[1]) if len(parts)>1 else 0,1000))
        with connection.cursor() as cur:
            cur.execute("SELECT id,nome FROM catalogo_masmorras WHERE tipo_sistema<>'cripta' ORDER BY mapa_id,ordem LIMIT 9 OFFSET %s",(page*8,))
            rows=cur.fetchall()
        buttons=[[B(name[:60],callback_data=f'ext_plan:{did}:0')] for did,name in rows[:8]]
        if page: buttons.append([B('Anterior',callback_data=f'ext_runs:{page-1}')])
        if len(rows)>8: buttons.append([B('Próxima',callback_data=f'ext_runs:{page+1}')])
        buttons.append([B('🗝️ Runs de Criptas',callback_data='lib_criptas')])
        await render(query,'atlas','🧭 PLANEJAR RUN\n\nEscolha o destino. Não é uma previsão de vitória.',K(buttons+[home]))
    elif parts[0]=='ext_plan':
        await show_plan(connection,query,int(parts[1]),int(parts[2]),render)
    else:
        return False
    return True


async def show_skin(connection,query,skin_id,render):
    with connection.cursor() as cur:
        cur.execute('''SELECT nome,classe,variante,obtencao,confirmado,telegram_file_id
            FROM catalogo_skins WHERE id=%s AND ativo''',(skin_id,))
        row=cur.fetchone()
        if not row: return
        cur.execute('''SELECT d.nome,r.grupo,r.confirmado FROM skin_requisitos r
            JOIN catalogo_masmorras d ON d.id=r.masmorra_id WHERE r.skin_id=%s ORDER BY d.nome''',(skin_id,))
        requirements=cur.fetchall()
    name,cl,variant,origin,confirmed,photo=row
    text=f'🎭 {name}\n🏷️ {cl} · {variant or "Variante não informada"}\n\n📍 Obtenção: {origin or "a informar"}\n🔎 {"Confirmado" if confirmed else "Em revisão"}'
    if requirements:
        text+='\n\n🔐 Usada na entrada (pode exigir outras skins da equipe):\n'+'\n'.join(f'• {d} — {"confirmado" if ok else "a confirmar"}' for d,_,ok in requirements)
    await render(query,'biblioteca',text,K([[B('⬅ Skins',callback_data='ext_skins')],[B('📚 Biblioteca',callback_data='lib_inicio')]]),file_id=photo)


async def show_plan(connection,query,dungeon_id,party,render):
    with connection.cursor() as cur:
        cur.execute('''SELECT d.nome,d.mapa_id,m.nome,m.nivel_minimo,d.minimo_jogadores,
            d.maximo_jogadores,d.xp_por_equipe,d.requisitos_texto,d.confirmado,d.tipo_sistema
            FROM catalogo_masmorras d JOIN catalogo_mapas m ON m.id=d.mapa_id WHERE d.id=%s''',(dungeon_id,))
        row=cur.fetchone()
        if not row: return
        name,map_id,map_name,level,minimum,maximum,xps,requirements,confirmed,system=row
        minimum,maximum=minimum or 1,maximum or 5
        if not party:
            await render(query,'atlas',f'🧭 {name}\n\nQual é o tamanho da equipe?',K([
                [B(str(n),callback_data=f'ext_plan:{dungeon_id}:{n}') for n in range(minimum,min(maximum,5)+1)],
                [B('⬅ Destinos',callback_data='ext_runs')]]))
            return
        if not minimum<=party<=maximum:
            await query.message.reply_text('Tamanho de equipe não permitido para este destino.')
            return
        cur.execute('''SELECT COUNT(*),COUNT(*) FILTER(WHERE habilidade IS NOT NULL),
            COUNT(*) FILTER(WHERE habilidade IS NULL AND NOT COALESCE(sem_habilidade,FALSE)),
            MAX(CASE risco WHEN 'Alto' THEN 3 WHEN 'Médio' THEN 2 WHEN 'Baixo' THEN 1 ELSE 0 END),
            SUM(xp),COUNT(xp) FROM catalogo_monstros WHERE masmorra_id=%s''',(dungeon_id,))
        mobs,skills,missing,risk,xp_total,xp_count=cur.fetchone()
        cur.execute('''SELECT r.grupo,s.nome,r.confirmado FROM skin_requisitos r
            JOIN catalogo_skins s ON s.id=r.skin_id WHERE masmorra_id=%s ORDER BY grupo,s.nome''',(dungeon_id,))
        skins=cur.fetchall()
    xp=(xps or {}).get(str(party))
    if system=='fenda': xp=xp_total if mobs and xp_count==mobs else None
    groups={}
    for group,skin,ok in skins: groups.setdefault(group,[]).append(skin+('' if ok else ' (a confirmar)'))
    text=f'🧭 {name}\n🗺️ {map_name} · nível do mapa: {level or "a confirmar"}\n👥 Equipe: {party}\n'
    text+=f'⭐ XP cadastrado: {xp if xp is not None else "não informado"}'+(' (em revisão)' if not confirmed and xp is not None else '')+'\n'
    text+=f'⚠️ Risco cadastrado: {("não informado","Baixo","Médio","Alto")[risk or 0]}\n👹 {mobs} monstros · {skills} com habilidade · {missing} a revisar\n'
    text+='\n🔐 Requisitos: '+(requirements or 'a confirmar')
    for group,names in groups.items(): text+='\n• Grupo '+str(group)+': '+' OU '.join(names)
    if groups: text+='\nÉ preciso atender TODOS os grupos de skins na mesma equipe.'
    text+='\n\nℹ️ Confira itens/skins da equipe e níveis individuais no jogo. Não temos o inventário nem um cálculo validado de sobrevivência.'
    await render(query,'atlas',text,K([[B('Ver destino e monstros',callback_data=f'atlas_d_{map_id}_{dungeon_id}')],[B('Alterar equipe',callback_data=f'ext_plan:{dungeon_id}:0')],[B('📚 Biblioteca',callback_data='lib_inicio')]]))
