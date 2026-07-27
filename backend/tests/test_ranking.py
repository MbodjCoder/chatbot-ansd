"""
Classement des régions (« classe les régions par population décroissante »...).

Défaut corrigé : ces demandes retombaient sur le CHIFFRE NATIONAL
(« Le Sénégal comptait 18 126 390 habitants ») au lieu de classer les régions.
"""


def test_classement_population_decroissant(chatbot):
    r = chatbot.ask("Classe les régions par population décroissante")
    assert r.route == "SQL"
    assert r.guardrail == "ok"
    assert "18 126 390" not in r.answer          # pas le national substitué
    assert "classement" in r.answer.lower()
    assert r.data and len(r.data["rows"]) == 14   # les 14 régions
    # ordre décroissant : 1ʳᵉ ligne >= dernière
    assert r.data["rows"][0][-1] >= r.data["rows"][-1][-1]
    assert "Dakar" in r.answer                    # la plus peuplée en tête


def test_classement_population_croissant(chatbot):
    r = chatbot.ask("Classe les régions par population croissante")
    assert r.route == "SQL" and r.guardrail == "ok"
    assert r.data["rows"][0][-1] <= r.data["rows"][-1][-1]  # croissant


def test_classement_pauvrete(chatbot):
    r = chatbot.ask("Classe les régions par taux de pauvreté décroissant")
    assert r.route == "SQL" and r.guardrail == "ok"
    assert r.data and len(r.data["rows"]) == 14


def test_national_inchange(chatbot):
    r = chatbot.ask("Quelle est la population du Sénégal en 2023 ?")
    assert r.route == "SQL" and "18 126 390" in r.answer
