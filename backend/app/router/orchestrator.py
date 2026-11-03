"""Choix de la voie de réponse : SQL (chiffre), RAG (document) ou HYBRID (les deux).

1. Classifieur rapide : TF-IDF et régression logistique, entraîné sur
   data/datasets/routing_dataset.csv (scripts/train_router.py).
2. Si sa confiance est inférieure au seuil, le modèle de langage tranche.

Évaluation : app/evaluation/evaluate_router.py.
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
    """Classifieur TF-IDF et régression logistique."""

    def __init__(self, artifact: str):
        import joblib
        obj = joblib.load(artifact)
        self.pipe, self.labels = obj["pipeline"], obj["labels"]

    def predict(self, question: str) -> tuple[str, float]:
        proba = self.pipe.predict_proba([question])[0]
        i = proba.argmax()
        return self.labels[i], float(proba[i])


class DebertaClassifier:
    """Classifieur DeBERTa-v3 affiné, si le modèle est installé (optionnel)."""

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
                # DeBERTa absent : classifieur TF-IDF
                self.classifier = (DemoClassifier(str(artifact))
                                   if artifact.exists() else None)

    def route(self, question: str) -> RouteDecision:
        # classifieur rapide
        if self.classifier is not None:
            label, conf = self.classifier.predict(question)
            if conf >= settings.router_confidence_threshold:
                return RouteDecision(label, conf, "classifier")
        # cas ambigu : le modèle de langage tranche
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
