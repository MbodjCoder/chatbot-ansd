"""Récupère le texte de pages du site ansd.sn, sans menus ni pieds de page,
pour le corpus documentaire.

Sortie : data/documents/web_*.md
Usage  : python scripts/harvest_web.py
"""
import html
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DOCS = BASE / "data" / "documents"

# Pages a fort contenu textuel (definitions, methodologie, presentation).
# (titre_court, slug_fichier, url)
PAGES = [
    ("Enquête Emploi (ENES)", "web_enes",
     "https://www.ansd.sn/Indicateur/enquete-emploi"),
    ("Indice des prix (IHPC)", "web_ihpc",
     "https://www.ansd.sn/Indicateur/evolution-annuelle-de-lindice-harmonise-des-prix-la-consommation"),
    ("Suivi de la pauvreté", "web_pauvrete",
     "https://www.ansd.sn/Indicateur/rapport-des-enquetes-de-suivi-de-la-pauvrete"),
    ("BDEF — données économiques", "web_bdef",
     "https://www.ansd.sn/Indicateur/banque-de-donnees-economiques-et-financieres-bdef"),
    ("RGPH-5 2023 — présentation", "web_rgph5",
     "https://www.ansd.sn/enquete-et-etude/recensement-general-de-la-population-et-de-lhabitat-rgph-5-2023"),
    ("Bases de données de l'ANSD", "web_bases",
     "https://www.ansd.sn/bases-de-donnees"),
    ("Calendrier de publications", "web_calendrier",
     "https://www.ansd.sn/calendrier-de-publications"),
    ("Enquêtes et études en cours", "web_enquetes",
     "https://www.ansd.sn/enquete"),
]


def fetch(url: str) -> str:
    r = subprocess.run(["curl", "-sk", "--max-time", "30", url],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.stdout or ""


def clean(raw: str) -> str:
    """Extrait le corps utile : retire scripts/styles/balises, puis coupe le
    menu (avant 'Accueil') et le pied de page (menu bas / Suivez-nous)."""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(re.sub(r"\s+", " ", t)).strip()
    # le corps commence apres la derniere occurrence de "Accueil" du fil d'Ariane
    m = list(re.finditer(r"\bAccueil\b", t))
    if m:
        t = t[m[0].end():]
    # couper l'habillage de bas de page (repete sur tout le site)
    for marqueur in ["Menu bas de page", "Suivez-nous", "Licence d",
                     "Pied de page", "Accès rapides", "S'abonner"]:
        i = t.find(marqueur)
        if i > 200:
            t = t[:i]
            break
    return t.strip()


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    n = 0
    for titre, slug, url in PAGES:
        raw = fetch(url)
        if not raw:
            print(f"  [SKIP] {url} (injoignable)")
            continue
        corps = clean(raw)
        if len(corps.split()) < 40:
            print(f"  [SKIP] {url} (contenu trop court : {len(corps.split())} mots)")
            continue
        doc = (f"# {titre} — page officielle ANSD\n\n"
               f"Source : {url} (contenu du site officiel, consulté en 2026).\n\n"
               f"{corps}\n")
        (DOCS / f"{slug}.md").write_text(doc, encoding="utf-8")
        print(f"  [OK ] {slug}.md ({len(corps.split())} mots) <- {url}")
        n += 1
    print(f"\n{n} page(s) recoltee(s) dans {DOCS}")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
