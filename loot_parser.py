import re
import unicodedata
from difflib import SequenceMatcher


MARCADORES_RECOMPENSA = (
    "recompensas",
    "vitoria!",
    "item:",
    "voce coletou:",
    "drops:",
    "drop:",
)


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", texto).strip().casefold()


def correspondencia_aproximada(texto, candidatos, limiar=0.88, margem=0.05):
    """Retorna um candidato apenas quando a semelhança é alta e inequívoca.

    ``candidatos`` contém pares ``(valor, nomes_aceitos)``. A função é pura
    para que as variações vindas do Telegram possam ser testadas sem banco.
    """
    procurado = normalizar(texto)
    if not procurado:
        return None
    pontuados = []
    for valor, nomes in candidatos:
        variantes = [normalizar(nome) for nome in nomes if normalizar(nome)]
        if not variantes:
            continue
        if procurado in variantes:
            pontuacao = 1.0
        else:
            pontuacao = max(
                SequenceMatcher(None, procurado, variante).ratio()
                for variante in variantes
            )
        pontuados.append((pontuacao, valor))
    pontuados.sort(key=lambda item: item[0], reverse=True)
    if not pontuados or pontuados[0][0] < limiar:
        return None
    if len(pontuados) > 1 and pontuados[0][0] - pontuados[1][0] < margem:
        return None
    return pontuados[0][1]


def extrair_monstro_combate(texto):
    """Extrai nome e HP de caçadas comuns e encontros de guerra."""
    linhas = [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]

    def cabecalho_de_encontro(linha):
        limpa = normalizar(linha)
        return (
            "combate iniciado" in limpa
            or bool(re.search(r"\bguerra\b.*\bvs\b", limpa))
        )

    indice = next(
        (i for i, linha in enumerate(linhas)
         if cabecalho_de_encontro(linha)),
        None,
    )
    if indice is None or indice + 1 >= len(linhas):
        return None

    nome = re.sub(r"^[^\wÀ-ÿ]+", "", linhas[indice + 1]).strip()
    if not nome:
        return None

    hp = None
    for linha in linhas[indice + 2:]:
        if normalizar(linha).endswith("voce"):
            break
        match = re.search(r"(?:❤️?\s*)?([\d.,]+)\s*/\s*([\d.,]+)", linha)
        if match:
            hp = int(re.sub(r"\D", "", match.group(2)))
            break

    if hp is None:
        return None
    return {"nome": nome, "hp": hp}


def extrair_monstro_masmorra(texto):
    """Extrai apenas o bloco atual da sala, ignorando recompensas anteriores."""
    linhas = [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]
    cabecalho = None
    indice = None
    # O jogo usa dois cabeçalhos válidos: o legado
    # "MASMORRA DA PLANÍCIE Sala: 1/4" e o atual, que pode trazer apenas
    # o nome próprio, como "SANTUARIO DE ALTHERYN Sala: 4/4".
    padrao = re.compile(
        r"^(.+?)\s+sala:\s*(\d+)\s*/\s*(\d+)"
        r"(?:\s+.*)?$",
        re.IGNORECASE,
    )
    for posicao, linha in enumerate(linhas):
        limpa = re.sub(r"^[^\wÀ-ÿ]+", "", linha).strip()
        match = padrao.search(limpa)
        if match:
            cabecalho = match
            indice = posicao
            break

    if cabecalho is None or indice is None or indice + 1 >= len(linhas):
        return None

    nome = re.sub(r"^[^\wÀ-ÿ]+", "", linhas[indice + 1]).strip()
    if not nome:
        return None

    hp_atual = None
    hp_maximo = None
    codigo_execucao = None
    for linha in linhas[indice + 2:]:
        if normalizar(linha).startswith("grupo"):
            break
        match_hp = re.search(
            r"HP:\s*([\d.,]+)\s*/\s*([\d.,]+)", linha, re.IGNORECASE
        )
        if match_hp:
            hp_atual = int(re.sub(r"\D", "", match_hp.group(1)))
            hp_maximo = int(re.sub(r"\D", "", match_hp.group(2)))
            match_id = re.search(r"\bID:\s*([A-Z0-9]+)", linha, re.IGNORECASE)
            if match_id:
                codigo_execucao = match_id.group(1).upper()
            break

    trecho_grupo = linhas[indice + 2:]
    tamanho_grupo = sum(
        1 for linha in trecho_grupo
        if re.search(r"—\s*Nv\.\s*\d+", linha, re.IGNORECASE)
    )

    andar = int(cabecalho.group(2))
    total_andares = int(cabecalho.group(3))
    nome_masmorra = cabecalho.group(1).strip()
    if normalizar(nome_masmorra).startswith("masmorra "):
        nome_masmorra = re.sub(
            r"^masmorra\s+", "Masmorra ", nome_masmorra,
            flags=re.IGNORECASE,
        )
    return {
        "masmorra": nome_masmorra,
        "andar": andar,
        "total_andares": total_andares,
        "boss": andar == total_andares,
        "nome": nome,
        "hp_atual": hp_atual,
        "hp_max": hp_maximo,
        "codigo_execucao": codigo_execucao,
        "tamanho_grupo": tamanho_grupo or None,
    }


