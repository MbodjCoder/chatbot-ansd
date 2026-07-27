"""
Guardrails specifiques a la statistique publique.

Justification (memoire, sect. 4.4) : les Principes fondamentaux de la
statistique officielle (Nations Unies, 2014) imposent qu'un assistant
statistique ne puisse ni inventer des donnees (Principe 2), ni les
interpreter politiquement (Principe 1), ni sortir de son perimetre
(Principe 4 - prevention des usages errones).

Quatre rails, inspires de la taxonomie NeMo Guardrails (Rebedea et al., 2023),
implementes ici nativement (zero dependance) et interchangeables avec NeMo
en production via la meme interface `check_input` / `check_output` :

  1. Rail d'entree - Topical    : rester dans le domaine statistique
  2. Rail d'entree - Safety     : bloquer contenus inappropries / injections
  3. Rail de sortie - Factual   : verification de fidelite (Self-RAG simplifie,
                                  Asai et al., 2023) : chaque chiffre de la
                                  reponse doit apparaitre dans les sources
  4. Rail structurel            : SQL en lecture seule (voir app/sql/pipeline.py)
"""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass

from app.core.config import settings

REFUS_HORS_DOMAINE = ("Je suis l'assistant statistique de l'ANSD : je reponds "
                      "uniquement aux questions portant sur les statistiques "
                      "officielles du Senegal (demographie, economie, social). "
                      "Reformulez votre question dans ce perimetre.")

REFUS_POLITIQUE = ("Conformement au principe d'impartialite de la statistique "
                   "officielle, je ne formule aucune interpretation politique. "
                   "Je peux en revanche vous fournir les chiffres officiels.")

_INJECTION_PATTERNS = [
    r"ignore\s+(tes|les|vos)\s+(instructions|consignes|regles)",
    r"oublie\s+(tes|les)\s+(instructions|consignes)",
    r"system\s*prompt", r"jailbreak", r"mode\s+developpeur",
    r"fais\s+semblant\s+d.etre", r"tu\s+n.es\s+plus",
]
_POLITICAL_PATTERNS = [
    r"\bpour\s+qui\s+voter\b", r"meilleur\s+(president|parti|candidat)",
    r"\b(critique|juge)\s+le\s+gouvernement\b", r"opinion\s+politique",
    # électoral / prédictif : hors périmètre statistique (l'ANSD ne pronostique
    # pas d'élection ni ne prend parti)
    r"\belection", r"\belectoral", r"presidentiel", r"legislativ",
    r"\bscrutin\b", r"(va|vont|pourrait|devrait)\s+(gagner|remporter|l.emporter)",
    r"qui\s+va\s+(gagner|remporter|etre\s+elu)", r"intention[s]?\s+de\s+vote",
    r"\bparti\s+au\s+pouvoir\b", r"\bmajorite\s+presidentielle\b",
]
# Lexique du domaine sous forme de RACINES (stems, sans accents). Le matching
# se fait par mot entier / prefixe de mot (P1-4) : "region" accepte "regions",
# "regional" ; mais "site" n'est plus declenche par "parasite" (ce dernier ne
# COMMENCE pas par "site"). Couvre l'ensemble des thematiques reellement
# produites par l'ANSD (menu du site : Economie, Demographie, Societe, Autres
# statistiques) pour eliminer les refus injustifies de questions legitimes.
_DOMAIN_STEMS = [
    # --- Demographie ---
    "population", "habitant", "peupl", "demograph", "recensement", "rgph",
    "fecondit", "mortalit", "natalit", "naissance", "deces", "mariage",
    "nuptialit", "migration", "migrant", "urbanisation", "urbain", "rural",
    "menage", "esperance", "age", "sexe", "masculinit",
    # --- Géographie / territoire (régions + zones naturelles) ---
    "superfici", "densit", "surface", "region", "territoire", "zone",
    "casamance", "saloum", "ferlo", "oriental",
    # --- Economie ---
    "economie", "economiq", "pib", "croissance", "inflation", "prix", "ihpc",
    "entreprise", "industrie", "commerce", "import", "export", "echange",
    "comptes", "conjoncture", "monnaie", "financ", "ninea", "immatricul",
    # --- Emploi / travail ---
    "emploi", "chomage", "chomeur", "travail", "activit", "salair",
    "remuneration", "main-d", "informel",
    # --- Societe / conditions de vie ---
    "pauvret", "pauvre", "inegalit", "gini", "ehcvm", "condition de vie",
    "sante", "maladie", "vaccination", "nutrition", "education", "scolar",
    "alphabetis", "instruction", "genre", "femme", "violence", "justice",
    "habitat", "logement", "eau", "electricit", "assainissement", "securite alimentaire",
    # --- Autres statistiques sectorielles ---
    "agricole", "agriculture", "elevage", "peche", "btp", "environnement",
    "mine", "tic", "numerique", "tourisme", "transport",
    # --- Indicateurs / méta-statistique ---
    "statistiq", "indicateur", "taux", "indice", "donnee", "chiffre",
    "enquete", "etude", "enes", "eds", "esps", "esam", "recens",
    "tendance", "marche", "participation", "secteur", "filiere", "serie",
    "bdef", "badis", "ninea", "sesn", "annuaire", "phare", "flash",
    # --- ANSD / navigation / services ---
    "ansd", "senegal", "publication", "rapport", "document", "telecharg",
    "acceder", "trouver", "consulter", "portail", "anads", "microdonnee",
    "metadonnee", "methodolog", "definition", "open", "annuaire", "calendrier",
    "parution", "presse", "communiqu", "abonn", "adresse", "telephone",
    "contact", "memoire", "site", "bulletin", "phare",
    # --- ENSAE / formation ---
    "ensae", "formation", "concours", "statisticien", "master", "ecole",
    "etudiant", "stage", "diplome", "cursus", "admission",
    # --- 14 régions ---
    "dakar", "thies", "diourbel", "saint-louis", "ziguinchor", "kaolack",
    "fatick", "kolda", "louga", "matam", "tambacounda", "kedougou",
    "kaffrine", "sedhiou",
]
# indices multi-mots (verifies par sous-chaine, ils sont non ambigus)
_DOMAIN_PHRASES = ["esperance de vie", "comptes nationaux", "open data",
                   "conditions de vie", "securite alimentaire", "main d oeuvre",
                   "saint louis", "situation economique"]


