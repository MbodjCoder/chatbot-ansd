# Résumé du mémoire — RAMA

> Ce document condense l'intégralité du mémoire pour une relecture rapide avant la soutenance.
> Chaque section suit le chapitre correspondant ; les chiffres sont ceux du document complet.
> Temps de lecture : 20 à 25 minutes.

---

## L'essentiel en dix points

1. **Le problème** : l'information statistique de l'ANSD est riche mais dispersée (rapports PDF, portails, fiches) — trouver un chiffre exige de connaître l'organisation du système statistique.
2. **Le verrou** : un modèle de langage seul répond avec fluidité mais peut inventer — l'*hallucination* — ce qui est inacceptable pour un service public d'information.
3. **La question centrale** : rendre les statistiques accessibles en langage naturel **tout en garantissant, de façon vérifiable**, que chaque chiffre et chaque lien provient d'une source officielle.
4. **La réponse** : une architecture **hybride routée** — un routeur dirige chaque question vers la voie adaptée (SQL pour un chiffre, RAG pour une explication, HYBRID pour les deux).
5. **Le cœur** : trois garanties tenues **par construction** — P1 (tout nombre vient des preuves), P2 (toute URL vient des sources vérifiées), P3 (refus sûr avant tout appel au modèle).
6. **Le principe directeur** : le modèle de langage comprend, reformule, rédige — **il ne produit jamais un fait** ; les chiffres sont copiés depuis la base, les liens injectés après génération.
7. **Les données** : base SQLite construite par script rejouable avec assertions sur les totaux officiels ; corpus de 25 documents ; catalogue de 285 fiches moissonné par API publique.
8. **Les résultats** : routeur 0,857 d'exactitude (F1 macro 0,805, n = 328, p ≈ 10⁻⁷⁵) ; jeu gold 24/24 ; sécurité 4/4 ; SQL 15/15 ; médiane 5 ms hors ligne ; zéro hallucination observée.
9. **La robustesse** : le service survit à la panne du fournisseur d'IA — les garanties ne dépendent d'aucun appel au modèle.
10. **L'honnêteté scientifique** : hypothèses *corroborées sur le périmètre évalué*, non prouvées en général ; limites et menaces à la validité explicitées.

---

## Chapitre 1 — Introduction : le problème et la démarche

**Contexte.** L'ANSD produit recensements (RGPH), enquêtes ménages (EHCVM), emploi (ENES), prix (IHPC), comptes nationaux, et gère une archive de 285 opérations statistiques (ANADS). Cette production est dispersée sur plusieurs supports et portails.

**Problématique.** La charge de la découverte repose sur l'usager. La solution naturelle — un assistant en langage naturel — se heurte au verrou de l'hallucination : un assistant public qui invente désinforme sous l'apparence de l'officiel.

**Question centrale.** Comment rendre les statistiques accessibles en langage naturel tout en garantissant, de manière vérifiable, l'origine officielle de chaque chiffre et de chaque lien ?

**Trois questions de recherche, trois hypothèses réfutables :**

| # | Hypothèse | Critère de réfutation |
|---|-----------|----------------------|
| H1 | Le routage vers des voies spécialisées réduit l'erreur factuelle | Le routeur ne fait pas mieux que le hasard |
| H2 | L'ancrage structurel maintient l'hallucination à zéro | Un seul chiffre ou lien hors des sources |
| H3 | Des composants légers et déterministes suffisent | Une panne du fournisseur d'IA rend le service indisponible |

**Contributions** : (a) l'architecture hybride routée avec garanties par construction ; (b) sa réalisation complète et déployable sans GPU ; (c) un protocole d'évaluation indépendant et rejouable ; (d) une traçabilité de 90 décisions techniques argumentées.

*Pour construire cela, il faut d'abord choisir ses outils : c'est l'objet du chapitre 2 — le chapitre à connaître le mieux.*

---

## Chapitre 2 — État de l'art : chaque méthode définie, comparée, choisie

Le chapitre suit toujours le même mouvement, et c'est ce qui fait sa force : **expliquer la méthode simplement, la comparer à ses alternatives, puis dire ce qu'elle vaut dans notre contexte** — un office statistique national, un corpus modeste, des serveurs sans GPU, une exigence de fiabilité absolue sur les faits.

