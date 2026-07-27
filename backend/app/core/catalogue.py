"""
Recherche dans le catalogue ANADS (300 fiches d'etudes recoltees via l'API
publique NADA — scripts/harvest_anads.py, metadonnees officielles).

Le chatbot devient capable de repondre a « quelles enquetes existent sur la
sante ? », « y a-t-il des microdonnees sur l'agriculture ? », etc., en citant
les fiches EXACTES du catalogue (titre, periode, producteur, lien direct).
Grounding structurel : chaque element de la reponse provient verbatim du
catalogue — meme garantie que la verbalisation SQL (decision #10).

Les fichiers de microdonnees restent soumis a la demande d'acces sur la
plateforme : la reponse oriente vers la fiche ou cette demande se fait,
c'est le parcours officiel ANSD.
"""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path

from app.core.config import settings

_CAT_PATH = Path(settings.database_path).parent / "anads_catalogue.json"

# vocabulaire theme -> termes de recherche etendus (synonymes du domaine)
_EXPANSIONS = {
    "sante": ["sante", "demographique et de sante", "eds", "paludisme",
              "vaccination", "mortalite", "vih", "tabagisme", "nutrition"],
    "agriculture": ["agricole", "agriculture", "rural", "recolte", "elevage",
                    "horticole"],
    "emploi": ["emploi", "travail", "informel", "main d oeuvre", "enes"],
    "pauvrete": ["pauvrete", "conditions de vie", "ehcvm", "esam", "esps",
                 "menages", "bien-etre"],
    "education": ["education", "alphabetisation", "scolaire", "competences"],
    "population": ["recensement", "population", "habitat", "rgph",
                   "demographique", "migration"],
    "entreprise": ["entreprise", "unites de production", "industrie",
                   "commerce", "informel", "cuci"],
    "prix": ["prix", "consommation", "ihpc", "indice"],
    "genre": ["genre", "femme", "violence", "fecondite"],
    "peche": ["peche", "pirogue", "halieutique", "maritime", "aquaculture",
              "piroguier", "poisson", "peche artisanale"],
    "tourisme": ["tourisme", "touristique", "hotel", "hebergement"],
    "transport": ["transport", "mobilite", "routier"],
    "commerce": ["commerce", "commercial", "importation", "exportation",
                 "echanges"],
}

# Mots non discriminants : presents dans presque toutes les fiches (ex.
# « senegal ») ou issus de la formulation de la demande (« donnees »,
# « statistiques », « je veux »...). Les garder fausserait le score et ferait
# remonter des etudes recentes hors sujet au lieu des etudes du theme demande.
_STOP = {
    "senegal", "donnee", "donnees", "statistique", "statistiques", "chiffre",
    "chiffres", "data", "dataset", "microdonnee", "microdonnees", "information",
    "informations", "veux", "voudrais", "souhaite", "cherche", "aimerais",
    "desire", "avoir", "obtenir", "trouver", "consulter", "telecharger",
    "montre", "montrez", "donne", "donnez", "national", "nationale",
    "nationales", "enquete", "enquetes", "etude", "etudes", "operation",
    "operations", "pour", "avec", "dans", "cette", "quel", "quelle",
    "quelles", "liste", "existe", "disponible", "disponibles",
}


def _fold(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", str(text).lower())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", t)


class CatalogueANADS:
    def __init__(self, path: Path | None = None):
        data = json.loads((path or _CAT_PATH).read_text(encoding="utf-8"))
        vus, self.etudes = set(), []
        for e in data["etudes"]:
            if e["id"] not in vus:
                vus.add(e["id"])
                e["_texte"] = _fold(f"{e['titre']} {e['collection'] or ''} "
                                    f"{e['producteur'] or ''}")
                self.etudes.append(e)
        self.total = len(self.etudes)
        # Index d'auto-liaison des TITRES : toute mention d'un titre d'étude
        # dans une réponse (même rédigée par le LLM) devient un lien vers sa
        # fiche. Un titre plus long est apparié en premier (évite qu'un titre
        # court, sous-chaîne d'un autre, capture la mention). Le millésime que
        # le modèle ajoute parfois (« (2015) ») est inclus dans le texte lié.
        _AN = r"(?:\s*\((?:19|20)\d{2}(?:\s*[-/–]\s*\d{2,4})?\))?"
        idx = []
        for e in self.etudes:
            t = (e["titre"] or "").strip()
            if len(t) >= 12:
                idx.append((re.compile(re.escape(t) + _AN, re.I), e["url"], len(t)))
        idx.sort(key=lambda x: -x[2])
        self._title_index = [(rx, url) for rx, url, _ in idx]

    def autolink_titles(self, text: str, max_links: int = 10) -> str:
        """Transforme en liens markdown les mentions de titres d'études ANADS
        présentes dans `text` (vers leur fiche officielle). Ne retouche pas les
        zones déjà liées ; chaque fiche n'est liée qu'une fois ; sélection sans
        chevauchement. Applicable à N'IMPORTE QUELLE réponse (RAG, HYBRID…)."""
        if not text or not self._title_index:
            return text
        deja = [m.span() for m in
                re.finditer(r"\[[^\]]+\]\(https?://[^)]+\)", text)]

        def inside(s, e):
            return any(not (e <= a or s >= b) for a, b in deja)

        cands, vus = [], set()
        for rx, url in self._title_index:
            if url in vus:
                continue
            m = rx.search(text)
            if m and m.group(0).strip() and not inside(*m.span()):
                cands.append((m.start(), m.end(), url))
                vus.add(url)
        # sélection gloutonne sans chevauchement, dans l'ordre du texte
        cands.sort(key=lambda c: (c[0], -(c[1] - c[0])))
        chosen, occ = [], []
        for s, e, u in cands:
            if any(not (e <= a or s >= b) for a, b in occ):
                continue
            chosen.append((s, e, u))
            occ.append((s, e))
            if len(chosen) >= max_links:
                break
        for s, e, u in sorted(chosen, key=lambda c: -c[0]):
            text = f"{text[:s]}[{text[s:e]}]({u}){text[e:]}"
        return text

    def search(self, question: str, k: int = 4) -> list[dict]:
        q = _fold(question)
        terms = {t for t in re.findall(r"[a-z]{4,}", q) if t not in _STOP}
        # expansion thematique (synonymes officiels du domaine)
        for theme, syns in _EXPANSIONS.items():
            if theme in q:
                terms.update(s for syn in syns for s in syn.split() if s not in _STOP)
        year = re.search(r"\b(19|20)\d{2}\b", q)
        scored = []
        for e in self.etudes:
            s = sum(1.0 for t in terms if t in e["_texte"])
            if year and e["annee_debut"] and \
                    e["annee_debut"] <= year.group(0) <= (e["annee_fin"] or e["annee_debut"]):
                s += 2.0
            # priorite aux etudes couvrant le Senegal
            if "senegal" in _fold(e["pays"] or ""):
                s += 0.5
            if s >= 1.5:
                scored.append((s, e))
        scored.sort(key=lambda x: (-x[0], -(int(x[1]["annee_debut"] or 0))))
        return [e for _, e in scored[:k]]
