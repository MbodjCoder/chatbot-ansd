"""
Evaluation du routage : accuracy, F1 macro, matrice de confusion,
test du chi2 d'independance (H1 du memoire) via validation croisee
stratifiee 5 plis - voir scripts/train_router.py pour l'entrainement.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
from scipy.stats import chi2_contingency
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_predict

import joblib


def main():
    base = Path(__file__).resolve().parents[2]
    df = pd.read_csv(base / "data" / "datasets" / "routing_dataset.csv")
    X, y = df["question"].tolist(), df["label"].to_numpy()
    art = joblib.load(base / "data" / "router_demo.joblib")
    pipe = art["pipeline"]
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    pred = cross_val_predict(pipe, X, y, cv=cv)
    labels = sorted(set(y))
    cm = confusion_matrix(y, pred, labels=labels)
    chi2, p, dof, _ = chi2_contingency(cm)
    print(classification_report(y, pred, labels=labels, digits=3))
    print("Matrice de confusion", labels)
    print(cm)
    print(f"Chi2 = {chi2:.1f}, ddl = {dof}, p = {p:.2e} "
          f"({'association significative prediction/verite' if p < 0.05 else 'ns'})")


if __name__ == "__main__":
    main()