### 2.1 — Pourquoi un assistant : publier ne suffit pas

Les principes des Nations Unies [Nations Unies, 2014] font de l'accessibilité une **obligation** de la statistique officielle. Or Janssen et ses co-auteurs [Janssen et al., 2012] ont montré que « mettre les données en ligne pour qu'elles soient utilisées » est un **mythe** : l'usage réel dépend de la facilité à découvrir la bonne ressource et d'une *médiation* entre producteur et public. Un assistant conversationnel est exactement cette médiation : il ne remplace pas les sources, il en abaisse le coût d'accès — avec une contrainte déontologique héritée : ne jamais déformer, ne jamais glisser vers l'interprétation politique (on la retrouvera dans les garde-fous).

### 2.2 — Trois idées de la recherche sur le dialogue

- **L'acte social** [Stolcke et al., 2000] : « bonjour » ou « merci » n'est pas une demande d'information ; il appelle une réponse sociale, détectable de façon fiable → règle : le traiter à part, *avant* toute mécanique de recherche.
- **La maxime de qualité de Grice** [Grice, 1975] : ne pas affirmer ce dont on manque de preuve. L'hallucination est précisément une violation de cette maxime — un assistant qui invente n'est pas seulement dangereux, *il converse mal*.
- **L'initiative mixte** [Horvitz, 1999] : une bonne interface ne se contente pas de répondre, elle **propose** (suggestions après chaque réponse). Et pour les suivis (« et en 2013 ? ») : la réécriture de question conversationnelle [Vakulenko et al., 2021], implémentée simplement par substitution d'entités dans la dernière question complète.

### 2.3 — Le LLM : force, défaut, et trois conséquences

Programme entraîné sur d'immenses corpus à prédire la suite la plus probable d'un texte (la technologie de ChatGPT). Force : la fluidité. Défaut : l'**hallucination**. Trois résultats orientent la conception :
1. Le remède principal est l'**ancrage** [Ji et al., 2023] : fournir les documents pertinents et exiger de s'y tenir.
2. Les modèles exploitent mal le milieu des longs contextes [Liu et al., 2023] → mieux vaut **peu de passages bien choisis** qu'une inondation de documents.
3. L'ancrage réduit l'hallucination mais **ne l'élimine pas** → un contrôle extérieur à la génération reste nécessaire — et pour les chiffres, *ne jamais laisser le modèle les écrire lui-même*. C'est le choix le plus structurant du mémoire.

### 2.4 — Retrouver un document : lexical contre dense

**TF-IDF** [Salton et al., 1975] : le poids d'un mot = sa fréquence dans le document × sa rareté dans la **collection** — la collection étant l'ensemble des documents où l'on cherche, ici les fiches de l'archive ANADS. *Exemple* : dans « je cherche les données sur la pêche au Sénégal », « pêche » est rare → il pèse lourd et désigne les bonnes fiches ; « Sénégal » est partout → poids vers zéro. Formule : w(t,d) = tf(t,d) × log(N/df(t)). BM25 [Robertson & Zaragoza, 2009] en est le raffinement standard.

**Recherche dense** [DPR, Karpukhin et al., 2020 ; Sentence-BERT, Reimers & Gurevych, 2019] : un réseau de neurones convertit textes en vecteurs proches quand les sens sont proches — retrouve « mortalité des enfants » depuis « décès infantile ».

| Critère | Lexicale (TF-IDF, BM25) | Dense (DPR, SBERT) |
|---|---|---|
| Capte les synonymes | Non (sauf enrichissement) | **Oui** |
| Matériel requis | **Processeur ordinaire** | GPU souhaitable |
| Explicable | **Oui** (poids inspectables) | Difficilement |
| Latence | **Milliseconde** | Dizaines de ms à s |
| Petit corpus spécialisé | **Bonne** (vocabulaire stable) | Bonne, sans avantage net |

**Choix : TF-IDF.** Corpus petit (~25 documents, 285 fiches), vocabulaire institutionnel stable, pas de GPU : l'avantage sémantique du dense ne compense ni son coût ni son opacité. Faiblesse sur les synonymes compensée par un **enrichissement thématique manuel** (« pêche » étend vers « halieutique », « aquaculture ») et des mots vides du domaine. Dense = évolution naturelle si le corpus décuple.

