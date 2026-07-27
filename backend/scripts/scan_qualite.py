"""
Scan de qualite systematique : batterie de questions couvrant toutes les
voies (SQL, RAG, HYBRID, NAV, CATALOG, CHAT, suivis, guardrails), avec
detection AUTOMATIQUE des defauts de reponse :
  - phrase dupliquee dans la reponse ;
  - echo de la question ;
  - reponse vide ou tronquee ;
  - jargon technique restant (nom =, SELECT, chunk...) ;
  - refus injustifie (guardrail sur une question du domaine).
Usage : ANSD_MODE=demo python scripts/scan_qualite.py
"""
import io
import os
import re
import sys
import unicodedata
from pathlib import Path

os.environ.setdefault("ANSD_MODE", "demo")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.core.chatbot import ANSDChatbot

QUESTIONS = [
    # SQL simples et superlatifs
    # AVEC accents : c'est ainsi que les usagers ecrivent reellement
    "Quelle est la population du Sénégal en 2023 ?",
    "Quel est le taux de chômage en 2024 ?",
    "quelle est la région la plus peuplée du Sénégal",
    "Quelle région a le plus faible taux de pauvreté ?",
    "Quel est le taux d'inflation en 2024 ?",
    "Quelle est l'espérance de vie au Sénégal ?",
    "Classe les régions par taux de pauvreté décroissant",
    "Comment la population a-t-elle évolué depuis 1976 ?",
    # RAG methodologie / definitions
    "Comment le recensement RGPH-5 a-t-il été réalisé ?",
    "Comment l'ANSD mesure-t-elle la pauvreté ?",
    "Comment l'IHPC est-il calculé ?",
    "Qu'est-ce que l'indice de Gini ?",
    "Quelle est la différence entre chômage strict et chômage élargi ?",
    "Qu'est-ce que l'EHCVM ?",
    "Quelles sont les missions de l'ANSD ?",
    "Qu'est-ce que l'indice synthétique de fécondité ?",
    # services / navigation / catalogue
    "Comment contacter l'ANSD ?",
    "Où télécharger le rapport EHCVM ?",
    "Quand paraît le prochain IHPC ?",
    "Quelles formations propose l'ENSAE ?",
    "Quelles enquêtes existent sur la santé ?",
    "Y a-t-il des microdonnées sur l'agriculture ?",
    "Quelles sont les enquêtes en cours à l'ANSD ?",
    "Comment accéder aux microdonnées (ANADS) ?",
    # social / guardrails
    "salut",
    "merci beaucoup",
    "qui es-tu ?",
    "Pour qui voter aux prochaines elections ?",
    "Quelle est la capitale de la France ?",
]


def _fold(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower())
                   if unicodedata.category(c) != "Mn")


def defauts(question: str, r) -> list[str]:
    pb = []
    a = r.answer
    # phrases dupliquees
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", a) if len(s.strip()) > 25]
    vus = set()
    for s in sents:
        k = _fold(s)[:80]
        if k in vus:
            pb.append("PHRASE DUPLIQUEE")
            break
        vus.add(k)
    # echo de la question
    if _fold(question.rstrip(" ?")) in _fold(a) and len(a) < len(question) + 40:
        pb.append("ECHO DE LA QUESTION")
    # vide / jargon
    if len(a.strip()) < 15:
        pb.append("REPONSE VIDE")
    for jargon in ["nom =", "SELECT ", "chunk", "None", "np.", "col ="]:
        if jargon in a:
            pb.append(f"JARGON: {jargon}")
    # refus injustifie (les 2 dernieres questions DOIVENT etre refusees)
    domaine = question not in ("Pour qui voter aux prochaines elections ?",
                               "Quelle est la capitale de la France ?")
    if domaine and r.guardrail != "ok" and r.route != "CHAT":
        pb.append(f"REFUS INJUSTIFIE ({r.guardrail})")
    if not domaine and r.guardrail == "ok":
        pb.append("GUARDRAIL MANQUANT")
    return pb


def main():
    bot = ANSDChatbot()
    total_pb = 0
    for q in QUESTIONS:
        r = bot.ask(q)
        pb = defauts(q, r)
        statut = " ; ".join(pb) if pb else "ok"
        marque = "!!" if pb else "  "
        print(f"{marque} [{r.route:7}] {q[:52]:54} -> {statut}")
        if pb:
            total_pb += len(pb)
            print(f"      reponse: {r.answer[:150]}")
    print(f"\n{'SCAN PROPRE' if total_pb == 0 else str(total_pb) + ' DEFAUT(S) A CORRIGER'}")
    return 1 if total_pb else 0


if __name__ == "__main__":
    sys.exit(main())
