"""Construction de la base statistique (data/ansd_stats.db).

Seules des valeurs publiées par l'ANSD sont insérées ; une valeur non publiée
reste vide (NULL). Les totaux sont contrôlés à chaque construction.

Sources :
  RGPH-5 2023 et RGPH-4 2013 (résultats définitifs)   https://www.ansd.sn/rapports/rgph-5-2023
  EHCVM II 2021/2022 (rapport final, tableau III-2)
  ENES trimestrielles 2023-2025, IHPC 2019-2024, comptes nationaux 2022-2024
  Projections démographiques 2025 (Annuaire Population du Sénégal 2025),
  extraites par scripts/extraire_annuaire_2025.py
"""
import csv
import sqlite3
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
DB = DATA / "ansd_stats.db"
SOURCES = DATA / "sources"

SCHEMA = """
CREATE TABLE regions (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,
    chef_lieu TEXT NOT NULL,
    superficie_km2 REAL
);
CREATE TABLE demographie (              -- population par région aux recensements
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_id INTEGER REFERENCES regions(id),
    annee INTEGER NOT NULL,
    population INTEGER NOT NULL,
    UNIQUE(region_id, annee)
);
CREATE TABLE population_nationale (      -- recensements 1976 à 2023
    annee INTEGER PRIMARY KEY,
    population INTEGER NOT NULL
);
CREATE TABLE population_2025 (           -- projection ANSD par région
    region_id INTEGER PRIMARY KEY REFERENCES regions(id),
    hommes INTEGER NOT NULL,
    femmes INTEGER NOT NULL,
    population INTEGER NOT NULL,
    urbaine INTEGER NOT NULL,
    rurale INTEGER NOT NULL,
    part_urbaine REAL NOT NULL           -- %
);
CREATE TABLE structure_age_2025 (        -- projection ANSD par région et groupe d'âges
    region_id INTEGER REFERENCES regions(id),
    groupe_age TEXT NOT NULL,            -- '0-4', '5-9', ..., '80+'
    age_min INTEGER NOT NULL,
    hommes INTEGER NOT NULL,
    femmes INTEGER NOT NULL,
    population INTEGER NOT NULL,
    PRIMARY KEY (region_id, groupe_age)
);
CREATE TABLE emploi (                    -- ENES trimestrielle (%)
    annee INTEGER NOT NULL,
    trimestre INTEGER NOT NULL,
    taux_chomage_elargi REAL,
    taux_chomage_bit REAL,
    taux_activite REAL,
    PRIMARY KEY (annee, trimestre)
);
CREATE TABLE inflation (                 -- variation annuelle moyenne de l'IHPC (%)
    annee INTEGER PRIMARY KEY,
    taux_inflation REAL NOT NULL
);
CREATE TABLE pauvrete (                  -- EHCVM II 2021/2022
    region_id INTEGER PRIMARY KEY REFERENCES regions(id),
    taux_pauvrete REAL NOT NULL,         -- incidence P0 (%)
    profondeur REAL,                     -- P1 (%)
    severite REAL,                       -- P2 (%)
    gini REAL,
    conso_moyenne_fcfa INTEGER           -- consommation annuelle par tête
);
CREATE TABLE pib (                       -- croissance du PIB réel (%)
    annee INTEGER PRIMARY KEY,
    croissance_reelle REAL NOT NULL
);
CREATE TABLE indicateurs_nationaux (
    code TEXT PRIMARY KEY,
    libelle TEXT NOT NULL,
    valeur REAL NOT NULL,
    unite TEXT,
    annee INTEGER,
    source TEXT
);
"""

REGIONS = [
    (1, "Dakar", "Dakar", 547), (2, "Thies", "Thies", 6670),
    (3, "Diourbel", "Diourbel", 4824), (4, "Saint-Louis", "Saint-Louis", 19034),
    (5, "Ziguinchor", "Ziguinchor", 7352), (6, "Kaolack", "Kaolack", 5357),
    (7, "Fatick", "Fatick", 6849), (8, "Kolda", "Kolda", 13771),
    (9, "Louga", "Louga", 24847), (10, "Matam", "Matam", 29445),
    (11, "Tambacounda", "Tambacounda", 42364), (12, "Kedougou", "Kedougou", 16800),
    (13, "Kaffrine", "Kaffrine", 11262), (14, "Sedhiou", "Sedhiou", 7341),
]

