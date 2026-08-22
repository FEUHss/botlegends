import unittest

from loot_parser import (
    correspondencia_aproximada,
    extrair_mapa_visual,
    extrair_masmorra_visual,
    extrair_monstro_combate,
    extrair_monstro_masmorra,
)


def test_dungeon_name_variations_resolve_to_canonical_name():
    candidates = [
        ("Masmorra da Planície", ["Masmorra da Planície"]),
        ("Covil de Zul'gor", ["Covil de Zul'gor"]),
    ]
    for received in (
        "masmorra DA PLANICIE",
        "MASMORRA DA PLANICIA",
        "Masmorra da planicie",
        "Masmorra da plánicie",
    ):
        assert correspondencia_aproximada(received, candidates) == "Masmorra da Planície"


def test_dungeon_name_does_not_guess_between_ambiguous_candidates():
    candidates = [
        ("Masmorra Norte", ["Masmorra Norte"]),
        ("Masmorra Morte", ["Masmorra Morte"]),
    ]
    assert correspondencia_aproximada("Masmorra Forte", candidates) is None


class ExtracaoMasmorraTests(unittest.TestCase):
    def test_nome_de_futura_masmorra_e_tudo_antes_de_sala(self):
        texto = """🗝 TEMPLO SUBMERSO DE NERYS Sala: 2/4 🗝
Sentinela das Marés
❤️ HP: 830 / 830 ID: A1B2C3
👥 Grupo ⚔ 40 🛡 30
🧙 Vênus — Nv. 28"""

        resultado = extrair_monstro_masmorra(texto)

        self.assertEqual(resultado["masmorra"], "TEMPLO SUBMERSO DE NERYS")
        self.assertEqual(resultado["nome"], "Sentinela das Marés")
        self.assertEqual(resultado["andar"], 2)
        self.assertEqual(resultado["total_andares"], 4)

    def test_boss_com_nome_proprio_sem_prefixo_masmorra(self):
        texto = """🗝 SANTUARIO DE ALTHERYN  Sala: 4/4 👑 Boss 🗝
Aparição de Altheryn
❤️ HP: 2470 / 2470  ID: D90C9F
👥 Grupo ⚔ 46 🛡 18
🧙 [CROW]Ryuarkano (Líder) — Nv. 31
🧙 Vênus — Nv. 28"""

        resultado = extrair_monstro_masmorra(texto)

        self.assertEqual(resultado["masmorra"], "SANTUARIO DE ALTHERYN")
        self.assertEqual(resultado["nome"], "Aparição de Altheryn")
        self.assertEqual(resultado["hp_max"], 2470)
        self.assertEqual(resultado["andar"], 4)
        self.assertTrue(resultado["boss"])

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

    def test_mesmo_subboss_pode_ter_hp_diferente_no_segundo_andar(self):
        texto = """🗝 MASMORRA DA PLANÍCIE  Sala: 2/4 🗝
Lobo Alfa da Masmorra
❤️ HP: 291 / 291  ID: 3F00C9
👥 Grupo ⚔ 34 🛡 89
🧙 O Rastreador (Líder) — Nv. 45
🧙 EremitaDeSantoBerço — Nv. 46"""

        resultado = extrair_monstro_masmorra(texto)

        self.assertEqual(resultado["andar"], 2)
        self.assertEqual(resultado["hp_max"], 291)
        self.assertEqual(resultado["nome"], "Lobo Alfa da Masmorra")
        self.assertFalse(resultado["boss"])

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


class ExtracaoImagensAtlasTests(unittest.TestCase):
    def test_tela_principal_identifica_mapa(self):
        texto = """🏰 Planície (Lv 1)
🧙 46 EremitaDeSantoBerço
⚡ ENERGIA: 40/40 (Carrega/12min)
🧀 Tofus: 49
💰 Gold: 4850242
🗝 Chaves de Masmorra: 83"""

        self.assertEqual(
            extrair_mapa_visual(texto),
            {"nome": "Planície", "nivel": 1},
        )

    def test_entrada_identifica_masmorra_e_mapa(self):
        texto = """🗝 Masmorra da Planície
Mapa: Planície

Crie uma sala para seu grupo ou entre com o código de um amigo."""

        self.assertEqual(
            extrair_masmorra_visual(texto),
            {
                "nome": "Masmorra da Planície",
                "mapa": "Planície",
                "codigo_sala": None,
            },
        )

    def test_lobby_remove_codigo_temporario_da_masmorra(self):
        texto = """🏔 RUÍNAS DE AZULGOR F46E1F

Membros (1/5):
👑 ❌ Lv46 mago EremitaDeSantoBerço
🔑 O líder precisa de 1 Chave das Minas
Marque-se como pronto para começar!"""

        self.assertEqual(
            extrair_masmorra_visual(texto),
            {
                "nome": "RUÍNAS DE AZULGOR",
                "mapa": None,
                "codigo_sala": "F46E1F",
            },
        )


if __name__ == "__main__":
    unittest.main()

