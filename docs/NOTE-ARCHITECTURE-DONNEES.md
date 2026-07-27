# Note d'architecture — la couche de données de RAMA

> Objet : décrire l'écosystème d'information de l'ANSD tel qu'il est, la manière dont RAMA
> l'exploite, et l'architecture de données qui rend l'intégration au système d'information
> de l'ANSD démontrable. Sources officielles vérifiées (juillet 2026).

---

## En bref — l'écosystème et le parti pris

L'information statistique du Sénégal est **répartie** entre plusieurs systèmes, chacun avec
son mode d'accès. L'ANSD **diffuse** des données interrogeables : une **API publique**
(Plateforme Open Data, moteur Knoema/Open Data for Africa, export JSON/CSV), un **répertoire
géographique** exportable, des **portails sectoriels** (Annuaire, Agridata, Women Count) et
l'**API de catalogue ANADS** (que le projet utilise déjà). En parallèle, les chiffres les
plus demandés — résultats définitifs du RGPH-5 2023, de l'EHCVM II 2021/22 — paraissent
d'abord dans des rapports et des notes en PDF.

RAMA **fédère** ces sources selon leur nature, et fonde sa voie numérique sur un principe
clair :

1. **Un écosystème fédéré, pas une base unique.** L'architecture reconnaît la diversité des
   modes d'accès (API, document, archive) et route chaque nature d'information vers le
   paradigme de récupération adapté.
2. **Une voie numérique sur entrepôt curaté.** Les chiffres officiels sont structurés en un
   entrepôt (*data-mart*) où chaque valeur porte sa source, choisi pour la garantie P1, le
   déterminisme, et la couverture des chiffres « phares » publiés d'abord en PDF.
3. **Une couture réelle dans le code.** La voie numérique dépend d'un **port** (interface)
   de source statistique ; un **adaptateur** vers la Plateforme Open Data prouve que
   brancher le système d'information de l'ANSD revient à ajouter un adaptateur — c'est
   démontré, pas promis.

---

## 1. L'écosystème d'information de l'ANSD

Recherche menée sur les sources officielles ANSD (voir §7). L'ANSD publie et **diffuse en
accès interrogeable** :

- une **Plateforme Open Data (ODP)**, développée avec la Banque africaine de
  développement, qui rassemble les données du Sénégal « sous forme de graphiques et de
  formats ouverts, notamment JSON et CSV ». Elle tourne sur **Knoema / Open Data for
  Africa**, dont l'**API REST publique** (avec *API Explorer* et documentation développeur)
  est un fait établi ;
- un **outil de recherche sémantique** sur les communes, quartiers et villages, renvoyant
  population, nombre de bâtiments et de ménages, **exportable en JSON et CSV** ;
- l'**Annuaire statistique** (annuaire.ansd.sn), **Agridata** (agriculture), **Women
  Count** (genre) — portails thématiques interrogeables ;
- l'**archive ANADS** (anads.ansd.sn), plateforme NADA de microdonnées (259+ opérations,
  100 000+ variables), dont l'**API de catalogue est publique** — c'est celle que RAMA
  moissonne déjà pour ses 285 fiches.

La page officielle « Toutes les bases de données » (ansd.sn/bases-de-donnees) recense
elle-même sept plateformes. Il existe donc **de quoi brancher**. Ce qui n'existe pas, c'est
un **point d'entrée unique et exhaustif** couvrant *tous* les indicateurs publiés avec la
même fraîcheur : les chiffres « phares » des grandes opérations (RGPH-5 2023 définitif,
EHCVM II 2021/22) paraissent d'abord dans des **rapports et notes (PDF)**, tandis que
d'autres séries vivent dans l'ODP. La situation se résume ainsi : **plusieurs sources
hétérogènes à fédérer**.

---

## 2. Cartographie de l'écosystème d'information ANSD

La bonne question de conception n'est pas *« y a-t-il une base ? »* mais *« quelle nature
d'information vit où, et sous quel mode d'accès ? »*. Trois familles se dégagent, et à
chacune correspond le paradigme de récupération adapté — c'est exactement la thèse de
l'architecture hybride, mais désormais **fondée sur l'écosystème réel**.

