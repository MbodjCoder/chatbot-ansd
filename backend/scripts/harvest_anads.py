"""
Recolte du catalogue complet de l'ANADS (anads.ansd.sn).

L'ANADS est une instance NADA (outil de catalogage de microdonnees de la
Banque mondiale) dont l'API de recherche est publique. Ce script recolte
les metadonnees de TOUTES les etudes du catalogue (285 au 2026-07-06) :
identifiant, titre, pays, producteur, periode, collection thematique,
nombre de variables, URL directe de la fiche.

Les fichiers de microdonnees eux-memes sont soumis a une demande d'acces
sur la plateforme (licence) : le chatbot oriente l'usager vers la fiche
exacte, ou il peut soumettre sa demande — c'est precisement le parcours
officiel voulu par l'ANSD.

Usage : python scripts/harvest_anads.py
Sortie : data/anads_catalogue.json
"""
import json
import ssl
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
API = "https://anads.ansd.sn/index.php/api/catalog/search"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def fetch(page: int, ps: int = 100) -> dict:
    # NADA pagine par `page` (le parametre `from`/`offset` est ignore)
    req = urllib.request.Request(f"{API}?ps={ps}&page={page}",
                                 headers={"User-Agent": "RAMA-ANSD/1.0"})
    with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
        return json.load(r)["result"]


def main():
    rows, page, total = [], 1, None
    while total is None or len(rows) < total:
        res = fetch(page)
        total = int(res["found"])
        page_rows = res["rows"]
        if not page_rows:
            break
        for r in page_rows:
            rows.append({
                "id": r["id"],
                "idno": r.get("idno"),
                "titre": r.get("title"),
                "pays": r.get("nation"),
                "producteur": r.get("authoring_entity"),
                "annee_debut": r.get("year_start"),
                "annee_fin": r.get("year_end"),
                "collection": r.get("repo_title"),
                "nb_variables": r.get("varcount"),
                "acces": r.get("form_model"),
                "url": r.get("url"),
            })
        page += 1
        print(f"  {len(rows)}/{total}")
    out = BASE / "data" / "anads_catalogue.json"
    out.write_text(json.dumps({"harvested": "2026-07-06", "total": len(rows),
                               "etudes": rows}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"Catalogue ANADS sauvegarde : {out} ({len(rows)} etudes)")


if __name__ == "__main__":
    sys.exit(main())
