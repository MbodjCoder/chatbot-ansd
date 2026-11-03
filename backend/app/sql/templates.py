"""Traduction déterministe des questions fréquentes en requêtes SQL.

Le schéma est fermé : les questions usuelles se ramènent à un nombre borné de
formes. Ces gabarits répondent en une milliseconde, sans appel au modèle de
langage. Une question hors gabarit renvoie None et passe au modèle de langage.
"""
from __future__ import annotations

import re
import unicodedata

REGIONS = ["dakar", "thies", "diourbel", "saint-louis", "ziguinchor",
           "kaolack", "fatick", "kolda", "louga", "matam", "tambacounda",
           "kedougou", "kaffrine", "sedhiou"]

# Tranches d'âge reconnues : (expressions, condition SQL, libellé affiché)
TRANCHES = [
    (("moins de 5 ans", "moins de cinq ans", "0-4 ans", "0 a 4 ans", "nourrisson", "bebe"),
     "s.age_min < 5", "moins de 5 ans"),
    (("moins de 15 ans", "moins de quinze ans", "0-14 ans", "0 a 14 ans", "enfants"),
     "s.age_min < 15", "moins de 15 ans"),
    (("15-24 ans", "15 a 24 ans"), "s.age_min BETWEEN 15 AND 20", "15 à 24 ans"),
    (("15-59 ans", "15 a 59 ans", "age de travailler", "age actif"),
     "s.age_min BETWEEN 15 AND 55", "15 à 59 ans"),
    (("60 ans", "soixante ans", "personnes agees", "troisieme age", "3e age", "seniors"),
     "s.age_min >= 60", "60 ans et plus"),
]

_SOURCE_2025 = "FROM population_2025 p JOIN regions r ON r.id = p.region_id"


