import unittest

from loot_parser import extrair_monstro_combate, extrair_monstro_masmorra


class ExtracaoMasmorraTests(unittest.TestCase):
    def test_subboss_preserva_andar_e_hp_maximo(self):
        texto = """🗝 MASMORRA DA PLANÍCIE  Sala: 1/4 🗝
Lobo Alfa da Masmorra
❤️ HP: 224 / 224  ID: 3F00C9
👥 Grupo ⚔ 34 🛡 89
🧙 O Rastreador (Líder) — Nv. 45
🧙 EremitaDeSantoBerço — Nv. 46
⌛ Status — Aguardando ações... 45s"""

        self.assertEqual(
            extrair_monstro_masmorra(texto),
            {
                "masmorra": "Masmorra DA PLANÍCIE",
                "andar": 1,
                "total_andares": 4,
                "boss": False,
                "nome": "Lobo Alfa da Masmorra",
                "hp_atual": 224,
                "hp_max": 224,
                "codigo_execucao": "3F00C9",
                "tamanho_grupo": 2,
            },
        )

    def test_boss_ignora_nome_no_bloco_de_recompensas(self):
        texto = """🗝 MASMORRA DA PLANÍCIE  Sala: 4/4 👑 Boss 🗝
Senhor dos Rochedos
❤️ HP: 880 / 880  ID: 3F00C9
👥 Grupo ⚔ 34 🛡 89
🧙 O Rastreador (Líder) — Nv. 45
🧙 EremitaDeSantoBerço — Nv. 46
⌛ Status — Aguardando ações... 45s
🎁 Recompensas (vs Aranha Rochedo):
⭐ 180 XP"""

        resultado = extrair_monstro_masmorra(texto)

        self.assertEqual(resultado["nome"], "Senhor dos Rochedos")
        self.assertEqual(resultado["hp_max"], 880)
        self.assertEqual(resultado["andar"], 4)
        self.assertTrue(resultado["boss"])

    def test_combate_de_cacada_continua_compativel(self):
        texto = """⚔ COMBATE INICIADO
🧟 Slime Viscoso
❤️ 160/160
👤 Você
❤️ 114/242"""

        self.assertEqual(
            extrair_monstro_combate(texto),
            {"nome": "Slime Viscoso", "hp": 160},
        )


if __name__ == "__main__":
    unittest.main()
