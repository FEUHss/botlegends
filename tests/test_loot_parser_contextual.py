from loot_parser import analisar_texto_loot, extrair_secao_recompensas


def test_dungeon_rewards_are_scoped_to_the_monster_section_and_include_souls():
    text = """🗝️ PIRÂMIDE DO DESERTO Sala: 2/4
Djinn Errante
❤️ HP: 1087 / 1087
📜 Eventos: alguém usou Orbe Solar
🎁 Recompensas (vs Djinn Errante):
👤 Jogador A: 💰 21g ⭐ 700 XP · ⚪ Nenhum item
👤 Jogador B: 💰 51g ⭐ 700 XP · 🟠 Flecha do Djinn
🏅 Destaques: Jogador B
"""
    proposals = analisar_texto_loot(
        text,
        [(10, "Orbe Solar")],
        [(6, "Deserto Escaldante")],
        [(11, "Flecha do Djinn")],
    )
    assert extrair_secao_recompensas(text).startswith("👤 Jogador A")
    assert [(row["catalog_type"], row["catalog_id"], row["monstro_nome"])
            for row in proposals] == [("soul", 11, "Djinn Errante")]


def test_reward_section_can_propose_an_item_and_a_soul_independently():
    text = """Recompensas (vs Guardião):
Ana: 🟠 Espada Curta
Bia: 🟣 Golpe Sombrio
Destaques: Ana
"""
    proposals = analisar_texto_loot(
        text, [(2, "Espada Curta")], [], [(3, "Golpe Sombrio")]
    )
    assert {(row["catalog_type"], row["catalog_id"]) for row in proposals} == {
        ("item", 2), ("soul", 3)
    }
