"""
Rattachement des ressources officielles ANSD (liens verifies) aux reponses.

Objectif du memoire : faciliter l'ACCES A L'INFORMATION ET LA NAVIGATION sur
le site de l'ANSD. Chaque reponse est accompagnee des pages et documents
officiels pertinents, issus d'une base de liens dont chaque URL a ete
verifiee (HTTP 200, date de verification dans data/resources.json).

Appariement par PRECISION decroissante (un lien non pertinent nuit plus que
l'absence de lien — meme arbitrage que la decision #34) :
  1. table SQL utilisee -> publication source de cette table (deterministe) ;
  2. document RAG cite -> publication dont il est extrait (deterministe) ;
  3. themes de la question (lexical), avec seuil minimal ;
les portails generiques (accueil, dernieres parutions, ANADS) ne sortent
QUE sur une question de navigation explicite ("ou trouver", "telecharger"...).
"""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path

from app.core.config import settings

_RES_PATH = Path(settings.database_path).parent / "resources.json"

# Auto-linking (decision #78) : quand la reponse MENTIONNE une ressource
# officielle par son nom, ce nom devient un lien cliquable vers la page/document
# correspondant. Liste ordonnee du motif le PLUS specifique au moins specifique
# (le premier qui matche gagne) ; chaque ressource n'est liee qu'UNE fois
# (premiere occurrence) pour ne pas sur-charger le texte. Motifs tolerants aux
# accents. Les URLs proviennent de la base verifiee resources.json.
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
    # « SES » seul est ambigu (mot français) : on n'accroche que la forme
    # entre parenthèses « (SES) » ou la dénomination complète.
    (r"situation\s+[ée]conomique\s+et\s+sociale(?:\s+du\s+s[ée]n[ée]gal)?|\(SES\)", "ses_nationales"),
    (r"\bDAPSA\b|statistiques?\s+agricoles?", "dapsa"),
    (r"\bIPAR\b", "ipar"),
    (r"publications?\s+de\s+l['’ ]?ANSD", "ansd_publications"),
    (r"site\s+(?:web\s+)?(?:officiel\s+)?de\s+l['’ ]?ANSD|www\.ansd\.sn", "ansd_accueil"),
]

# document du corpus RAG -> ressources sources correspondantes
DOC_TO_RESOURCE = {
    "rgph5_synthese.md": ["rgph5_rapports"],
    "ehcvm_pauvrete.md": ["ehcvm_rapport_pdf"],
    "enes_emploi.md": ["enes_page"],
    "ihpc_methodologie.md": ["ihpc_page"],
    "ansd_missions.md": ["ansd_accueil"],
    "comptes_nationaux.md": ["economie_2024"],
    "navigation_site_ansd.md": ["flash_stats", "anads"],
    # une seule ressource canonique : les autres (calendrier, bases) sortent
    # par les themes de la question, pas systematiquement
    "services_usagers_ansd.md": ["ansd_contact"],
    "operations_enquetes_ansd.md": ["ansd_enquetes"],
    "ensae_formation.md": ["ensae"],
    "faq_pratique_ansd.md": ["ansd_contact"],
    # le glossaire est transversal : pas de publication source unique,
    # l'appariement thematique fait le travail
    "glossaire_indicateurs.md": [],
}

# table SQL interrogee -> publication d'origine des chiffres
TABLE_TO_RESOURCE = {
    "emploi": ["enes_page"],
    "inflation": ["ihpc_page"],
    "pauvrete": ["ehcvm_rapport_pdf"],
    "pib": ["economie_2024"],
    "demographie": ["rgph5_rapports"],
    "population_nationale": ["rgph5_rapports"],
    # "regions" volontairement absent : cette table n'apparait que par
    # jointure instrumentale, elle ne designe pas la publication d'origine
    "indicateurs_nationaux": [],   # resolu par le CODE de l'indicateur (ci-dessous)
}

# indicateurs_nationaux : la source depend du CODE interroge. Les indicateurs de
# pauvrete/inegalite/securite alimentaire viennent de l'EHCVM ; tous les autres
# (demographie, education, equipement des menages, esperance de vie...) du RGPH-5.
# Garantit un lien source pour CHAQUE indicateur (promesse P2 : toujours la source).
_INDIC_EHCVM = {"pauvrete_nationale", "pauvrete_2018", "pauvrete_extreme",
                "pauvrete_rurale", "pauvrete_urbaine", "gini_national",
                "insecurite_alim"}

