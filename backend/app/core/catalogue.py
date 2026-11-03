"""Recherche dans le catalogue ANADS (285 fiches, récoltées par scripts/harvest_anads.py).

Chaque réponse cite des fiches exactes (titre, période, producteur, lien).
L'accès aux microdonnées se demande sur la fiche elle-même.
"""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path

from app.core.config import settings

_CAT_PATH = Path(settings.database_path).parent / "anads_catalogue.json"

# thème -> termes de recherche associés
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

# mots présents partout ou propres à la formulation : ignorés au classement
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
        # titres des fiches, du plus long au plus court, pour les rendre cliquables
        _AN = r"(?:\s*\((?:19|20)\d{2}(?:\s*[-/–]\s*\d{2,4})?\))?"
        idx = []
        for e in self.etudes:
            t = (e["titre"] or "").strip()
            if len(t) >= 12:
                idx.append((re.compile(re.escape(t) + _AN, re.I), e["url"], len(t)))
        idx.sort(key=lambda x: -x[2])
        self._title_index = [(rx, url) for rx, url, _ in idx]

    def autolink_titles(self, text: str, max_links: int = 10) -> str:
        """Rend cliquables les titres d'études cités (une fois chacun, sans
        toucher aux liens existants)."""
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
        # termes associés au thème
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
            # priorité aux études nationales
            if "senegal" in _fold(e["pays"] or ""):
                s += 0.5
            if s >= 1.5:
                scored.append((s, e))
        scored.sort(key=lambda x: (-x[0], -(int(x[1]["annee_debut"] or 0))))
        return [e for _, e in scored[:k]]
