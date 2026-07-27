# Note de méthode — exploiter un patrimoine statistique hétérogène, à moindre coût et de façon référencée

> Document de travail, destiné à être intégré au mémoire. Objet : transformer l'abondance
> et la dispersion des données de l'ANSD, non en obstacle, mais en **contribution
> scientifique** — la conception d'une méthode d'acquisition et d'exploitation *exhaustive,
> référencée et peu coûteuse* d'un patrimoine statistique multi-formats, pour un assistant
> conversationnel déployable sans GPU.

---

## En bref — la thèse

Le patrimoine statistique de l'ANSD et du Système Statistique National (SSN) est **abondant**
et **dispersé** sur des supports hétérogènes : plateformes interrogeables avec interface de
programmation (Open Data / Knoema, archive ANADS, répertoire des localités), rapports et
notes en PDF (dont la *Situation Économique et Sociale* nationale et régionale, publiée
depuis 2005 et couvrant presque tous les secteurs), pages web institutionnelles, et portails
de producteurs partenaires (DAPSA pour l'agriculture, ANAT pour le territoire, BCEAO pour la
monnaie et la finance).

Cette abondance est notre **matière première**. La question de recherche devient : *quelle
est la méthode la plus efficace et la moins coûteuse pour rendre l'ensemble de ce patrimoine
exploitable, de façon référencée (chaque fait traçable à sa source officielle), dans un
assistant conversationnel sans matériel spécialisé ?* Y répondre rigoureusement est une
contribution à part entière — c'est le cœur de cette note.

---

## 1. Le principe directeur : le traitement le moins coûteux qui suffit

Le runtime de RAMA suit déjà une règle : *emprunter d'abord le chemin le plus sûr et le
moins coûteux*. On l'**étend à l'acquisition**. Face à une source, on choisit la technique
d'ingestion **minimale qui satisfait le besoin** — jamais la plus riche par principe :

- une **interface de programmation** vaut mieux qu'un extracteur de page ;
- un **extracteur déterministe** vaut mieux qu'une saisie manuelle ;
- on ne **structure finement** que ce qui est réellement interrogé (*curation pilotée par la
  demande*), le reste restant **atteignable par référence** plutôt qu'ingéré aveuglément.

C'est l'optimum de Pareto de l'exploitation : **couverture maximale, coût minimal, tout
référencé**. Ingérer tout le patrimoine dans un grand index vectoriel, ou bâtir un entrepôt
SQL exhaustif de toutes les publications, aurait un coût (calcul, maintenance, matériel)
disproportionné au regard de ce qui est effectivement demandé — et introduirait de
l'opacité et un risque d'erreur sur les chiffres, inacceptables pour un service public.

---

## 2. La garantie de complétude : trois dispositions exhaustives (« rien n'est perdu »)

Comment garantir qu'*aucune* information ANSD n'est laissée de côté sans tout ingérer ? En
observant que toute information tombe dans **exactement une** des trois dispositions
suivantes — partition **totale et sans recouvrement** :

1. **Ingérée** — structurée dans l'entrepôt curaté (chiffres) ou le corpus documentaire
   (explications) : pour le cœur à forte demande.
2. **Connectée** — servie en direct par une interface de programmation (Open Data, ANADS) :
   pour la fraîcheur et la largeur, sans copie.
3. **Référencée** — pointée par un lien vérifié ou une fiche de catalogue : pour la longue
   traîne, l'assistant y mène en un clic, avec sa provenance.

La conséquence est forte : une question dont la donnée n'est ni ingérée ni connectée reçoit
**toujours** au moins la **référence officielle exacte** — jamais un vide, jamais une
invention. La complétude n'est pas une promesse quantitative (« nous avons tout copié »)
mais une propriété **structurelle** de la méthode : les trois dispositions couvrent
l'ensemble, et les garanties P1 (chiffres ancrés), P2 (liens vérifiés) et P3 (refus sûr)
valent sur chacune.

---

## 3. La chaîne d'acquisition en cinq tiers de coût croissant

Chaque source est d'abord **classée** selon quatre critères — structure, mode d'accès,
volatilité, licence — puis routée vers le tier d'ingestion le moins coûteux qui suffit.

