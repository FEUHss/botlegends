import os
import re
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters, CommandHandler

# ==============================
# CONFIG (Railway)
# ==============================
TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# ==============================
# CONFIG GRUPO / TÓPICO
# ==============================
GRUPO_ID = -1003792787717
TOPICO_PRESENCA = 16325

# ==============================
# CONEXÃO DATABASE
# ==============================
def get_conn():
    return psycopg2.connect(DATABASE_URL)

# ==============================
# LIMPAR TEXTO (remove emojis)
# ==============================
def limpar(texto):
    return re.sub(r"[^\w\s,.\-]", "", texto)

# ==============================
# EXTRAIR DADOS
# ==============================
def extrair_dados(texto):
    try:
        linhas = texto.split("\n")

        # Nome (linha do papiro)
        nome_linha = next(l for l in linhas if "📜" in l)
        nome_limpo = limpar(nome_linha)

        # Remove nível do começo
        nome = re.sub(r"^\s*\d+\s*", "", nome_limpo).strip()

        # Classe e nível
        classe_linha = next(l for l in linhas if "Classe:" in l)
        classe = classe_linha.split("Classe:")[1].split("Lv")[0].strip().lower()
        nivel = int(re.search(r"Lv\s*(\d+)", classe_linha).group(1))

        # ATK DEF CRIT HP
        status_linha = next(l for l in linhas if "ATK" in l)

        atk = int(re.search(r"ATK\s*(\d+)", status_linha).group(1))
        defesa = float(re.search(r"DEF\s*([\d.]+)", status_linha).group(1))
        crit = int(re.search(r"CRIT\s*(\d+)", status_linha).group(1))
        hp = int(re.search(r"HP:\s*(\d+)", status_linha).group(1))

        return nome, classe, nivel, atk, defesa, crit, hp

    except Exception as e:
        print("ERRO AO EXTRAIR:", e)
        return None

# ==============================
# SALVAR NO BANCO (POR NOME)
# ==============================
def salvar_perfil(dados):
    nome, classe, nivel, atk, defesa, crit, hp = dados

    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO perfis (nome, classe, nivel, atk, defesa, crit, hp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (nome) DO UPDATE SET
                classe = EXCLUDED.classe,
                nivel = EXCLUDED.nivel,
                atk = EXCLUDED.atk,
                defesa = EXCLUDED.defesa,
                crit = EXCLUDED.crit,
                hp = EXCLUDED.hp
        """, (nome, classe, nivel, atk, defesa, crit, hp))

        conn.commit()
        print(f"SALVO: {nome}")

    except Exception as e:
        print("ERRO AO SALVAR:", e)

    finally:
        cursor.close()
        conn.close()

# ==============================
# CAPTURA DE MENSAGENS
# ==============================
async def receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg or not msg.text:
        return

    # Verifica grupo
    if msg.chat.id != GRUPO_ID:
        return

    # Verifica tópico
    if msg.message_thread_id != TOPICO_PRESENCA:
        return

    print("---- NOVA MENSAGEM ----")
    print(msg.text)

    dados = extrair_dados(msg.text)

    if dados:
        print("DADOS EXTRAIDOS:", dados)
        salvar_perfil(dados)
    else:
        print("Mensagem ignorada")

# ==============================
# COMANDO /ver
# ==============================
async def ver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT nome, classe, nivel, atk, defesa, crit, hp
        FROM perfis
        ORDER BY nivel DESC
        LIMIT 10
    """)

    resultados = cursor.fetchall()

    if not resultados:
        await update.message.reply_text("Nenhum perfil salvo.")
        return

    texto = "📊 Perfis salvos:\n\n"

    for r in resultados:
        texto += f"🏷 {r[0]}\n"
        texto += f"Classe: {r[1]} | Lv {r[2]}\n"
        texto += f"ATK {r[3]} | DEF {r[4]} | CRIT {r[5]} | HP {r[6]}\n\n"

    await update.message.reply_text(texto)

    cursor.close()
    conn.close()

# ==============================
# MAIN
# ==============================
def main():
    print("Bot rodando...")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), receber))
    app.add_handler(CommandHandler("ver", ver))

    app.run_polling()

if __name__ == "__main__":
    main()
