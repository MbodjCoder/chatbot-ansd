"""
Peuplement de la base statistique ansd_stats.db avec les DONNEES OFFICIELLES
publiees par l'ANSD (collecte : juillet 2026, sources verifiees et triangulees).

Sources primaires :
  - RGPH-5 2023 (resultats definitifs, ANSD, juillet 2024) : population totale
    18 126 390 ; repartition regionale verifiee (somme exacte = total officiel).
    https://www.ansd.sn/rapports/rgph-5-2023
  - RGPH-4 2013 : population 13 508 715 (somme regionale exacte).
  - EHCVM II 2021/2022 (rapport final ANSD, tableau III-2) : incidence de la
    pauvrete, profondeur, severite, Gini par region.
    https://www.ansd.sn/sites/default/files/2024-07/Rapport_Final_EHCVM_2021-2022_VF_0.pdf
  - ENES trimestrielles 2023-2025 (notes d'information ANSD) : taux de chomage
    elargi par trimestre. https://www.ansd.sn/Indicateur/enquete-emploi
  - IHPC (ANSD, notes annuelles) : inflation moyenne annuelle 2019-2024.
  - Comptes nationaux trimestriels (ANSD) : croissance du PIB reel 2022-2024.

Regle de qualite (Principe 2, Nations Unies 2014) : seule une valeur publiee
par l'ANSD et verifiee dans un document officiel est inseree ; les valeurs
non publiees restent NULL plutot qu'estimees.
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "ansd_stats.db"
DB.parent.mkdir(parents=True, exist_ok=True)
if DB.exists():
    DB.unlink()

con = sqlite3.connect(DB)
cur = con.cursor()

cur.executescript("""
CREATE TABLE regions (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,               -- nom de la region administrative
    chef_lieu TEXT NOT NULL,
    superficie_km2 REAL              -- superficie officielle
);
CREATE TABLE demographie (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_id INTEGER REFERENCES regions(id),
    annee INTEGER NOT NULL,          -- annee de recensement (RGPH-4 2013, RGPH-5 2023)
    population INTEGER NOT NULL,     -- population residente (resultats definitifs)
    UNIQUE(region_id, annee)
);
CREATE TABLE population_nationale (
    annee INTEGER PRIMARY KEY,       -- recensements 1976 -> 2023
    population INTEGER NOT NULL
);
CREATE TABLE emploi (
    annee INTEGER NOT NULL,
    trimestre INTEGER NOT NULL,      -- 1..4 (ENES trimestrielle)
    taux_chomage_elargi REAL,        -- taux de chomage au sens elargi (%)
    taux_chomage_bit REAL,           -- taux au sens strict du BIT (%), si publie
    taux_activite REAL,              -- taux d'activite elargi (%), si publie
    PRIMARY KEY (annee, trimestre)
);
CREATE TABLE inflation (
    annee INTEGER PRIMARY KEY,
    taux_inflation REAL NOT NULL     -- variation annuelle moyenne de l'IHPC (%)
);
CREATE TABLE pauvrete (
    region_id INTEGER PRIMARY KEY REFERENCES regions(id),
    taux_pauvrete REAL NOT NULL,     -- incidence P0 (%, EHCVM II 2021/22)
    profondeur REAL,                 -- P1 (%)
    severite REAL,                   -- P2 (%)
    gini REAL,                       -- indice de Gini (0-1)
    conso_moyenne_fcfa INTEGER       -- consommation annuelle moyenne/tete (FCFA)
);
CREATE TABLE pib (
    annee INTEGER PRIMARY KEY,
    croissance_reelle REAL NOT NULL  -- croissance du PIB reel (%, comptes nationaux)
);
CREATE TABLE indicateurs_nationaux (
    code TEXT PRIMARY KEY,
    libelle TEXT NOT NULL,
    valeur REAL NOT NULL,
    unite TEXT,
    annee INTEGER,
    source TEXT
);
""")

# --- Regions (superficies usuelles ANSD/SES) --------------------------------
regions = [
    (1, "Dakar", "Dakar", 547), (2, "Thies", "Thies", 6670),
    (3, "Diourbel", "Diourbel", 4824), (4, "Saint-Louis", "Saint-Louis", 19034),
    (5, "Ziguinchor", "Ziguinchor", 7352), (6, "Kaolack", "Kaolack", 5357),
    (7, "Fatick", "Fatick", 6849), (8, "Kolda", "Kolda", 13771),
    (9, "Louga", "Louga", 24847), (10, "Matam", "Matam", 29445),
    (11, "Tambacounda", "Tambacounda", 42364), (12, "Kedougou", "Kedougou", 16800),
    (13, "Kaffrine", "Kaffrine", 11262), (14, "Sedhiou", "Sedhiou", 7341),
]
cur.executemany("INSERT INTO regions VALUES (?,?,?,?)", regions)

# --- Population par region : recensements officiels -------------------------
# RGPH-4 2013 et RGPH-5 2023 (resultats definitifs ; les deux sommes regionales
# egalent exactement les totaux nationaux officiels).
pop = {
    #        nom            2013       2023
    1:  ("Dakar",        3137196, 4004427),
    2:  ("Thies",        1788864, 2463678),
    3:  ("Diourbel",     1497456, 2080335),
    4:  ("Saint-Louis",   908942, 1202442),
    5:  ("Ziguinchor",    549151,  617568),
    6:  ("Kaolack",       960875, 1336719),
    7:  ("Fatick",        714392,  906918),
    8:  ("Kolda",         662455,  914798),
    9:  ("Louga",         874193, 1125908),
    10: ("Matam",         562538,  831629),
    11: ("Tambacounda",   681310,  987151),
    12: ("Kedougou",      151357,  245146),
    13: ("Kaffrine",      566992,  820405),
    14: ("Sedhiou",       452994,  589266),
}
for rid, (_, p13, p23) in pop.items():
    cur.execute("INSERT INTO demographie(region_id,annee,population) VALUES (?,?,?)", (rid, 2013, p13))
    cur.execute("INSERT INTO demographie(region_id,annee,population) VALUES (?,?,?)", (rid, 2023, p23))

assert sum(v[1] for v in pop.values()) == 13508715, "somme 2013 != total officiel RGPH-4"
assert sum(v[2] for v in pop.values()) == 18126390, "somme 2023 != total officiel RGPH-5"

# --- Population nationale aux recensements (RGPH 1976 -> 2023) --------------
cur.executemany("INSERT INTO population_nationale VALUES (?,?)", [
    (1976, 4958085), (1988, 6881919), (2002, 9858482),
    (2013, 13508715), (2023, 18126390),
])

# --- Emploi : ENES trimestrielles (taux de chomage elargi, %) ----------------
# Notes d'information ANSD ; NULL quand la valeur n'est pas publiee.
cur.executemany("INSERT INTO emploi VALUES (?,?,?,?,?)", [
    (2023, 1, 21.5, None, None),
    (2023, 2, 18.6, None, None),
    (2023, 3, 19.5, None, None),
    (2023, 4, 22.3, None, None),
    (2024, 1, 23.2, None, None),
    (2024, 2, 21.6, None, 57.6),
    (2024, 3, 20.3, None, 58.3),
    (2024, 4, 20.0, None, None),
    (2025, 1, 21.7, 4.9, None),
])

# --- Inflation : IHPC, variation annuelle moyenne (%) ------------------------
cur.executemany("INSERT INTO inflation VALUES (?,?)", [
    (2019, 1.0), (2020, 2.5), (2021, 2.2), (2022, 9.7), (2023, 5.9), (2024, 0.8),
])

# --- Pauvrete : EHCVM II 2021/2022, tableau III-2 du rapport final -----------
#      region_id, P0,   P1,   P2,  Gini,  conso moyenne/tete (FCFA/an)
cur.executemany("INSERT INTO pauvrete VALUES (?,?,?,?,?,?)", [
    (1,  9.3,  1.1,  0.3, 0.328, 861364),   # Dakar
    (2, 29.9,  8.3,  3.5, 0.289, 540343),   # Thies
    (3, 37.4,  9.0,  3.2, 0.244, 464236),   # Diourbel
    (4, 37.3,  9.8,  3.6, 0.286, 498177),   # Saint-Louis
    (5, 48.3, 11.0,  3.8, 0.255, 437354),   # Ziguinchor
    (6, 49.6, 13.7,  5.3, 0.291, 442489),   # Kaolack
    (7, 46.5, 11.9,  4.2, 0.265, 433634),   # Fatick
    (8, 62.5, 19.1,  7.9, 0.293, 387934),   # Kolda
    (9, 47.0, 12.4,  4.5, 0.271, 444651),   # Louga
    (10, 44.7, 12.9, 5.2, 0.267, 439221),   # Matam
    (11, 62.8, 21.6, 9.5, 0.293, 363543),   # Tambacounda
    (12, 65.7, 25.4, 12.9, 0.342, 359121),  # Kedougou
    (13, 58.2, 16.3, 6.2, 0.262, 391980),   # Kaffrine
    (14, 64.4, 20.3, 8.7, 0.247, 345506),   # Sedhiou
])

# --- PIB : croissance reelle (comptes nationaux ANSD) ------------------------
cur.executemany("INSERT INTO pib VALUES (?,?)", [
    (2022, 3.8), (2023, 4.3), (2024, 6.3),
])

# --- Indicateurs nationaux de reference (RGPH-5 2023 / EHCVM II) -------------
cur.executemany("INSERT INTO indicateurs_nationaux VALUES (?,?,?,?,?,?)", [
    ("pop_totale", "Population residente totale", 18126390, "habitants", 2023, "RGPH-5"),
    ("croissance_demo", "Taux d'accroissement annuel moyen 2013-2023", 2.9, "%", 2023, "RGPH-5"),
    ("urbanisation", "Taux d'urbanisation", 54.7, "%", 2023, "RGPH-5"),
    ("densite", "Densite de population", 92, "hab/km2", 2023, "RGPH-5"),
    ("densite_dakar", "Densite de la region de Dakar", 7277, "hab/km2", 2023, "RGPH-5"),
    ("esperance_vie", "Esperance de vie a la naissance", 68.9, "ans", 2023, "RGPH-5"),
    ("esperance_vie_femmes", "Esperance de vie des femmes", 70.0, "ans", 2023, "RGPH-5"),
    ("esperance_vie_hommes", "Esperance de vie des hommes", 67.7, "ans", 2023, "RGPH-5"),
    ("isf", "Indice synthetique de fecondite", 4.2, "enfants/femme", 2023, "RGPH-5"),
    ("age_median", "Age median de la population", 19, "ans", 2023, "RGPH-5"),
    ("moins_15_ans", "Part des moins de 15 ans", 39.2, "%", 2023, "RGPH-5"),
    ("menages", "Nombre de menages ordinaires", 1991012, "menages", 2023, "RGPH-5"),
    ("taille_menage", "Taille moyenne des menages ordinaires", 9, "personnes", 2023, "RGPH-5"),
    ("tbs_primaire", "Taux brut de scolarisation au primaire", 81.0, "%", 2023, "RGPH-5"),
    ("electricite", "Menages utilisant l'electricite pour l'eclairage", 74.4, "%", 2023, "RGPH-5"),
    ("eau_robinet", "Menages disposant d'un robinet dans le logement", 69.9, "%", 2023, "RGPH-5"),
    ("handicap", "Taux de prevalence du handicap", 7.3, "%", 2023, "RGPH-5"),
    ("menages_agricoles", "Part des menages agricoles", 44.5, "%", 2023, "RGPH-5"),
    ("proprietaires", "Menages proprietaires de leur logement", 67.4, "%", 2023, "RGPH-5"),
    ("pauvrete_nationale", "Incidence de la pauvrete monetaire", 37.5, "%", 2022, "EHCVM II 2021/22"),
    ("pauvrete_2018", "Incidence de la pauvrete monetaire (edition precedente)", 37.8, "%", 2019, "EHCVM I 2018/19"),
    ("pauvrete_extreme", "Incidence de l'extreme pauvrete", 5.6, "%", 2022, "EHCVM II 2021/22"),
    ("pauvrete_rurale", "Incidence de la pauvrete en milieu rural", 53.3, "%", 2022, "EHCVM II 2021/22"),
    ("pauvrete_urbaine", "Incidence de la pauvrete en milieu urbain", 20.0, "%", 2022, "EHCVM II 2021/22"),
    ("gini_national", "Indice de Gini national", 0.334, "indice", 2022, "EHCVM II 2021/22"),
    ("insecurite_alim", "Prevalence de l'insecurite alimentaire moderee ou severe", 29.9, "%", 2022, "EHCVM II 2021/22"),
])

con.commit()
tot = cur.execute("SELECT population FROM population_nationale WHERE annee=2023").fetchone()[0]
n_ind = cur.execute("SELECT COUNT(*) FROM indicateurs_nationaux").fetchone()[0]
print(f"Base creee : {DB}")
print(f"  Population RGPH-5 2023 = {tot:,} (officiel)  |  {n_ind} indicateurs nationaux")
con.close()