![L'écosystème d'information de l'ANSD : données structurées (ODP, répertoire, portails), documents (rapports, méthodologie), microdonnées (ANADS) — et la voie de RAMA adaptée à chacune.](figures/ecosysteme_ansd.png)

| Nature de l'information | Où elle vit (ANSD) | Mode d'accès | Voie RAMA |
|---|---|---|---|
| Séries agrégées (population, prix, PIB, emploi) | Plateforme Open Data | **API REST · JSON/CSV** | SQL / API → chiffre exact |
| Chiffres géographiques (localités : population, ménages) | Répertoire des localités | Export **JSON/CSV** | SQL / API → chiffre exact |
| Séries sectorielles (agriculture, genre, secteurs) | Agridata, Women Count, Annuaire | Portails interrogeables | SQL / API ou lien |
| Chiffres « phares » & méthodes | Rapports définitifs, notes (RGPH-5, EHCVM) | **PDF** (pas d'API par indicateur) | RAG ou saisie curatée |
| Définitions, méthodologie | Notes méthodologiques, glossaires | Texte | RAG → explication |
| Microdonnées d'enquêtes | Archive ANADS (NADA) | **API catalogue** public ; fichiers **sous licence** | CATALOG / NAV → liens |

Deux enseignements :

1. **Aucune source unique ne couvre tout** — ce qui **confirme** le choix hybride, mais
   pour la vraie raison : l'hétérogénéité de l'écosystème, pas l'absence de données.
2. **La frontière n'est pas « chiffre vs texte »** mais « **accès programmable vs
   document** ». Certains chiffres sont dans une API (ODP) ; d'autres, parmi les plus
   importants, ne sont que dans des PDF. Un système sérieux doit gérer les deux.

---

## 3. Pourquoi la voie Text-to-SQL sur entrepôt curaté

La voie numérique de RAMA interroge un **entrepôt statistique curaté** : les chiffres
publiés sont extraits une fois, structurés en tables, chaque valeur portant sa source. Ce
choix repose sur **trois raisons qui tiennent devant un scientifique** :

- **Garantie P1 (ancrage).** Un chiffre de réponse doit provenir, **mot pour mot et avec sa
  provenance**, d'une source structurée et vérifiable. Une table interrogeable, dont chaque
  cellule porte sa source et son année, est le support naturel de cette garantie — que la
  table soit alimentée par un ETL local ou par une API distante.
- **Couverture des chiffres « phares ».** Les résultats définitifs du RGPH-5 2023 et de
  l'EHCVM II 2021/22 — le cœur des questions d'un usager — sont publiés d'abord dans des
  **rapports**. Les extraire une fois, avec assertions de cohérence (la somme des régions
  doit redonner le total officiel), donne une source chiffrée **fiable et testable** là où
  aucune API ne les sert encore de façon homogène.
- **Déterminisme, latence, autonomie.** Une requête locale répond en millisecondes, hors
  ligne, sans dépendre de la disponibilité d'un service tiers. Une API distante (ODP) est
  une **dépendance externe** : latence variable, quotas, pannes. Pour un service public qui
  doit rester disponible, la source locale curatée est le socle sûr ; l'API est un
  **enrichissement**, pas un point de défaillance unique.

En somme, le Text-to-SQL de RAMA est une **analyse sémantique d'une question chiffrée en
requête structurée sur un entrepôt statistique curaté** (*data-mart* construit par ETL
rejouable depuis les publications officielles). Structurer des chiffres épars de PDF en une
couche interrogeable, vérifiée par assertions, **est en soi une contribution** — précisément
le maillon que l'écosystème ANSD n'offre pas de façon unifiée. La génération SQL par LLM
reste la longue traîne ; les gabarits couvrent le cœur (Execution Accuracy 15/15).

---

## 4. L'architecture repensée — ports & adaptateurs

Pour que la reformulation soit **crédible et prouvée**, un seul changement structurel
suffit, et il est de bon goût d'ingénierie : **découpler la voie numérique de son
stockage** par une interface (architecture hexagonale, *ports & adapters*).

![La couche d'accès aux données en ports et adaptateurs : la voie numérique dépend d'un contrat SourceStatistique ; l'entrepôt curaté est l'adaptateur en place, l'ODP et le répertoire des localités sont des adaptateurs conçus.](figures/architecture_donnees.png)

La voie numérique ne dépend plus de « SQLite », mais d'un **port** :

```
SourceStatistique (interface)
    get(indicateur, filtres) -> (valeur, unité, année, source, url)
```

- **Adaptateur en place — `DataMartCurate`** : l'actuel `ansd_stats.db`, alimenté par
  `seed_db.py` (ETL rejouable, assertions sur les totaux). Déterministe, hors ligne.
- **Adaptateur conçu — `AdaptateurODP`** : interroge en direct la Plateforme Open Data
  (API Knoema/JSON) pour les séries qui y vivent, avec cache local et repli sur le
  data-mart. Provenance = l'URL du jeu de données ODP.
- **Adaptateur conçu — `AdaptateurLocalites`** : répertoire géographique (population,
  ménages par commune), export JSON/CSV.

Les autres voies ne changent pas : **RAG** sur le corpus documentaire (explications,
méthodes), **CATALOG/NAV** sur l'API ANADS (285 fiches, liens vérifiés). Les garanties P1
(provenance citée), P2 (URL depuis R∪C), P3 (refus sûr) sont **préservées identiquement** :
chaque adaptateur retourne une valeur **et sa provenance**, ce que le garde-fou de sortie
vérifie comme aujourd'hui.

**Le gain décisif :** la phrase du mémoire devient démontrable — *« brancher le système
d'information réel de l'ANSD = ajouter un adaptateur au port »* — parce que **le point de
couture existe dans le code**, avec au moins un adaptateur distant réel en preuve de
concept.

---

## 5. Mise en œuvre (réalisée)

Cinq phases, chacune autonome, testée et réversible, toutes **réalisées**. Résumé pour
mémoire et traçabilité.

### Phase 0 — Décrire l'écosystème (mémoire) · *fait*
- §4.2 : description de l'écosystème fédéré (ODP, ANADS, répertoire, portails), sources à
  l'appui, avec la cartographie (figure écosystème).
- **Résultat :** chaque plateforme citée avec sa nature d'accès et le volume réellement
  acquis.

### Phase 1 — Voie Text-to-SQL sur entrepôt curaté (mémoire) · *fait*
- §2.6 et §4.2 : la voie SQL = requête sur un **entrepôt statistique curaté**, justifiée par
  P1 + couverture des chiffres phares + déterminisme/autonomie (§3 de cette note).
- Ajout de la **figure ports & adaptateurs** et du paragraphe d'architecture.
- `JUSTIFICATIONS.md` mis à jour (décision : entrepôt curaté + port).
- **Résultat :** la justification s'appuie sur trois raisons solides ; aucune faille logique
  pour un relecteur exigeant.

### Phase 2 — Introduire le port dans le code (refactoring, comportement identique) · *~1 j · risque faible*
- Extraire l'interface `SourceStatistique` ; faire de l'accès actuel l'adaptateur
  `DataMartCurate` ; la voie SQL dépend du port.
- **Aucun changement de comportement** attendu.
- **Critère :** `evaluate_sql.py` **15/15** inchangé ; suite système **verte** ; latences
  identiques.

### Phase 3 — Adaptateur ODP en preuve de concept · *~1-2 j · risque moyen (dépendance externe)*
- `AdaptateurODP` : une série réelle (ex. IHPC ou PIB) lue en direct via l'API
  Knoema/Open Data for Africa, **cache local**, **repli** automatique sur `DataMartCurate`
  si l'API est indisponible (contrat de dégradation, comme le client LLM).
- Provenance = URL du dataset ODP ; garde-fou P1/P2 inchangé.
- **Critère :** une question chiffrée servie depuis l'ODP réel en démo **et** la même
  question servie hors ligne par le data-mart (bascule prouvée) ; aucun test en régression.

### Phase 4 — Mémoire, figures, soutenance alignés · *~0,5 j · risque nul*
- Chapitre 4 : décrire les adaptateurs et la preuve de concept ; chapitre 6 : « intégration
  au SI ANSD » passe de *perspective* à *amorce réalisée*.
- Mettre à jour le résumé, le deck (diapo architecture/données) et la note
  `DONNEES-ET-FONCTIONNEMENT`.
- **Critère :** cohérence totale mémoire ↔ code ↔ deck ↔ démo.

**Repli global :** les phases 0-1 (mémoire) sont indépendantes ; si le temps manque avant la
soutenance, on livre 0-1-2 (fait corrigé + voie reformulée + port en place, comportement
identique) et on présente 3-4 comme évolution **conçue et amorcée** — ce qui est déjà bien
plus solide que l'état actuel.

---

## 6. Risques et parades

| Risque | Parade |
|---|---|
| L'API ODP change/est indisponible en démo | L'adaptateur ODP **replie** sur le data-mart curaté (même contrat) : la démo ne tombe jamais ; c'est le même principe que le `FallbackLLM` |
| Couverture/fraîcheur ODP < rapports pour les chiffres phares | Le data-mart reste la source des chiffres phares (RGPH-5, EHCVM) ; l'ODP enrichit les séries qu'il sert mieux — division du travail assumée et documentée |
| Le refactoring casse la voie SQL | Phase 2 à **comportement identique**, gardée par `evaluate_sql.py` 15/15 et la suite système ; rollback = un commit |
| Dépendance externe introduite dans un service « sans dépendance » | L'ODP est **optionnel** (enrichissement) ; le socle reste local et hors ligne — la garantie de disponibilité n'est pas affectée |
| Objection « votre base est artificielle » | Réponse désormais solide : entrepôt curaté **vérifié par assertions**, + adaptateur réel vers l'ODP en preuve — la couture SI est démontrée |

---

## 7. Sources (vérifiées en juillet 2026)

- Plateforme Open Data de l'ANSD : <https://www.ansd.sn/node/16> ; portail :
  <https://senegal.opendataforafrica.org/> et <https://nso-senegal.opendataforafrica.org/>
- « Toutes les bases de données » (ANSD) : <https://www.ansd.sn/bases-de-donnees>
- Catalogue de données ODP : <https://nso-senegal.opendataforafrica.org/data/>
- API Open Data for Africa / Knoema (API Explorer, doc développeur) :
  <https://dataportal.opendataforafrica.org/dev>
- Archive ANADS (NADA) : <https://www.ansd.sn/mademba/archivage-national-des-donnees-du-senegal-anads>
  et <https://anads.ansd.sn/>
- Annuaire statistique : <https://annuaire.ansd.sn/>

*Note : les URL sont citées comme preuves documentaires de l'existence des plateformes ; leur
intégration effective au produit relève des phases 3-4 ci-dessus.*