def extrair_mapa_visual(texto):
    """Reconhece a tela principal do mapa sem confundi-la com um perfil."""
    texto_normalizado = normalizar(texto)
    marcadores = ("energia:", "tofus:", "gold:", "chaves de masmorra:")
    if sum(marcador in texto_normalizado for marcador in marcadores) < 3:
        return None

    for linha in (texto or "").splitlines():
        limpa = re.sub(r"^[^\wÀ-ÿ]+", "", linha).strip()
        match = re.match(
            r"(.+?)\s*\(\s*Lv\s*(\d+)\s*\)\s*$",
            limpa,
            re.IGNORECASE,
        )
        if match:
            return {
                "nome": match.group(1).strip(),
                "nivel": int(match.group(2)),
            }
    return None


def extrair_masmorra_visual(texto):
    """Reconhece a entrada ou o lobby de uma masmorra e remove o código da sala."""
    linhas = [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]
    if not linhas:
        return None

    # Algumas masmorras exibem somente o nome e a pergunta de privacidade,
    # sem a linha "Mapa:". O nome imediatamente anterior à pergunta é o
    # identificador oficial que será resolvido no catálogo, sem criar dados.
    for indice, linha in enumerate(linhas):
        if "como deseja criar a sala" not in normalizar(linha):
            continue
        if indice == 0:
            return None
        nome = re.sub(r"^[^\wÀ-ÿ]+", "", linhas[indice - 1]).strip()
        if nome:
            return {"nome": nome, "mapa": None, "codigo_sala": None}
        return None

    # Tela de entrada: nome e mapa aparecem explicitamente.
    if "crie uma sala" in normalizar(texto):
        nome = None
        mapa = None
        for linha in linhas:
            limpa = re.sub(r"^[^\wÀ-ÿ]+", "", linha).strip()
            if normalizar(limpa).startswith("masmorra ") and nome is None:
                nome = limpa
            match_mapa = re.match(r"Mapa:\s*(.+)$", limpa, re.IGNORECASE)
            if match_mapa:
                mapa = match_mapa.group(1).strip()
        if nome and mapa:
            return {"nome": nome, "mapa": mapa, "codigo_sala": None}

    # Lobby criado: o cabeçalho termina em um código hexadecimal temporário.
    if "membros (" in normalizar(texto) and "marque-se como pronto" in normalizar(texto):
        cabecalho = re.sub(r"^[^\wÀ-ÿ]+", "", linhas[0]).strip()
        match = re.match(r"(.+?)\s+([A-F0-9]{6})$", cabecalho, re.IGNORECASE)
        if match:
            return {
                "nome": match.group(1).strip(),
                "mapa": None,
                "codigo_sala": match.group(2).upper(),
            }
    return None


def chave_origem_drop(item_id, monstro_id=None, mapa_id=None, forma=None):
    """Chave semântica: variações de legenda não repetem a mesma origem."""
    if monstro_id:
        return f"{item_id}:monstro:{monstro_id}"
    if mapa_id:
        return f"{item_id}:mapa:{mapa_id}"
    return f"{item_id}:forma:{normalizar(forma or '')}"


