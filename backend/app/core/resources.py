"""Liens vers les publications de l'ANSD, tirés du registre vérifié data/resources.json.

Ordre de priorité :
  1. table SQL interrogée -> publication source ;
  2. document cité -> publication d'origine ;
  3. thèmes de la question, avec un seuil minimal.
Les portails généraux ne sont proposés que sur une demande de navigation.
"""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path

from app.core.config import settings

_RES_PATH = Path(settings.database_path).parent / "resources.json"

# Mentions rendues cliquables dans les réponses, du motif le plus précis au
# plus général ; chaque ressource n'est liée qu'une fois.
AUTOLINK_PATTERNS = [
    (r"annuaire statistique(?:\s+du\s+s[ée]n[ée]gal)?", "ansd_bases"),
    (r"plateforme\s+open\s+data(?:\s+du\s+s[ée]n[ée]gal)?|\bopen\s+data\b|\bODP\b", "ansd_bases"),
    (r"\bANADS\b|archivage\s+national\s+des\s+donn[ée]es", "anads"),
    (r"microdonn[ée]es", "anads"),
    (r"contact(?:er|ez)?\s+(?:directement\s+)?l['’ ]?ANSD|nous\s+contacter", "ansd_contact"),
    (r"calendrier\s+de[s]?\s+publications?", "ansd_calendrier"),
    (r"derni[èe]res\s+parutions|flash[\s-]?stats?", "flash_stats"),
    (r"banque\s+de\s+donn[ée]es\s+[ée]conomiques(?:\s+et\s+financi[èe]res)?|\bBDEF\b", "bdef"),
    (r"\bEHCVM\b", "ehcvm_rapport_pdf"),
    (r"enqu[êe]te\s+emploi|\bENES\b", "enes_page"),
    (r"indice\s+harmonis[ée]\s+des\s+prix[^.,;]*|\bIHPC\b", "ihpc_page"),
    (r"RGPH[\s-]?5|recensement\s+g[ée]n[ée]ral(?:\s+de\s+la\s+population)?", "rgph5_rapports"),
    (r"\bENSAE\b|[ée]cole\s+.{0,20}statistique", "ensae"),
    (r"comptes\s+nationaux", "economie_2024"),
    # « SES » seul est ambigu : forme « (SES) » ou nom complet uniquement
    (r"situation\s+[ée]conomique\s+et\s+sociale(?:\s+du\s+s[ée]n[ée]gal)?|\(SES\)", "ses_nationales"),
    (r"\bDAPSA\b|statistiques?\s+agricoles?", "dapsa"),
    (r"\bIPAR\b", "ipar"),
    (r"publications?\s+de\s+l['’ ]?ANSD", "ansd_publications"),
    (r"site\s+(?:web\s+)?(?:officiel\s+)?de\s+l['’ ]?ANSD|www\.ansd\.sn", "ansd_accueil"),
]

# document du corpus -> publication source
DOC_TO_RESOURCE = {
    "rgph5_synthese.md": ["rgph5_rapports"],
    "ehcvm_pauvrete.md": ["ehcvm_rapport_pdf"],
    "enes_emploi.md": ["enes_page"],
    "ihpc_methodologie.md": ["ihpc_page"],
    "ansd_missions.md": ["ansd_accueil"],
    "comptes_nationaux.md": ["economie_2024"],
    "navigation_site_ansd.md": ["flash_stats", "anads"],
    "services_usagers_ansd.md": ["ansd_contact"],
    "operations_enquetes_ansd.md": ["ansd_enquetes"],
    "ensae_formation.md": ["ensae"],
    "faq_pratique_ansd.md": ["ansd_contact"],
    "annuaire_population_2025.md": ["annuaire_population_2025"],
    "glossaire_indicateurs.md": [],
}

# table SQL -> publication d'origine des chiffres
TABLE_TO_RESOURCE = {
    "emploi": ["enes_page"],
    "inflation": ["ihpc_page"],
    "pauvrete": ["ehcvm_rapport_pdf"],
    "pib": ["economie_2024"],
    "demographie": ["rgph5_rapports"],
    "population_nationale": ["rgph5_rapports"],
    "population_2025": ["annuaire_population_2025"],
    "structure_age_2025": ["annuaire_population_2025"],
    "indicateurs_nationaux": [],   # source déterminée par le code de l'indicateur
}

# indicateurs issus de l'EHCVM ; tous les autres viennent du RGPH-5
_INDIC_EHCVM = {"pauvrete_nationale", "pauvrete_2018", "pauvrete_extreme",
                "pauvrete_rurale", "pauvrete_urbaine", "gini_national",
                "insecurite_alim"}

# portails généraux : seulement sur une demande de navigation
_GENERIC = {"ansd_accueil", "flash_stats", "anads", "recensement_sn", "bdef",
            "ansd_publications", "ansd_indicateurs", "ansd_actualites",
            "ansd_bases"}
