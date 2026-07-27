"""
Questions les plus recherchees, par categorie thematique.

Justification (memoire, principe d'initiative mixte — Horvitz 1999) : proposer a
l'usager les questions reellement les plus posees reduit son effort de formulation
et l'oriente vers les donnees pertinentes. Le classement n'est pas arbitraire : il
est *calcule* sur la telemetrie reelle du service (interactions.jsonl), voie et
guardrail compris, en excluant les actes sociaux et les refus (qui ne sont pas des
recherches d'information). Une base curatee garantit la couverture et une
formulation soignee ; la frequence observee ordonne l'ensemble.

Confidentialite (Principe 6, Nations Unies 2014) : on n'agrege que le TEXTE des
questions et leur frequence ; aucun identifiant, aucune donnee personnelle.
"""
from __future__ import annotations

import re
import time
import unicodedata
from collections import Counter

from app.core import telemetry

# --- categories : libelle grand public + icone + mots-cles de classification ---
# L'ordre des cles compte : une question est classee dans la PREMIERE categorie
# dont un mot-cle correspond (les plus specifiques d'abord).
CATEGORIES: list[dict] = [
    {
        "id": "population", "label": "Population & démographie", "icon": "👥",
        "hint": "Habitants, régions, urbanisation, croissance démographique",
        "keywords": ["population", "habitant", "demograph", "peupl", "urbanisation",
                     "urbain", "densite", "recensement", "rgph", "accroissement",
                     "natalite", "fecondite", "menage"],
        "seeds": [
            "Quelle est la population du Sénégal en 2023 ?",
            "Quelle est la population de Dakar en 2023 ?",
            "Quel est le taux d'urbanisation du pays ?",
            "Quel est le taux d'accroissement de la population depuis 2013 ?",
            "Classe les régions par population décroissante",
            "Quelle est la région la plus peuplée du Sénégal ?",
        ],
    },
    {
        "id": "emploi", "label": "Emploi & chômage", "icon": "💼",
        "hint": "Chômage, activité, emploi des jeunes",
        "keywords": ["chomage", "chômage", "emploi", "activite", "travail",
                     "actifs", "bit", "enes"],
        "seeds": [
            "Quel est le taux de chômage en 2024 ?",
            "Quel est le taux de chômage des jeunes ?",
            "Quel est le taux d'activité au Sénégal ?",
            "Comment évolue le chômage depuis 2019 ?",
        ],
    },
    {
        "id": "pauvrete", "label": "Pauvreté & niveau de vie", "icon": "🏠",
        "hint": "Taux de pauvreté, inégalités, consommation",
        "keywords": ["pauvret", "pauvre", "gini", "inegalit", "niveau de vie",
                     "consommation", "ehcvm", "seuil"],
        "seeds": [
            "Classe les régions par taux de pauvreté décroissant",
            "Quel est le taux de pauvreté au Sénégal ?",
            "Qu'est-ce que l'indice de Gini ?",
            "Comment l'ANSD mesure-t-elle la pauvreté ?",
            "Quelle région est la plus touchée par la pauvreté ?",
        ],
    },
    {
        # Prix & inflation fusionnés ici : l'économie couvre PIB, croissance,
        # comptes nationaux ET prix/inflation (une seule entrée thématique).
        "id": "economie", "label": "Économie & croissance", "icon": "📈",
        "hint": "PIB, croissance, comptes nationaux, prix & inflation",
        "keywords": ["pib", "croissance", "comptes nationaux", "economie",
                     "economique", "richesse", "valeur ajoutee",
                     "inflation", "prix", "ihpc", "cout de la vie", "cherte",
                     "pouvoir d'achat"],
        "seeds": [
            "Quelle est la croissance du PIB en 2024 ?",
            "Quel est le taux d'inflation en 2024 ?",
            "Comment évolue la croissance depuis 2019 ?",
            "Quel est le PIB du Sénégal ?",
            "Comment l'IHPC est-il calculé ?",
        ],
    },
    {
        "id": "documents", "label": "Trouver un document", "icon": "🧭",
        "hint": "Rapports, enquêtes, microdonnées ANADS, contact",
        "keywords": ["telecharg", "rapport", "ou trouver", "ou est", "document",
                     "enquete", "enquetes", "microdonnee", "anads", "publication",
                     "contacter", "contact", "fiche", "donnees sur", "catalogue"],
        "seeds": [
            "Où trouver les rapports du RGPH-5 ?",
            "Où télécharger le rapport EHCVM ?",
            "Quelles enquêtes sur la santé ?",
            "Je veux les données sur la pêche",
            "Comment contacter l'ANSD ?",
        ],
    },
]

_CACHE: dict = {"ts": 0.0, "data": None}
_TTL = 60.0  # s : le classement est recalcule au plus une fois par minute