def _in_domain(folded_q: str) -> bool:
    """Vrai si la question releve du domaine ANSD. Matching par mot/prefixe :
    un mot de la question doit COMMENCER par une racine du lexique (evite les
    faux positifs par sous-chaine, ex. 'parasite' vs 'site')."""
    if any(p in folded_q for p in _DOMAIN_PHRASES):
        return True
    mots = re.findall(r"[a-z0-9-]+", folded_q)
    return any(m.startswith(stem) for m in mots for stem in _DOMAIN_STEMS)


@dataclass
class RailVerdict:
    allowed: bool
    reason: str = ""
    message: str = ""


def _fold(text: str) -> str:
    """Normalisation Unicode (suppression des accents) : le rail topical doit
    reconnaitre "pauvreté" comme "pauvrete" (robustesse a la casse/graphie)."""
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def check_input(question: str) -> RailVerdict:
    q = _fold(question.lower().strip())
    if not q:
        return RailVerdict(False, "empty", "Veuillez poser une question.")
    if len(q) > settings.max_query_length:
        return RailVerdict(False, "too_long",
                           "Question trop longue : merci de la reformuler plus brievement.")
    for p in _INJECTION_PATTERNS:
        if re.search(p, q):
            return RailVerdict(False, "injection", REFUS_HORS_DOMAINE)
    for p in _POLITICAL_PATTERNS:
        if re.search(p, q):
            return RailVerdict(False, "political", REFUS_POLITIQUE)
    if not _in_domain(q):
        return RailVerdict(False, "off_topic", REFUS_HORS_DOMAINE)
    return RailVerdict(True)


# Nombres NON statistiques a ignorer par le rail de fidelite : ce ne sont pas
# des donnees chiffrees mais des references contextuelles (ordinaux \u00ab 19e / 5\u1d49 \u00bb,
# numeros de conventions/normes/articles, objectifs ODD, conferences CIST...).
# Les flaguer produisait des blocages intermittents sur les reponses de
# METHODOLOGIE (ex. \u00ab 19\u1d49 Conference du BIT \u00bb), d'ou un comportement non
# deterministe. On les retire AVANT extraction, cote reponse uniquement.
_ORDINAUX = re.compile(r"\b\d+(?:\s*(?:er|re|\u00e8?[me]e?|\u1d49|\u1d63|e))\b", re.I)
_REFERENCES = re.compile(
    r"\b(?:convention|norme|article|objectif|odd|cist|conf[e\u00e9]rence|r[e\u00e9]solution|"
    r"recommandation|sdg|ilo|bit)\s*(?:n[\u00b0o]\s*)?\d+", re.I)


def _numbers(text: str, *, is_answer: bool = False) -> set[str]:
    """Extraction des nombres avec normalisation des separateurs de milliers
    a la francaise (espace, point) : "4 137 000" -> "4137000".

    is_answer=True (cote reponse generee) : on retire d'abord les nombres NON
    statistiques (ordinaux, numeros de reference) pour ne garder que les
    valeurs chiffrees reelles \u2014 le rail garde ainsi tout son mordant sur les
    donnees (P1) sans bloquer par intermittence une reference contextuelle."""
    if is_answer:
        text = _REFERENCES.sub(" ", text)
        text = _ORDINAUX.sub(" ", text)
    t = re.sub(r"(?<=\d)[\s\u202f.,](?=\d{3}(?!\d))", "", text)
    return {m for m in re.findall(r"\d+", t) if len(m) > 1}


def check_output_faithfulness(answer: str, evidence: str) -> RailVerdict:
    """Rail factuel : tout nombre present dans la reponse doit exister dans
    les elements de preuve (contexte RAG ou resultat SQL). Approche
    verifiable et deterministe ; en production, elle est doublee d'un juge
    LLM type Self-RAG (Asai et al., 2023)."""
    if not settings.faithfulness_check:
        return RailVerdict(True)
    unsupported = _numbers(answer, is_answer=True) - _numbers(evidence)
    if unsupported:
        return RailVerdict(False, "unfaithful",
                           "Reponse retenue par le controle de fidelite : un chiffre "
                           "n'a pas pu etre verifie dans les sources. "
                           "Veuillez consulter directement les publications ANSD.")
    return RailVerdict(True)