_NAV_CUES = re.compile(
    r"ou (trouver|acceder|telecharger|consulter)|comment (trouver|acceder|"
    r"telecharger|obtenir)|site de l ansd|sur le site|microdonnee|catalogue|"
    r"publication|parution|rapport|telecharger|open data|base de donnees|"
    r"annuaire", re.I)


def _fold(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", text.lower())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[-'’]", " ", t)


class ResourceLinker:
    def __init__(self, path: Path | None = None):
        data = json.loads((path or _RES_PATH).read_text(encoding="utf-8"))
        self.resources = {r["id"]: r for r in data["resources"]}

    @staticmethod
    def _tables_of(sql: str) -> list[str]:
        return re.findall(r"\b(?:FROM|JOIN)\s+([a-z_]+)", sql or "", re.I)

    def autolink(self, text: str, max_links: int = 6) -> str:
        """Rend cliquables les mentions de publications (première occurrence,
        sans toucher aux liens existants ni aux chiffres)."""
        if not text:
            return text
        # liens déjà présents : laissés tels quels
        deja = [m.span() for m in re.finditer(r"\[[^\]]+\]\(https?://[^)]+\)", text)]

        def dans_lien(s, e):
            return any(not (e <= a or s >= b) for a, b in deja)

        # première occurrence de chaque motif
        cands = []   # (start, end, url)
        for pattern, rid in AUTOLINK_PATTERNS:
            if rid not in self.resources:
                continue
            for m in re.finditer(pattern, text, re.I):
                if m.group(0).strip() and not dans_lien(*m.span()):
                    cands.append((m.start(), m.end(), self.resources[rid]["url"]))
                    break
        # sélection sans chevauchement, avec un plafond
        cands.sort()
        choisis, fin = [], -1
        for s, e, url in cands:
            if s >= fin and len(choisis) < max_links:
                choisis.append((s, e, url))
                fin = e
        # insertion de droite à gauche (positions préservées)
        for s, e, url in sorted(choisis, reverse=True):
            text = f"{text[:s]}[{text[s:e]}]({url}){text[e:]}"
        return text

    def links_for(self, question: str, doc_sources: list[str],
                  sql: str | None = None, k: int = 3,
                  relax: bool = False) -> list[dict]:
        """relax=True pour une demande de lien : un seul thème commun suffit."""
        q = _fold(question)
        nav = bool(_NAV_CUES.search(q)) or relax
        scores: dict[str, float] = {}
        # 1. table SQL interrogée
        tables = [t.lower() for t in self._tables_of(sql)]
        for table in tables:
            for rid in TABLE_TO_RESOURCE.get(table, []):
                scores[rid] = scores.get(rid, 0) + 4.0
        # indicateur national : source selon son code
        if "indicateurs_nationaux" in tables:
            codes = re.findall(r"'([a-z0-9_]+)'", sql or "")
            rid = ("ehcvm_rapport_pdf" if any(c in _INDIC_EHCVM for c in codes)
                   else "rgph5_rapports")
            scores[rid] = scores.get(rid, 0) + 4.0
        # 2. document cité (le premier compte pleinement, les autres faiblement)
        for rank, doc in enumerate(dict.fromkeys(doc_sources)):
            w = 3.0 if rank == 0 else 1.0
            for rid in DOC_TO_RESOURCE.get(doc, []):
                scores[rid] = scores.get(rid, 0) + w
        # 3. thèmes communs (une expression de plusieurs mots compte double)
        for rid, res in self.resources.items():
            hit = sum(2.0 if " " in t else 1.0
                      for t in res["themes"] if _fold(t) in q)
            if hit:
                scores[rid] = scores.get(rid, 0) + hit
        # seuil de pertinence ; portails généraux sur demande de navigation seulement
        def ok(rid: str, s: float) -> bool:
            if rid in _GENERIC:
                return nav and s >= 1.0
            return s >= (1.0 if relax else 2.0)
        # document précis avant portail général
        best = sorted(((rid, s) for rid, s in scores.items() if ok(rid, s)),
                      key=lambda x: (x[0] in _GENERIC, -x[1]))[:k]
        return [self._as_link(rid) for rid, _ in best]

    def _as_link(self, rid: str) -> dict:
        r = self.resources[rid]
        return {"titre": r["titre"], "url": r["url"], "type": r["type"]}

    def fallback(self, prefer: str = "ansd_indicateurs") -> dict:
        """Lien de secours vers une page vérifiée de l'ANSD."""
        for rid in (prefer, "ansd_indicateurs", "ansd_publications", "ansd_accueil"):
            if rid in self.resources:
                return self._as_link(rid)
        return self._as_link(next(iter(self.resources)))
