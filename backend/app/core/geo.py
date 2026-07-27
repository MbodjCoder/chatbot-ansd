"""
Garde géographique : garantir qu'une question portant sur un lieu reçoit une
réponse pour l'ENTITÉ RÉELLEMENT DEMANDÉE — jamais un chiffre national (ou d'une
autre entité) substitué en silence.

Motivation (système « incontestable », P1 — ancrage vérifiable). Défaut corrigé :
« Quelle est la population de la Casamance ? » renvoyait la population NATIONALE
(18 126 390) — un chiffre vrai, mais qui ne répond PAS à la question. La règle
générale : si le lieu demandé n'est pas résoluble à la maille publiée par l'ANSD
(national + 14 régions), on ne substitue rien — on répond honnêtement.

Trois cas résolus :
  - RÉGION administrative connue      -> voie normale (le pipeline SQL répond) ;
  - ZONE naturelle connue (agrégat)   -> réponse correcte par agrégation des
                                         régions qui la composent (ex. Casamance
                                         = Ziguinchor + Sédhiou + Kolda) ;
  - LIEU non résolu (pays voisin,
    ville, département, zone inconnue) -> réponse honnête, sans chiffre substitué.

Tout le reste (question nationale ou non géographique) est laissé au pipeline
existant : ce module n'intervient QUE pour les cas « zone » et « inconnu ».
"""
from __future__ import annotations

import re
import unicodedata

from app.sql.templates import REGIONS

# Libellés d'affichage (accentués) des 14 régions administratives.
REGION_DISPLAY: dict[str, str] = {
    "dakar": "Dakar", "thies": "Thiès", "diourbel": "Diourbel",
    "saint-louis": "Saint-Louis", "ziguinchor": "Ziguinchor",
    "kaolack": "Kaolack", "fatick": "Fatick", "kolda": "Kolda",
    "louga": "Louga", "matam": "Matam", "tambacounda": "Tambacounda",
    "kedougou": "Kédougou", "kaffrine": "Kaffrine", "sedhiou": "Sédhiou",
}

# Zones NATURELLES (non administratives) = agrégats de régions officielles.
# Une population/superficie de zone est la SOMME de ses régions (agrégation
# valide) ; un taux (pauvreté, densité, Gini) ne s'additionne pas (voir chatbot).
ZONES: dict[str, list[str]] = {
    "casamance": ["ziguinchor", "sedhiou", "kolda"],
    "sine saloum": ["fatick", "kaolack", "kaffrine"],
    "sine-saloum": ["fatick", "kaolack", "kaffrine"],
    "saloum": ["fatick", "kaolack", "kaffrine"],
    "senegal oriental": ["tambacounda", "kedougou"],
}

# Alias d'un objet locatif vers une région administrative.
ALIASES: dict[str, str] = {"capitale": "dakar"}

# Indicateurs qui ont un sens PAR LIEU (les seuls où un lieu est pertinent).
_GEO_KW = ("population", "habitant", "peupl", "recensement", "demograph",
           "pauvre", "pauvrete", "densite", "dense", "superficie", "gini")

# Objets locatifs qui ne désignent PAS un lieu résoluble à refuser : termes
# nationaux/génériques et sous-populations démographiques courantes.
_STOP = {
    "senegal", "pays", "nation", "national", "nationale", "territoire",
    "ensemble", "total", "totale", "region", "regions", "milieu", "monde",
    "urbain", "urbaine", "rural", "rurale", "ville", "villes", "campagne",
    "campagnes", "menage", "menages", "population", "habitant", "habitants",
    "gens", "personnes", "individus", "resident", "residents", "jeune",
    "jeunes", "femme", "femmes", "homme", "hommes", "enfant", "enfants",
    "adulte", "adultes", "senior", "seniors", "actif", "actifs", "chomeur",
    "chomeurs", "etranger", "etrangers", "migrant", "migrants", "etudiant",
    "etudiants", "travailleur", "travailleurs", "pauvre", "pauvres", "riche",
    "riches", "moyenne", "moyen",
}

