"""Independent, live authorization for private game-photo contributions."""
import logging


def can_submit_photo(connection, telegram_id, owner_id):
    if not telegram_id:
        return False
    # Preserve the existing owner's workflow, including during migrations.
    if telegram_id == owner_id:
        return True
    try:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT 1
                FROM site_acessos sa
                JOIN membros m ON m.telegram_id=sa.telegram_id
                LEFT JOIN membro_administracao ma ON ma.telegram_id=m.telegram_id
                WHERE sa.telegram_id=%s AND sa.pode_enviar_fotos=TRUE
                  AND sa.permitido=TRUE AND COALESCE(ma.ativo, TRUE)=TRUE""",
                (telegram_id,))
            return cursor.fetchone() is not None
    except Exception:
        # A missing migration or database failure must never grant access.
        connection.rollback()
        logging.warning("Não foi possível verificar permissão de coleta por fotos.")
        return False