# tournures interrogatives de tete, pur bruit de formulation : les retirer permet
# de fusionner « Population du Senegal en 2023 ? » et « Quelle est la population… ».
_LEADS = [
    "qu est ce que", "qu est ce qui", "quelle est la", "quelle est le",
    "quel est le", "quel est la", "quelles sont les", "quels sont les",
    "quelle est", "quel est", "combien de", "combien d", "c est quoi le",
    "c est quoi la", "c est quoi", "que signifie le", "que signifie la",
    "que signifie", "donne moi le", "donne moi la", "donne moi",
    "je veux le", "je veux la", "je veux les", "je veux",
]


def _base(s: str) -> str:
    """Minuscules, sans accents, sans ponctuation finale, espaces reduits."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[?!.]+$", "", s).strip()
    s = re.sub(r"[’']", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm(s: str) -> str:
    """Cle de regroupement : forme de base, tournure interrogative de tete retiree,
    pour que deux formulations de la meme recherche comptent ensemble."""
    s = _base(s)
    changed = True
    while changed:
        changed = False
        for lead in _LEADS:
            if s.startswith(lead + " "):
                s = s[len(lead) + 1:]
                changed = True
                break
    return s


def _classify(qn: str) -> str | None:
    for cat in CATEGORIES:
        for kw in cat["keywords"]:
            if kw in qn:
                return cat["id"]
    return None


def compute(limit: int = 6) -> dict:
    """Retourne, par categorie, les questions les plus recherchees, classees par
    frequence reelle observee. Les questions curatees garantissent la couverture ;
    les comptes issus de la telemetrie determinent l'ordre et ajoutent les
    formulations reelles frequentes absentes de la base curatee."""
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < _TTL:
        return _CACHE["data"]

    inter = telemetry._read("interactions.jsonl")
    # comptes par (categorie, cle normalisee) ; on garde la meilleure forme d'affichage
    counts: Counter = Counter()
    display: dict[tuple[str, str], str] = {}
    for r in inter:
        # exclure les actes sociaux et les refus : ce ne sont pas des recherches
        if r.get("route") == "CHAT":
            continue
        if r.get("guardrail", "ok") != "ok":
            continue
        q = (r.get("question") or "").strip()
        if len(q) < 6:
            continue
        qn = _norm(q)
        cat = _classify(qn)
        if not cat:
            continue
        key = (cat, qn)
        counts[key] += 1
        # forme d'affichage : la plus « propre » vue (avec accents / majuscule initiale)
        prev = display.get(key)
        if prev is None or _cleanliness(q) > _cleanliness(prev):
            display[key] = q

    out_cats = []
    for cat in CATEGORIES:
        cid = cat["id"]
        # 1) questions curatees, avec leur compte reel (0 si jamais posee)
        seen: set[str] = set()
        items: list[dict] = []
        for seed in cat["seeds"]:
            kn = _norm(seed)
            seen.add(kn)
            items.append({"q": seed, "n": counts.get((cid, kn), 0), "seed": True})
        # 2) formulations reelles frequentes hors base curatee (bruit ecarte : n>=3)
        extras = [((c, k), n) for (c, k), n in counts.items()
                  if c == cid and k not in seen and n >= 3]
        extras.sort(key=lambda x: -x[1])
        for (c, k), n in extras[:4]:
            items.append({"q": _polish(display[(c, k)]), "n": n, "seed": False})
        # tri final : par frequence reelle decroissante, les curatees non posees
        # gardant une visibilite (elles restent, mais apres les vraies populaires)
        items.sort(key=lambda it: (-it["n"], not it["seed"]))
        total = sum(it["n"] for it in items)
        out_cats.append({
            "id": cid, "label": cat["label"], "icon": cat["icon"],
            "hint": cat["hint"], "total_recherches": total,
            "questions": [{"q": it["q"], "recherches": it["n"]}
                          for it in items[:limit]],
        })

    # ordonner les categories par volume total de recherches (les plus actives d'abord)
    out_cats.sort(key=lambda c: -c["total_recherches"])
    data = {"categories": out_cats,
            "note": "Classement calculé sur la télémétrie réelle du service "
                    "(hors salutations et refus)."}
    _CACHE.update(ts=now, data=data)
    return data


def _polish(s: str) -> str:
    """Presentation : majuscule initiale, espaces propres. On ne touche pas a la
    ponctuation (une consigne « je veux… » ne prend pas de « ? »)."""
    s = s.strip()
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s


def _cleanliness(s: str) -> int:
    """Score heuristique de « propreté » d'une formulation pour l'affichage :
    presence d'accents et d'une majuscule initiale = plus lisible."""
    score = 0
    if s[:1].isupper():
        score += 1
    if any(unicodedata.combining(c) for c in unicodedata.normalize("NFD", s)):
        score += 2  # a des accents
    if s.rstrip().endswith("?"):
        score += 1
    return score