### 2.5 — Le RAG : expliquer honnêtement

**Définition** [Lewis et al., 2020] : deux temps — un *récupérateur* cherche les passages pertinents, puis le *générateur* rédige en s'appuyant sur eux, cités comme sources. Le modèle ne répond plus « de mémoire » : il répond « **documents en main** ». Variantes [Gao et al., 2023] : **Self-RAG** [Asai et al., 2023] apprend au modèle à critiquer ses réponses — mais exige un réentraînement ; **CRAG** [Yan et al., 2024] filtre la qualité des passages avant génération — simple, sans apprentissage.

**Choix : RAG pour les explications, avec l'idée de CRAG** (filtrage de pertinence avant génération) — Self-RAG est hors de portée et hors de propos pour notre taille de corpus. Et surtout : **on ne demande jamais au RAG de produire un chiffre** — c'est le rôle d'une autre voie. Les passages sont conservés comme *preuves* pour le contrôle de sortie.

### 2.6 — Le Text-to-SQL : le chiffre exact

**Définition** : une base relationnelle range l'information en tables ; SQL l'interroge ; le Text-to-SQL traduit « quelle est la population de Dakar ? » en `SELECT population FROM demographie WHERE region='Dakar'`. Intérêt décisif : le résultat est **exact par construction** puisqu'il sort de la base — toute la difficulté est dans la traduction. Historique : Seq2SQL [Zhong et al., 2017], le jeu Spider [Yu et al., 2018] (qui impose la bonne métrique, l'*exactitude d'exécution* : même résultat = requêtes équivalentes), DIN-SQL [Pourreza & Rafiei, 2023] pour la génération guidée par LLM.

**L'alternative : les gabarits** — des requêtes à trous écrites et testées à l'avance ; « population de {région} en {année} » couvre « population de Dakar en 2023 ? » comme « combien d'habitants à Thiès en 2013 ? ».

| Critère | Gabarits paramétrés | Génération par LLM |
|---|---|---|
| Exactitude d'exécution | **Totale** sur les formes couvertes | Élevée, non garantie |
| Couverture | Bornée aux formes prévues | **Ouverte** |
| Latence | **Milliseconde** | Seconde(s) |
| Sécurité | **Aucune requête arbitraire** | Requête à contrôler |
| Schémas visés | **Fermés et connus** | Arbitraires (Spider) |

**Choix : gabarits d'abord.** La génération LLM répond au problème de Spider — schéma arbitraire ou inconnu. Notre situation est l'**inverse** : schéma petit, fermé, entièrement maîtrisé ; les questions usuelles se projettent sur des formes prévisibles. Les gabarits donnent tout ce que la génération promet, *plus* la garantie, la vitesse, la sécurité. La génération LLM reste en extension pour les formulations imprévues — sur une base ouverte en **lecture seule** : même une requête inattendue ne peut rien modifier.

### 2.7 — Classer l'intention : la référence avant la complexité

Décider la voie = classification de texte : « chiffre » (SQL), « explication » (RAG), « les deux » (HYBRID). L'état de l'art est DeBERTa [He et al., 2021] — mais un **principe méthodologique** commande de commencer plus bas : établir une référence simple et reproductible, puis mesurer ce que la complexité apporte.

**La régression logistique** : apprend un poids par mot et par classe (positif = plaide pour, négatif = contre) ; pour classer, elle additionne les poids et convertit en probabilités. *Exemple* : dans « combien d'habitants à Dakar ? », « combien » et « habitants » ont des poids forts pour « chiffre » — et la décision **s'explique** en montrant quels mots ont pesé. Trois vertus : entraînement en secondes sans GPU, décisions explicables, probabilités = score de confiance que l'architecture exploitera.

**La validation croisée à 5 plis** [Kohavi, 1995] : évaluer sur les données d'entraînement est trompeur — comme noter un étudiant sur les exercices appris par cœur. On découpe en cinq parts, on entraîne sur quatre, on teste sur la cinquième, en tournant : **chaque question est testée une fois par un modèle qui ne l'a jamais vue**. Version *stratifiée* : chaque part garde les proportions des classes.

**Choix : TF-IDF + régression logistique en référence, DeBERTa prévu en production.** Ce n'est pas une concession : c'est ce qui permet de chiffrer où la référence échoue — son point faible (HYBRID) est instructif, et l'architecture est précisément construite pour le couvrir (arbitrage LLM au second niveau).

