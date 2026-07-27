"""
Recolte et extraction de texte des PDF officiels de l'ANSD (harvest_pdf.py).

Objectif : integrer le contenu des rapports et notes PDF a la base de
connaissance documentaire. On privilegie les documents en PROSE (notes de
presse, syntheses) plutot que les gros rapports tabulaires : l'extraction de
tableaux produit un texte bruite peu exploitable par le RAG.

Chaque PDF est telecharge (curl), son texte extrait (pypdf), nettoye, tronque
aux premieres pages utiles, et sauvegarde comme document de corpus avec sa
source. URLs verifiees (HTTP 200).

Usage : python scripts/harvest_pdf.py
Sortie : data/documents/pdf_*.md
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DOCS = BASE / "data" / "documents"

# documents en prose (notes de presse / syntheses), pas les gros rapports
PDFS = [
    ("Note de presse EHCVM II — pauvreté", "pdf_ehcvm_note",
     "https://www.ansd.sn/sites/default/files/2024-07/NOTE%20DE%20PRESSE%20EHCVM%20II.pdf"),
    ("Note ENES T1 2024 — emploi", "pdf_enes_note",
     "https://www.ansd.sn/sites/default/files/2024-07/Rapport_enes_T1_2024_VF.pdf"),
    ("Rapport préliminaire RGPH-5 2023", "pdf_rgph5_prelim",
     "https://www.ansd.sn/sites/default/files/2023-10/RAPPORT-PRELIMINAIRE-RGPH-5_2023-.pdf"),
]

MAX_WORDS = 900   # premieres pages utiles (resume, principaux resultats)


def extract(url: str) -> str:
    try:
        import pypdf
    except ImportError:
        print("  pip install pypdf")
        return ""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        tmp = Path(f.name)
    try:
        subprocess.run(["curl", "-sk", "--max-time", "60", "-o", str(tmp), url],
                       check=False)
        if tmp.stat().st_size < 1000:
            return ""
        reader = pypdf.PdfReader(str(tmp))
        pages = []
        for p in reader.pages[:6]:
            pages.append(p.extract_text() or "")
        return "\n".join(pages)
    except Exception as e:  # noqa: BLE001
        print(f"  extraction echouee : {e}")
        return ""
    finally:
        tmp.unlink(missing_ok=True)


def clean(t: str) -> str:
    t = re.sub(r"[ \t]+", " ", t)
    # retirer numeros de page isoles et lignes vides multiples
    t = re.sub(r"\n\s*\d+\s*\n", "\n", t)
    t = re.sub(r"\n{2,}", "\n", t)
    mots = t.split()
    if len(mots) > MAX_WORDS:
        t = " ".join(mots[:MAX_WORDS])
    return t.strip()


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    n = 0
    for titre, slug, url in PDFS:
        raw = extract(url)
        corps = clean(raw) if raw else ""
        if len(corps.split()) < 60:
            print(f"  [SKIP] {url} (texte insuffisant)")
            continue
        doc = (f"# {titre} (document PDF officiel ANSD)\n\n"
               f"Source : {url} (extrait des premieres pages, 2026).\n\n"
               f"{corps}\n")
        (DOCS / f"{slug}.md").write_text(doc, encoding="utf-8")
        print(f"  [OK ] {slug}.md ({len(corps.split())} mots)")
        n += 1
    print(f"\n{n} PDF recolte(s)")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