# Population par région : RGPH-4 2013 et RGPH-5 2023
POPULATION = {
    1: (3137196, 4004427), 2: (1788864, 2463678), 3: (1497456, 2080335),
    4: (908942, 1202442), 5: (549151, 617568), 6: (960875, 1336719),
    7: (714392, 906918), 8: (662455, 914798), 9: (874193, 1125908),
    10: (562538, 831629), 11: (681310, 987151), 12: (151357, 245146),
    13: (566992, 820405), 14: (452994, 589266),
}

POPULATION_NATIONALE = [(1976, 4958085), (1988, 6881919), (2002, 9858482),
                        (2013, 13508715), (2023, 18126390)]

# Taux de chômage élargi, taux BIT et taux d'activité (NULL si non publié)
EMPLOI = [
    (2023, 1, 21.5, None, None), (2023, 2, 18.6, None, None),
    (2023, 3, 19.5, None, None), (2023, 4, 22.3, None, None),
    (2024, 1, 23.2, None, None), (2024, 2, 21.6, None, 57.6),
    (2024, 3, 20.3, None, 58.3), (2024, 4, 20.0, None, None),
    (2025, 1, 21.7, 4.9, None),
]

INFLATION = [(2019, 1.0), (2020, 2.5), (2021, 2.2), (2022, 9.7), (2023, 5.9), (2024, 0.8)]

# region_id, P0, P1, P2, Gini, consommation moyenne par tête (FCFA/an)
PAUVRETE = [
    (1, 9.3, 1.1, 0.3, 0.328, 861364), (2, 29.9, 8.3, 3.5, 0.289, 540343),
    (3, 37.4, 9.0, 3.2, 0.244, 464236), (4, 37.3, 9.8, 3.6, 0.286, 498177),
    (5, 48.3, 11.0, 3.8, 0.255, 437354), (6, 49.6, 13.7, 5.3, 0.291, 442489),
    (7, 46.5, 11.9, 4.2, 0.265, 433634), (8, 62.5, 19.1, 7.9, 0.293, 387934),
    (9, 47.0, 12.4, 4.5, 0.271, 444651), (10, 44.7, 12.9, 5.2, 0.267, 439221),
    (11, 62.8, 21.6, 9.5, 0.293, 363543), (12, 65.7, 25.4, 12.9, 0.342, 359121),
    (13, 58.2, 16.3, 6.2, 0.262, 391980), (14, 64.4, 20.3, 8.7, 0.247, 345506),
]

PIB = [(2022, 3.8), (2023, 4.3), (2024, 6.3)]

INDICATEURS = [
    ("pop_totale", "Population résidente totale", 18126390, "habitants", 2023, "RGPH-5"),
    ("croissance_demo", "Taux d'accroissement annuel moyen 2013-2023", 2.9, "%", 2023, "RGPH-5"),
    ("urbanisation", "Taux d'urbanisation", 54.7, "%", 2023, "RGPH-5"),
    ("densite", "Densité de population", 92, "hab/km2", 2023, "RGPH-5"),
    ("densite_dakar", "Densité de la région de Dakar", 7277, "hab/km2", 2023, "RGPH-5"),
    ("esperance_vie", "Espérance de vie à la naissance", 68.9, "ans", 2023, "RGPH-5"),
    ("esperance_vie_femmes", "Espérance de vie des femmes", 70.0, "ans", 2023, "RGPH-5"),
    ("esperance_vie_hommes", "Espérance de vie des hommes", 67.7, "ans", 2023, "RGPH-5"),
    ("isf", "Indice synthétique de fécondité", 4.2, "enfants/femme", 2023, "RGPH-5"),
    ("age_median", "Âge médian de la population", 19, "ans", 2023, "RGPH-5"),
    ("moins_15_ans", "Part des moins de 15 ans", 39.2, "%", 2023, "RGPH-5"),
    ("menages", "Nombre de ménages ordinaires", 1991012, "ménages", 2023, "RGPH-5"),
    ("taille_menage", "Taille moyenne des ménages ordinaires", 9, "personnes", 2023, "RGPH-5"),
    ("tbs_primaire", "Taux brut de scolarisation au primaire", 81.0, "%", 2023, "RGPH-5"),
    ("electricite", "Ménages utilisant l'électricité pour l'éclairage", 74.4, "%", 2023, "RGPH-5"),
    ("eau_robinet", "Ménages disposant d'un robinet dans le logement", 69.9, "%", 2023, "RGPH-5"),
    ("handicap", "Taux de prévalence du handicap", 7.3, "%", 2023, "RGPH-5"),
    ("menages_agricoles", "Part des ménages agricoles", 44.5, "%", 2023, "RGPH-5"),
    ("proprietaires", "Ménages propriétaires de leur logement", 67.4, "%", 2023, "RGPH-5"),
    ("pauvrete_nationale", "Incidence de la pauvreté monétaire", 37.5, "%", 2022, "EHCVM II 2021/22"),
    ("pauvrete_2018", "Incidence de la pauvreté monétaire (édition précédente)", 37.8, "%", 2019, "EHCVM I 2018/19"),
    ("pauvrete_extreme", "Incidence de l'extrême pauvreté", 5.6, "%", 2022, "EHCVM II 2021/22"),
    ("pauvrete_rurale", "Incidence de la pauvreté en milieu rural", 53.3, "%", 2022, "EHCVM II 2021/22"),
    ("pauvrete_urbaine", "Incidence de la pauvreté en milieu urbain", 20.0, "%", 2022, "EHCVM II 2021/22"),
    ("gini_national", "Indice de Gini national", 0.334, "indice", 2022, "EHCVM II 2021/22"),
    ("insecurite_alim", "Prévalence de l'insécurité alimentaire modérée ou sévère", 29.9, "%", 2022, "EHCVM II 2021/22"),
]


