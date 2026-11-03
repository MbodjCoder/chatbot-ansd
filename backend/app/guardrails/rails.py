"""Contrôles d'entrée et de sortie.

- domaine : la question porte sur les statistiques du Sénégal ;
- sécurité : contenus inappropriés, tentatives de manipulation, opinions politiques ;
- fidélité : chaque nombre de la réponse figure dans les sources.
(La lecture seule des requêtes SQL est contrôlée dans app/sql/pipeline.py.)
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
    # élections et pronostics : hors périmètre
    r"\belection", r"\belectoral", r"presidentiel", r"legislativ",
    r"\bscrutin\b", r"(va|vont|pourrait|devrait)\s+(gagner|remporter|l.emporter)",
    r"qui\s+va\s+(gagner|remporter|etre\s+elu)", r"intention[s]?\s+de\s+vote",
    r"\bparti\s+au\s+pouvoir\b", r"\bmajorite\s+presidentielle\b",
]
# Racines du vocabulaire du domaine (sans accents), comparées au début des mots :
# « region » accepte « régionale », mais « site » n'accepte pas « parasite ».
_DOMAIN_STEMS = [
    # démographie
    "population", "habitant", "peupl", "demograph", "recensement", "rgph",
    "fecondit", "mortalit", "natalit", "naissance", "deces", "mariage",
    "nuptialit", "migration", "migrant", "urbanisation", "urbain", "rural",
    "menage", "esperance", "age", "ans", "sexe", "masculinit", "enfant",
    "jeune", "homme", "projection",
    # territoire
    "superfici", "densit", "surface", "region", "territoire", "zone",
    "casamance", "saloum", "ferlo", "oriental",
    # économie
    "economie", "economiq", "pib", "croissance", "inflation", "prix", "ihpc",
    "entreprise", "industrie", "commerce", "import", "export", "echange",
    "comptes", "conjoncture", "monnaie", "financ", "ninea", "immatricul",
    # emploi
    "emploi", "chomage", "chomeur", "travail", "activit", "salair",
    "remuneration", "main-d", "informel",
    # société et conditions de vie
    "pauvret", "pauvre", "inegalit", "gini", "ehcvm", "condition de vie",
    "sante", "maladie", "vaccination", "nutrition", "education", "scolar",
    "alphabetis", "instruction", "genre", "femme", "violence", "justice",
    "habitat", "logement", "eau", "electricit", "assainissement", "securite alimentaire",
    # statistiques sectorielles
    "agricole", "agriculture", "elevage", "peche", "btp", "environnement",
    "mine", "tic", "numerique", "tourisme", "transport",
    # vocabulaire statistique
    "statistiq", "indicateur", "taux", "indice", "donnee", "chiffre",
    "enquete", "etude", "enes", "eds", "esps", "esam", "recens",
    "tendance", "marche", "participation", "secteur", "filiere", "serie",
    "bdef", "badis", "ninea", "sesn", "annuaire", "phare", "flash",
    # ANSD et services
    "ansd", "senegal", "publication", "rapport", "document", "telecharg",
    "acceder", "trouver", "consulter", "portail", "anads", "microdonnee",
    "metadonnee", "methodolog", "definition", "open", "annuaire", "calendrier",
    "parution", "presse", "communiqu", "abonn", "adresse", "telephone",
    "contact", "memoire", "site", "bulletin", "phare",
    # formation
    "ensae", "formation", "concours", "statisticien", "master", "ecole",
    "etudiant", "stage", "diplome", "cursus", "admission",
    # régions
    "dakar", "thies", "diourbel", "saint-louis", "ziguinchor", "kaolack",
    "fatick", "kolda", "louga", "matam", "tambacounda", "kedougou",
    "kaffrine", "sedhiou",
]
# expressions de plusieurs mots (recherchées telles quelles)
_DOMAIN_PHRASES = ["esperance de vie", "comptes nationaux", "open data",
                   "conditions de vie", "securite alimentaire", "main d oeuvre",
                   "saint louis", "situation economique"]


def _in_domain(folded_q: str) -> bool:
    """Vrai si un mot de la question commence par une racine du domaine."""
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
    """Texte sans accents."""
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


# Nombres non statistiques ignorés côté réponse : ordinaux (« 19ᵉ conférence »),
# numéros de conventions, d'articles ou d'objectifs (ODD).
_ORDINAUX = re.compile(r"\b\d+(?:\s*(?:er|re|\u00e8?[me]e?|\u1d49|\u1d63|e))\b", re.I)
_REFERENCES = re.compile(
    r"\b(?:convention|norme|article|objectif|odd|cist|conf[e\u00e9]rence|r[e\u00e9]solution|"
    r"recommandation|sdg|ilo|bit)\s*(?:n[\u00b0o]\s*)?\d+", re.I)


def _numbers(text: str, *, is_answer: bool = False) -> set[str]:
    """Nombres du texte, séparateurs de milliers retirés (« 4 137 000 » -> « 4137000 »).
    Côté réponse, les nombres non statistiques sont ignorés."""
    if is_answer:
        text = _REFERENCES.sub(" ", text)
        text = _ORDINAUX.sub(" ", text)
    t = re.sub(r"(?<=\d)[\s\u202f.,](?=\d{3}(?!\d))", "", text)
    return {m for m in re.findall(r"\d+", t) if len(m) > 1}


def check_output_faithfulness(answer: str, evidence: str) -> RailVerdict:
    """Chaque nombre de la réponse doit figurer dans la preuve (passages ou résultat SQL)."""
    if not settings.faithfulness_check:
        return RailVerdict(True)
    unsupported = _numbers(answer, is_answer=True) - _numbers(evidence)
    if unsupported:
        return RailVerdict(False, "unfaithful",
                           "Reponse retenue par le controle de fidelite : un chiffre "
                           "n'a pas pu etre verifie dans les sources. "
                           "Veuillez consulter directement les publications ANSD.")
    return RailVerdict(True)
