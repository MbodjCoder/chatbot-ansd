"""Portée géographique d'une question : jamais le chiffre d'un autre lieu.

  région connue          -> traitement normal
  zone naturelle connue  -> somme des régions qui la composent (Casamance =
                            Ziguinchor + Sédhiou + Kolda)
  lieu inconnu           -> réponse honnête, sans chiffre (ville, pays voisin...)
"""
from __future__ import annotations

import re
import unicodedata

from app.sql.templates import REGIONS

# noms affichés des 14 régions
REGION_DISPLAY: dict[str, str] = {
    "dakar": "Dakar", "thies": "Thiès", "diourbel": "Diourbel",
    "saint-louis": "Saint-Louis", "ziguinchor": "Ziguinchor",
    "kaolack": "Kaolack", "fatick": "Fatick", "kolda": "Kolda",
    "louga": "Louga", "matam": "Matam", "tambacounda": "Tambacounda",
    "kedougou": "Kédougou", "kaffrine": "Kaffrine", "sedhiou": "Sédhiou",
}

# zones naturelles : population et superficie s'additionnent, pas les taux
ZONES: dict[str, list[str]] = {
    "casamance": ["ziguinchor", "sedhiou", "kolda"],
    "sine saloum": ["fatick", "kaolack", "kaffrine"],
    "sine-saloum": ["fatick", "kaolack", "kaffrine"],
    "saloum": ["fatick", "kaolack", "kaffrine"],
    "senegal oriental": ["tambacounda", "kedougou"],
}

# alias vers une région
ALIASES: dict[str, str] = {"capitale": "dakar"}

# indicateurs publiés par lieu
_GEO_KW = ("population", "habitant", "peupl", "recensement", "demograph",
           "pauvre", "pauvrete", "densite", "dense", "superficie", "gini")

# termes qui ne désignent pas un lieu (national, générique, groupe de population)
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

# lieux fréquents non couverts (pays voisins, grandes villes)
_KNOWN_NON_REGION = {
    "gambie", "mali", "mauritanie", "guinee", "guinee-bissau", "bissau",
    "cote d ivoire", "cap-vert", "cap vert", "france", "europe", "afrique",
    "touba", "mbour", "rufisque", "pikine", "guediawaye", "tivaouane",
    "mbacke", "richard-toll", "joal", "dagana", "podor", "bignona", "kebemer",
}

# prépositions de lieu (« à Touba », « dans le Ferlo »)
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
    """'population' ou 'superficie' (additionnables), sinon 'other' (taux)."""
    qf = _fold(question)
    if any(k in qf for k in ("population", "habitant", "peupl", "recensement",
                             "demograph")):
        return "population"
    if "superficie" in qf:
        return "superficie"
    return "other"


def scope(question: str) -> dict:
    """Portée de la question :
      {"kind": "na"} | {"kind": "region", "region": r} | {"kind": "national"}
      {"kind": "zone", "zone": z, "regions": [...]} | {"kind": "unknown", "place": "..."}
    """
    qf = _fold(question)
    if not any(k in qf for k in _GEO_KW):
        return {"kind": "na"}

    # région nommée
    reg = next((r for r in REGIONS if re.search(r"\b" + re.escape(r) + r"\b", qf)),
               None)
    if reg:
        return {"kind": "region", "region": reg}

    # zone naturelle
    for z, members in ZONES.items():
        if re.search(r"\b" + re.escape(z) + r"\b", qf):
            return {"kind": "zone", "zone": z, "regions": members}

    # alias (« capitale » -> Dakar)
    for a, r in ALIASES.items():
        if re.search(r"\b" + re.escape(a) + r"\b", qf):
            return {"kind": "region", "region": r}

    # nom propre, lieu connu ou préposition de lieu non résolus : lieu inconnu
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

    # sinon : niveau national
    return {"kind": "national"}


def regions_examples(n: int = 6) -> str:
    """Quelques régions, pour orienter l'usager après un refus."""
    noms = [REGION_DISPLAY[r] for r in ["dakar", "thies", "saint-louis",
                                        "ziguinchor", "kaolack", "kolda"][:n]]
    return ", ".join(noms)


def display(region_key: str) -> str:
    return REGION_DISPLAY.get(region_key, region_key.title())