def lire_csv(nom: str) -> list[dict]:
    with open(SOURCES / nom, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def projections_2025(ids: dict) -> tuple[list, list]:
    """Charge les projections 2025 et revérifie leurs totaux."""
    regions = lire_csv("population_2025_regions.csv")
    ages = lire_csv("population_2025_ages.csv")
    lignes_regions = [(ids[r["region"]], int(r["hommes"]), int(r["femmes"]), int(r["population"]),
                       int(r["urbaine"]), int(r["rurale"]), float(r["part_urbaine"]))
                      for r in regions]
    lignes_ages = [(ids[a["region"]], a["groupe_age"], int(a["age_min"]), int(a["hommes"]),
                    int(a["femmes"]), int(a["population"])) for a in ages]
    assert sum(r[3] for r in lignes_regions) == 19075959, "total 2025 != total officiel"
    for rid, h, f, total, *_ in lignes_regions:
        assert h + f == total
        assert sum(a[5] for a in lignes_ages if a[0] == rid) == total
    return lignes_regions, lignes_ages


def main():
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    ids = {nom: rid for rid, nom, _, _ in REGIONS}

    con.executemany("INSERT INTO regions VALUES (?,?,?,?)", REGIONS)
    for rid, (p2013, p2023) in POPULATION.items():
        con.execute("INSERT INTO demographie(region_id, annee, population) VALUES (?,?,?)", (rid, 2013, p2013))
        con.execute("INSERT INTO demographie(region_id, annee, population) VALUES (?,?,?)", (rid, 2023, p2023))
    assert sum(p[0] for p in POPULATION.values()) == 13508715, "somme 2013 != total RGPH-4"
    assert sum(p[1] for p in POPULATION.values()) == 18126390, "somme 2023 != total RGPH-5"

    regions_2025, ages_2025 = projections_2025(ids)
    con.executemany("INSERT INTO population_2025 VALUES (?,?,?,?,?,?,?)", regions_2025)
    con.executemany("INSERT INTO structure_age_2025 VALUES (?,?,?,?,?,?)", ages_2025)

    con.executemany("INSERT INTO population_nationale VALUES (?,?)", POPULATION_NATIONALE)
    con.executemany("INSERT INTO emploi VALUES (?,?,?,?,?)", EMPLOI)
    con.executemany("INSERT INTO inflation VALUES (?,?)", INFLATION)
    con.executemany("INSERT INTO pauvrete VALUES (?,?,?,?,?,?)", PAUVRETE)
    con.executemany("INSERT INTO pib VALUES (?,?)", PIB)
    con.executemany("INSERT INTO indicateurs_nationaux VALUES (?,?,?,?,?,?)", INDICATEURS)
    con.commit()

    tables = [t for (t,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    lignes = sum(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables)
    print(f"Base créée : {len(tables)} tables, {lignes} lignes, totaux contrôlés.")
    con.close()


if __name__ == "__main__":
    main()
