"""Questions de suivi proposées après chaque réponse.

Le sujet est déduit de la table interrogée, du document cité et des mots de la
question. Une suggestion n'est retenue que si le chatbot sait y répondre.
"""
from __future__ import annotations
import re
import unicodedata

# table ou document -> sujet
TABLE_TOPIC = {
    "emploi": "emploi", "inflation": "prix", "pauvrete": "pauvrete",
    "pib": "economie", "demographie": "demographie",
    "population_nationale": "demographie",
}
DOC_TOPIC = {
    "enes_emploi.md": "emploi", "ihpc_methodologie.md": "prix",
    "ehcvm_pauvrete.md": "pauvrete", "comptes_nationaux.md": "economie",
    "rgph5_synthese.md": "demographie", "navigation_site_ansd.md": "navigation",
    "services_usagers_ansd.md": "services", "ensae_formation.md": "ensae",
    "operations_enquetes_ansd.md": "enquetes", "ansd_missions.md": "services",
}
KEYWORD_TOPIC = [
    (r"chomage|emploi|activite|travail", "emploi"),
    (r"inflation|prix|ihpc", "prix"),
    (r"pauvre|gini|inegalit|conditions de vie", "pauvrete"),
    (r"pib|croissance|econom", "economie"),
    (r"population|habitant|recensement|demograph|fecondite|esperance|urbanis", "demographie"),
    (r"ensae|concours|formation|etudiant|master|statisticien|debouche|metier de statist", "ensae"),
    (r"enquete|collecte|operation", "enquetes"),
    (r"contact|adresse|telephone|calendrier|presse|abonn", "services"),
    (r"trouver|telecharg|microdonnee|anads|open data|publication|site", "navigation"),
]

SUGGESTIONS: dict[str, list[str]] = {
    "demographie": [
        "Comment la population a-t-elle évolué depuis 1976 ?",
        "Quelle est la région la plus peuplée ?",
        "Quel est le taux d'urbanisation ?",
        "Comment le recensement RGPH-5 a-t-il été réalisé ?",
        "Quelle est l'espérance de vie au Sénégal ?",
    ],
    "emploi": [
        "Comment l'ANSD mesure-t-elle le chômage ?",
        "Quel est le taux d'activité le plus récent ?",
        "Quelle est la différence entre chômage strict et chômage élargi ?",
        "Quel est le taux de chômage en 2024 ?",
    ],
    "prix": [
        "Comment l'IHPC est-il calculé ?",
        "Comment l'inflation a-t-elle évolué depuis 2019 ?",
        "Quand paraît le prochain indice des prix ?",
        "Quel est le taux d'inflation en 2024 ?",
    ],
    "pauvrete": [
        "Classe les régions par taux de pauvreté décroissant",
        "Qu'est-ce que l'indice de Gini ?",
        "Où télécharger le rapport EHCVM ?",
        "Quelle région a le plus faible taux de pauvreté ?",
    ],
    "economie": [
        "Comment le PIB est-il calculé ?",
        "Quelle est la croissance du PIB en 2024 ?",
        "Où trouver les comptes nationaux ?",
    ],
    "navigation": [
        "Comment accéder aux microdonnées (ANADS) ?",
        "Quel est le calendrier des publications ?",
        "Comment contacter l'ANSD ?",
        "Où trouver les rapports du RGPH-5 ?",
    ],
    "services": [
        "Comment contacter l'ANSD ?",
        "Quelles sont les enquêtes en cours ?",
        "Quand paraît la prochaine publication ?",
        "Comment accéder aux microdonnées (ANADS) ?",
    ],
    "enquetes": [
        "Quelles sont les enquêtes en cours à l'ANSD ?",
        "Comment accéder aux microdonnées (ANADS) ?",
        "Comment l'ANSD mesure-t-elle la pauvreté ?",
    ],
    "ensae": [
        "Quelles formations propose l'ENSAE ?",
        "Comment se passent les concours de l'ENSAE ?",
        "Quels sont les débouchés du métier de statisticien ?",
    ],
    "accueil": [
        "Quelle est la population du Sénégal en 2023 ?",
        "Quel est le taux de chômage le plus récent ?",
        "Classe les régions par taux de pauvreté décroissant",
        "Où trouver les rapports du RGPH-5 ?",
    ],
}


