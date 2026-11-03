"""Extraction des tableaux de l'Annuaire Population du Sénégal 2025 (ANSD).

Source : projections démographiques officielles de l'ANSD (avril 2026).
Le PDF est téléchargé, ses tableaux lus, puis chaque ligne est contrôlée :
hommes + femmes = ensemble, somme des tranches d'âge = total régional,
somme des régions = total national. Toute incohérence arrête le script.

Sorties : data/sources/population_2025_regions.csv
          data/sources/population_2025_ages.csv
Usage   : python scripts/extraire_annuaire_2025.py
"""
import csv
import re
import tempfile
import unicodedata
import urllib.request
from itertools import combinations
from pathlib import Path

URL = ("https://www.ansd.sn/sites/default/files/2026-04/"
       "Rapport%20sur%20la%20Population%20du%20Se%CC%81ne%CC%81gal%202025%2029_avril_OK.pdf")
SORTIE = Path(__file__).resolve().parents[1] / "data" / "sources"
TOTAL_NATIONAL = 19_075_959

REGIONS = ["Dakar", "Diourbel", "Fatick", "Kaffrine", "Kaolack", "Kedougou", "Kolda",
           "Louga", "Matam", "Saint-Louis", "Sedhiou", "Tambacounda", "Thies", "Ziguinchor"]


def sans_accent(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte)
                   if unicodedata.category(c) != "Mn")


def decouper(groupes: list[str], n: int, controle) -> list[int]:
    """Découpe des groupes de chiffres (« 1 095 376 1 112 902 ») en n nombres.

    L'espace sépare à la fois les milliers et les colonnes : on retient
    l'unique découpage qui respecte le contrôle du tableau."""
    solutions = []
    for coupes in combinations(range(1, len(groupes)), n - 1):
        bornes = (0, *coupes, len(groupes))
        morceaux = [groupes[a:b] for a, b in zip(bornes, bornes[1:])]
        if any(len(m) > 3 or any(len(g) != 3 for g in m[1:]) for m in morceaux):
            continue
        nombres = [int("".join(m)) for m in morceaux]
        if controle(nombres):
            solutions.append(nombres)
    if len(solutions) != 1:
        raise ValueError(f"découpage ambigu ou impossible : {' '.join(groupes)}")
    return solutions[0]


def texte_pdf() -> str:
    import pypdf
    with tempfile.TemporaryDirectory() as dossier:
        chemin = Path(dossier) / "annuaire_2025.pdf"
        requete = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        chemin.write_bytes(urllib.request.urlopen(requete, timeout=120).read())
        return "\n".join(p.extract_text() for p in pypdf.PdfReader(str(chemin)).pages)


def regions_par_sexe(texte: str) -> dict:
    """Tableau 2 : population par région et par sexe."""
    bloc = texte.split("Tableau 2", 1)[1].split("Tableau 3", 1)[0]
    lignes = {}
    for ligne in bloc.splitlines():
        m = re.match(r"([A-Za-zÀ-ÿ\- ]+?) ((?:\d{1,3} ?)+) [\d,]+$", ligne.strip())
        if not m:
            continue
        nom = sans_accent(m.group(1).strip())
        h, f, e = decouper(m.group(2).split(), 3, lambda x: x[0] + x[1] == x[2])
        lignes[nom] = {"hommes": h, "femmes": f, "population": e}
    return lignes


def regions_par_milieu(texte: str) -> dict:
    """Tableau 17 : population urbaine et rurale par région."""
    bloc = texte.split("Tableau 17", 1)[1].split("Tableau 18", 1)[0]
    lignes = {}
    for ligne in bloc.splitlines():
        m = re.match(r"([A-Za-zÀ-ÿ\- ]+?) ((?:\d{1,3} ?)+) ([\d,]+)$", ligne.strip())
        if not m:
            continue
        nom = sans_accent(m.group(1).strip())
        if nom == "Senegal":    # ligne nationale arrondie, contrôlée par le tableau 2
            continue
        # urbain (h, f, e), rural (h, f, e), total ; le total arrondi peut
        # différer de quelques unités de la somme urbain + rural
        valeurs = decouper(m.group(2).split(), 7, lambda x: x[0] + x[1] == x[2]
                           and x[3] + x[4] == x[5] and abs(x[2] + x[5] - x[6]) <= 10)
        lignes[nom] = {"urbaine": valeurs[2], "rurale": valeurs[5],
                       "part_urbaine": float(m.group(3).replace(",", "."))}
    return lignes


def ages_par_region(texte: str) -> list[dict]:
    """Tableaux 3 à 16 : chaque région par groupe d'âges et par sexe."""
    lignes, region = [], None
    for ligne in texte.splitlines():
        titre = re.search(r"population de la région de ([A-Za-zÀ-ÿ\- ]+?) par groupe", ligne)
        if titre:
            region = sans_accent(titre.group(1)).replace(" ", "-")
            continue
        m = re.match(r"\s*(\d+-\d+|80 ans ou plus|80\+)(?: ans)? ((?:\d{1,3} ?)+)$", ligne)
        if region and m:
            h, f, e = decouper(m.group(2).split(), 3, lambda x: x[0] + x[1] == x[2])
            groupe = "80+" if m.group(1).startswith("80") else m.group(1)
            lignes.append({"region": region, "groupe_age": groupe,
                           "age_min": int(re.match(r"\d+", groupe).group()),
                           "hommes": h, "femmes": f, "population": e})
    return lignes


def main():
    texte = texte_pdf().split("INTRODUCTION", 1)[1]   # ignore la table des matières
    sexe, milieu, ages = regions_par_sexe(texte), regions_par_milieu(texte), ages_par_region(texte)

    assert set(sexe) == set(REGIONS) | {"Senegal"}, sorted(sexe)
    assert sum(sexe[r]["population"] for r in REGIONS) == TOTAL_NATIONAL
    assert sexe["Senegal"]["population"] == TOTAL_NATIONAL
    for r in REGIONS:
        tranches = [a for a in ages if a["region"] == r]
        assert len(tranches) == 17, (r, len(tranches))
        assert sum(a["population"] for a in tranches) == sexe[r]["population"], r
        assert abs(milieu[r]["urbaine"] + milieu[r]["rurale"] - sexe[r]["population"]) <= 10, r

    SORTIE.mkdir(parents=True, exist_ok=True)
    with open(SORTIE / "population_2025_regions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["region", "hommes", "femmes", "population", "urbaine", "rurale", "part_urbaine"])
        for r in REGIONS:
            w.writerow([r, *sexe[r].values(), *milieu[r].values()])
    with open(SORTIE / "population_2025_ages.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ages[0]))
        w.writeheader()
        w.writerows(ages)
    print(f"{len(REGIONS)} régions et {len(ages)} tranches d'âge extraites, contrôles validés.")


if __name__ == "__main__":
    main()
