"""Entraîne le classifieur de choix de voie (TF-IDF et régression logistique)
sur data/datasets/routing_dataset.csv, avec validation croisée à 5 plis.

Sortie : data/router_demo.joblib
Usage  : python scripts/train_router.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline, FeatureUnion

BASE = Path(__file__).resolve().parents[1]
df = pd.read_csv(BASE / "data" / "datasets" / "routing_dataset.csv")
X, y = df["question"].tolist(), df["label"].tolist()

pipe = Pipeline([
    ("features", FeatureUnion([
        # strip_accents : le corpus d'entrainement est majoritairement sans
        # accents, les usagers ecrivent avec — le repli unifie les deux
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True,
                                 strip_accents="unicode")),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                 strip_accents="unicode")),
    ])),
    ("clf", LogisticRegression(max_iter=2000, C=4.0)),
])

cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
pred = cross_val_predict(pipe, X, y, cv=cv)
acc = float(np.mean(pred == np.array(y)))
f1 = f1_score(y, pred, average="macro")
labels = sorted(set(y))
cm = confusion_matrix(y, pred, labels=labels)

print(f"Validation croisee 5 plis (n={len(y)})")
print(f"  Accuracy : {acc:.3f}")
print(f"  F1 macro : {f1:.3f}")
print(f"  Matrice de confusion (lignes = verite, colonnes = prediction) {labels} :")
for lab, row in zip(labels, cm):
    print(f"    {lab:>7} {row}")

pipe.fit(X, y)
out = BASE / "data" / "router_demo.joblib"
joblib.dump({"pipeline": pipe, "labels": labels,
             "cv_accuracy": acc, "cv_f1_macro": f1}, out)
print(f"Artefact sauvegarde : {out}")