def _fold(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", text.lower())
                if unicodedata.category(c) != "Mn")
    t = re.sub(r"[-'’?!.,:;]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def detect_topic(question: str, sql: str | None, doc_sources: list[str]) -> str:
    for t in re.findall(r"\b(?:FROM|JOIN)\s+([a-z_]+)", sql or "", re.I):
        if t in TABLE_TOPIC:
            return TABLE_TOPIC[t]
    for d in doc_sources:
        if d in DOC_TOPIC:
            return DOC_TOPIC[d]
    q = _fold(question)
    for pattern, topic in KEYWORD_TOPIC:
        if re.search(pattern, q):
            return topic
    return "accueil"


def _too_close(key: str, seen: set[str]) -> bool:
    """Vrai si `key` est déjà vue ou quasi identique à une entrée de `seen`."""
    return key in seen or any(key[:30] in h or h[:30] in key for h in seen)


# Une suggestion ne doit jamais mener à une réponse vide : pas de demande de
# chiffre sur un thème absent de la base. Les demandes de documents restent valides.
_HORS_PERIMETRE_CHIFFRE = (
    "rendement", "riz", "mais", "arachide", " mil ", "sorgho", "culture",
    "recolte", "hectare", "tonne", "elevage", "cheptel", "betail",
    "tourisme", "touriste", "hotel", "importation", "exportation",
    "balance commerciale", "commerce exterieur", "dette", "budget de l etat",
    "salaire moyen", "smic", "investissement direct", "petrole", "gaz naturel",
    "phosphate", "abonnes", "internet", "criminalite", "accidents",
    "mortalite maternelle", "mortalite infantile", "vaccination", "medecins",
    "hopitaux", "lits d hopital",
)
_DEMANDE_VALEUR = re.compile(
    r"\b(quel|quelle|combien|taux|nombre|montant|valeur|rendement|moyenn|"
    r"proportion|pourcentage)\b")
_DEMANDE_DOC = re.compile(
    r"\b(ou |trouver|telecharg|rapport|publication|document|enquete|"
    r"microdonnee|anads|contact|calendrier|methode|definit|signifie|"
    r"qu est ce|comment|donnees sur|donnee sur|chiffres sur|statistiques sur|"
    r"informations sur|je veux)\b")


# indicateurs disponibles par région ; les autres sont seulement nationaux
_THEME_REGIONAL = ("population", "habitant", "peupl", "pauvre", "pauvrete",
                   "superficie", "dense", "densite", "gini")
_QUESTION_REGIONALE = re.compile(r"\bregion|par region|dans (la|le|l ) region")


def is_answerable(s: str) -> bool:
    """Vrai si la suggestion mène à une vraie réponse (chiffre de la base, sujet
    documentaire connu ou catalogue)."""
    q = _fold(s)
    documentaire = bool(_DEMANDE_DOC.search(q))
    # chiffre demandé sur un thème absent de la base
    if (_DEMANDE_VALEUR.search(q) and not documentaire
            and any(k in q for k in _HORS_PERIMETRE_CHIFFRE)):
        return False
    # question régionale sur un indicateur seulement national
    if _QUESTION_REGIONALE.search(q) and not any(w in q for w in _THEME_REGIONAL):
        return False
    # accepté : gabarit SQL connu, question documentaire ou sujet reconnu
    from app.sql.templates import template_sql
    if template_sql(s) is not None:
        return True
    if documentaire:
        return True
    return detect_topic(s, None, []) != "accueil"


def suggest(question: str, sql: str | None, doc_sources: list[str],
            history_questions: list[str], k: int = 3,
            avoid: set[str] | None = None) -> list[str]:
    """Questions de suivi du même sujet, ni déjà posées ni déjà proposées (`avoid`)."""
    topic = detect_topic(question, sql, doc_sources)
    seen = {_fold(h)[:60] for h in history_questions} | {_fold(question)[:60]}
    seen |= (avoid or set())
    out = []
    for s in SUGGESTIONS.get(topic, []):
        key = _fold(s)[:60]
        if _too_close(key, seen):
            continue
        out.append(s)
        seen.add(key)
        if len(out) >= k:
            break
    return out


# Suggestions rédigées par le modèle de langage, à partir de la réponse donnée
SUGGEST_SYSTEM = (
    "Tu es le moteur de suggestions d'un assistant statistique officiel de "
    "l'ANSD (Agence Nationale de la Statistique et de la Démographie du "
    "Sénégal). À partir de la QUESTION de l'utilisateur et de la RÉPONSE "
    "qui vient de lui être donnée, propose les questions de suivi les plus "
    "PERTINENTES qu'il poserait logiquement ensuite.\n"
    "Règles strictes :\n"
    "- exactement {k} questions, une par ligne, sans numéro ni tiret ;\n"
    "- chaque question prolonge CONCRÈTEMENT la réponse : un chiffre voisin, "
    "une comparaison, une évolution dans le temps, une région, la méthode de "
    "calcul, ou le document/la source à consulter ;\n"
    "- courtes (5 à 14 mots), naturelles, en français, se terminant par « ? » ;\n"
    "- jamais une reformulation de la question déjà posée ;\n"
    "- reste dans le périmètre des statistiques officielles du Sénégal ;\n"
    "- n'invente aucun chiffre ; ce sont des QUESTIONS, pas des réponses.\n"
    "N'écris que les questions."
)


def suggest_llm(complete, question: str, answer: str,
                avoid: set[str], k: int = 3) -> list[str]:
    """k questions de suivi tirées de la réponse ; liste vide en cas d'échec."""
    resp = complete(
        SUGGEST_SYSTEM.replace("{k}", str(k)),
        f"QUESTION : {question}\nRÉPONSE : {answer[:1200]}",
        temperature=0.4, max_tokens=160)
    out, seen = [], set(avoid)
    for ligne in (resp.text or "").splitlines():
        s = ligne.strip().lstrip("-•*0123456789.) ").strip().strip('"').strip()
        if not s or "?" not in s:
            continue
        if not s.endswith("?"):
            s = s[:s.rfind("?") + 1]
        mots = s.split()
        if not (4 <= len(mots) <= 18) or len(s) > 130:
            continue
        # commentaires du modèle écartés
        if re.match(r"(voici|bien sur|je peux|par exemple|question)", s.lower()):
            continue
        # seulement des questions auxquelles le chatbot sait répondre
        if not is_answerable(s):
            continue
        key = _fold(s)[:60]
        if _too_close(key, seen):
            continue
        out.append(s)
        seen.add(key)
        if len(out) >= k:
            break
    return out
