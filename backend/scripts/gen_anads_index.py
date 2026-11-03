"""Génère data/documents/anads_catalogue_index.md (les fiches ANADS par collection)
à partir de data/anads_catalogue.json.

Usage : python scripts/gen_anads_index.py   (après harvest_anads.py)
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data"


def periode(e: dict) -> str:
    a = e["annee_debut"] or "?"
    if e["annee_fin"] and e["annee_fin"] != e["annee_debut"]:
        a += "–" + e["annee_fin"]
    return a


def main() -> None:
    d = json.loads((BASE / "anads_catalogue.json").read_text(encoding="utf-8"))
    seen, rows = set(), []
    for e in d["etudes"]:
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        rows.append(e)

    groups: dict[str, list[dict]] = defaultdict(list)
    for e in rows:
        groups[(e["collection"] or "Autres opérations").strip()].append(e)

    out = [
        "# Catalogue ANADS — index complet des opérations statistiques",
        "",
        f"L'archive nationale des microdonnées (ANADS) recense {len(rows)} "
        "opérations statistiques officielles (enquêtes, recensements, registres, "
        "études). Chaque fiche ci-dessous ouvre la page officielle correspondante, "
        "qui donne accès à la documentation, aux questionnaires et à la procédure "
        "de demande des microdonnées — quel que soit le format. "
        "Portail : https://anads.ansd.sn/",
        "",
    ]
    for coll in sorted(groups):
        out.append(f"## {coll}")
        out.append("")
        for e in sorted(groups[coll], key=lambda x: -(int(x["annee_debut"] or 0))):
            prod = (e["producteur"] or "").split(",")[0].strip()
            line = f"- [{e['titre']}]({e['url']}) — {periode(e)}"
            if prod:
                line += f", {prod}"
            if e.get("idno"):
                line += f" (réf. {e['idno']})"
            out.append(line)
        out.append("")

    txt = "\n".join(out)
    (BASE / "documents" / "anads_catalogue_index.md").write_text(txt, encoding="utf-8")
    print(f"wrote {len(rows)} etudes, {len(groups)} collections, {len(txt)} chars")


if __name__ == "__main__":
    main()