# Lieux fréquents NON couverts à la maille régionale (pays voisins, grandes
# villes) : permet de refuser proprement même en minuscules (sans majuscule).
_KNOWN_NON_REGION = {
    "gambie", "mali", "mauritanie", "guinee", "guinee-bissau", "bissau",
    "cote d ivoire", "cap-vert", "cap vert", "france", "europe", "afrique",
    "touba", "mbour", "rufisque", "pikine", "guediawaye", "tivaouane",
    "mbacke", "richard-toll", "joal", "dagana", "podor", "bignona", "kebemer",
}

# Prépositions FORTEMENT géographiques : l'objet est un lieu quelle que soit
# sa casse ("à Touba", "dans le Ferlo", "région de X").
_STRONG = {"a", "au", "aux", "dans", "dans le", "dans la", "dans l",
           "region de", "ville de", "departement de", "commune de", "zone de"}

_LOC = re.compile(
    r"\b(?P<prep>region de|ville de|departement de|commune de|zone de"
    r"|dans\s+l[ae]|dans\s+l|dans|de\s+la|de\s+l|du|des|de|a\s+la|au|aux|à\s+la|à|a)"
    r"\s+(?P<obj>[A-Za-zÀ-ÿ][\wÀ-ÿ'’-]*)",
    re.I)


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("’", " ").replace("'", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("saint louis", "saint-louis")
    return s


def indicator(question: str) -> str:
    """Type d'indicateur géographique : 'population', 'superficie' (agrégeables
    sur une zone) ou 'other' (taux — non agrégeable)."""
    qf = _fold(question)
    if any(k in qf for k in ("population", "habitant", "peupl", "recensement",
                             "demograph")):
        return "population"
    if "superficie" in qf:
        return "superficie"
    return "other"


def scope(question: str) -> dict:
    """Classe la portée géographique de la question.

    Renvoie un dict :
      {"kind": "na"}                         question non géographique -> ignorer
      {"kind": "region", "region": r}        région connue -> voie normale
      {"kind": "national"}                   national/générique -> voie normale
      {"kind": "zone", "zone": z, "regions": [...]}
      {"kind": "unknown", "place": "..."}    lieu non résoluble -> refus honnête
    """
    qf = _fold(question)
    if not any(k in qf for k in _GEO_KW):
        return {"kind": "na"}

    # 1) région administrative nommée (résolue d'abord, minuscules comprises)
    reg = next((r for r in REGIONS if re.search(r"\b" + re.escape(r) + r"\b", qf)),
               None)
    if reg:
        return {"kind": "region", "region": reg}

    # 2) zone naturelle connue (agrégat de régions)
    for z, members in ZONES.items():
        if re.search(r"\b" + re.escape(z) + r"\b", qf):
            return {"kind": "zone", "zone": z, "regions": members}

    # 3) alias (« capitale » -> Dakar)
    for a, r in ALIASES.items():
        if re.search(r"\b" + re.escape(a) + r"\b", qf):
            return {"kind": "region", "region": r}

    # 4) objet locatif non résolu ? (majuscule = nom propre, ou lieu connu, ou
    #    préposition fortement géographique) -> lieu inconnu, on refuse.
    for m in _LOC.finditer(question):
        prep = _fold(m.group("prep"))
        obj_raw = m.group("obj").strip()
        objf = _fold(obj_raw)
        head = objf.split(" ")[0]
        if not head or head in _STOP:
            continue
        capitalized = obj_raw[:1].isupper()
        is_place = (prep in _STRONG or capitalized
                    or objf in _KNOWN_NON_REGION or head in _KNOWN_NON_REGION)
        if is_place and len(head) >= 3:
            return {"kind": "unknown", "place": obj_raw}

    # 5) sinon : national / générique -> voie normale
    return {"kind": "national"}


def regions_examples(n: int = 6) -> str:
    """Quelques régions, pour orienter l'usager après un refus."""
    noms = [REGION_DISPLAY[r] for r in ["dakar", "thies", "saint-louis",
                                        "ziguinchor", "kaolack", "kolda"][:n]]
    return ", ".join(noms)


def display(region_key: str) -> str:
    return REGION_DISPLAY.get(region_key, region_key.title())