def _unaccent(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _tranche(q: str):
    if "par femme" in q:          # fécondité, pas une tranche d'âge
        return None
    return next(((cond, lib) for cles, cond, lib in TRANCHES if any(k in q for k in cles)), None)


def _parle_de_sexe(q: str) -> bool:
    return (re.search(r"\b(femmes?|hommes?|sexe|masculin|feminin)\b", q) is not None
            and not any(w in q for w in ("esperance", "chomage", "menage", "fecond", "scolar", "vie", "par femme")))


def _projection_2025(q: str, region: str | None, year: str | None) -> str | None:
    """Questions servies par les projections démographiques 2025."""
    filtre = f" WHERE lower(r.nom) = '{region}'" if region else ""
    tranche = _tranche(q)
    if tranche and (region or year == "2025"):
        cond, libelle = tranche
        selection = (f"2025 AS annee, '{libelle}' AS tranche, "
                     f"SUM(CASE WHEN {cond} THEN s.population END) AS effectif, "
                     f"ROUND(100.0 * SUM(CASE WHEN {cond} THEN s.population END) "
                     "/ SUM(s.population), 1) AS part")
        if region:
            return (f"SELECT r.nom, {selection} FROM structure_age_2025 s "
                    f"JOIN regions r ON r.id = s.region_id{filtre};")
        return f"SELECT {selection} FROM structure_age_2025 s;"
    if _parle_de_sexe(q):
        if region:
            return f"SELECT r.nom, 2025 AS annee, p.hommes, p.femmes, p.population {_SOURCE_2025}{filtre};"
        return ("SELECT 2025 AS annee, SUM(hommes) AS hommes, SUM(femmes) AS femmes, "
                "SUM(population) AS population FROM population_2025;")
    if any(w in q for w in ("urbain", "rural", "urbanis")) and (region or year == "2025"):
        if region:
            return f"SELECT r.nom, 2025 AS annee, p.part_urbaine {_SOURCE_2025}{filtre};"
        return ("SELECT 2025 AS annee, ROUND(100.0 * SUM(urbaine) / SUM(population), 1) "
                "AS part_urbaine FROM population_2025;")
    if year == "2025" and any(w in q for w in ("population", "habitant", "peupl")):
        if region:
            return f"SELECT r.nom, 2025 AS annee, p.population {_SOURCE_2025}{filtre};"
        return "SELECT 2025 AS annee, SUM(population) AS population FROM population_2025;"
    return None


# Indicateurs nationaux, du plus spécifique au plus générique
_IND = [
    (("esperance de vie des femmes", "esperance de vie feminine",
      "esperance de vie chez les femmes"), "esperance_vie_femmes"),
    (("esperance de vie des hommes", "esperance de vie masculine",
      "esperance de vie chez les hommes"), "esperance_vie_hommes"),
    (("esperance de vie", "duree de vie"), "esperance_vie"),
    (("age median", "age moyen", "age de la population"), "age_median"),
    (("moins de 15 ans", "moins de quinze", "part des jeunes",
      "jeunes de moins", "enfants de moins de 15"), "moins_15_ans"),
    (("accroissement", "croissance demographique",
      "croissance de la population", "rythme de croissance",
      "taux de croissance de la pop"), "croissance_demo"),
    (("robinet", "eau potable", "acces a l eau", "eau courante",
      "eau dans le logement", "eau au robinet"), "eau_robinet"),
    (("electricite", "eclairage", "electrification"), "electricite"),
    (("proprietaire", "propriete du logement",
      "proprietaires de leur logement"), "proprietaires"),
    (("menages agricoles", "menage agricole", "menages sont agricoles",
      "sont agricoles", "pratiquent l agriculture",
      "part des menages agric"), "menages_agricoles"),
    (("taille des menages", "taille du menage", "taille moyenne des menages",
      "personnes par menage", "membres par menage",
      "combien de personnes par"), "taille_menage"),
    (("nombre de menages", "combien de menages", "total des menages",
      "combien y a-t-il de menages", "menages ordinaires"), "menages"),
    (("handicap", "personnes handicapees", "prevalence du handicap"), "handicap"),
    (("insecurite alimentaire", "securite alimentaire",
      "acces a la nourriture", "faim"), "insecurite_alim"),
    (("scolarisation", "taux de scolarisation", "scolarise", "scolarite",
      "education au primaire", "primaire"), "tbs_primaire"),
    (("extreme pauvrete", "pauvrete extreme", "extremement pauvre"), "pauvrete_extreme"),
    (("pauvrete rurale", "pauvrete en milieu rural",
      "pauvrete a la campagne", "pauvrete des campagnes"), "pauvrete_rurale"),
    (("pauvrete urbaine", "pauvrete en milieu urbain", "pauvrete en ville",
      "pauvrete des villes"), "pauvrete_urbaine"),
]


def _indicateur(code: str) -> str:
    return ("SELECT libelle, valeur, unite, annee FROM indicateurs_nationaux "
            f"WHERE code = '{code}';")


def template_sql(user: str) -> str | None:
    q = _unaccent(user.lower()).replace("'", " ").replace("’", " ")
    q = re.sub(r"\s+", " ", q).replace("saint louis", "saint-louis")
    ym = re.search(r"\b(19|20)\d{2}\b", q)
    year = ym.group(0) if ym else None
    region = next((r for r in REGIONS if r in q), None)

    # Une question régionale sur un thème uniquement national (chômage,
    # inflation, PIB...) n'a pas de réponse : ne pas présenter le chiffre
    # national comme s'il était régional.
    theme_regional = (any(w in q for w in (
        "population", "habitant", "peupl", "pauvre", "superficie", "dense",
        "densite", "gini", "urbain", "rural", "urbanis"))
        or _parle_de_sexe(q) or _tranche(q) is not None)
    if (region is not None or "region" in q) and not theme_regional:
        return None

    # Superlatifs : « la région la plus peuplée », « la moins pauvre »
    sup = re.search(r"\b(plus|moins)\s*(\w*)", q)
    ranking = any(w in q for w in ["classe", "classer", "classement", "compare",
                                   "comparer", "toutes les regions", "par region",
                                   "rang", "ordre", "palmares", "decroiss", "croiss"])
    # « le plus récent » est temporel : traité par les règles standard
    if sup and sup.group(2) in {"recent", "recente", "recents", "recentes",
                                "actuel", "actuelle", "nouveau", "nouvelle"}:
        sup = None
    if sup and not ranking and _tranche(q) is None:
        direction = sup.group(1)
        if sup.group(2) in {"faible", "faibles", "bas", "basse", "petit", "petite"}:
            direction = "moins" if direction == "plus" else "plus"
        order = "DESC" if direction == "plus" else "ASC"
        if "urbanis" in q or "urbain" in q:
            return (f"SELECT r.nom, 2025 AS annee, p.part_urbaine {_SOURCE_2025} "
                    f"ORDER BY p.part_urbaine {order} LIMIT 1;")
        if "peuple" in q or "habitant" in q or ("population" in q and "region" in q):
            return ("SELECT r.nom, d.annee, d.population FROM demographie d "
                    "JOIN regions r ON r.id = d.region_id "
                    f"WHERE d.annee = 2023 ORDER BY d.population {order} LIMIT 1;")
        if "pauvre" in q:
            return ("SELECT r.nom, p.taux_pauvrete FROM pauvrete p JOIN regions r "
                    f"ON r.id = p.region_id ORDER BY p.taux_pauvrete {order} LIMIT 1;")
        if "grande" in q or "vaste" in q or "superficie" in q:
            return f"SELECT nom, superficie_km2 FROM regions ORDER BY superficie_km2 {order} LIMIT 1;"
        if "dense" in q:
            return ("SELECT r.nom, ROUND(d.population / r.superficie_km2, 1) AS densite_hab_km2 "
                    "FROM demographie d JOIN regions r ON r.id = d.region_id "
                    f"WHERE d.annee = 2023 ORDER BY densite_hab_km2 {order} LIMIT 1;")
        if "inflation" in q:
            return f"SELECT annee, taux_inflation FROM inflation ORDER BY taux_inflation {order} LIMIT 1;"
        if "chomage" in q:
            return ("SELECT annee, trimestre, taux_chomage_elargi FROM emploi "
                    f"ORDER BY taux_chomage_elargi {order} LIMIT 1;")
        if "gini" in q or "inegal" in q:
            return ("SELECT r.nom, p.gini FROM pauvrete p JOIN regions r "
                    f"ON r.id = p.region_id ORDER BY p.gini {order} LIMIT 1;")

    # Classement complet des régions
    if ranking and not region:
        r_order = "ASC" if "croiss" in q and "decroiss" not in q else "DESC"
        if "urbanis" in q or "urbain" in q:
            return (f"SELECT r.nom, 2025 AS annee, p.part_urbaine {_SOURCE_2025} "
                    f"ORDER BY p.part_urbaine {r_order};")
        if "peuple" in q or "habitant" in q or "population" in q or "demograph" in q:
            return ("SELECT r.nom, d.annee, d.population FROM demographie d JOIN regions r "
                    "ON r.id = d.region_id WHERE d.annee = (SELECT MAX(annee) FROM demographie) "
                    f"ORDER BY d.population {r_order};")
        if "pauvre" in q:
            return ("SELECT r.nom, p.taux_pauvrete FROM pauvrete p JOIN regions r "
                    f"ON r.id = p.region_id ORDER BY p.taux_pauvrete {r_order};")
        if "superficie" in q or "grande" in q or "vaste" in q or "etendue" in q:
            return f"SELECT nom, superficie_km2 FROM regions ORDER BY superficie_km2 {r_order};"
        if "dense" in q or "densite" in q:
            return ("SELECT r.nom, d.annee, ROUND(d.population / r.superficie_km2, 1) AS densite_hab_km2 "
                    "FROM demographie d JOIN regions r ON r.id = d.region_id "
                    f"WHERE d.annee = 2023 ORDER BY densite_hab_km2 {r_order};")
        if "gini" in q or "inegal" in q:
            return ("SELECT r.nom, p.gini FROM pauvrete p JOIN regions r "
                    f"ON r.id = p.region_id ORDER BY p.gini {r_order};")

    projection = _projection_2025(q, region, year)
    if projection:
        return projection

    if not region:
        if "menage" in q and "agricol" in q:
            return _indicateur("menages_agricoles")
        for cles, code in _IND:
            if any(k in q for k in cles):
                return _indicateur(code)

    if "chomage" in q:
        w = f"WHERE annee = {year}" if year else "ORDER BY annee DESC, trimestre DESC LIMIT 1"
        return f"SELECT annee, trimestre, taux_chomage_elargi FROM emploi {w};"
    if "activite" in q:
        return ("SELECT annee, trimestre, taux_activite FROM emploi "
                "WHERE taux_activite IS NOT NULL ORDER BY annee DESC, trimestre DESC LIMIT 1;")
    if "inflation" in q or "prix" in q or "ihpc" in q:
        if "evolution" in q or "depuis" in q or "evolue" in q:
            return "SELECT annee, taux_inflation FROM inflation ORDER BY annee;"
        w = f"WHERE annee = {year}" if year else "ORDER BY annee DESC LIMIT 1"
        return f"SELECT annee, taux_inflation FROM inflation {w};"
    if "pib" in q or "croissance econom" in q or "croissance du pib" in q:
        if "evolution" in q or "depuis" in q:
            return "SELECT annee, croissance_reelle FROM pib ORDER BY annee;"
        w = f"WHERE annee = {year}" if year else "ORDER BY annee DESC LIMIT 1"
        return f"SELECT annee, croissance_reelle FROM pib {w};"
    if "gini" in q or "inegalite" in q:
        if region:
            return ("SELECT r.nom, p.gini FROM pauvrete p JOIN regions r "
                    f"ON r.id = p.region_id WHERE lower(r.nom) = '{region}';")
        return "SELECT libelle, valeur, annee FROM indicateurs_nationaux WHERE code = 'gini_national';"
    if "pauvrete" in q or "pauvre" in q:
        if region:
            return ("SELECT r.nom, p.taux_pauvrete FROM pauvrete p JOIN regions r "
                    f"ON r.id = p.region_id WHERE lower(r.nom) = '{region}';")
        if any(w in q for w in ["classe", "classement", "region", "comparaison", "plus pauvre"]):
            return ("SELECT r.nom, p.taux_pauvrete FROM pauvrete p JOIN regions r "
                    "ON r.id = p.region_id ORDER BY p.taux_pauvrete DESC;")
        return ("SELECT libelle, valeur, unite, annee, source FROM indicateurs_nationaux "
                "WHERE code = 'pauvrete_nationale';")
    if "esperance de vie" in q:
        return _indicateur("esperance_vie")
    if "fecondite" in q or "enfants par femme" in q:
        return _indicateur("isf")
    if "urbanisation" in q or "urbaine" in q:
        return _indicateur("urbanisation")
    if "menage" in q:
        return ("SELECT libelle, valeur, unite, annee FROM indicateurs_nationaux "
                "WHERE code IN ('menages','taille_menage');")
    if "densite" in q:
        if region:
            return ("SELECT r.nom, ROUND(d.population / r.superficie_km2, 1) AS densite_hab_km2 "
                    "FROM demographie d JOIN regions r ON r.id = d.region_id "
                    f"WHERE lower(r.nom) = '{region}' AND d.annee = 2023;")
        return _indicateur("densite")
    if "population" in q or "habitant" in q or "recensement" in q or "demograph" in q:
        if "evolution" in q or "depuis" in q or "evolue" in q:
            return "SELECT annee, population FROM population_nationale ORDER BY annee;"
        if region:
            y = year or "(SELECT MAX(annee) FROM demographie)"
            return ("SELECT r.nom, d.annee, d.population FROM demographie d JOIN regions r "
                    f"ON r.id = d.region_id WHERE lower(r.nom) = '{region}' AND d.annee = {y};")
        if year and year not in ("2013", "2023"):
            return f"SELECT annee, population FROM population_nationale WHERE annee = {year};"
        y = year or "(SELECT MAX(annee) FROM population_nationale)"
        return f"SELECT annee, population FROM population_nationale WHERE annee = {y};"
    if "superficie" in q and region:
        return f"SELECT nom, superficie_km2 FROM regions WHERE lower(nom) = '{region}';"
    return None