### 2.8 — Les garde-fous : déterministes plutôt que génériques

Les cadres existants (NeMo Guardrails [Rebedea et al., 2023]) sont puissants mais génériques : formalisme propre, et des contrôles qui passent eux-mêmes par le modèle. **Choix : implémentation directe** par motifs et lexique du domaine, pour deux raisons — la **sûreté** (garde-fous déterministes, exécutés *avant* tout appel au modèle : impossibles à contourner en manipulant le modèle) et l'**auditabilité** (chaque règle se lit dans le code et se teste unitairement). Règles : hors-sujet, injection (« ignore tes instructions »), politique/électoral.

### 2.9 — Évaluer : trois niveaux, un principe

- *Composants* : validation croisée (routeur), exactitude d'exécution (SQL).
- *Réponses générées* : la **fidélité** de RAGAS [Es et al., 2024] — la part des affirmations soutenues par les passages ; version hors ligne restreinte mais stricte : **tout nombre de la réponse doit figurer dans les passages**.
- *Système entier* : caractéristiques ISO/IEC 25010 [2011] (adéquation, performance, fiabilité, sécurité) ; questionnaire SUS [Brooke, 1996] en perspective.

**Le principe** : le jeu de test est défini **indépendamment du système** — à partir des publications officielles, jamais des sorties observées — sinon l'évaluation est circulaire ; et le protocole doit être rejouable à l'identique par un tiers.

### 2.10 — Synthèse : pourquoi l'hybride routé

| Critère | LLM seul | RAG seul | Text-to-SQL seul | **Hybride routé (RAMA)** |
|---|---|---|---|---|
| Chiffre exact garanti | Non | Partiel | **Oui** | **Oui** (voie SQL) |
| Explication sourcée | Non | **Oui** | Non | **Oui** (voie RAG) |
| Liens jamais inventés | Non | Non | — | **Oui** (base fermée) |
| Demandes de documents | Non | Partiel | Non | **Oui** (voie catalogue) |
| Latence typique | seconde(s) | seconde(s) | **ms** | **ms**, s si LLM |
| Sans fournisseur LLM | Non | Non | **Oui** | **Oui** (repli) |

Aucune approche unique ne satisfait tout. La littérature étudie chaque brique isolément ; **la contribution est de les composer** en un système opérationnel pour un office statistique réel — avec deux exigences que la composition seule ne donne pas : des garanties tenues par l'architecture (pas par le bon comportement espéré du modèle) et une évaluation rejouable intégrée au cycle de vie.

*Le chapitre 3 opère cette composition : des exigences aux garanties.*

---

## Chapitre 3 — Conception

**Les exigences d'abord.** Tout part d'un tableau de 6 exigences fonctionnelles (répondre chiffré et sourcé, expliquer depuis le corpus, résoudre une demande de document en liens officiels, tenir une conversation, lier les études citées, suggérer sans se répéter) et 8 non fonctionnelles (zéro invention, refus des questions dangereuses, millisecondes hors LLM, service maintenu en panne, métriques consultables, déploiement sans GPU ni secret, évaluation bloquante, décisions tracées) — chacune rattachée à une caractéristique ISO/IEC 25010 et à la section du mémoire qui la **vérifie**.

