"""
Garde géographique (P1, « incontestable ») : on ne substitue JAMAIS un chiffre
d'une autre entité à celle demandée.

Défaut corrigé : « population de la Casamance » renvoyait la population NATIONALE
(vraie, mais hors-sujet). Désormais : zone naturelle -> agrégation correcte ;
lieu non résoluble -> réponse honnête, sans chiffre substitué ; région/national
-> voie normale inchangée.
"""
import pytest

from app.core import geo


@pytest.mark.parametrize("question,attendu", [
    # zones naturelles (agrégat de régions)
    ("Quelle est la population de la Casamance ?", "zone"),
    ("population de la casamance en 2023", "zone"),
    ("Quelle est la superficie de la Casamance ?", "zone"),
    ("Quelle est la population du Sine-Saloum ?", "zone"),
    # lieux non résolubles -> refus honnête
    ("Quelle est la population de la Gambie ?", "unknown"),
    ("population à Touba", "unknown"),
    ("population de la ville de Mbour", "unknown"),
    ("population dans le département de Bignona", "unknown"),
    # régions administratives -> voie normale
    ("Quelle est la population de Dakar en 2023 ?", "region"),
    ("population de saint louis", "region"),
    ("population de la capitale", "region"),
    # national / générique -> voie normale
    ("Quelle est la population du Sénégal en 2023 ?", "national"),
    ("Quelle est la population ?", "national"),
    ("population des jeunes au Sénégal", "national"),
    ("population de la région la plus peuplée", "national"),
    ("classe les régions par population décroissante", "national"),
    # non géographique -> ne pas intervenir
    ("Quel est le taux de chômage en 2024 ?", "na"),
])
def test_scope(question, attendu):
    assert geo.scope(question)["kind"] == attendu


def test_casamance_est_somme_des_regions(chatbot):
    """La population de la Casamance = somme de Ziguinchor + Sédhiou + Kolda,
    et surtout PAS la population nationale (18 126 390)."""
    r = chatbot.ask("Quelle est la population de la Casamance ?")
    assert r.route == "GEO"
    assert "18 126 390" not in r.answer            # jamais le national substitué
    assert "2 121 632" in r.answer                 # somme des trois régions
    for reg in ("Ziguinchor", "Kolda"):
        assert reg in r.answer                     # détail par région montré


def test_lieu_inconnu_refuse_sans_chiffre(chatbot):
    r = chatbot.ask("Quelle est la population de la Gambie ?")
    assert r.route == "GEO"
    assert "Gambie" in r.answer
    assert "18 126 390" not in r.answer            # aucun chiffre substitué
    assert "région" in r.answer.lower()            # oriente vers les régions


def test_zone_taux_non_agregeable(chatbot):
    r = chatbot.ask("Quel est le taux de pauvreté de la Casamance ?")
    assert r.route == "GEO"
    assert "additionne" in r.answer.lower() or "chacune" in r.answer.lower()


def test_region_et_national_inchanges(chatbot):
    """La garde ne perturbe pas les voies existantes."""
    rd = chatbot.ask("Quelle est la population de Dakar en 2023 ?")
    assert rd.route == "SQL" and "Dakar" in rd.answer
    rn = chatbot.ask("Quelle est la population du Sénégal en 2023 ?")
    assert rn.route == "SQL" and "18 126 390" in rn.answer
