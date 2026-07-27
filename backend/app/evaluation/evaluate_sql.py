"""
Evaluation du module Text-to-SQL selon le protocole Spider (Yu et al., 2018).

Metrique retenue : Execution Accuracy (EA) - le resultat de l'execution de
la requete generee est-il identique a celui de la requete de reference ?
L'EA est preferee a l'Exact Set Match car plusieurs SQL syntaxiquement
differents peuvent etre semantiquement equivalents (Zhong et al., 2020).
"""
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings
from app.llm.client import get_llm
from app.sql.pipeline import TextToSQLPipeline


def run(sql: str):
    con = sqlite3.connect(f"file:{settings.database_path}?mode=ro", uri=True)
    try:
        rows = con.execute(sql).fetchall()
        # comparaison insensible a l'ordre des colonnes de meme ligne
        return sorted(tuple(sorted(map(str, r))) for r in rows)
    finally:
        con.close()


def main():
    dataset = json.loads((Path(__file__).resolve().parents[2] / "data" /
                          "datasets" / "sql_test_set.json").read_text())
    pipe = TextToSQLPipeline(get_llm())
    ok, details = 0, []
    for item in dataset:
        res = pipe.answer(item["question"])
        try:
            match = run(res.sql) == run(item["gold_sql"])
        except sqlite3.Error:
            match = False
        ok += match
        details.append((item["question"], match, res.sql))
    ea = ok / len(dataset)
    print(f"Execution Accuracy : {ea:.2%}  ({ok}/{len(dataset)})")
    for q, m, s in details:
        print(f"  [{'OK ' if m else 'ECH'}] {q}\n        -> {s}")
    return ea


if __name__ == "__main__":
    import sys
    # seuil de non-regression pour la CI (P2-6) : EA doit rester a 100%
    sys.exit(0 if main() >= 0.999 else 1)
