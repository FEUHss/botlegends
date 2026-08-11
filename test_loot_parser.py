import unittest

from loot_parser import analisar_texto_loot, localizar_itens


ITENS = [
    (1, "Passos do Sol"),
    (2, "Poeira Estelar"),
    (3, "Tônico de Força"),
    (4, "Super Tônico de Força"),
    (5, "Anel da Areia Obscura"),
]

MAPAS = [
    (10, "Deserto Escaldante"),
    (11, "Oásis Perdido"),
]


class LootParserTests(unittest.TestCase):
    def test_vitoria_de_cacada_identifica_item_sem_inventar_mapa(self):
        texto = "🏆 Vitória!\n+170 XP\n🎁 Item: Passos do Sol (DEF+7, HP+5)"

        propostas = analisar_texto_loot(texto, ITENS, MAPAS)

        self.assertEqual(len(propostas), 1)
        self.assertEqual(propostas[0]["item_nome"], "Passos do Sol")
        self.assertEqual(propostas[0]["forma_obtencao"], "Caçada")
        self.assertIsNone(propostas[0]["mapa_id"])
        self.assertIsNone(propostas[0]["monstro_nome"])

    def test_recompensa_com_monstro_e_mapa_explicitos(self):
        texto = (
            "Recompensas (vs Sentinela de Areia):\n"
            "• Passos do Sol\nMapa: Deserto Escaldante"
        )

        propostas = analisar_texto_loot(texto, ITENS, MAPAS)

        self.assertEqual(propostas[0]["monstro_nome"], "Sentinela de Areia")
        self.assertEqual(propostas[0]["mapa_id"], 10)
        self.assertEqual(propostas[0]["forma_obtencao"], "Combate")

    def test_evento_estrela_caida(self):
        texto = (
            "🌟 Estrela Caída!\n"
            "Uma estrela pequena cruza o céu do deserto.\n"
            "✨ Você coletou: 1x Poeira Estelar"
        )

        propostas = analisar_texto_loot(texto, ITENS, MAPAS)

        self.assertEqual(propostas[0]["item_nome"], "Poeira Estelar")
        self.assertEqual(propostas[0]["forma_obtencao"], "Evento: Estrela Caída")
        self.assertIsNone(propostas[0]["mapa_id"])

    def test_oferta_de_vendedor_nao_e_drop(self):
        texto = "Ofertas Especiais:\nSuper Tônico de Força: 550g"
        self.assertEqual(analisar_texto_loot(texto, ITENS, MAPAS), [])

    def test_nome_longo_nao_gera_item_curto_sobreposto(self):
        encontrados = localizar_itens("Drop: Super Tônico de Força", ITENS)
        self.assertEqual(encontrados, [(4, "Super Tônico de Força")])

    def test_masmorra_preserva_nome_da_origem(self):
        texto = "Templo do Oásis — Vitória!\nDrops:\n• Anel da Areia Obscura"

        propostas = analisar_texto_loot(texto, ITENS, MAPAS)

        self.assertEqual(
            propostas[0]["forma_obtencao"],
            "Masmorra: Templo do Oásis",
        )
        self.assertIsNone(propostas[0]["mapa_id"])


if __name__ == "__main__":
    unittest.main()
