# Les données de RAMA — réponses claires et vérifiables

> Ce document répond à trois questions : possède-t-on réellement les 285 documents de l'archive ANADS ?
> Comment, pourquoi et où la base de données a-t-elle été construite ? Et à quoi ressemblent ces données ?
> Chaque affirmation est vérifiable dans le dépôt du projet (chemins indiqués).

---

## Question 1 — A-t-on réellement les 285 documents ?

**Réponse honnête : nous avons les 285 *fiches* complètes, pas les 285 *fichiers*.** La distinction est importante et assumée.

Ce que le système possède, c'est le **catalogue** : pour chacune des 285 opérations statistiques de l'archive ANADS, une fiche avec le titre exact, les années, le producteur, la collection, le nombre de variables et — surtout — **l'adresse officielle de la fiche en ligne**. Exemple réel, tel qu'il est stocké :

```json
{ "idno": "MMS-RSPCT-RSHS-2007-2008",
  "titre": "RuralStruc Household Survey (2007-2008)",
  "producteur": "RuralStruc Program Coordination Team",
  "annee_debut": "2007", "annee_fin": "2009",
  "collection": "Agriculture", "nb_variables": "171",
  "url": "https://anads.ansd.sn/index.php/catalog/181" }
```

**Comment ?** Par un script de moissonnage rejouable, `backend/scripts/harvest_anads.py`, qui interroge l'**API publique** de l'archive (le logiciel NADA qui équipe anads.ansd.sn expose son catalogue en JSON), page par page, jusqu'à couvrir les 285 opérations.

**Où ?** Dans `backend/data/anads_catalogue.json` (le fichier local, rechargeable à volonté) — et les documents eux-mêmes restent **là où ils doivent être : sur l'archive officielle**, à l'adresse portée par chaque fiche.

**Pourquoi ce choix ?** Les microdonnées, questionnaires et rapports de l'ANADS sont soumis à des **conditions d'accès et de licence** : les télécharger et les redistribuer ne serait ni légal ni souhaitable. Le rôle du système est de conduire l'usager, en un clic, jusqu'à la fiche officielle qui donne accès à tous les formats — c'est exactement la garantie P2 : tout lien pointe vers la source, jamais vers une copie.

---

## Question 2 — La base de données : comment, pourquoi, où ?

**Où ?** Un seul fichier : `backend/data/ansd_stats.db` — une base **SQLite** de huit tables (environ 105 lignes de données au total), ouverte **en lecture seule** par l'application.

**Pourquoi ?** L'ANSD *diffuse* bien des données interrogeables — une Plateforme Open Data (formats ouverts JSON/CSV, avec une interface de programmation), un répertoire des localités, des portails sectoriels, l'API de catalogue ANADS. Mais ces sources sont **réparties**, et les chiffres les plus demandés — résultats définitifs du RGPH-5 2023, de l'EHCVM II 2021/22 — paraissent d'abord dans des **rapports**. Notre base est donc un **entrepôt curaté** : les chiffres publiés sont extraits une fois et structurés en tables, chaque valeur portant sa source. Ce choix répond à la garantie P1 (tout chiffre d'une réponse doit venir, mot pour mot et avec sa provenance, d'une source structurée), à la couverture des chiffres phares, et à l'exigence de déterminisme (réponse en millisecondes, hors ligne). Surtout, la voie n'est **pas couplée à ce fichier** : elle passe par un contrat (une source statistique interrogeable) — brancher la Plateforme Open Data de l'ANSD revient à ajouter un adaptateur, sans rien changer d'autre.

**Comment ?** Par un script unique et rejouable de deux cents lignes, `backend/scripts/seed_db.py`, qui applique trois règles vérifiables :

1. **Chaque valeur porte sa source.** L'en-tête du script liste les documents officiels utilisés, avec leurs adresses : RGPH-5 2023 (résultats définitifs, juillet 2024), rapport final EHCVM II 2021/22 (tableau III-2), notes trimestrielles ENES, notes annuelles IHPC, comptes nationaux.
2. **Une valeur non publiée reste vide.** Jamais estimée, jamais interpolée — c'est le Principe 2 de la statistique officielle (ONU, 2014). On le voit dans la table `emploi` : les trimestres où le taux BIT n'a pas été publié contiennent `NULL`.
3. **La construction échoue si un total ne correspond pas au chiffre publié.** Ce sont les assertions, telles quelles dans le script :

```python
assert sum(v[1] for v in pop.values()) == 13508715, "somme 2013 != total officiel RGPH-4"
assert sum(v[2] for v in pop.values()) == 18126390, "somme 2023 != total officiel RGPH-5"
```

Autrement dit : si une seule population régionale était fausse, la base **refuserait de se construire**. La reconstruire entièrement prend une seconde : `python scripts/seed_db.py`.

Le schéma complet — les huit tables, leurs colonnes, leurs effectifs, leurs clés et la source de chacune — ainsi que l'arborescence des fichiers de données :

![Schéma relationnel réel de la base et fichiers de données du projet.](figures/schema_bd.png)

---

## Représentation 1 — Les données elles-mêmes

La figure suivante est produite par un script qui **lit la base au moment du rendu** : aucune valeur n'y est saisie à la main. On y voit les quatre indicateurs nationaux de référence, la population des quatorze régions aux deux derniers recensements (table `demographie`), et l'incidence de la pauvreté par région comparée au niveau national (table `pauvrete`).

![Les données réelles de ansd_stats.db : indicateurs nationaux, population régionale aux deux recensements, pauvreté régionale contre le repère national de 37,5 %.](figures/donnees_viz.png)

Trois lectures immédiates : Dakar concentre 4 004 427 habitants en 2023 (contre 3 137 196 en 2013) ; toutes les régions ont crû entre les deux recensements ; la pauvreté dessine un gradient net, de 9,3 % à Dakar à 65,7 % à Kédougou, de part et d'autre du repère national de 37,5 %.

---

## Représentation 2 — Ces données dans le fonctionnement du système

Où ces données interviennent-elles quand une question arrive ? Le pipeline ci-dessous montre le chemin d'une question ; chaque voie de sortie puise dans une source précise :

![Le pipeline de traitement : neuf étapes ordonnées du traitement le moins coûteux et le plus sûr vers le plus coûteux, avec sorties anticipées.](figures/pipeline_h.png)

- La voie **SQL** interroge `ansd_stats.db` (lecture seule) : c'est elle qui répond « 18 126 390 habitants » — le chiffre sort de la table, jamais du modèle de langage.
- La voie **RAG** puise dans les 25 documents du corpus (`backend/data/documents/`) pour rédiger une explication sourcée.
- La voie **CATALOG** interroge les 285 fiches de `anads_catalogue.json` : « je veux les données sur la pêche » reçoit la liste des fiches pertinentes, en liens officiels directs.
- Les liens de toute réponse proviennent exclusivement de `resources.json` (31 adresses vérifiées HTTP 200) et du catalogue — le modèle de langage n'a aucun moyen d'écrire une adresse lui-même.

La boucle est ainsi fermée : des publications officielles aux tables, des tables aux réponses, et de chaque réponse un lien qui ramène à la source officielle.

---

*Vérification par vous-même : `python scripts/seed_db.py` (reconstruit la base avec assertions) · `python scripts/harvest_anads.py` (re-moissonne le catalogue) · les chemins cités sont relatifs à `ansd-chatbot/backend/`.*