def tem_marcador_recompensa(texto):
    texto_normalizado = normalizar(texto)
    return any(marcador in texto_normalizado for marcador in MARCADORES_RECOMPENSA)


def localizar_itens(texto, itens):
    """Retorna itens do catálogo citados sem duplicar nomes sobrepostos."""
    texto_normalizado = normalizar(texto)
    candidatos = []

    for item_id, nome in itens:
        nome_normalizado = normalizar(nome)
        if not nome_normalizado:
            continue

        padrao = rf"(?<!\w){re.escape(nome_normalizado)}(?!\w)"
        for match in re.finditer(padrao, texto_normalizado):
            candidatos.append((
                -(match.end() - match.start()),
                match.start(),
                match.end(),
                item_id,
                nome,
            ))

    ocupados = []
    encontrados = {}
    for _, inicio, fim, item_id, nome in sorted(candidatos):
        if any(inicio < ocupado_fim and fim > ocupado_inicio
               for ocupado_inicio, ocupado_fim in ocupados):
            continue
        ocupados.append((inicio, fim))
        encontrados[item_id] = nome

    return sorted(encontrados.items(), key=lambda item: normalizar(item[1]))


def extrair_monstro(texto):
    padroes = (
        r"Recompensas\s*\(\s*vs\.?\s+([^\)]+)\)",
        r"Recompensa\s*\(\s*vs\.?\s+([^\)]+)\)",
    )
    for padrao in padroes:
        match = re.search(padrao, texto or "", re.IGNORECASE)
        if match:
            return match.group(1).strip(" \t\n:-")
    return None


def extrair_forma_obtencao(texto):
    texto_normalizado = normalizar(texto)

    titulo_masmorra = re.search(
        r"^\s*([^\n]{2,80}?)\s*[\u2014\-]\s*Vit[oó]ria!",
        texto or "",
        re.IGNORECASE | re.MULTILINE,
    )
    if titulo_masmorra:
        return f"Masmorra: {titulo_masmorra.group(1).strip()}"

    if "resumo da cacada em dupla" in texto_normalizado:
        return "Caçada em Dupla"
    if "estrela caída" in (texto or "").casefold() or "estrela caida" in texto_normalizado:
        return "Evento: Estrela Caída"
    if "saco de almas" in texto_normalizado:
        return "Saco de Almas"
    if "bau" in texto_normalizado and "tesouro" in texto_normalizado:
        return "Baú do Tesouro"
    if re.search(r"recompensas?\s*\(\s*vs\.? ?\s*", texto_normalizado):
        return "Combate"
    if "vitoria!" in texto_normalizado and "item:" in texto_normalizado:
        return "Caçada"
    if "voce coletou:" in texto_normalizado:
        return "Coleta/Evento"
    if "drops:" in texto_normalizado or "drop:" in texto_normalizado:
        return "Recompensa"
    return None


def analisar_texto_loot(texto, itens, mapas):
    if not tem_marcador_recompensa(texto):
        return []

    itens_encontrados = localizar_itens(texto, itens)
    if not itens_encontrados:
        return []

    texto_normalizado = normalizar(texto)
    mapas_encontrados = [
        (mapa_id, nome)
        for mapa_id, nome in mapas
        if re.search(
            rf"(?<!\w){re.escape(normalizar(nome))}(?!\w)",
            texto_normalizado,
        )
    ]

    # Mais de um mapa explícito torna a origem ambígua.
    mapa = mapas_encontrados[0] if len(mapas_encontrados) == 1 else (None, None)
    monstro = extrair_monstro(texto)
    forma = extrair_forma_obtencao(texto)

    # Um item sem qualquer informação de origem não gera proposta.
    if not monstro and not mapa[0] and not forma:
        return []

    return [
        {
            "item_id": item_id,
            "item_nome": item_nome,
            "monstro_nome": monstro,
            "mapa_id": mapa[0],
            "mapa_nome": mapa[1],
            "forma_obtencao": forma,
        }
        for item_id, item_nome in itens_encontrados
    ]