![Architecture en cinq couches : interface, API, orchestrateur, voies de réponse, données d'ancrage — garanties transversales à droite.](figures/architecture.png)

**Cinq couches** : interface web → API (protection du service) → orchestrateur → voies de réponse (adossées à un client LLM interchangeable) → données d'ancrage (base SQLite lecture seule, corpus, catalogue ANADS, liens vérifiés).

**Trois principes** (traduction directe du chapitre 2) : le chemin le plus sûr et le moins coûteux d'abord ; le modèle ne touche jamais aux faits ; défense en profondeur.

![Pipeline de neuf étapes, du traitement le moins coûteux au plus coûteux, avec sorties anticipées.](figures/pipeline_h.png)

**Le pipeline (9 étapes, ordre fixe)** : acte social → normalisation conditionnelle des fautes → résolution des suivis → garde-fou d'entrée → cache → détection documentaire → routage → garde-fou de sortie → enrichissement des liens. Les sorties anticipées règlent la majorité des requêtes sans appel au modèle (« bonjour » : 1 ms). Deux subtilités à connaître : la correction des fautes ne s'active que si la question contient des mots **absents du lexique du domaine** (« kel é le to de chaumage » est corrigée, une question propre passe sans surcoût) ; et une demande documentaire (« où télécharger… ») **court-circuite le routage** — la liste exacte des fiches vaut mieux que toute génération.

**Le routeur à deux niveaux.** La question est vectorisée par TF-IDF sur deux granularités — mots (1-2) et fragments de 3 à 5 caractères, qui rendent « chômage » et « chomage » presque identiques — puis la régression logistique produit une confiance ĉ(q) par classe. Règle : si max ĉ(q) ≥ τ = 0,85, la classe est retenue ; sinon arbitrage LLM à réponse contrainte (trois noms de classe, rien d'autre). Le seuil règle un compromis — trop bas, des erreurs passent ; trop haut, on paie des appels inutiles — fixé **a priori** à 0,85 ; ce que l'expérience justifie (§5.3), c'est l'existence du second niveau, l'incertitude se concentrant sur HYBRID.

**Les six voies de réponse** : **SQL** (chiffre exact par gabarits), **RAG** (explication sourcée, filtrage CRAG), **HYBRID** (chiffre puis explication enchaînés), **CATALOG** (fiches ANADS et portails en liens directs), **NAV** (orientation vers la bonne page du site), **CHAT** (actes sociaux, sans ressource). Les voies déterministes (SQL, CATALOG, NAV, CHAT) ne dépendent pas du client LLM.

**Les cinq familles de gabarits SQL** :

| Famille | Exemple couvert |
|---|---|
| Valeur simple | « Population du Sénégal en 2023 ? » |
| Filtre régional | « Taux de pauvreté à Kolda ? » |
| Comparaison | « Compare la pauvreté entre Dakar et Kolda » |
| Classement | « La région la plus peuplée ? » |
| Série temporelle | « Évolution de l'inflation depuis 2019 » |

**Les trois garanties (le cœur du mémoire)** — notation : le système produit (a, L, E) = réponse, liens, preuves ; R = 31 liens vérifiés, C = 285 fiches :

- **P1 — ancrage des chiffres** : nombres(a) ⊆ nombres(E). Les chiffres sont *copiés* puis mis en phrase — le générateur ne calcule jamais.
- **P2 — aucune adresse inventée** : URL(a) ⊆ R ∪ C. Les liens sont injectés *après* la génération — le modèle n'a aucun canal pour émettre une URL.
- **P3 — refus sûr** : hors périmètre, injection, politique → refus *avant* tout appel au modèle.

Le **garde-fou de sortie** ajoute un contrôle **redondant** de P1 sur les voies génératives : si un nombre de la réponse manque dans les preuves, la réponse est signalée — une ceinture de sécurité *en plus* de la construction, pas le mécanisme principal.

**Modèle de menaces** (référentiels OWASP) — huit menaces, chacune avec parade doublée : injection de consigne (« ignore tes instructions ») → motifs de refus P3 ; hors-sujet (« qui va gagner la CAN ? ») → lexique du domaine ; question électorale → motifs dédiés ; injection SQL → gabarits seuls + lecture seule ; adresse inventée → liens depuis R ∪ C seulement ; saturation → limitation de débit ; fuite d'information → journaux anonymes ; fuite de secrets → aucun secret dans l'image, vérifié.

**Traçabilité** : 90 décisions au format choix–alternatives–justification–référence — l'architecture n'est pas à croire sur parole, elle s'**audite** décision par décision.

*Le chapitre 4 montre que cette conception tient debout en vrai.*

---

## Chapitre 4 — Réalisation

**Règle unique** : chaque composant est le plus simple qui satisfasse l'exigence. Python + FastAPI, scikit-learn, SQLite (mode lecture seule), page web unique sans CDN, client LLM au standard OpenAI (fournisseurs interchangeables). ~2 000 lignes de cœur, modules à responsabilité unique, 46 tests, zéro secret dans l'image Docker.

**La chaîne d'acquisition** (l'atout scientifique) : le patrimoine ANSD/SSN est abondant et dispersé (API Open Data, ANADS, SES et rapports PDF, pages web, portails partenaires DAPSA/ANAT/BCEAO). Méthode = *le traitement le moins coûteux qui suffit*, en 5 tiers (T1 flux/API → T5 registre de liens vérifiés), avec **complétude par construction** : toute information est **ingérée, connectée ou référencée** — jamais un vide ni une invention. Alimente les 4 sources d'ancrage ci-dessous.

**Les données d'ancrage** (l'ANSD *diffuse* bien des données interrogeables — Plateforme Open Data avec API JSON/CSV, répertoire des localités, portails, API ANADS — mais réparties, et les chiffres phares paraissent d'abord en PDF ; notre base est donc un **entrepôt curaté**, adossé à un port `SourceStatistique` où l'on branche la source réelle par simple adaptateur) :

