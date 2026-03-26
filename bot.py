import os
import re
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL não encontrado")

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS perfis (
    user_id BIGINT PRIMARY KEY,
    nome TEXT,
    classe TEXT,
    nivel INT,
    atk INT,
    defesa FLOAT,
    crit INT,
    hp INT
)
""")
conn.commit()

# IDs (mantidos)
CHAT_ID = -1003792787717
TOPICO_PRESENCA = 16325


# =========================
# PARSER ROBUSTO
# =========================
def extrair_perfil(texto):
    try:
        linhas = texto.split("\n")

        # NOME
        nome = None
        if linhas:
            match_nome = re.search(r'\d+\s+(.*)', linhas[0])
            if match_nome:
                nome = match_nome.group(1).strip()

        # CLASSE + NIVEL
        match_classe = re.search(r'Classe:\s*(\w+)\s*Lv\s*(\d+)', texto, re.IGNORECASE)
        if not match_classe:
            return None

        classe = match_classe.group(1)
        nivel = int(match_classe.group(2))

        # ATRIBUTOS
        atk = re.search(r'ATK\s*(\d+)', texto)
        defesa = re.search(r'DEF\s*([\d.]+)', texto)
        crit = re.search(r'CRIT\s*(\d+)%', texto)
        hp = re.search(r'HP[:\s]*(\d+)/(\d+)', texto)

        return {
            "nome": nome,
            "classe": classe,
            "nivel": nivel,
            "atk": int(atk.group(1)) if atk else 0,
            "defesa": float(defesa.group(1)) if defesa else 0,
            "crit": int(crit.group(1)) if crit else 0,
            "hp": int(hp.group(2)) if hp else 0
        }

    except:
        return None


# =========================
# SALVAR
# =========================
async def salvar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg:
        return

    if update.effective_chat.id != CHAT_ID:
        return

    if msg.message_thread_id != TOPICO_PRESENCA:
        return

    # 🔥 CORREÇÃO CRÍTICA (mensagem encaminhada)
    texto = msg.text or msg.caption

    if not texto:
        return

    perfil = extrair_perfil(texto)

    if not perfil:
        print("Falha ao extrair perfil")
        return

    user_id = msg.from_user.id

    cursor.execute("""
    INSERT INTO perfis (user_id, nome, classe, nivel, atk, defesa, crit, hp)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (user_id) DO UPDATE SET
    nome = EXCLUDED.nome,
    classe = EXCLUDED.classe,
    nivel = EXCLUDED.nivel,
    atk = EXCLUDED.atk,
    defesa = EXCLUDED.defesa,
    crit = EXCLUDED.crit,
    hp = EXCLUDED.hp
    """, (
        user_id,
        perfil["nome"],
        perfil["classe"],
        perfil["nivel"],
        perfil["atk"],
        perfil["defesa"],
        perfil["crit"],
        perfil["hp"]
    ))

    conn.commit()
    print(f"SALVO: {perfil['nome']}")


# =========================
# /VER
# =========================
async def ver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    cursor.execute("SELECT * FROM perfis WHERE user_id = %s", (user_id,))
    dados = cursor.fetchone()

    if not dados:
        await update.message.reply_text("❌ Nenhum perfil salvo.")
        return

    nome = dados[1]
    classe = dados[2]
    nivel = dados[3]
    atk = dados[4]
    defesa = dados[5]
    crit = dados[6]
    hp = dados[7]

    msg = (
        f"📜 {nome}\n"
        f"Classe: {classe}\n"
        f"Lv {nivel}\n\n"
        f"⚔️ ATK {atk}\n"
        f"🛡️ DEF {defesa}\n"
        f"🎯 CRIT {crit}%\n"
        f"❤️ HP {hp}"
    )

    await update.message.reply_text(msg)


# =========================
# MAIN
# =========================
def main():
    print("Bot iniciando...")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("ver", ver))
    app.add_handler(MessageHandler(filters.ALL, salvar))

    app.run_polling()


if __name__ == "__main__":
    main()

