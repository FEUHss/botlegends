"""Strict photo matching; never create or rename a catalog monster."""
import re
import unicodedata


def name_key(value):
    value = unicodedata.normalize('NFC', value or '').strip()
    # Leading pictograms are decoration, not part of the name.
    value = re.sub(r'^[^\w]+', '', value, flags=re.UNICODE)
    return ' '.join(value.casefold().split())


def match_header_monster(text, records):
    """Match a complete name line among the first three non-empty lines."""
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    matches = [(i, row) for i, line in enumerate(lines[:3])
               for row in records if name_key(line) == name_key(row[1])]
    if len(matches) != 1:
        return None
    index, row = matches[0]
    hp = None
    # Only the immediately following monster-health line, never player HP.
    if index + 1 < len(lines):
        found = re.fullmatch(r'(?:❤️?\s*)?(?:HP:\s*)?(\d[\d.,]*)\s*/\s*(\d[\d.,]*)(?:\s+ID:\s*\w+)?', lines[index + 1], re.I)
        if found:
            current, maximum = [int(re.sub(r'[.,]', '', n)) for n in found.groups()]
            if 0 <= current <= maximum and maximum > 0:
                hp = maximum
    return row, hp


def rift_entrance_name(text):
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    if not lines or name_key(lines[0]) != 'ruptura dimensional!':
        return None
    # The entrance has an introductory paragraph before its name.
    for line in lines[1:8]:
        if line.startswith(('🏰', '⛓', '🌀')):
            return re.sub(r'^[^\w]+', '', line).strip()
    return None


async def save_header_photo(connection, msg, text):
    with connection.cursor() as cur:
        cur.execute("""SELECT cm.id, cm.nome, cm.tipo, d.tipo_sistema, mp.nome
            FROM catalogo_monstros cm
            LEFT JOIN catalogo_masmorras d ON d.id=cm.masmorra_id
            LEFT JOIN catalogo_mapas mp ON mp.id=cm.mapa_id
            ORDER BY cm.id""")
        matched = match_header_monster(text, cur.fetchall())
        if not matched:
            return False
        (monster_id, name, kind, system, map_name), hp = matched
        photo = msg.photo[-1]
        # Do not silently reassign an image already belonging to another mob.
        cur.execute("SELECT monstro_id FROM monstro_imagens WHERE telegram_file_unique_id=%s", (photo.file_unique_id,))
        old = cur.fetchone()
        if old and old[0] != monster_id:
            connection.rollback()
            await msg.reply_text('⚠️ Esta imagem já está ligada a outro monstro. Revise o cadastro no painel.')
            return True
        fixed = kind == 'Caçada' or system == 'fenda'
        if fixed and hp is not None:
            cur.execute("""UPDATE catalogo_monstros SET hp=%s,
                atualizado_em=CURRENT_TIMESTAMP WHERE id=%s""", (hp, monster_id))
        cur.execute("""INSERT INTO monstro_imagens
            (monstro_id, telegram_file_id, telegram_file_unique_id, nome_detectado, hp_detectado)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (telegram_file_unique_id) DO UPDATE SET
                telegram_file_id=EXCLUDED.telegram_file_id,
                nome_detectado=EXCLUDED.nome_detectado, hp_detectado=EXCLUDED.hp_detectado,
                atualizado_em=CURRENT_TIMESTAMP""",
            (monster_id, photo.file_id, photo.file_unique_id, name, hp))
        connection.commit()
    extra = f'❤️ HP máximo: {hp}' if fixed and hp is not None else (
        'ℹ️ HP não alterado: o andar não foi identificado.' if not fixed else 'ℹ️ HP não informado.')
    await msg.reply_text(f'✅ Imagem salva para {name}.\n🗺️ {map_name or "Mapa não informado"}\n{extra}')
    return True