# portails generiques : seulement si la question est une navigation explicite
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
        """Transforme en liens markdown les mentions de ressources officielles
        dans une reponse (decision #78). Chaque ressource est liee au plus une
        fois (premiere occurrence), sans chevauchement, hors zones deja liees.
        Le texte affiche (le nom mentionne) est conserve ; seule l'URL est
        ajoutee. Ne touche jamais aux chiffres."""
        if not text:
            return text
        # zones DEJA liees (le LLM produit parfois ses propres liens markdown) :
        # on ne les retouche pas, mais on continue a lier le reste du texte.
        deja = [m.span() for m in re.finditer(r"\[[^\]]+\]\(https?://[^)]+\)", text)]

        def dans_lien(s, e):
            return any(not (e <= a or s >= b) for a, b in deja)

        # 1) collecter la 1re occurrence de chaque MOTIF (chaque entite nommee
        #    est cliquable, meme si deux entites pointent vers la meme page :
        #    "Annuaire statistique" ET "Open Data" -> page Bases de donnees)
        cands = []   # (start, end, url)
        for pattern, rid in AUTOLINK_PATTERNS:
            if rid not in self.resources:
                continue
            for m in re.finditer(pattern, text, re.I):
                if m.group(0).strip() and not dans_lien(*m.span()):
                    cands.append((m.start(), m.end(), self.resources[rid]["url"]))
                    break   # premiere occurrence libre de ce motif
        # 2) selection gloutonne sans chevauchement, dans l'ordre du texte.
        #    Chaque entite nommee reste cliquable meme si deux pointent vers la
        #    meme page (Annuaire + Open Data -> Bases de donnees). Plafond pour
        #    ne pas sur-charger.
        cands.sort()
        choisis, fin = [], -1
        for s, e, url in cands:
            if s >= fin and len(choisis) < max_links:
                choisis.append((s, e, url))
                fin = e
        # 3) insertion de droite a gauche (preserve les offsets)
        for s, e, url in sorted(choisis, reverse=True):
            text = f"{text[:s]}[{text[s:e]}]({url}){text[e:]}"
        return text

    def links_for(self, question: str, doc_sources: list[str],
                  sql: str | None = None, k: int = 3,
                  relax: bool = False) -> list[dict]:
        """relax=True (voie navigation) : la question EST une demande de
        lien, le seuil anti-bruit est abaisse a 1 theme concordant."""
        q = _fold(question)
        nav = bool(_NAV_CUES.search(q)) or relax
        scores: dict[str, float] = {}
        # 1. deterministe : table SQL interrogee -> publication source
        tables = [t.lower() for t in self._tables_of(sql)]
        for table in tables:
            for rid in TABLE_TO_RESOURCE.get(table, []):
                scores[rid] = scores.get(rid, 0) + 4.0
        # 1bis. indicateurs_nationaux : source selon le CODE interroge
        if "indicateurs_nationaux" in tables:
            codes = re.findall(r"'([a-z0-9_]+)'", sql or "")
            rid = ("ehcvm_rapport_pdf" if any(c in _INDIC_EHCVM for c in codes)
                   else "rgph5_rapports")
            scores[rid] = scores.get(rid, 0) + 4.0
        # 2. deterministe : document RAG cite -> publication source.
        # Seul le document le MIEUX classe pese pleinement : les documents
        # secondaires du top-k n'apportent qu'un signal faible (sous le
        # seuil s'ils ne sont pas confirmes par les themes de la question)
        for rank, doc in enumerate(dict.fromkeys(doc_sources)):
            w = 3.0 if rank == 0 else 1.0
            for rid in DOC_TO_RESOURCE.get(doc, []):
                scores[rid] = scores.get(rid, 0) + w
        # 3. thematique : themes de la ressource presents dans la question
        #    (les themes multi-mots, plus specifiques, pesent double)
        for rid, res in self.resources.items():
            hit = sum(2.0 if " " in t else 1.0
                      for t in res["themes"] if _fold(t) in q)
            if hit:
                scores[rid] = scores.get(rid, 0) + hit
        # filtre de pertinence : les generiques exigent une question de
        # navigation ; les autres exigent un score minimal (seuil anti-bruit)
        def ok(rid: str, s: float) -> bool:
            if rid in _GENERIC:
                return nav and s >= 1.0
            return s >= (1.0 if relax else 2.0)
        # ressource SPECIFIQUE avant portail generique : le document exact
        # que cherche l'usager prime toujours sur la page d'ensemble
        best = sorted(((rid, s) for rid, s in scores.items() if ok(rid, s)),
                      key=lambda x: (x[0] in _GENERIC, -x[1]))[:k]
        return [self._as_link(rid) for rid, _ in best]

    def _as_link(self, rid: str) -> dict:
        r = self.resources[rid]
        return {"titre": r["titre"], "url": r["url"], "type": r["type"]}

    def fallback(self, prefer: str = "ansd_indicateurs") -> dict:
        """Lien source GARANTI (promesse P2 : toute reponse porte au moins une
        source officielle). Utilise quand aucun lien specifique n'a ete derive :
        une page verifiee de l'ANSD, jamais rien d'invente."""
        for rid in (prefer, "ansd_indicateurs", "ansd_publications", "ansd_accueil"):
            if rid in self.resources:
                return self._as_link(rid)
        return self._as_link(next(iter(self.resources)))
