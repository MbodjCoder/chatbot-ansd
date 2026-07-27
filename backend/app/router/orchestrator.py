"""
Orchestrateur de routage a deux niveaux (contribution centrale du memoire).

Formalisation : f(q) -> {SQL, RAG, HYBRID}

Niveau 1 - classifieur supervise leger :
  * production : DeBERTa-v3 fine-tune (He et al., 2021) sur le corpus annote
    data/datasets/routing_dataset.csv
  * demo       : TF-IDF (1-2 grammes, caracteres+mots) + regression logistique
    (baseline reproductible sans GPU ; meme protocole d'evaluation)
Niveau 2 - fallback LLM :
  si la confiance du classifieur < seuil (0.85), le LLM tranche via un
  prompt specialise (LLM-as-router). Ce schema combine l'efficacite
  computationnelle du niveau 1 (~ms) et la flexibilite du niveau 2
  pour les cas ambigus.

L'evaluation du routage (accuracy, matrice de confusion, test du chi2)
est implementee dans app/evaluation/evaluate_router.py.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.llm.client import LLMClient

LABELS = ["SQL", "RAG", "HYBRID"]

ROUTE_SYSTEM = """ROUTE_CLASSIFICATION - Tu es le routeur d'un systeme hybride de
question-reponse statistique (ANSD). Classe la question :
- "SQL"    : la reponse est un chiffre/agregat present en base de donnees
- "RAG"    : la reponse est dans des documents (methodologie, definitions, rapports)
- "HYBRID" : il faut combiner un chiffre ET une explication documentaire
Reponds en JSON strict : {"route": "...", "confidence": 0.0-1.0}"""


@dataclass
class RouteDecision:
    route: str
    confidence: float
    level: str  # "classifier" | "llm_fallback"


class DemoClassifier:
    """Niveau 1 en mode demo : TF-IDF + regression logistique calibree.
    Entraine par scripts/train_router.py sur le corpus annote."""

    def __init__(self, artifact: str):
        import joblib
        obj = joblib.load(artifact)
        self.pipe, self.labels = obj["pipeline"], obj["labels"]

    def predict(self, question: str) -> tuple[str, float]:
        proba = self.pipe.predict_proba([question])[0]
        i = proba.argmax()
        return self.labels[i], float(proba[i])


class DebertaClassifier:
    """Niveau 1 en production : DeBERTa-v3 fine-tune (sequence classification).
    Le script de fine-tuning est fourni dans scripts/finetune_deberta.py."""

    def __init__(self, model_dir: str):
        from transformers import pipeline
        self.pipe = pipeline("text-classification", model=model_dir, top_k=None)

    def predict(self, question: str) -> tuple[str, float]:
        scores = self.pipe(question)[0]
        best = max(scores, key=lambda s: s["score"])
        return best["label"], float(best["score"])


class Orchestrator:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.classifier = None
        artifact = Path(settings.router_artifact)
        if settings.mode == "demo" and artifact.exists():
            self.classifier = DemoClassifier(str(artifact))
        elif settings.mode == "production":
            try:
                self.classifier = DebertaClassifier(settings.router_model)
            except Exception:
                # degradation controlee : DeBERTa absent -> classifieur TF-IDF
                # (meme corpus, meme protocole) plutot que LLM-as-router seul
                # (latence et cout par question superieurs sinon)
                self.classifier = (DemoClassifier(str(artifact))
                                   if artifact.exists() else None)

    def route(self, question: str) -> RouteDecision:
        # Niveau 1 : classifieur rapide
        if self.classifier is not None:
            label, conf = self.classifier.predict(question)
            if conf >= settings.router_confidence_threshold:
                return RouteDecision(label, conf, "classifier")
        # Niveau 2 : fallback LLM pour les cas ambigus
        resp = self.llm.complete(ROUTE_SYSTEM, question, temperature=0.0)
        try:
            data = json.loads(resp.text)
            route = data.get("route", "RAG")
            conf = float(data.get("confidence", 0.5))
            if route not in LABELS:
                route = "RAG"
        except (json.JSONDecodeError, ValueError):
            route, conf = "RAG", 0.5
        return RouteDecision(route, conf, "llm_fallback")