- `ansd_stats.db` : 8 tables (~105 lignes), construite par `seed_db.py` — chaque valeur sourcée (RGPH-5, EHCVM II, ENES, IHPC, comptes nationaux), valeur non publiée = NULL (jamais estimée), **assertions** qui font échouer la construction si un total ≠ chiffre publié (somme des régions 2023 = 18 126 390).
- `anads_catalogue.json` : 285 fiches moissonnées par `harvest_anads.py` sur l'API publique NADA — les documents restent sur l'archive officielle (licence + P2).
- `resources.json` : 31 liens officiels vérifiés (HTTP 200).

![Les données réelles de la base : indicateurs nationaux, population régionale aux deux recensements, pauvreté régionale contre le repère national.](figures/donnees_viz.png)

**La liaison automatique des liens** — le mécanisme concret de P2 : après la génération, un composant unique apparie les noms d'études et d'indicateurs du texte contre R ∪ C et insère les liens ; c'est le **seul point d'entrée des URL** dans une réponse.

**Continuité de service** : le client LLM ne lève jamais d'erreur — bascule fournisseur de secours puis moteur local déterministe ; sémaphore sur la concurrence ; mode éclair si le fournisseur ralentit. Les garanties P1–P3 ne dépendent d'aucun appel au modèle : une panne dégrade le confort, jamais la fiabilité.

