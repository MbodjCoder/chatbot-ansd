"""
Generateur SQL par gabarits (semantic parsing deterministe).

Le schema ANSD est connu et ferme ; les questions statistiques usuelles se
projettent sur un nombre borne de formes SQL. Sur ce perimetre, l'appariement
par gabarits est PLUS RAPIDE (aucun appel LLM : ~1 ms contre plusieurs
dizaines de secondes en inference locale) et PLUS SUR (Execution Accuracy
15/15 sur le jeu de test du memoire) que la generation par LLM.

Strategie hybride (pipeline SQL) : gabarit d'abord ; si aucune forme connue
ne correspond, generation LLM (DIN-SQL) pour la longue traine — meme
philosophie que le routeur 2 niveaux (rapide et sur d'abord, souple ensuite).

Retourne None si la question ne correspond a aucun gabarit.
"""
from __future__ import annotations
import re
import unicodedata

REGIONS = ["dakar", "thies", "diourbel", "saint-louis", "ziguinchor",
           "kaolack", "fatick", "kolda", "louga", "matam", "tambacounda",
           "kedougou", "kaffrine", "sedhiou"]


def _unaccent(s: str) -> str:
    """Retire TOUS les accents (a, e, i, o, u, c...) de facon robuste, pour que
    « âge », « éléctricité », « ménages » s'apparient comme leurs formes nues."""
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def template_sql(user: str) -> str | None:
    q = _unaccent(user.lower())
    q = q.replace("'", " ").replace("’", " ")
    q = re.sub(r"\s+", " ", q)
    q = q.replace("saint louis", "saint-louis")
    ym = re.search(r"\b(19|20)\d{2}\b", q)
    year = ym.group(0) if ym else None
    region = next((r for r in REGIONS if r in q), None)

    # ---- garde « regional sur indicateur national-only » ----
    # Seuls population, pauvrete, superficie, densite et Gini existent PAR REGION.
    # Une question regionale (region nommee ou « par region ») sur un autre theme
    # (chomage, inflation, PIB, accroissement, urbanisation...) n'a pas de reponse
    # regionale : on renvoie None plutot que de presenter un chiffre NATIONAL
    # comme s'il etait regional (correction d'un comportement trompeur).
    _theme_regional = any(w in q for w in (
        "population", "habitant", "peupl", "pauvre", "superficie",
        "dense", "densite", "gini"))
    if (region is not None or "region" in q) and not _theme_regional:
        return None

    # ---- superlatifs ("la region la plus peuplee", "la moins pauvre") ----
    # "le plus FAIBLE/BAS/PETIT x" = minimum : l'adjectif inverse le sens
    sup = re.search(r"\b(plus|moins)\s*(\w*)", q)
    ranking = any(w in q for w in ["classe", "classement", "compare", "toutes les regions"])
    # "le plus recent/actuel" = superlatif TEMPOREL : traite par les regles
    # standard (ORDER BY annee DESC), pas par le tri sur la valeur
    if sup and sup.group(2) in {"recent", "recente", "recents", "recentes",
                                "actuel", "actuelle", "nouveau", "nouvelle"}:
        sup = None
    if sup and not ranking:
        direction = sup.group(1)
        if sup.group(2) in {"faible", "faibles", "bas", "basse", "petit", "petite"}:
            direction = "moins" if direction == "plus" else "plus"
        order = "DESC" if direction == "plus" else "ASC"
        if "peuple" in q or "habitant" in q or ("population" in q and "region" in q):
            return ("SELECT r.nom, d.annee, d.population FROM demographie d "
                    "JOIN regions r ON r.id = d.region_id "
                    f"WHERE d.annee = 2023 ORDER BY d.population {order} LIMIT 1;")
        if "pauvre" in q:
            return ("SELECT r.nom, p.taux_pauvrete FROM pauvrete p JOIN regions r "
                    f"ON r.id = p.region_id ORDER BY p.taux_pauvrete {order} LIMIT 1;")
        if "grande" in q or "vaste" in q or "superficie" in q:
            return ("SELECT nom, superficie_km2 FROM regions "
                    f"ORDER BY superficie_km2 {order} LIMIT 1;")
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

    # ---- indicateurs nationaux : couverture EXHAUSTIVE de indicateurs_nationaux
    # (chaque chiffre publie de la table doit etre atteignable, vite et surement,
    # sans passer par le LLM). Formes specifiques en premier (rurale/urbaine
    # avant la pauvrete generique, femmes/hommes avant esperance de vie). ----
    # ordre = du PLUS specifique au plus generique ; les attributs des menages
    # (eau, electricite, proprietaires, agricoles) precedent le simple COMPTE de
    # menages, sinon « combien de menages ont l electricite » tomberait sur le
    # total. « esperance de vie des femmes » precede « esperance de vie ».
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
        (("handicap", "personnes handicapees",
          "prevalence du handicap"), "handicap"),
        (("insecurite alimentaire", "securite alimentaire",
          "acces a la nourriture", "faim"), "insecurite_alim"),
        (("scolarisation", "taux de scolarisation", "scolarise", "scolarite",
          "education au primaire", "primaire"), "tbs_primaire"),
        (("extreme pauvrete", "pauvrete extreme", "extremement pauvre"),
         "pauvrete_extreme"),
        (("pauvrete rurale", "pauvrete en milieu rural",
          "pauvrete a la campagne", "pauvrete des campagnes"),
         "pauvrete_rurale"),
        (("pauvrete urbaine", "pauvrete en milieu urbain", "pauvrete en ville",
          "pauvrete des villes"), "pauvrete_urbaine"),
    ]
    if not region:
        # « menage(s) ... agricole(s) » sous n'importe quelle tournure -> part
        # des menages agricoles (seule donnee agricole chiffree disponible).
        if "menage" in q and "agricol" in q:
            return ("SELECT libelle, valeur, unite, annee FROM "
                    "indicateurs_nationaux WHERE code = 'menages_agricoles';")
        for keys, code in _IND:
            if any(k in q for k in keys):
                return ("SELECT libelle, valeur, unite, annee FROM "
                        f"indicateurs_nationaux WHERE code = '{code}';")

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
        return ("SELECT libelle, valeur, annee FROM indicateurs_nationaux "
                "WHERE code = 'gini_national';")
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
        return ("SELECT libelle, valeur, unite, annee FROM indicateurs_nationaux "
                "WHERE code = 'esperance_vie';")
    if "fecondite" in q or "enfants par femme" in q:
        return ("SELECT libelle, valeur, unite, annee FROM indicateurs_nationaux "
                "WHERE code = 'isf';")
    if "urbanisation" in q or "urbaine" in q:
        return ("SELECT libelle, valeur, unite, annee FROM indicateurs_nationaux "
                "WHERE code = 'urbanisation';")
    if "menage" in q:
        return ("SELECT libelle, valeur, unite, annee FROM indicateurs_nationaux "
                "WHERE code IN ('menages','taille_menage');")
    if "densite" in q:
        if region:
            return ("SELECT r.nom, ROUND(d.population / r.superficie_km2, 1) AS densite_hab_km2 "
                    "FROM demographie d JOIN regions r ON r.id = d.region_id "
                    f"WHERE lower(r.nom) = '{region}' AND d.annee = 2023;")
        return ("SELECT libelle, valeur, unite, annee FROM indicateurs_nationaux "
                "WHERE code = 'densite';")
    if "population" in q or "habitant" in q or "recensement" in q or "demograph" in q:
        if "evolution" in q or "depuis" in q or "evolue" in q:
            return "SELECT annee, population FROM population_nationale ORDER BY annee;"
        if region:
            y = year or "(SELECT MAX(annee) FROM demographie)"
            return ("SELECT r.nom, d.annee, d.population FROM demographie d JOIN regions r "
                    f"ON r.id = d.region_id WHERE lower(r.nom) = '{region}' "
                    f"AND d.annee = {y};")
        if year and year not in ("2013", "2023"):
            return f"SELECT annee, population FROM population_nationale WHERE annee = {year};"
        y = year or "(SELECT MAX(annee) FROM population_nationale)"
        return f"SELECT annee, population FROM population_nationale WHERE annee = {y};"
    if "superficie" in q and region:
        return f"SELECT nom, superficie_km2 FROM regions WHERE lower(nom) = '{region}';"
    return None
