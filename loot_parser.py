import re
import unicodedata


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
