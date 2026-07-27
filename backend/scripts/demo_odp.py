# -*- coding: utf-8 -*-
"""
Démonstration de la fédération de sources (décision #94) — pour la soutenance.

Construit une source composite [Plateforme Open Data → entrepôt curaté] et sert une
question chiffrée. Affiche QUELLE source a répondu : l'ODP en direct si le réseau le
permet, sinon l'entrepôt curaté en repli. Prouve, en direct, que « brancher le SI réel
de l'ANSD = ajouter un adaptateur » — et que le service ne tombe jamais.

    python scripts/demo_odp.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sql.sources import DataMartCurate, SourceComposite
from app.sql.odp import AdaptateurODP

SQL = "SELECT annee, taux_inflation FROM inflation ORDER BY annee;"


def main():
    mart = DataMartCurate()
    composite = SourceComposite([AdaptateurODP(), mart])

    print("Question : évolution de l'inflation (IHPC) au Sénégal\n")
    print("Source composite branchée : Plateforme Open Data (ODP) → entrepôt curaté (repli)\n")

    r = composite.execute(SQL)
    live = "Open Data" in r.provenance
    print(f"  → répondu par : {r.provenance}")
    print(f"    ({'ODP en direct' if live else 'repli entrepôt curaté — ODP indisponible depuis ce réseau'})\n")
    for annee, taux in r.rows:
        print(f"    {annee} : {str(taux).replace('.', ',')} %")
    print("\nLe même code servira l'ODP en direct dès qu'il est joignable — "
          "aucun autre changement dans l'architecture.")


if __name__ == "__main__":
    main()
