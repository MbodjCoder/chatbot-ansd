"""
Couche conversationnelle sociale (small talk).

Probleme corrige : sans cette couche, un message social ("salut", "merci")
etait traite comme une question de suivi elliptique, contextualise avec le
tour precedent, et re-declenchait la reponse precedente — defaut d'usage
majeur pour un chatbot grand public.

Approche : detection deterministe par lexique normalise (sans accents),
AVANT la contextualisation et les guardrails. Les actes de dialogue sociaux
(salutation, remerciement, cloture, presentation de soi, demande d'aide)
sont une categorie standard des systemes de dialogue (dialog acts,
Stolcke et al., 2000) et se traitent sans acces aux donnees.

Deux cas :
  - message PUREMENT social  -> reponse sociale directe (variantes pour
    eviter l'effet robotique), sans routage ni historique ;
  - salutation SUIVIE d'une question ("Bonjour, quelle est la population ?")
    -> la salutation est retiree et la question est traitee normalement.
"""
from __future__ import annotations
import re
import unicodedata


def _fold(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", text.lower())
                if unicodedata.category(c) != "Mn")
    t = re.sub(r"[!?.,;:…\-'’]+", " ", t)   # ponctuation, traits d'union, apostrophes
    return re.sub(r"\s+", " ", t).strip()


# lexique des actes sociaux (formes normalisees, sans accents)
_GREET = {"salut", "bonjour", "bonsoir", "hello", "hi", "coucou", "slt",
          "cc", "yo", "bjr", "salam", "salamalekoum", "assalamou alaikoum",
          "nanga def", "hey"}
_HOWRU = {"ca va", "ca va bien", "comment ca va", "comment vas tu",
          "comment allez vous", "tu vas bien", "vous allez bien", "la forme"}
_THANKS = {"merci", "merci beaucoup", "merci bien", "thanks", "thank you",
           "jerejef", "c est gentil", "super merci", "parfait merci",
           "ok merci", "d accord merci", "tres bien merci"}
_BYE = {"au revoir", "bye", "a bientot", "a plus", "bonne journee",
        "bonne soiree", "bonne nuit", "a demain", "ciao", "adieu"}
_ACK = {"ok", "d accord", "dac", "bien", "tres bien", "parfait", "super",
        "genial", "top", "compris", "noted", "excellent", "daccord"}
_WHO = {"qui es tu", "qui etes vous", "tu es qui", "t es qui", "c est quoi rama",
        "qu est ce que rama", "presente toi", "tu t appelles comment",
        "quel est ton nom", "c est qui rama", "c est quoi sage", "c est qui sage"}
_HELP = {"aide", "help", "aide moi", "que peux tu faire", "tu peux faire quoi",
         "que sais tu faire", "comment ca marche", "comment tu marches",
         "que proposes tu", "tu sers a quoi", "a quoi sers tu",
         "quelles questions poser", "exemples de questions"}

_RESPONSES: dict[str, list[str]] = {
    "greet": [
        "Bonjour 👋 Je suis RAMA, l'assistant statistique de l'ANSD. "
        "Posez-moi votre question sur les statistiques du Sénégal — "
        "population, emploi, prix, pauvreté, croissance…",
        "Bonjour ! Ravi de vous accueillir. Que souhaitez-vous savoir sur "
        "les statistiques officielles du Sénégal ?",
        "Bonjour 👋 Comment puis-je vous aider ? Vous pouvez par exemple me "
        "demander la population du Sénégal, le taux de chômage, ou où "
        "trouver un rapport de l'ANSD.",
    ],
    "howru": [
        "Très bien, merci ! Et prêt à répondre à vos questions sur les "
        "statistiques du Sénégal. Que souhaitez-vous savoir ?",
    ],
    "thanks": [
        "Avec plaisir ! N'hésitez pas si vous avez d'autres questions sur "
        "les statistiques du Sénégal.",
        "Je vous en prie 😊 Autre chose sur les données de l'ANSD ?",
    ],
    "bye": [
        "Au revoir, et merci de votre visite ! Retrouvez toutes les "
        "publications officielles sur www.ansd.sn. À bientôt 👋",
    ],
    "ack": [
        "Parfait ! Je reste à votre disposition pour toute question sur les "
        "statistiques du Sénégal.",
    ],
    "who": [
        "Je suis **RAMA**, l'assistant virtuel de l'ANSD — "
        "l'Agence Nationale de la Statistique "
        "et de la Démographie du Sénégal. Je réponds à vos questions à partir "
        "des données et publications officielles (recensement RGPH-5, enquêtes "
        "EHCVM et ENES, indice des prix, comptes nationaux) et je vous oriente "
        "vers les bons documents du site ansd.sn.",
    ],
    "help": [
        "Je peux :\n"
        "- **Donner un chiffre officiel** — « Quelle est la population du Sénégal en 2023 ? », « Quel est le taux d'inflation en 2024 ? »\n"
        "- **Comparer et classer** — « Classe les régions par taux de pauvreté »\n"
        "- **Montrer une évolution** — « Comment la population a-t-elle évolué depuis 1976 ? » (avec graphique)\n"
        "- **Expliquer une méthode** — « Comment l'ANSD mesure-t-elle le chômage ? »\n"
        "- **Vous orienter sur le site** — « Où trouver les rapports du RGPH-5 ? »\n\n"
        "Je comprends aussi les questions de suivi : après une réponse, "
        "demandez simplement « Et en 2023 ? ».",
    ],
}

_CATEGORIES = [("who", _WHO), ("help", _HELP), ("howru", _HOWRU),
               ("thanks", _THANKS), ("bye", _BYE), ("greet", _GREET),
               ("ack", _ACK)]


def detect(question: str) -> str | None:
    """Retourne la categorie d'acte social si le message est PUREMENT social."""
    q = _fold(question)
    if not q or len(q.split()) > 6:
        return None
    for cat, lexicon in _CATEGORIES:
        if q in lexicon:
            return cat
    # salutation composee ("bonjour sage", "salut ca va", "hello bonjour")
    words = q.split()
    if words[0] in _GREET and len(words) <= 4:
        rest = " ".join(words[1:])
        if not rest or rest in _HOWRU or rest in {"rama", "sage", "monsieur", "madame", "a tous"} \
                or all(w in _GREET for w in words[1:]):
            return "howru" if rest in _HOWRU else "greet"
    return None


def strip_greeting(question: str) -> str:
    """Retire une salutation en tete d'une vraie question.
    "Bonjour, quelle est la population ?" -> "quelle est la population ?" """
    m = re.match(r"^\s*(salut|bonjour|bonsoir|hello|hi|coucou|slt|bjr|hey)\b[\s,!.:]*",
                 question, re.I)
    if m and len(question[m.end():].split()) >= 3:
        return question[m.end():].strip()
    return question


def respond(category: str, seed: int = 0) -> str:
    variants = _RESPONSES[category]
    return variants[seed % len(variants)]