**Interface et observabilité** : page web unique sans dépendance externe ; métriques d'exploitation consultables ; journaux **anonymes** (aucune donnée personnelle) ; gestionnaire d'exceptions global (aucune trace d'erreur exposée).

**Deux traces de bout en bout** (dans le mémoire, §4.9) : une question chiffrée (voie SQL) et une question documentaire (voie CATALOG), suivies étape par étape à travers le pipeline — à relire pour pouvoir dérouler un exemple complet au tableau.

*Le système existe ; le chapitre 5 le soumet à la mesure.*

---

## Chapitre 5 — Évaluation expérimentale

**Protocole (trois instruments rejouables)** :
1. Jeu **gold** de 26 cas (24 cœur + 2 robustesse), défini à partir des publications officielles — jamais des sorties du système (pas de circularité), couvrant 11 capacités.
2. **Validation croisée** du routeur : 5 plis stratifiés, tirage fixé — chaque question testée une fois par un modèle qui ne l'a jamais vue.
3. **Test de charge** : 120 requêtes, 40 simultanées. Le harnais est branché sur l'intégration continue : toute régression bloque la livraison.

**Métriques** : précision (parmi les questions envoyées vers une classe, la part qui y appartenait), rappel (parmi les questions de la classe, la part correctement envoyée), F1 (élevé seulement si les deux le sont ; moyenne macro = même poids aux trois classes), exactitude d'exécution SQL, latence médiane et p95.

**Résultats — routeur (n = 328)** :

| Classe | Précision | Rappel | F1 |
|---|---|---|---|
| RAG | 0,914 | 0,955 | 0,934 |
| SQL | 0,815 | 0,894 | 0,852 |
| HYBRID | 0,762 | 0,533 | 0,627 |
| **Global** | **exactitude 0,857** | | **F1 macro 0,805** |

Khi-deux = 353,4 (4 ddl), p ≈ 3,2·10⁻⁷⁵ : le lien entre prédiction et vérité ne doit rien au hasard. La confusion se concentre sur HYBRID (caractère « chiffre ET explication » invisible pour une représentation par mots) — d'où l'arbitrage LLM placé sur cette zone et DeBERTa prévu en production. L'erreur résiduelle penche du côté sûr : HYBRID→SQL donne le chiffre exact sans l'explication, jamais l'inverse.

**Résultats — système complet** : gold 24/24 (exactitude fonctionnelle), sécurité 4/4, fidélité 3/3, SQL 15/15. **Latence** : ~1 ms (actes sociaux, refus), 3–5 ms (documentaire, SQL), 13 ms (RAG) ; médiane globale 5 ms hors ligne, 621 ms avec fournisseur LLM. **Charge** : 40 simultanées → 0 erreur serveur, excédent refusé proprement (code 429).

**Retour sur les hypothèses** : H1 corroborée (routage ≫ hasard, aucune question chiffrée déviée) ; H2 corroborée (zéro chiffre, zéro lien hors sources sur tout le protocole) ; H3 corroborée (millisecondes sans LLM, service maintenu sous charge et en panne). *Corroborées sur le périmètre évalué — non prouvées en général.*

*Ce que valent ces résultats, et ce qu'ils ne valent pas : chapitre 6.*

---

## Chapitre 6 — Discussion : limites et validité

**Limites assumées** : couverture SQL limitée aux gabarits (longue traîne via repli) ; rappel HYBRID 0,533 au premier niveau ; corpus ~25 documents ; français uniquement ; une seule instance.

**Menaces à la validité** : jeu gold modeste mais indépendant et non circulaire ; résultats propres à l'ANSD (architecture transférable) ; fidélité approchée par les nombres (RAGAS complet prévu en production).

**Éthique** : aucune donnée personnelle, journaux anonymes, refus des questions politiques, respect des licences (les microdonnées restent sur l'archive officielle).

---

## Chapitre 7 — Conclusion et perspectives

**Conclusion.** La contradiction entre langage naturel et rigueur statistique se résout par l'architecture : le modèle comprend, reformule, rédige — il ne produit jamais un chiffre ni un lien. Système conteneurisé, documenté, prêt au déploiement.

**Perspectives (du plus proche au plus ambitieux)** : DeBERTa sur HYBRID et calibration de τ ; RAGAS avec juge + étude SUS auprès d'usagers réels ; corpus enrichi ; anglais puis langues nationales ; multi-instances ; instanciation sur un second office statistique — le vrai test de généralité.

---

## Carte des chiffres à mémoriser

| Chiffre | Signification |
|---|---|
| **18 126 390** | Population du Sénégal, RGPH-5 2023 (l'exemple phare) |
| **0,857 / 0,805** | Exactitude / F1 macro du routeur (n = 328, CV 5 plis) |
| **p ≈ 10⁻⁷⁵** | Khi-deux : la performance ne doit rien au hasard |
| **0,533** | Rappel HYBRID au premier niveau (la limite assumée) |
| **τ = 0,85** | Seuil de confiance du routeur, fixé a priori |
| **24/24 · 4/4 · 3/3 · 15/15** | Gold · sécurité · fidélité · exécution SQL |
| **5 ms / 621 ms** | Médiane hors ligne / avec fournisseur LLM |
| **40 → 0 erreur** | Requêtes simultanées → aucune erreur serveur |
| **285 · 31 · 25** | Fiches ANADS · liens vérifiés · documents du corpus |
| **8 tables · ~105 lignes** | La base `ansd_stats.db` |
| **90 · 46 · ~2 000** | Décisions tracées · tests · lignes de cœur |

## Lexique éclair

- **Hallucination** : affirmation fluide, plausible et fausse produite par un LLM.
- **Collection** : l'ensemble des documents dans lequel une recherche s'effectue.
- **TF-IDF** : poids d'un mot = fréquence locale × rareté dans la collection.
- **RAG** : le LLM rédige uniquement à partir de passages récupérés, cités comme sources.
- **Gabarit** : requête SQL à trous, écrite et testée à l'avance.
- **Routeur** : classifieur qui envoie la question vers SQL, RAG ou HYBRID.
- **Régression logistique** : classifieur statistique simple produisant une confiance par classe.
- **Validation croisée (5 plis)** : chaque question testée par un modèle qui ne l'a jamais vue.
- **F1 macro** : moyenne des F1 par classe, même poids pour chacune.
- **Par construction** : la propriété est garantie par la structure du code, pas par le bon comportement espéré du modèle.