![La chaîne d'acquisition référencée : classification des sources, cinq tiers d'ingestion du moins coûteux au plus coûteux, couche d'ancrage unifiée à provenance préservée, alimentant le runtime.](figures/chaine_acquisition.png)

| Tier | Nature de la source | Exemples ANSD / SSN | Technique d'ingestion | Coût | Alimente |
|---|---|---|---|---|---|
| **T1** | Flux structuré / interface de programmation | Open Data (Knoema, JSON/CSV), catalogue ANADS, répertoire des localités | Adaptateur direct (port `SourceStatistique`) ou moisson d'interface | très faible | entrepôt · index catalogue |
| **T2** | Tables dans des documents | *Situation Économique et Sociale*, Annuaire, tableaux de rapports | Extraction de tables déterministe → assertions de cohérence | faible | entrepôt curaté |
| **T3** | Documents narratifs | notes de méthodologie, notes de presse, pages web ansd.sn, portails partenaires | Extraction de texte + segmentation + index lexical (TF-IDF, sans GPU) | faible | corpus RAG |
| **T4** | Catalogue / métadonnées | 285+ opérations de l'archive ANADS, opérations du SSN | Moissonnage rejouable → index de catalogue | très faible | index catalogue |
| **T5** | Références / portails | pages officielles, DAPSA, ANAT, BCEAO, Open Data | Registre de liens vérifiés (contrôle HTTP 200) | quasi nul | registre R |

Chaque tier **conserve la provenance** (URL du jeu de données, document et section, date de
vérification). La couche d'ancrage qui en résulte — entrepôt curaté accessible par le port,
corpus RAG, index de catalogue, registre de liens — est donc **unifiée par la provenance** :
peu importe le tier d'origine, chaque fait exposé à l'usager sait d'où il vient.

---

## 4. Justification scientifique : pourquoi cette méthode, et pas une autre

| Méthode envisagée | Pourquoi écartée |
|---|---|
| **Tout-vectoriel** (embeddings massifs de tout le patrimoine + extraction par LLM) | Coût de calcul et matériel (GPU) disproportionné ; opacité de la récupération ; risque d'hallucination sur les chiffres ; obsolescence dès qu'une source change. Inadapté à un office public exigeant déterminisme et vérifiabilité. |
| **Entrepôt SQL exhaustif unique** (structurer *toutes* les publications) | Un tel entrepôt n'existe pas côté ANSD, et le bâtir intégralement serait très coûteux alors que l'essentiel ne serait jamais interrogé — rendement fortement décroissant. |
| **Scraping massif de tout le web ANSD et partenaires** | Fragile (structure des pages changeante), coûteux à maintenir, sans garantie de fraîcheur ni de respect des licences. À réserver à un ciblage précis. |
| **Méthode retenue : acquisition en tiers, pilotée par la demande, à provenance préservée** | Le moins coûteux qui suffit à chaque source ; couverture totale par la partition ingéré / connecté / référencé ; déterministe, sans GPU, rejouable, auditable. C'est la transposition à l'acquisition du principe runtime « chemin le plus sûr au moindre coût ». |

Le point décisif face à un jury : la valeur n'est pas d'avoir « tout aspiré », mais d'avoir
conçu une méthode qui **maximise l'exploitation référencée à coût minimal** et **prouve sa
complétude par construction** (la partition en trois dispositions), là où les approches
naïves paient cher une couverture qu'elles ne garantissent même pas.

---

## 5. Plan d'application au mémoire (couvrir le sujet sans faille)

1. **Chapitre 1 (problématique).** Élever l'abondance-dispersion au rang d'**atout** :
   reformuler le problème comme « exploiter un patrimoine riche et hétérogène de façon
   référencée à moindre coût », et l'ajouter à la liste des contributions.
2. **Nouvelle section (chapitre 3 ou 4) — « La chaîne d'acquisition ».** Insérer §1 à §4 de
   cette note : principe du moindre coût, partition de complétude, tableau des cinq tiers,
   figure `chaine_acquisition.png`, tableau de justification des alternatives écartées.
3. **Cohérence transversale.** Relier au port `SourceStatistique` (T1), aux garanties P1/P2
   (provenance de bout en bout), au principe runtime (même règle de coût).
4. **`JUSTIFICATIONS.md`.** Ajouter la décision : méthode d'acquisition en tiers, pilotée
   par la demande, à complétude structurelle.
5. **Résumé, deck, note données.** Répercuter la reformulation « abondance = atout » et la
   figure d'acquisition.
6. **Rebuild** de tous les livrables (HTML/DOCX, résumé, deck), vérification visuelle.

---

## 6. Sources (vérifiées, juillet 2026)

- *Situation Économique et Sociale* (SES nationales, série depuis 2005) :
  <https://www.ansd.sn/rapports-donnees/themes/situation-economiques-et-sociales/ses-nationales>
- Toutes les publications de l'ANSD : <https://www.ansd.sn/toutes-les-publications>
- Plateforme Open Data (Knoema) : <https://senegal.opendataforafrica.org/> ;
  série agricole DAPSA hébergée sur l'ODP : <https://senegal.opendataforafrica.org/lqhbmne>
- Archive ANADS (NADA) : <https://anads.ansd.sn/>
- DAPSA (producteur agricole du SSN) : <https://www.dapsa.gouv.sn/>
- Toutes les bases de données ANSD : <https://www.ansd.sn/bases-de-donnees>
