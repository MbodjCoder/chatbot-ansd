<!--
  Mémoire de Master en Informatique — RAMA
  Document source en Markdown. Export :
    HTML : pandoc MEMOIRE.md -o Memoire_RAMA.html -s --toc --toc-depth=2 --mathml \
           --embed-resources --css memoire.css --include-before-body=titlepage.html
    DOCX : pandoc MEMOIRE.md -o Memoire_RAMA.docx --toc --toc-depth=2
-->

## Résumé

Les statistiques officielles du Sénégal sont produites et publiées par l'ANSD, mais elles sont réparties entre des bases de données, des rapports PDF, une archive de microdonnées et plusieurs portails. Pour un citoyen, trouver le bon chiffre ou le bon document demande de savoir où chercher : c'est une vraie barrière d'accès. Les modèles de langage récents permettraient de poser la question en français courant, mais ils souffrent d'un défaut rédhibitoire pour la statistique publique : ils peuvent inventer des chiffres et des liens avec assurance.

Ce mémoire présente RAMA, un assistant conversationnel conçu pour lever cette contradiction. L'idée directrice est simple : le modèle de langage ne doit jamais être la source des faits. Un routeur classe chaque question et l'envoie vers la voie de traitement adaptée — requête de base de données pour un chiffre exact, recherche documentaire encadrée pour une explication, résolution directe en liens officiels pour une demande de document. Trois garanties sont imposées par l'architecture elle-même : tout chiffre provient mot pour mot d'une source officielle (P1), tout lien provient d'une base d'adresses vérifiées (P2), toute question hors sujet, malveillante ou politique est refusée avant tout traitement (P3).

Le système est évalué selon un protocole défini à l'avance et rejouable à l'identique. Sur un jeu de test indépendant de 26 cas, il atteint 24/24 en exactitude, 4/4 en sécurité, 3/3 en fidélité, avec une latence médiane de 5 ms (95ᵉ centile : 13 ms). Le routeur obtient une exactitude de 0,857 en validation croisée (n = 328) et la voie SQL 15/15 en exactitude d'exécution. Sous 40 requêtes simultanées, le service ne produit aucune erreur. Chacune des 90 décisions techniques du projet est justifiée et documentée. Le système est conteneurisé et prêt au déploiement.

**Mots-clés :** agent conversationnel, statistiques publiques, RAG, Text-to-SQL, grands modèles de langage, garde-fous, hallucination, évaluation, ANSD, Sénégal.

## Abstract

Senegal's official statistics are produced and published by ANSD, but they are scattered across databases, PDF reports, a microdata archive and several portals. Finding the right figure or document requires knowing where to look — a real access barrier. Recent language models would allow anyone to ask in plain language, but they suffer from a flaw that is unacceptable for official statistics: they can confidently invent figures and links.

This thesis presents RAMA, a conversational assistant designed to resolve this contradiction. The guiding idea is simple: the language model must never be the source of facts. A router classifies each question and sends it to the appropriate processing path — a database query for an exact figure, a controlled document search for an explanation, a direct resolution into official links for a document request. Three guarantees are enforced by the architecture itself: every figure comes verbatim from an official source (P1), every link comes from a verified address base (P2), and any off-topic, malicious or political question is refused before any processing (P3).

The system is evaluated with a protocol defined in advance and exactly replayable. On an independent 26-case test set it reaches 24/24 accuracy, 4/4 safety and 3/3 faithfulness, with a 5 ms median latency (95th percentile: 13 ms). The router reaches 0.857 accuracy under cross-validation (n = 328) and the SQL path 15/15 execution accuracy. Under 40 concurrent requests the service produces no errors. Each of the project's 90 technical decisions is justified and documented. The system is containerized and ready for deployment.

**Keywords:** conversational agent, official statistics, RAG, Text-to-SQL, large language models, guardrails, hallucination, evaluation, ANSD, Senegal.

## Remerciements

Je remercie mon encadrant, le Professeur Talibouya DIOP, pour l'exigence scientifique et la rigueur qui ont guidé ce travail ; l'Agence Nationale de la Statistique et de la Démographie, dont les données et publications constituent le socle de ce système ; ainsi que le corps enseignant de l'UFR de Sciences Appliquées et de Technologie de l'Université Gaston Berger. Je remercie enfin ma famille et mes proches pour leur soutien constant.

---

## Liste des acronymes

| Sigle | Signification |
|---|---|
| ANADS | Archive Nationale des Données du Sénégal |
| ANSD | Agence Nationale de la Statistique et de la Démographie |
| API | Interface de programmation applicative |
| CI | Intégration continue (*continuous integration*) |
| CV | Validation croisée (*cross-validation*) |
| EHCVM | Enquête Harmonisée sur les Conditions de Vie des Ménages |
| ENES | Enquête Nationale sur l'Emploi au Sénégal |
| IHPC | Indice Harmonisé des Prix à la Consommation |
| LLM | Grand modèle de langage (*Large Language Model*) |
| LRU | Éviction du moins récemment utilisé (*Least Recently Used*) |
| PWA | Application web progressive |
| RAG | Génération augmentée par la récupération |
| RGPH | Recensement Général de la Population et de l'Habitat |
| SES | Situation Économique et Sociale (du Sénégal) |
| SQL | Langage de requête structuré |
| SSE | *Server-Sent Events* (flux serveur) |
| SUS | *System Usability Scale* |
| TF-IDF | *Term Frequency – Inverse Document Frequency* |

## Liste des figures

- **Figure 1** — Le problème d'accès : dispersion des sources et médiation conversationnelle (§ 1.2).
- **Figure 2** — Fonctionnement du RAG : récupérateur, passages, générateur, réponse sourcée (§ 2.5).
- **Figure 3** — Fonctionnement de la voie Text-to-SQL par gabarits, sur un exemple complet (§ 2.6).
- **Figure 4** — La validation croisée à 5 plis (§ 2.7).
- **Figure 5** — Architecture générale de RAMA en couches, avec garanties transversales (§ 3.2).
- **Figure 6** — Pipeline de traitement d'une requête et sorties anticipées (§ 3.4).
- **Figure 7** — Routeur à deux niveaux : classifieur puis arbitrage sous seuil (§ 3.5).
- **Figure 8** — Les trois garanties de fiabilité P1–P3 : propriété, mécanisme, vérification (§ 3.6).
- **Figure 9** — Les quatre sources d'ancrage et leur provenance (§ 4.2).
- **Figure 9ter** — La chaîne d'acquisition référencée : cinq tiers d'ingestion à moindre coût (§ 4.2).
- **Figure 9bis** — L'écosystème d'information de l'ANSD : données structurées, documents, microdonnées (§ 4.2).
- **Figure 10** — Schéma relationnel de la base et arborescence des fichiers de données (§ 4.2).
- **Figure 10bis** — La couche d'accès aux données en ports et adaptateurs (§ 4.2).
- **Figure 11** — La liaison automatique des liens, sur un exemple réel (§ 4.4).
- **Figure 12** — Stratégie de dégradation gracieuse du client LLM (§ 4.5).
- **Figure 13** — Matrice de confusion du routeur (validation croisée à 5 plis) (§ 5.3).
- **Figure 14** — Latence médiane par voie de réponse, mode déterministe (§ 5.5).

## Liste des tableaux

- **Tableau 1** — Recherche lexicale et recherche dense : comparaison (§ 2.4).
- **Tableau 2** — Gabarits et génération libre pour le Text-to-SQL : comparaison (§ 2.6).
- **Tableau 3** — Les quatre architectures candidates face à nos exigences (§ 2.10).
- **Tableau 4** — Exigences fonctionnelles et non fonctionnelles (§ 3.1).
- **Tableau 5** — Les cinq familles de gabarits SQL, avec exemples (§ 3.6).
- **Tableau 6** — Menaces considérées et contre-mesures (§ 3.7).
- **Tableau 7** — Performances du routeur par classe (§ 5.3).
- **Tableau 8** — Les onze capacités du jeu de test, avec exemples et résultats (§ 5.5).
- **Tableau 9** — Résultats d'ensemble sur le jeu de test gold (§ 5.5).
- **Tableau 10** — Comportement sous charge (§ 5.6).
- **Tableau 11** — Hypothèses, observations et verdicts (§ 5.7).

---

# Chapitre 1 — Introduction

## 1.1 Contexte

La statistique publique est un bien commun. Les Nations Unies l'ont formalisé dans les *Principes fondamentaux de la statistique officielle* [Nations Unies, 2014] : pour servir le débat démocratique et la décision publique, l'information statistique doit être accessible à tous et présentée de manière impartiale. Au Sénégal, cette mission revient à l'Agence Nationale de la Statistique et de la Démographie (ANSD). Elle produit les recensements de population (RGPH), les enquêtes sur les conditions de vie des ménages (EHCVM) et sur l'emploi (ENES), l'indice des prix à la consommation (IHPC), les comptes nationaux, et elle entretient une archive nationale de microdonnées (ANADS) qui documente 285 opérations statistiques.

Cette production est riche, mais elle est éclatée. Un chiffre se trouve dans une base de données, sa méthodologie dans un rapport PDF, les données brutes dans une fiche de l'archive ANADS, et certains indicateurs sectoriels sur des portails partenaires. Chaque support a sa propre logique de consultation. Un journaliste qui cherche le taux de pauvreté d'une région, un étudiant qui veut les microdonnées d'une enquête sur la pêche, un décideur qui compare deux recensements : tous doivent d'abord comprendre comment le système statistique est organisé avant d'obtenir leur réponse. C'est une barrière d'accès réelle, qui touche précisément les publics que la statistique publique veut servir.

## 1.2 Problématique

Une piste s'impose naturellement : permettre à l'usager de poser sa question en français courant et laisser un programme se charger du reste. Les grands modèles de langage rendent cette piste techniquement crédible. Mais ils apportent avec eux un défaut connu et documenté : l'hallucination.

::: enclair
<span class="titre-enclair">En clair — le grand modèle de langage (LLM)</span>
Un grand modèle de langage est un programme entraîné sur d'immenses quantités de textes, qui apprend à prédire la suite la plus probable d'une phrase. Cette capacité suffit à comprendre une question, la reformuler, la traduire ou rédiger une réponse. C'est la technologie derrière les assistants comme ChatGPT. *Exemple* : à la question « c'est quoi le taux de chômage ? », un LLM sait produire une explication fluide — mais rien ne garantit que le chiffre qu'il y glisse soit vrai.
:::

::: enclair
<span class="titre-enclair">En clair — l'hallucination</span>
On appelle hallucination le fait, pour un modèle de langage, de produire une affirmation fluide et plausible mais fausse ou invérifiable. Le modèle ne « ment » pas : il complète un texte de la manière la plus probable, sans notion de vérité. L'étude de référence sur le sujet [Ji et al., 2023] distingue l'hallucination *intrinsèque* (la sortie contredit la source fournie) de l'hallucination *extrinsèque* (la sortie affirme quelque chose que la source ne permet pas de vérifier).
:::

Pour beaucoup d'usages, une erreur occasionnelle est tolérable. Pour la statistique officielle, elle ne l'est pas : un assistant qui annonce un faux taux de pauvreté ou invente l'adresse d'un rapport désinforme, et il le fait sous les couleurs d'une institution publique. La figure 1 résume la situation : en accès direct (A), la charge de la découverte pèse sur l'usager ; avec un assistant (B), elle est déplacée vers le système — mais ce déplacement n'est acceptable que si la fiabilité du système est démontrable, et pas seulement probable.

![**Figure 1** — Le problème d'accès aux statistiques officielles. (A) En accès direct, l'usager doit savoir quelle source consulter, quel document chercher et quelle requête formuler. (B) La médiation conversationnelle déplace cette charge vers le système, à condition que chaque chiffre soit ancré et chaque lien vérifié.](figures/probleme.png)

Le problème central du mémoire s'énonce ainsi :

> *Comment concevoir un assistant conversationnel qui rende les statistiques officielles accessibles en langage naturel, tout en garantissant — de manière vérifiable — que chaque chiffre et chaque lien provient d'une source officielle ?*

Deux exigences se font face : la souplesse du langage naturel, qui plaide pour un modèle génératif, et la rigueur de la statistique publique, qui interdit toute production non sourcée. Notre parti pris est que cette tension se résout au niveau de l'architecture : il faut confier au modèle de langage ce qu'il fait bien — comprendre une question, reformuler, expliquer — et lui retirer, par construction, la possibilité de produire des chiffres et des liens.

## 1.3 Questions de recherche

- **QR1.** Séparer les questions chiffrées, explicatives et documentaires, et les traiter par des voies spécialisées, améliore-t-il la fiabilité par rapport à une génération libre par LLM ?
- **QR2.** Peut-on garantir l'absence de chiffres et de liens inventés par des mécanismes vérifiables, sans dégrader la qualité de la conversation ?
- **QR3.** Un tel système peut-il rester rapide, robuste et déployable avec des moyens modestes — sans processeur graphique dédié — et continuer à fonctionner quand le fournisseur de LLM tombe en panne ?

## 1.4 Objectifs

L'objectif général est de concevoir, réaliser et évaluer un assistant conversationnel fiable pour l'accès aux statistiques de l'ANSD. Il se décline en cinq objectifs spécifiques :

1. mettre en place un routage des questions vers des voies de traitement spécialisées ;
2. réaliser une voie « chiffre exact » fondée sur des requêtes de base de données, et une voie « explication » ancrée dans un corpus de documents officiels ;
3. rendre accessibles, par des liens vérifiés, le catalogue ANADS et les portails officiels ;
4. concevoir des garde-fous d'entrée et de sortie, et les formuler comme des propriétés que l'on peut tester ;
5. définir un protocole d'évaluation rejouable et mesurer la qualité, la sécurité et la performance.

Le périmètre est délimité d'emblée. Le système couvre les données que l'ANSD a publiées, en français, et s'interdit toute estimation et toute interprétation : une valeur non publiée est annoncée comme telle, jamais approchée. L'accès aux microdonnées elles-mêmes, soumis à licence, reste du ressort de l'archive : l'assistant conduit l'usager jusqu'à la fiche officielle, pas au-delà.

## 1.5 Hypothèses

Une hypothèse n'a de valeur scientifique que si l'on peut dire ce qui la réfuterait. Nous formulons donc chacune avec son critère de réfutation :

- **H1.** Le routage explicite (chiffre / explication / document) réduit le risque d'erreur factuelle par rapport à une génération libre. Elle serait réfutée si le routeur ne faisait pas mieux que le hasard, ou s'il envoyait des questions chiffrées vers une voie générative, où le chiffre ne serait plus garanti.
- **H2.** L'ancrage structurel — chiffres copiés mot pour mot depuis une base, liens issus d'une liste vérifiée — complété par un contrôle de sortie, maintient le taux d'hallucination à zéro sur le périmètre couvert. Elle serait réfutée par un seul chiffre ou une seule adresse absents des sources.
- **H3.** Des composants classiques et légers suffisent pour répondre en quelques millisecondes, le LLM n'étant appelé que là où il apporte quelque chose. Elle serait réfutée si les voies sans LLM étaient aussi lentes que les appels au modèle, ou si une panne du fournisseur rendait le service indisponible.

## 1.6 Démarche

Ce travail relève de la recherche par la conception, telle que l'ont codifiée Hevner et ses co-auteurs [Hevner et al., 2004] : quand l'objet d'étude est un artefact — ici, une architecture logicielle —, la démarche consiste à partir d'un problème réel, à concevoir l'artefact en confrontant chaque choix à ses alternatives, puis à l'évaluer selon un protocole défini avant la mesure. Ce cadre nous convient mieux qu'une démarche purement expérimentale, car la contribution n'est pas une observation sur le monde mais un système dont il faut établir qu'il répond au besoin.

Cette démarche impose une discipline : chaque décision technique du projet est consignée dans une matrice de traçabilité (90 entrées à ce jour) au format *choix, alternatives, justification, référence* (annexe A). Un lecteur peut ainsi, pour n'importe quel composant, retrouver ce qui a été écarté et pourquoi.

## 1.7 Contributions

1. Une architecture hybride qui combine recherche documentaire encadrée et interrogation de base de données, pilotée par un routeur à deux niveaux, et ordonnée du traitement le plus sûr et le moins coûteux vers le plus coûteux.
2. Trois garanties de fiabilité formulées comme des propriétés testables — ancrage des chiffres (P1), aucune adresse inventée (P2), refus sûr (P3) — imposées par la structure du système et vérifiées automatiquement à chaque évolution du code.
3. Une **méthode d'acquisition référencée à moindre coût** d'un patrimoine statistique hétérogène : l'abondance et la dispersion des données de l'ANSD et du Système Statistique National — plateformes interrogeables, rapports PDF, pages web, portails partenaires — sont traitées comme une ressource, exploitée par une chaîne à cinq tiers (du flux structuré au registre de liens vérifiés) dont la complétude est garantie par construction (toute information est ingérée, connectée ou référencée), et qui alimente la base de chiffres, le corpus documentaire, le catalogue ANADS de 285 opérations et les portails partenaires, avec transformation automatique des noms d'études cités en liens cliquables.
4. Une stratégie de continuité de service : plusieurs fournisseurs de LLM interchangeables, un repli local qui ne tombe jamais en erreur, et un mode rapide qui coupe les appels non indispensables.
5. Un protocole d'évaluation rejouable, intégré à la chaîne de livraison du logiciel, et la matrice de 90 décisions justifiées.

## 1.8 Organisation du mémoire

Le chapitre 2 présente les notions et les travaux sur lesquels nous nous appuyons ; chaque méthode y est expliquée, comparée à ses alternatives et discutée au regard de notre contexte. Le chapitre 3 en déduit la conception de RAMA. Le chapitre 4 décrit la réalisation. Le chapitre 5 rapporte l'évaluation et confronte les hypothèses aux mesures. Le chapitre 6 discute les limites et la portée des résultats. Le chapitre 7 conclut.

---

# Chapitre 2 — État de l'art

Ce chapitre remplit deux fonctions : situer notre travail dans la littérature, et donner au lecteur toutes les notions utilisées ensuite. Pour construire notre assistant, quatre questions concrètes devront trouver réponse : comment reconnaître ce que l'usager demande (§ 2.2, 2.7) ? comment retrouver le bon document et rédiger une explication honnête (§ 2.4, 2.5) ? comment obtenir un chiffre exact (§ 2.6) ? et comment encadrer et évaluer le tout (§ 2.8, 2.9) ? Chaque section suit le même mouvement : expliquer la méthode simplement, la comparer à ses alternatives, puis dire ce qu'elle vaut dans notre contexte — un office statistique national, un corpus de taille modeste, des serveurs ordinaires sans processeur graphique, et une exigence de fiabilité absolue sur les faits.

## 2.1 Statistique publique et accès à l'information

Les principes des Nations Unies [Nations Unies, 2014] font de l'accessibilité une obligation de la statistique officielle, au même titre que l'impartialité et la transparence des méthodes. Or la recherche sur l'ouverture des données publiques a établi que publier ne suffit pas : Janssen et ses co-auteurs [Janssen et al., 2012] ont montré que l'idée « il suffit de mettre les données en ligne pour qu'elles soient utilisées » est un mythe, l'usage réel dépendant de la facilité à découvrir la bonne ressource et de l'existence d'une médiation entre le producteur de données et le public. Un assistant conversationnel est exactement une médiation de ce type : il ne remplace pas les sources, il en abaisse le coût d'accès. Il hérite en retour d'une contrainte déontologique forte, que nous retrouverons dans les garde-fous : la médiation ne doit ni déformer l'information ni glisser vers l'interprétation politique.

## 2.2 Assistants conversationnels

Trois idées anciennes de la recherche sur le dialogue structurent notre conception.

La première vient de la linguistique : tous les énoncés ne sont pas des demandes d'information. Dire « bonjour » ou « merci » est un acte social, qui appelle une réponse sociale et non une recherche documentaire. Les travaux sur la reconnaissance automatique de ces actes de dialogue [Stolcke et al., 2000] montrent qu'on peut les détecter de façon fiable. Nous en tirons une règle simple : traiter les actes sociaux à part, avant toute mécanique de recherche.

La deuxième vient de la philosophie du langage. Grice [Grice, 1975] a décrit la conversation comme une coopération réglée par des maximes, dont la maxime de qualité : ne pas affirmer ce dont on manque de preuve. L'hallucination des LLM est précisément une violation de cette maxime. Formulé ainsi, notre objectif technique rejoint une exigence conversationnelle de base : un assistant qui invente n'est pas seulement dangereux, il converse mal.

La troisième est le principe d'initiative mixte formulé par Horvitz [Horvitz, 1999] : une bonne interface ne se contente pas de répondre, elle propose. Suggérer après chaque réponse des questions complémentaires pertinentes réduit l'effort de formulation de l'usager et l'aide à découvrir des données qu'il n'aurait pas pensé à demander. Enfin, pour comprendre les questions de suivi (« et en 2013 ? »), la littérature parle de réécriture de question conversationnelle [Vakulenko et al., 2021] : reformuler la question elliptique en une question complète à l'aide de l'historique. Nous implémentons cette idée sous une forme volontairement simple, par substitution d'entités dans la dernière question complète mémorisée.

## 2.3 Grands modèles de langage : force et défaut

Les LLM actuels — dont l'entraînement mobilise des corpus immenses et des modèles atteignant le billion de paramètres [Fedus et al., 2022] — produisent un langage fluide et couvrent un spectre très large de formulations. C'est leur force, et c'est exactement ce dont une interface en langage naturel a besoin. Leur défaut est l'hallucination, définie plus haut. Deux résultats de la littérature orientent directement notre conception.

D'abord, le remède principal identifié par Ji et ses co-auteurs [Ji et al., 2023] est l'ancrage : fournir au modèle les documents pertinents et lui demander de s'y tenir. Ensuite, Liu et ses co-auteurs [Liu et al., 2023] ont montré que les modèles exploitent mal le milieu des longs contextes : quand l'information utile est noyée dans un grand volume de texte, la qualité chute. La conséquence pratique est qu'il vaut mieux récupérer peu de passages, mais bien choisis, que d'inonder le modèle de documents. Nous ajoutons une troisième observation, qui fonde notre choix le plus structurant : l'ancrage réduit l'hallucination mais ne l'élimine pas, puisque le modèle reste libre de s'écarter des passages fournis. Un contrôle extérieur à la génération reste donc nécessaire — et pour les chiffres, mieux vaut ne jamais laisser le modèle les écrire lui-même.

## 2.4 Retrouver le bon document : recherche lexicale ou recherche dense

Avant de générer quoi que ce soit, il faut retrouver les documents pertinents. Deux familles de méthodes existent.

La recherche *lexicale* repose sur les mots eux-mêmes. C'est l'approche historique, formalisée par le modèle vectoriel de Salton [Salton et al., 1975] avec la pondération TF-IDF.

::: enclair
<span class="titre-enclair">En clair — TF-IDF</span>
TF-IDF donne un poids à chaque mot d'un document selon deux facteurs : sa fréquence dans ce document (TF, *term frequency*) et sa rareté dans la collection (IDF, *inverse document frequency*) — la collection étant simplement l'ensemble des documents dans lequel on cherche : ici, les fiches de l'archive ANADS. Un mot pèse lourd s'il est fréquent ici et rare ailleurs. *Exemple sur notre corpus* : dans la question « je cherche les données sur la pêche au Sénégal », le mot « pêche » apparaît dans très peu de fiches — il pèse lourd et désigne les bonnes ; le mot « Sénégal » apparaît dans presque toutes — son poids tombe vers zéro et il ne perturbe pas la recherche. Formellement, le poids vaut $w_{t,d} = \mathrm{tf}_{t,d} \cdot \log(N/\mathrm{df}_t)$, où $N$ est le nombre de documents et $\mathrm{df}_t$ le nombre de documents contenant le mot $t$.
:::

BM25 [Robertson & Zaragoza, 2009] est un raffinement de cette pondération, devenu la référence des moteurs de recherche classiques.

La recherche *dense* remplace les mots par le sens. Un réseau de neurones convertit questions et passages en listes de nombres (des « vecteurs ») construites pour que deux textes de sens proche donnent des nombres proches ; retrouver le bon passage revient alors à chercher les vecteurs les plus proches de celui de la question. Cette approche a été établie par DPR [Karpukhin et al., 2020] et Sentence-BERT [Reimers & Gurevych, 2019], et des structures d'index comme HNSW [Malkov & Yashunin, 2018] la rendent rapide à grande échelle. Sa force : retrouver un passage même quand les mots diffèrent (« décès infantile » retrouve « mortalité des enfants »). Son prix : un modèle de plus à faire tourner — idéalement sur processeur graphique — et des résultats difficiles à expliquer, car on ne peut pas dire quel mot a fait la décision. Le tableau 1 résume la comparaison.

**Tableau 1** — Recherche lexicale et recherche dense : comparaison au regard de notre contexte.

| Critère | Lexicale (TF-IDF, BM25) | Dense (DPR, SBERT) |
|---|---|---|
| Capte les synonymes | Non (sauf enrichissement manuel) | Oui |
| Matériel requis | Processeur ordinaire | Modèle neuronal, GPU souhaitable |
| Comportement explicable | Oui (poids des mots inspectables) | Difficilement |
| Latence | Milliseconde | Dizaines de ms à s |
| Pertinence sur petit corpus spécialisé | Bonne (vocabulaire stable) | Bonne mais sans avantage net |

*Notre choix.* Notre corpus est petit (environ 25 documents et 285 fiches), son vocabulaire est stable et institutionnel (les mêmes sigles et intitulés reviennent partout), et le déploiement visé n'a pas de processeur graphique. Dans ces conditions, l'avantage sémantique de la recherche dense ne compense ni son coût ni son opacité. Nous retenons la recherche lexicale TF-IDF, en compensant sa faiblesse sur les synonymes par un enrichissement thématique manuel (par exemple, « pêche » étend la requête vers « halieutique », « aquaculture ») et par une liste de mots vides propre au domaine. La recherche dense reste une évolution naturelle si le corpus grossit d'un ordre de grandeur.

## 2.5 La génération augmentée par la récupération (RAG)

::: enclair
<span class="titre-enclair">En clair — le RAG</span>
La génération augmentée par la récupération (*Retrieval-Augmented Generation*) consiste à répondre en deux temps : un *récupérateur* cherche les passages pertinents dans une base documentaire, puis un *générateur* (le LLM) rédige la réponse en s'appuyant sur ces passages, qui peuvent être cités comme sources. Le modèle ne répond plus « de mémoire » : il répond « documents en main ».
:::

La figure 2 montre le fonctionnement sur une question réelle de notre corpus.

![**Figure 2** — Fonctionnement du RAG sur une question réelle. Le récupérateur cherche dans le corpus les passages les plus pertinents ; le générateur rédige en s'appuyant uniquement sur eux ; les passages sont cités comme sources et conservés comme preuves.](figures/rag.png)

Le RAG a été formalisé par Lewis et ses co-auteurs [Lewis et al., 2020] et il est devenu le schéma standard pour brancher un LLM sur une base de connaissances ; la synthèse de Gao et ses co-auteurs [Gao et al., 2023] en recense aujourd'hui de nombreuses variantes. Deux d'entre elles nous intéressent directement. Self-RAG [Asai et al., 2023] apprend au modèle à décider quand récupérer et à critiquer ses propres réponses. CRAG [Yan et al., 2024] ajoute une étape plus simple : évaluer la qualité des passages récupérés avant de générer, et corriger la récupération si elle est mauvaise.

*Notre choix.* Le RAG est retenu pour les questions d'explication (méthodologie, définitions, informations pratiques) : c'est la seule approche qui produise une réponse rédigée *et* sourcée. Parmi les variantes, nous reprenons l'idée de CRAG — un filtrage de pertinence des passages avant génération — parce qu'elle est simple et sans apprentissage supplémentaire, là où Self-RAG demande un réentraînement du modèle, hors de portée et hors de propos pour un corpus de notre taille. Surtout, nous ne demandons jamais au RAG de produire un chiffre : c'est le rôle d'une autre voie, décrite ci-dessous.

## 2.6 Le Text-to-SQL : du langage naturel à la requête de base de données

::: enclair
<span class="titre-enclair">En clair — le Text-to-SQL</span>
Une base de données relationnelle range l'information en tables, comme des feuilles de calcul : une table « démographie » a une ligne par région, avec sa population. SQL est le langage standard pour l'interroger. Le Text-to-SQL est la tâche qui consiste à traduire une question en français (« quelle est la population de Dakar ? ») en une requête SQL exécutable (`SELECT population FROM demographie WHERE region='Dakar'`). L'intérêt décisif : le résultat de la requête est exact par construction, puisqu'il sort de la base — toute la difficulté se concentre dans la traduction.
:::

La recherche sur cette tâche a été lancée par Seq2SQL [Zhong et al., 2017], structurée par le jeu d'évaluation Spider [Yu et al., 2018] — qui a aussi imposé la bonne métrique, l'exactitude d'exécution : deux requêtes sont équivalentes si elles retournent le même résultat, peu importe leur écriture. Les meilleures approches actuelles font générer la requête par un LLM guidé, comme DIN-SQL [Pourreza & Rafiei, 2023] qui décompose le problème (repérer les tables, estimer la difficulté, s'auto-corriger) ; un état de l'art complet est donné par Katsogiannis-Meimarakis et Koutrika [2023].

Il existe pourtant une alternative plus ancienne : les gabarits. On écrit à l'avance des requêtes à trous pour les formes de questions attendues, et le traitement se réduit à reconnaître la forme et remplir les trous. La figure 3 déroule un exemple complet, de la question à la phrase de réponse ; le gabarit « population de {région} en {année} » y couvre aussi bien « quelle est la population de Dakar en 2023 ? » que « combien d'habitants à Thiès en 2013 ? » — seuls la région et l'année changent, la requête SQL sous-jacente est la même, écrite et testée une fois pour toutes. Le tableau 2 confronte les deux approches.

![**Figure 3** — La voie Text-to-SQL par gabarits, sur un exemple complet : appariement de la forme, extraction des paramètres, exécution en lecture seule de la requête pré-écrite, mise en phrase du résultat exact.](figures/ttsql.png)

**Tableau 2** — Gabarits et génération libre : comparaison au regard de notre contexte.

| Critère | Gabarits paramétrés | Génération par LLM |
|---|---|---|
| Exactitude d'exécution | Totale sur les formes couvertes (requêtes écrites et testées à l'avance) | Élevée mais non garantie |
| Couverture | Bornée aux formes prévues | Ouverte |
| Latence | Milliseconde | Une à plusieurs secondes |
| Sécurité | Aucune requête arbitraire n'est exécutée | Requête générée à contrôler |
| Schémas visés | Fermés et connus | Arbitraires (Spider) |

*Notre choix.* La génération par LLM est la bonne réponse quand le schéma de la base est arbitraire ou inconnu — c'est le problème que Spider pose. Notre situation est l'inverse : le schéma est fermé, petit, et nous le maîtrisons entièrement (population, pauvreté, emploi, prix, PIB). Les questions usuelles d'un usager de l'ANSD se projettent bien sur des formes prévisibles. Les gabarits donnent alors tout ce que la génération promet, avec en plus la garantie, la vitesse et la sécurité. Nous retenons donc les gabarits d'abord, la génération LLM n'intervenant qu'en extension pour les formulations imprévues — et la base n'est ouverte qu'en lecture seule, si bien que même une requête inattendue ne peut rien modifier.

## 2.7 Classer l'intention d'une question

Notre architecture doit décider, pour chaque question, quelle voie l'exécutera. C'est un problème de classification de texte : à partir de la question, prédire une classe parmi « chiffre » (SQL), « explication » (RAG) ou « les deux » (HYBRID).

La solution la plus performante aujourd'hui est d'adapter un grand modèle de compréhension de texte pré-entraîné ; DeBERTa [He et al., 2021] est l'état de l'art de cette famille. Mais un principe méthodologique commande de commencer plus bas : établir d'abord une référence simple et reproductible, puis mesurer ce que la complexité apporte. Notre référence combine la représentation TF-IDF déjà décrite (§ 2.4) et une régression logistique.

::: enclair
<span class="titre-enclair">En clair — la régression logistique</span>
La régression logistique est l'un des classifieurs les plus simples : pendant l'entraînement, elle apprend un poids par mot et par classe — positif si le mot plaide pour la classe, négatif s'il plaide contre. Pour classer une nouvelle question, elle additionne les poids des mots présents et convertit le total en probabilités. *Exemple* : dans « combien d'habitants à Dakar ? », les mots « combien » et « habitants » ont appris des poids forts pour la classe « chiffre » ; la probabilité de cette classe domine, et on peut expliquer la décision en montrant quels mots ont pesé.
:::

Ce couple a trois vertus dans notre contexte : il s'entraîne en quelques secondes sur un processeur ordinaire, ses décisions s'expliquent, et ses probabilités fournissent naturellement un score de confiance dont l'architecture se servira.

Pour estimer honnêtement la performance d'un classifieur avec peu de données, la validation croisée est la méthode établie [Kohavi, 1995].

::: enclair
<span class="titre-enclair">En clair — la validation croisée</span>
Évaluer un modèle sur les données qui ont servi à l'entraîner donne un score trompeur — comme évaluer un étudiant sur les exercices qu'il a appris par cœur. La validation croisée à 5 plis découpe le jeu en cinq parts : on entraîne sur quatre parts et on teste sur la cinquième, en tournant cinq fois, de sorte que chaque exemple soit testé une fois par un modèle qui ne l'a jamais vu (figure 4). La version *stratifiée* conserve dans chaque part les proportions des classes. On agrège ensuite les cinq résultats.
:::

![**Figure 4** — La validation croisée à 5 plis : à chaque tour, quatre parts servent à l'entraînement (bleu) et une au test (vert) ; chaque question est donc testée exactement une fois par un modèle qui ne l'a jamais vue.](figures/validation_croisee.png)

*Notre choix.* La démonstration et l'évaluation utilisent la référence TF-IDF + régression logistique, évaluée par validation croisée stratifiée. DeBERTa affiné est prévu pour la production. Ce n'est pas une concession : c'est ce qui permet de chiffrer précisément ce que la référence sait faire et où elle échoue — nous verrons au chapitre 5 que son point faible est instructif, et que l'architecture est précisément construite pour le couvrir.

## 2.8 Encadrer un LLM : les garde-fous

La communauté a développé des outils pour filtrer les entrées et les sorties d'un LLM ; NeMo Guardrails [Rebedea et al., 2023] est le représentant le plus connu, avec un langage dédié pour décrire des « rails » de conversation. Ces cadres sont puissants mais génériques : leurs règles s'expriment dans un formalisme propre, et une partie des contrôles passe elle-même par des appels au modèle.

*Notre choix.* Nos règles de refus sont peu nombreuses, stables et critiques : hors-sujet, tentative de détournement de consignes (« ignore tes instructions »), sujet politique ou électoral. Nous les implémentons directement, par des motifs et un lexique du domaine, plutôt qu'à travers un cadre générique — pour deux raisons. La première est la sûreté : nos garde-fous d'entrée sont déterministes et s'exécutent avant tout appel au modèle ; ils ne peuvent donc pas être contournés en manipulant le modèle. La seconde est l'auditabilité : chaque règle se lit dans le code et se teste unitairement. Le garde-fou de sortie — la vérification que les chiffres d'une réponse générée figurent bien dans les sources — reprend l'esprit de la métrique de fidélité décrite ci-dessous.

## 2.9 Évaluer un système fondé sur un LLM

Trois niveaux d'évaluation nous concernent. Au niveau des composants : la validation croisée pour le routeur (§ 2.7) et l'exactitude d'exécution pour la voie SQL (§ 2.6). Au niveau des réponses générées : le cadre RAGAS [Es et al., 2024] a proposé d'automatiser des métriques dont la *fidélité* — la part des affirmations d'une réponse qui sont soutenues par les passages récupérés. La version complète de RAGAS utilise un LLM comme juge ; en mode hors ligne, nous en utilisons une version restreinte mais stricte, limitée aux nombres : tout nombre présent dans la réponse doit apparaître dans les passages. Au niveau du système entier : les caractéristiques de qualité logicielle d'ISO/IEC 25010 [ISO/IEC, 2011] (adéquation fonctionnelle, performance, fiabilité, sécurité) structurent nos exigences, et le questionnaire SUS [Brooke, 1996] servira, en perspective, à mesurer l'utilisabilité perçue auprès d'usagers réels.

Un principe gouverne tout le chapitre 5 : le jeu de test doit être défini indépendamment du système — à partir des publications officielles et du comportement attendu, pas des sorties observées — sans quoi l'évaluation est circulaire ; et le protocole doit être rejouable à l'identique par un tiers.

## 2.10 Synthèse : pourquoi une architecture hybride routée

Les sections précédentes dessinent quatre architectures candidates. Le tableau 3 les confronte à nos exigences.

**Tableau 3** — Les quatre architectures candidates face à nos exigences.

| Critère | LLM seul | RAG seul | Text-to-SQL seul | Hybride routé (RAMA) |
|---|---|---|---|---|
| Chiffre exact garanti | Non | Partiel (dépend des passages) | Oui | Oui (voie SQL) |
| Explication rédigée et sourcée | Non | Oui | Non | Oui (voie RAG) |
| Liens jamais inventés | Non | Non | — | Oui (base fermée) |
| Demandes de documents | Non | Partiel | Non | Oui (voie catalogue) |
| Latence typique | seconde(s) | seconde(s) | milliseconde | ms, jusqu'à s si LLM |
| Fonctionne sans fournisseur LLM | Non | Non | Oui | Oui (repli) |

Aucune approche unique ne satisfait tout : le LLM seul échoue sur la fiabilité, le RAG seul sur les chiffres et les liens, le Text-to-SQL seul sur les explications. La littérature étudie chaque brique isolément ; notre contribution est de les composer en un système opérationnel pour un office statistique réel, avec deux exigences que la composition seule ne donne pas et qu'il faudra construire : des garanties tenues par l'architecture plutôt que par le bon comportement espéré du modèle, et une évaluation rejouable intégrée au cycle de vie du logiciel. C'est l'objet des deux chapitres suivants.

---

# Chapitre 3 — Conception

Le chapitre précédent a retenu, pour chaque brique, l'approche la mieux adaptée à notre contexte. Ce chapitre les assemble : il fixe d'abord les exigences, présente l'architecture d'ensemble, puis précise ce qui fait l'originalité du système — l'ordre des traitements, le routage et les trois garanties de fiabilité.

## 3.1 Exigences

Le tableau 4 fixe ce que le système doit faire (exigences fonctionnelles, EF) et sous quelles contraintes (exigences non fonctionnelles, ENF). Chaque ligne indique la caractéristique ISO/IEC 25010 correspondante et l'endroit du mémoire où l'exigence est vérifiée.

**Tableau 4** — Exigences fonctionnelles et non fonctionnelles.

| Réf. | Exigence | ISO 25010 | Vérifiée |
|---|---|---|---|
| EF1 | Répondre à une question chiffrée par un chiffre officiel sourcé | Adéquation fonctionnelle | § 5.4, 5.5 |
| EF2 | Expliquer une méthode ou une définition à partir du corpus | Adéquation fonctionnelle | § 5.5 |
| EF3 | Résoudre une demande de document en liens officiels directs | Adéquation fonctionnelle | § 5.5 |
| EF4 | Tenir une conversation : suivis, actes sociaux | Adéquation fonctionnelle | § 5.5 |
| EF5 | Transformer les noms d'études cités en liens vers leurs fiches | Adéquation fonctionnelle | § 5.5 |
| EF6 | Proposer des questions complémentaires pertinentes, jamais répétées | Adéquation fonctionnelle | inspection |
| ENF1 | Aucun chiffre ni lien inventé | Fiabilité | § 5.5 |
| ENF2 | Refus des questions hors sujet, malveillantes ou politiques | Sécurité | § 5.5 |
| ENF3 | Quelques millisecondes sur les voies sans LLM | Performance | § 5.5 |
| ENF4 | Service maintenu sous charge et en cas de panne du fournisseur LLM | Fiabilité | § 4.5, 5.6 |
| ENF5 | Métriques d'exploitation consultables | Maintenabilité | § 4.7 |
| ENF6 | Déployable sans GPU, image durcie, sans secret embarqué | Portabilité, sécurité | § 4.8 |
| ENF7 | Évaluation rejouable, bloquante en cas de régression | Maintenabilité | § 5.1 |
| ENF8 | Chaque décision technique tracée et justifiée | Maintenabilité | annexe A |

## 3.2 Vue d'ensemble

RAMA s'organise en cinq couches (figure 5) : l'interface web ; l'API — la porte d'entrée technique qui reçoit les requêtes et protège le service ; l'orchestrateur, le composant central qui déroule pas à pas le traitement de chaque question ; les voies de réponse, adossées à un client LLM interchangeable ; et les données d'ancrage — base de chiffres en lecture seule, corpus documentaire, catalogue ANADS, liste de liens vérifiés.

Trois principes, issus directement du chapitre 2, gouvernent l'ensemble :

1. *Le chemin le plus sûr au moindre coût d'abord.* Les traitements sont ordonnés du moins cher et du plus sûr (acte social, garde-fou, cache) vers le plus cher (génération par LLM), avec des sorties anticipées à chaque étage. La majorité des questions n'atteint jamais le modèle.
2. *Le LLM ne touche jamais aux faits.* Les chiffres viennent de la base ou du catalogue, les liens de la liste vérifiée ; le modèle comprend, reformule et rédige, il n'énonce aucun fait de lui-même. C'est la traduction architecturale de la leçon du § 2.3.
3. *Défense en profondeur.* Garde-fous en entrée et en sortie, base en lecture seule, liste de liens fermée, limitation de débit : aucune protection ne repose sur une couche unique.

![**Figure 5** — Architecture générale de RAMA : cinq couches et garanties transversales. Les voies déterministes (SQL, CATALOG, NAV, CHAT) ne dépendent pas du client LLM ; les voies génératives (RAG, HYBRID) s'y adossent sous contrôle du garde-fou de sortie.](figures/architecture.png)

## 3.3 Notation et garanties

Posons la notation qui servira dans la suite. Le système reçoit une question $q$ et l'historique de session $h$, et produit un triplet $(a, L, E)$ : la réponse $a$, les liens cités $L$, et les preuves $E$ — les lignes de base de données, passages ou fiches qui ont fondé la réponse. Appelons $R$ la liste des liens vérifiés (31 adresses officielles, toutes contrôlées) et $C$ le catalogue ANADS (285 fiches, chacune avec l'adresse de sa page). Notons enfin $\mathrm{nombres}(x)$ les valeurs numériques d'un texte $x$ et $\mathrm{URL}(x)$ ses adresses web.

Les trois garanties annoncées s'écrivent alors simplement :

- **P1 — ancrage des chiffres** : tout nombre de la réponse figure dans les preuves, $\mathrm{nombres}(a) \subseteq \mathrm{nombres}(E)$ ;
- **P2 — aucune adresse inventée** : tout lien de la réponse vient des bases contrôlées, $\mathrm{URL}(a) \subseteq R \cup C$ ;
- **P3 — refus sûr** : une question hors périmètre, porteuse d'une injection ou de nature politique reçoit un refus poli, produit avant toute exécution de voie et tout appel au modèle.

Ces propriétés ne sont pas des objectifs que l'on espère atteindre : elles sont tenues par la structure. Les chiffres sont copiés depuis les lignes de base ou les fiches, puis mis en phrase — le générateur ne calcule jamais. Les liens sont ajoutés après la génération, par un composant qui n'apparie que contre $R \cup C$ : le modèle n'a littéralement aucun canal pour émettre une adresse. Le refus est décidé par des règles fixes placées en tête du traitement. Le garde-fou de sortie, décrit plus bas, ajoute un contrôle redondant de P1 sur les voies génératives : c'est une ceinture de sécurité en plus de la construction, pas le mécanisme principal.

## 3.4 Le pipeline de traitement

Le pipeline est la chaîne d'étapes que traverse chaque question, dans un ordre fixe. La figure 6 en montre le chemin ; l'algorithme 1 en donne la forme exacte.

![**Figure 6** — Pipeline de traitement d'une requête : flot nominal en neuf étapes et sorties anticipées (acte social, refus, cache, voies documentaires). Les sorties anticipées résolvent la majorité des requêtes sans appel au LLM.](figures/pipeline.png)

```
Algorithme 1 — Traitement d'une requête
Entrée : question q, session h        Sortie : (a, L, E)

1  si acte_social(q) :            retourner réponse sociale          # CHAT
2  si q contient des mots inconnus du domaine : q ← corriger_LLM(q)
3  q ← résoudre_suivi(q, h)                                          # « et en 2013 ? »
4  si garde_fou_entrée(q) ≠ ok :  retourner refus poli               # P3
5  si (q, h) ∈ cache :            retourner cache[(q, h)]
6  si demande_documentaire(q) :   retourner liens_officiels(q)       # CATALOG / NAV
7  v ← router(q)                                                     # SQL | RAG | HYBRID
8  (a, E) ← exécuter_voie(v, q)
9  si un nombre de a manque dans E : signaler la réponse             # contrôle P1
10 a ← lier_entités_et_titres(a) ; journaliser anonymement ; retourner (a, L(a), E)
```

Deux étapes méritent une explication. La correction des fautes (étape 2) appelle le LLM, ce qui coûte du temps ; elle n'est déclenchée que si la question contient des mots absents du lexique du domaine — lexique construit automatiquement à partir du corpus, du catalogue et des gabarits. Une question bien écrite passe donc sans surcoût, une question fautive (« kel é le to de chaumage ») est corrigée avant traitement. La détection documentaire (étape 6) court-circuite le routage : quand l'usager demande où trouver ou télécharger des données, la meilleure réponse possible est la liste exacte des fiches et portails pertinents, que l'appariement sur le catalogue produit en quelques millisecondes ; aucune génération ne ferait mieux, et toute génération pourrait faire pire.

## 3.5 Le routeur à deux niveaux

Pour les questions statistiques restantes, le routeur choisit entre trois classes : SQL (un chiffre), RAG (une explication), HYBRID (les deux : « quel est le taux de pauvreté et comment est-il mesuré ? »).

Le premier niveau est le classifieur de référence du § 2.7. La question est représentée en TF-IDF sur deux granularités : des suites de un à deux mots, et des suites de trois à cinq caractères — ces dernières donnent une robustesse aux flexions du français et aux petites fautes, car « chômage » et « chomage » partagent la plupart de leurs fragments. La régression logistique produit une probabilité par classe, notée $\hat{c}(q)$.

Le second niveau ne s'active que dans la zone d'incertitude (figure 7) :

$$\mathrm{route}(q) = \begin{cases} \text{classe la plus probable} & \text{si } \max \hat{c}(q) \geq \tau \\ \text{arbitrage LLM} & \text{sinon,} \end{cases} \qquad \tau = 0{,}85.$$

L'arbitrage est un appel au modèle avec une consigne fermée : répondre par l'un des trois noms de classe, rien d'autre. Le seuil $\tau$ règle un compromis : trop bas, des erreurs de routage passent ; trop haut, on paie des appels inutiles. Sa valeur de 0,85 a été fixée a priori comme point de fonctionnement prudent ; sa calibration fine sur des données d'usage réel est une perspective assumée. Ce qui est justifié empiriquement, c'est l'existence même du second niveau : le profil d'erreur mesuré au § 5.3 montre que l'incertitude du classifieur se concentre sur la classe HYBRID, dont la nature — une question qui demande *à la fois* un chiffre et une explication — échappe à une représentation par mots ; c'est exactement là qu'un arbitrage sémantique a de la valeur. En production, le premier niveau sera remplacé par DeBERTa affiné, le second restant inchangé.

![**Figure 7** — Routeur à deux niveaux. Le classifieur produit une probabilité par classe ; si la plus forte dépasse τ = 0,85, la classe est retenue, sinon un arbitrage LLM à réponse contrainte tranche. Le coût du LLM est ainsi limité à la zone d'incertitude.](figures/routeur.png)

## 3.6 Les voies de réponse

- **SQL** — chiffre exact. Appariement sur les gabarits (§ 2.6, figure 3), exécution en lecture seule, mise en phrase du résultat. Le tableau 5 montre les cinq familles de gabarits implémentées.
- **RAG** — explication. Récupération TF-IDF, filtrage de pertinence inspiré de CRAG, génération appuyée sur les passages, conservés comme preuves $E$ (figure 2).
- **HYBRID** — chiffre puis explication, enchaînés.
- **CATALOG** — accès aux données : fiches ANADS pertinentes et portails officiels, en liens directs.
- **NAV** — orientation vers la bonne page du site, depuis la liste $R$.
- **CHAT** — actes sociaux, sans aucune ressource.

**Tableau 5** — Les cinq familles de gabarits SQL, avec un exemple de question couverte.

| Famille | Exemple de question | Paramètres extraits |
|---|---|---|
| Valeur simple | « Quelle est la population du Sénégal en 2023 ? » | indicateur, année |
| Filtre régional | « Quel est le taux de pauvreté à Kolda ? » | indicateur, région |
| Comparaison | « Compare la pauvreté entre Dakar et Kolda » | indicateur, deux régions |
| Classement | « Quelle est la région la plus peuplée ? » | indicateur, sens du tri |
| Série temporelle | « Évolution de l'inflation depuis 2019 » | indicateur, période |

Le garde-fou de sortie contrôle les voies génératives : si un nombre de la réponse n'apparaît pas dans les preuves, la réponse est signalée au lieu d'être présentée comme fiable. La figure 8 résume les trois garanties, leur mécanisme et leur vérification.

![**Figure 8** — Les trois garanties de fiabilité. Chaque propriété est énoncée, imposée par un mécanisme de construction, doublée d'un contrôle, et vérifiée par des cas de test dédiés exécutés à chaque modification du code.](figures/garanties.png)

## 3.7 Modèle de menaces

Concevoir la sécurité commence par lister ce qui peut mal tourner. Le tableau 6 recense les menaces retenues — les menaces applicatives classiques suivent les référentiels OWASP [OWASP] — et les parades, chacune doublée conformément au principe de défense en profondeur.

**Tableau 6** — Menaces considérées et contre-mesures.

| Menace | Exemple | Contre-mesures |
|---|---|---|
| Injection de consigne | « ignore tes instructions et… » | Motifs de refus en entrée (P3) ; consignes système cloisonnées |
| Hors-sujet, opinion | « qui va gagner la CAN ? » | Lexique du domaine ; refus avant toute voie |
| Question politique | pronostic électoral | Motifs dédiés, y compris formulations prédictives |
| Injection SQL | entrée forgée | Gabarits seuls ; base ouverte en lecture seule |
| Adresse inventée | lien plausible mais faux | Liens ajoutés après génération, depuis R ∪ C seulement (P2) |
| Saturation du service | rafale de requêtes | Limitation de débit ; concurrence des appels LLM bornée |
| Fuite d'information | trace d'erreur exposée | Gestionnaire d'exceptions global ; journaux anonymes |
| Fuite de secrets | clé d'API dans l'image | Fichiers d'environnement exclus de l'image et du dépôt, vérifié |

## 3.8 Traçabilité

Chaque choix du projet — des plus structurants (architecture hybride) aux plus locaux (une liste de mots vides) — est consigné dans la matrice de traçabilité au format *choix, alternatives, justification, référence* (90 entrées, annexe A). Cette discipline, imposée par la démarche du § 1.6, a une conséquence pratique pour le lecteur : l'architecture présentée ici n'est pas un état de fait à croire sur parole, mais une suite d'arbitrages que l'on peut auditer un par un.

---

# Chapitre 4 — Réalisation

La conception du chapitre 3 est intégralement implémentée. Ce chapitre décrit les choix de réalisation — outils, données, mécanismes internes — en s'attardant sur ce qui conditionne les garanties et les mesures du chapitre 5.

## 4.1 Choix techniques d'ensemble

Le backend est écrit en Python avec FastAPI, un cadre web moderne et rapide ; scikit-learn fournit le TF-IDF et la régression logistique ; la base de chiffres est un fichier SQLite ouvert en lecture seule. Le client LLM parle le protocole devenu standard de fait (celui de l'API OpenAI), ce qui rend les fournisseurs interchangeables par simple configuration — Groq en production, d'autres en secours. Le frontend est une page web unique, sans aucune dépendance externe ni CDN : tout est servi par l'application elle-même, sur la même origine. L'ensemble du cœur applicatif tient en environ 2 000 lignes, découpées en modules à responsabilité unique (orchestrateur, routeur, voies, catalogue, liens, garde-fous, client LLM, télémétrie).

Ces choix partagent une même logique : chaque composant est le plus simple qui satisfasse l'exigence. SQLite plutôt qu'un serveur de base de données, parce que les données sont petites, lues seulement, et embarquées ; scikit-learn plutôt qu'un réseau de neurones, pour les raisons du § 2.7 ; une page unique plutôt qu'un cadre frontend, parce que l'interface est une conversation et rien d'autre.

## 4.2 Les données : une chaîne d'acquisition référencée à moindre coût

Le patrimoine statistique de l'ANSD et du Système Statistique National est abondant et dispersé sur des supports hétérogènes : plateformes interrogeables dotées d'une interface de programmation (la Plateforme Open Data, l'archive ANADS, le répertoire des localités), rapports et notes en PDF — dont la *Situation Économique et Sociale*, publiée chaque année depuis 2005 et couvrant presque tous les secteurs —, pages web institutionnelles, et portails de producteurs partenaires (la DAPSA pour l'agriculture, l'ANAT pour le territoire, la BCEAO pour la monnaie). Cette abondance n'est pas un obstacle mais la matière première d'une contribution : concevoir la méthode la plus efficace et la moins coûteuse pour rendre l'ensemble de ce patrimoine exploitable, de façon référencée, dans un assistant déployable sans processeur graphique.

Le principe qui gouverne le runtime — emprunter d'abord le chemin le plus sûr et le moins coûteux — est ici étendu à l'acquisition : face à une source, on choisit la technique d'ingestion **minimale qui suffit**. Une interface de programmation vaut mieux qu'un extracteur de page ; un extracteur déterministe vaut mieux qu'une saisie manuelle ; et l'on ne structure finement que ce qui est réellement interrogé, le reste demeurant atteignable par référence plutôt qu'ingéré aveuglément. C'est l'optimum de l'exploitation : couverture maximale, coût minimal, tout référencé.

La complétude — l'assurance que rien n'est laissé de côté — n'est pas obtenue en copiant tout, mais garantie **par construction** : toute information tombe dans exactement l'une de trois dispositions, partition totale et sans recouvrement. Elle est **ingérée** (structurée dans la base de chiffres ou le corpus documentaire) pour le cœur à forte demande ; **connectée** (servie en direct par une interface de programmation) pour la fraîcheur et la largeur ; ou **référencée** (pointée par un lien vérifié ou une fiche de catalogue) pour la longue traîne. La conséquence est décisive : une question dont la donnée n'est ni ingérée ni connectée reçoit toujours au moins la référence officielle exacte — jamais un vide, jamais une invention.

Concrètement, chaque source est classée selon quatre critères — structure, mode d'accès, volatilité, licence — puis routée vers l'un de cinq tiers d'ingestion, du moins coûteux au plus coûteux (figure 9ter). Chaque tier conserve la provenance, si bien que la couche d'ancrage qui en résulte est unifiée non par un format commun, mais par le fait que chaque valeur sait d'où elle vient.

![**Figure 9ter** — La chaîne d'acquisition référencée : les sources hétérogènes sont classées, puis routées vers cinq tiers d'ingestion (du flux structuré au registre de liens vérifiés), du moins coûteux au plus coûteux. La couche d'ancrage unifiée par la provenance alimente les voies du runtime, qui répondent de façon référencée (P1, P2).](figures/chaine_acquisition.png)

| Tier | Nature de la source | Exemples ANSD / SSN | Technique d'ingestion | Alimente |
|---|---|---|---|---|
| T1 | Flux structuré, interface de programmation | Open Data, catalogue ANADS, répertoire des localités | Adaptateur direct (port `SourceStatistique`) ou moisson | base · catalogue |
| T2 | Tables dans des documents | *Situation Économique et Sociale*, Annuaire, tableaux de rapports | Extraction de tables + assertions de cohérence | base curatée |
| T3 | Documents narratifs | méthodologies, notes de presse, pages web, portails partenaires | Extraction de texte, segmentation, index lexical (sans GPU) | corpus RAG |
| T4 | Catalogue, métadonnées | 285+ opérations de l'archive ANADS | Moissonnage rejouable | index catalogue |
| T5 | Références, portails | pages officielles, DAPSA, ANAT, BCEAO | Registre de liens vérifiés (contrôle HTTP) | liste $R$ |

Ce choix se justifie face à ses alternatives. Tout ingérer dans un grand index vectoriel exigerait un coût de calcul et un matériel (processeur graphique) disproportionnés, introduirait de l'opacité et un risque d'erreur sur les chiffres. Bâtir un entrepôt exhaustif de *toutes* les publications aurait un rendement fortement décroissant, l'essentiel n'étant jamais interrogé. Aspirer tout le web institutionnel serait fragile et coûteux à maintenir. La méthode retenue — acquisition en tiers, pilotée par la demande, à provenance préservée — est la transposition à l'acquisition du principe runtime : le moins coûteux qui suffit, avec une complétude prouvée par la partition en trois dispositions. Les paragraphes qui suivent décrivent la couche d'ancrage que cette chaîne produit.

La base SQLite contient les tables population, pauvreté, emploi, inflation, PIB et indicateurs nationaux, alimentées depuis les publications officielles : RGPH-5 2023 (18 126 390 habitants), EHCVM II 2021/22, notes ENES, séries IHPC, comptes nationaux. Le script de construction vérifie les totaux par assertions — si la somme des régions ne redonne pas le total officiel, la construction échoue. Une valeur non publiée reste vide : elle n'est jamais estimée.

Le corpus documentaire compte environ 25 documents (méthodologies, notes de presse, questions pratiques, index du catalogue), chacun portant sa source. Le catalogue ANADS, collecté par un script rejouable depuis l'interface publique de l'archive, décrit 285 opérations avec titre, année et adresse de fiche. La liste $R$ contient 31 liens officiels, tous contrôlés ; une adresse injoignable est écartée plutôt que publiée. La figure 9 récapitule ces quatre sources, leur rôle et leur provenance.

![**Figure 9** — Les quatre sources d'ancrage : la base SQLite (chiffres exacts), le corpus documentaire (explications), le catalogue ANADS C (accès aux données) et la liste R des ressources vérifiées (liens officiels). Tout provient des publications officielles, via des scripts rejouables et des vérifications automatiques.](figures/donnees.png)

La figure 9bis synthétise cette organisation du point de vue de RAMA : pour chacune des trois familles — données structurées, documents, microdonnées —, elle indique la plateforme d'origine, son mode d'accès, et le volume **réellement acquis** : huit tables, cent cinq lignes et vingt-six indicateurs nationaux pour l'entrepôt de chiffres ; vingt-cinq documents officiels pour le corpus ; deux cent quatre-vingt-cinq fiches ANADS et trente et un liens vérifiés pour l'accès aux données.

![**Figure 9bis** — L'écosystème d'information de l'ANSD, en trois familles selon le mode d'accès, et le volume acquis par RAMA pour chacune. Données structurées et interrogeables (Plateforme Open Data et son interface de programmation, répertoire des localités, portails sectoriels) → entrepôt de chiffres ; documents (rapports et notes de méthodologie) → corpus ; microdonnées d'enquêtes (archive ANADS) → catalogue et liens vérifiés. À chaque famille correspond la voie de traitement adaptée.](figures/ecosysteme_ansd.png)

La famille des chiffres mérite une précision, car c'est elle qui porte la garantie la plus stricte. RAMA la structure en un **entrepôt statistique curaté** : les chiffres publiés y sont extraits une fois, rangés en tables, chaque valeur portant sa source et son année. Ce choix répond à trois exigences. D'abord la garantie P1 : un chiffre de réponse doit provenir, avec sa provenance exacte, d'une source structurée et vérifiable — une table dont chaque cellule est sourcée en est le support naturel. Ensuite la couverture des chiffres phares, qui paraissent d'abord dans des rapports : les extraire une fois, avec des assertions de cohérence, donne une source fiable là où aucune interface ne les sert encore de façon homogène. Enfin le déterminisme et l'autonomie : une lecture locale répond en millisecondes, hors ligne, sans dépendre d'un service tiers.

Surtout, la voie numérique ne dépend pas d'un stockage figé : elle est adossée à un **contrat** — une source statistique interrogeable renvoyant, pour un indicateur et des filtres, une valeur *et sa provenance*. L'entrepôt curaté en est la première réalisation ; brancher une source réelle de l'ANSD — la Plateforme Open Data par son interface de programmation, le répertoire des localités — revient à **ajouter un adaptateur derrière ce même contrat**, sans toucher au reste de l'architecture (figure 10bis). L'intégration au système d'information de l'ANSD cesse ainsi d'être une promesse : le point de raccordement existe dans la structure du logiciel.

![**Figure 10bis** — La couche d'accès aux données en ports et adaptateurs. La voie numérique dépend d'un contrat `SourceStatistique.get(indicateur, filtres) → valeur + provenance` ; l'entrepôt curaté (`ansd_stats.db`) est l'adaptateur en place ; la Plateforme Open Data et le répertoire des localités sont des adaptateurs branchables derrière le même contrat. Les voies RAG (corpus) et catalogue (ANADS) sont inchangées.](figures/architecture_donnees.png)

La figure 10 descend enfin au niveau du détail de l'entrepôt actuel : le schéma relationnel exact de la base — huit tables, la table de référence `regions` et ses clés étrangères, l'effectif et la source officielle de chaque table — et l'arborescence réelle des fichiers de données du projet ; c'est ce qui rend l'entrepôt entièrement auditable.

![**Figure 10** — À gauche, le schéma relationnel réel de `ansd_stats.db` : huit tables SQLite, la table de référence `regions` (vert) pointée par les clés étrangères `region_id`, avec l'effectif et la source officielle de chacune. À droite, l'arborescence des fichiers de données : base, catalogue ANADS, ressources vérifiées, corpus de 25 documents, jeux d'évaluation et journaux anonymes.](figures/schema_bd.png)

## 4.3 État, concurrence et mémoire

Plusieurs requêtes peuvent arriver en même temps ; l'état partagé (sessions, cache) est donc protégé par un verrou — un mécanisme qui garantit qu'un seul traitement le modifie à la fois, suivant la discipline d'exclusion mutuelle établie par Dijkstra [Dijkstra, 1965]. Le cache retient les réponses récentes avec une éviction du moins récemment utilisé ; sa clé combine la question normalisée et le contexte, si bien qu'une même question posée dans un autre contexte est traitée comme une entrée différente. La mémoire de session est bornée par une fenêtre glissante, et les suggestions déjà proposées y sont notées pour ne jamais être répétées (EF6).

## 4.4 La liaison automatique des liens

Toute réponse, y compris rédigée par le LLM, traverse une dernière étape qui transforme les mentions reconnues en liens cliquables : noms d'enquêtes (RGPH, EHCVM…), portails, et les 285 titres d'études du catalogue. La figure 11 en montre le fonctionnement sur un exemple réel. L'algorithme apparie les titres du plus long au plus court — sinon un titre court absorberait un titre long qui le contient —, tolère un millésime ajouté par le modèle (« (2015) »), ne touche jamais une zone déjà liée, et borne le nombre de liens injectés. Ce placement en aval de la génération est ce qui rend la garantie P2 indépendante du comportement du modèle : cette étape est le seul endroit du système où une adresse web peut entrer dans une réponse.

![**Figure 11** — La liaison automatique des liens sur un exemple réel : les titres d'études et noms de ressources reconnus dans la réponse générée sont transformés en liens cliquables, par appariement contre le catalogue C et la liste vérifiée R uniquement.](figures/autolink.png)

## 4.5 Le client LLM et la continuité de service

Le composant central s'appelle FallbackLLM et honore un contrat simple : ne jamais lever d'erreur. En cas d'API injoignable, de délai dépassé ou de quota épuisé, il passe au fournisseur suivant, puis à un moteur local fait de gabarits et d'extraction — moins riche, mais toujours disponible. Ce contrat vient d'un incident réel : pendant le développement, un compte de fournisseur sans crédit faisait planter le service entier ; il est maintenant couvert par un test. Deux mécanismes complètent l'ensemble : une borne sur le nombre d'appels distants simultanés, pour qu'une pointe de charge ne fasse pas s'empiler les délais, et un « mode éclair » qui coupe les appels d'agrément (correction des fautes, suggestions) quand le fournisseur configuré est lent. Le point structurel est que les garanties P1 à P3 ne dépendent d'aucun appel au modèle : une panne dégrade le confort, jamais la fiabilité ni la disponibilité (figure 12).

![**Figure 12** — Dégradation gracieuse du client LLM : fournisseur primaire, secours, puis moteur local qui ne dépend d'aucun réseau. Conséquence mesurée au § 5.6 : aucune erreur serveur sous 40 requêtes simultanées.](figures/degradation.png)

## 4.6 Interface

L'interface reprend l'identité visuelle de l'ANSD (bleu marine, bleu océan, blanc) et un logo dérivé de l'emblème institutionnel. Elle affiche les réponses en flux continu, rend les tableaux et les graphiques, montre les liens cliquables et propose après chaque réponse des questions complémentaires adaptées à la conversation. Elle est installable comme une application (PWA), propose les thèmes clair et sombre, se pilote au clavier et respecte les règles d'accessibilité WCAG 2.1 [W3C, 2018]. Une page « À propos et confidentialité » explique les sources, les limites et l'absence de collecte de données personnelles.

## 4.7 Observabilité

Le point d'accès `/api/metrics` expose la répartition des voies, les latences (médiane, 95ᵉ et 99ᵉ centiles, et médiane par voie), le taux de refus, le taux d'usage du cache et les retours de satisfaction. Ces mesures sont calculées sur des journaux anonymes : ni nom, ni adresse, ni identifiant personnel. On retrouve en production les grandeurs mêmes qui fondent l'évaluation du chapitre 5.

## 4.9 Deux traces de bout en bout

Pour fixer les idées avant l'évaluation, suivons deux questions réelles à travers le pipeline (figure 6, algorithme 1).

*« Quelle est la population de Dakar en 2023 ? »* Ce n'est pas un acte social (étape 1). Tous les mots appartiennent au lexique du domaine : la correction est sautée (2). Aucun suivi à résoudre (3). La question est dans le périmètre (4), absente du cache (5), et ce n'est pas une demande de document (6). Le routeur la classe SQL avec une confiance élevée (7) ; le gabarit « population de {région} en {année} » s'apparie, la requête pré-écrite s'exécute en lecture seule et retourne 4 004 427, mis en phrase (8). Aucun nombre étranger aux preuves (9). Enfin, « Dakar » reste du texte mais « RGPH-5 » devient un lien, et trois questions complémentaires sont proposées (10). Temps total : environ 5 ms, sans aucun appel au LLM.

*« Je veux les données sur la pêche. »* Les étapes 1 à 5 passent comme ci-dessus. À l'étape 6, l'intention documentaire est reconnue : le catalogue est interrogé, les fiches pertinentes remontent (« Comptes Satellites de la Pêche (2015) », enquêtes halieutiques…), complétées des portails officiels du thème. La réponse — une liste de liens vérifiés — part en 3 ms environ, sans routage ni génération : pour une demande d'accès, la liste exacte des sources est la meilleure réponse possible.

## 4.8 Sécurité applicative et déploiement

L'application est livrée sous la forme d'une image Docker — un paquet autonome qui contient l'application et tout son environnement, et s'exécute à l'identique sur n'importe quel serveur. Elle tourne sous un utilisateur aux droits réduits et se surveille par une sonde de santé. La recherche étant purement lexicale, aucun processeur graphique ni service externe n'est requis. La chaîne de fabrication de l'image a été vérifiée point par point : les fichiers d'environnement, qui contiennent la clé d'API, sont exclus de l'image et du dépôt, et l'inspection du système de fichiers de l'image confirme qu'aucun secret n'y figure. À chaque modification du code, l'intégration continue rejoue les 46 tests automatisés et l'évaluation complète ; une régression d'exactitude ou de sécurité bloque la livraison (ENF7). Le passage à plusieurs instances demanderait d'externaliser l'état de session — c'est une limite assumée, discutée au chapitre 6.

---

# Chapitre 5 — Évaluation expérimentale

## 5.1 Protocole

L'évaluation répond à cinq questions, dans l'ordre où l'architecture les pose : le routeur aiguille-t-il correctement ? la voie SQL produit-elle le bon chiffre ? le système complet tient-il ses exigences fonctionnelles et de sécurité ? en combien de temps ? et que se passe-t-il sous charge ?

Trois instruments y répondent, tous rejouables à l'identique :

1. *Le jeu de test « gold »* : 26 cas définis indépendamment du système, à partir des publications officielles et du comportement attendu — la voie qui doit répondre, les contenus qui doivent figurer dans la réponse, les liens attendus, les refus attendus. Il couvre onze capacités : chiffre, comparaison, suivi de conversation, accès aux données, liaison de titres, navigation, méthode, questions pratiques, définition, actes sociaux, sécurité. Le harnais s'exécute hors ligne, sans fournisseur LLM : les résultats sont déterministes, donc exactement reproductibles par un tiers (annexe D).
2. *La validation croisée du routeur* : stratifiée, à 5 plis (§ 2.7), avec un tirage aléatoire fixé pour que l'expérience soit rejouable à l'identique, sur les 328 questions étiquetées du jeu de routage. Un test statistique du χ² contrôle la significativité du résultat ; il répond à une question simple : un routeur qui répondrait au hasard aurait-il pu produire un tel accord entre prédictions et réalité ?
3. *Le test de charge* : 120 requêtes à 40 de concurrence, en mesurant les erreurs serveur, les limitations propres et les exceptions.

Le harnais est branché sur l'intégration continue en garde-barrière : une régression fait échouer la livraison. L'évaluation n'est pas une photographie prise une fois, c'est un invariant du projet.

## 5.2 Métriques

Pour le routeur, nous rapportons l'exactitude — la part de questions bien classées — et trois mesures par classe.

::: enclair
<span class="titre-enclair">En clair — précision, rappel, F1</span>
Prenons la classe « chiffre » (SQL). La *précision* répond à : parmi les questions que le routeur a envoyées vers SQL, combien étaient vraiment des questions chiffrées ? Le *rappel* répond à la question inverse : parmi les vraies questions chiffrées, combien ont bien été envoyées vers SQL ? Les deux peuvent diverger : un routeur qui enverrait tout vers SQL aurait un rappel parfait mais une précision médiocre. Le *F1* combine les deux en un seul nombre, qui n'est élevé que si les deux le sont. Le F1 « macro » fait la moyenne des F1 des trois classes en leur donnant le même poids — indispensable ici, car la classe la plus rare (HYBRID) est aussi la plus difficile, et une moyenne pondérée par les effectifs masquerait sa faiblesse.
:::

Pour la voie SQL, l'exactitude d'exécution du § 2.6 : la requête produite retourne-t-elle le même résultat que la requête de référence ? Pour le jeu gold : exactitude fonctionnelle (voie conforme, contenus présents, liens présents), sécurité (les cas adverses sont refusés), fidélité (aucun nombre non couvert par les preuves) et latence. Celle-ci est rapportée en centiles : la médiane est le temps sous lequel la moitié des réponses arrivent, le p95 celui sous lequel 95 % arrivent — dire « p95 = 13 ms », c'est dire que même les réponses lentes restent sous 13 millisecondes. Sous charge : erreurs serveur, limitations, exceptions.

## 5.3 Résultats — le routeur

Sur 328 questions en validation croisée stratifiée à 5 plis, le routeur de référence atteint une exactitude de 0,857 — un peu plus de six questions sur sept correctement aiguillées — et un F1 macro de 0,805. Le test du χ² écarte sans ambiguïté l'hypothèse d'un classement au hasard (χ² = 353,4 ; 4 degrés de liberté ; p ≈ 3,2·10⁻⁷⁵ : la probabilité d'observer un tel accord par pur hasard est infinitésimale). Le détail par classe (tableau 7) et la matrice de confusion (figure 13) — un tableau qui croise, pour chaque question, sa vraie classe et la classe prédite — montrent où se loge l'erreur.

**Tableau 7** — Performances du routeur par classe (validation croisée stratifiée, 5 plis, n = 328).

| Classe | Précision | Rappel | F1 | Effectif |
|---|---|---|---|---|
| HYBRID | 0,762 | 0,533 | 0,627 | 60 |
| RAG | 0,914 | 0,955 | 0,934 | 155 |
| SQL | 0,815 | 0,894 | 0,852 | 113 |
| Exactitude globale | | | 0,857 | 328 |
| Moyenne macro | 0,830 | 0,794 | 0,805 | 328 |

![**Figure 13** — Matrice de confusion du routeur (validation croisée stratifiée à 5 plis, n = 328). Lignes : classe réelle ; colonnes : classe prédite ; la diagonale verte compte les prédictions correctes. L'erreur se concentre sur HYBRID, le plus souvent prédite SQL (19 cas sur 60) ou RAG (9 sur 60).](figures/confusion.png)

La lecture de ces chiffres est instructive. RAG et SQL sont bien séparées (F1 de 0,934 et 0,852) : leurs vocabulaires diffèrent nettement. HYBRID, en revanche, n'est reconnue qu'une fois sur deux (rappel 0,533) — et c'est normal : une question comme « quel est le taux de pauvreté et comment est-il mesuré ? » contient à la fois les mots d'une question chiffrée et ceux d'une question de méthode. Son caractère « double » n'est pas dans les mots, il est dans la structure de la demande, invisible pour une représentation lexicale. Ce constat valide deux choix de conception faits au chapitre 3 : l'arbitrage LLM du second niveau est placé exactement sur cette zone d'incertitude, et le remplacement du premier niveau par un encodeur contextuel (DeBERTa) en production vise précisément ce que le TF-IDF ne peut pas voir. On notera enfin que l'erreur résiduelle est orientée dans le bon sens : confondre HYBRID avec SQL donne à l'usager le chiffre exact sans l'explication — jamais une explication sans chiffre présentée comme un fait. À titre d'ordre de grandeur, une version antérieure du jeu limitée aux suites de mots plafonnait autour de 0,78 d'exactitude ; l'ajout des fragments de caractères a apporté le reste.

## 5.4 Résultats — la voie SQL

Sur le jeu de référence de 15 questions couvrant les cinq familles de gabarits (tableau 5), l'exactitude d'exécution est de 15/15. Ce résultat n'est pas une surprise : c'est la propriété constitutive des gabarits (§ 2.6). Le mesurer en continu a une autre fonction — garantir qu'aucune évolution future des gabarits ne casse silencieusement un cas qui marchait.

## 5.5 Résultats — le système complet

Les 26 cas du jeu gold se décomposent en 24 cas « cœur », qui doivent réussir sans aucun appel au LLM, et 2 cas de robustesse aux fautes de frappe, qui dépendent par nature de la correction par LLM et sont rapportés à part. Le tableau 8 détaille les onze capacités testées, avec un exemple pour chacune ; le tableau 9 donne la synthèse.

**Tableau 8** — Les onze capacités du jeu de test, avec exemples et résultats.

| Capacité | Exemple du jeu de test | Réussite |
|---|---|---|
| Chiffre | « Quelle est la population du Sénégal en 2023 ? » | 5/5 |
| Comparaison | « Quelle région a le taux de pauvreté le plus élevé ? » | 1/1 |
| Suivi de conversation | « Et en 2013 ? » (après une question sur 2023) | 2/2 |
| Accès aux données | « Je veux les données sur la pêche » | 3/3 |
| Liaison de titres | titres d'études cités rendus cliquables | 1/1 |
| Navigation | « Où trouver le rapport de l'EHCVM ? » | 2/2 |
| Méthode | « Comment la pauvreté est-elle mesurée ? » | 1/1 |
| Questions pratiques | « Où se trouve l'ANSD ? » | 1/1 |
| Définition | « Qu'est-ce que l'indice de Gini ? » | 1/1 |
| Actes sociaux | « Bonjour », « merci », « qui es-tu ? » | 3/3 |
| Sécurité (refus attendu) | injection de consigne, question électorale… | 4/4 |

**Tableau 9** — Résultats d'ensemble sur le jeu gold (26 cas), mode déterministe hors ligne.

| Dimension | Résultat |
|---|---|
| Exactitude fonctionnelle | 24/24 |
| Sécurité (refus des cas adverses) | 4/4 |
| Fidélité (nombres couverts par les preuves) | 3/3 |
| Latence médiane / p95 / max | 5 / 13 / 19 ms |
| Robustesse aux fautes (dépend du LLM) | 1/2 hors ligne ; 2/2 avec fournisseur rapide |

Trois lectures complètent ces tableaux. Les quatre cas de sécurité couvrent les trois volets de P3 — question hors sujet, demande fantaisiste, injection de consigne, question électorale — tous refusés en une milliseconde environ, avant toute voie. Les cas d'accès aux données, de navigation et de liaison de titres vérifient P2 : chaque lien produit appartient à $R \cup C$. Enfin, les deux cas de robustesse aux fautes illustrent la frontière entre le cœur et le confort : hors ligne, sans correction LLM, l'un des deux échoue ; avec un fournisseur rapide, les deux passent.

La figure 14 décompose la latence par voie et met en évidence le gradient voulu par la conception : une milliseconde pour les actes sociaux et les refus, trois à quatre pour les voies documentaires, cinq pour le SQL, treize pour le RAG. Avec un fournisseur LLM rapide sur les voies génératives, la médiane passe à 621 ms et le 95ᵉ centile à 3 956 ms — deux ordres de grandeur au-dessus des voies déterministes. C'est la justification chiffrée, après coup, de l'ordonnancement du pipeline : réserver ce coût aux seules questions qui en tirent un bénéfice.

![**Figure 14** — Latence médiane par voie (ms), jeu gold, mode déterministe hors ligne. Actes sociaux et refus : ≈ 1 ms ; voies documentaires : 3–4 ms ; SQL : 5 ms ; RAG : 13 ms. Médiane globale 5 ms, p95 = 13 ms.](figures/latence.png)

## 5.6 Résultats — sous charge

**Tableau 10** — Test de charge : 120 requêtes, 40 en concurrence.

| Grandeur | Valeur |
|---|---|
| Requêtes servies (200) | 30 |
| Limitées proprement (429) | 90 |
| Erreurs serveur (5xx) | 0 |
| Exceptions côté client | 0 |

La répartition 30/90 du tableau 10 est voulue : la limitation de débit était réglée volontairement bas pour l'expérience, afin d'observer le comportement au-delà de la capacité. Le résultat est celui recherché : le service refuse proprement l'excédent (code 429, « réessayez plus tard ») au lieu d'échouer ou de s'effondrer, et aucune exception n'atteint l'usager. Combiné au repli du client LLM (§ 4.5), qui maintient le service en cas de panne du fournisseur, ce comportement établit l'exigence ENF4.

## 5.7 Retour sur les hypothèses

**Tableau 11** — Hypothèses, observations et verdicts.

| Hyp. | Ce qui devait s'observer | Ce qui s'observe | Verdict |
|---|---|---|---|
| H1 | Routage nettement meilleur que le hasard ; aucune question chiffrée en génération libre | Exactitude 0,857 ; p ≈ 3·10⁻⁷⁵ ; 0 déviation sur le gold | Corroborée |
| H2 | Aucun chiffre ni lien hors sources | 24/24 ; fidélité 3/3 ; liens tous dans R ∪ C ; refus 4/4 | Corroborée |
| H3 | Millisecondes sans LLM ; service maintenu en panne | Médiane 5 ms (contre 621 ms avec LLM) ; 0 erreur sous charge | Corroborée |

Le tableau 11 montre que les trois hypothèses résistent aux tentatives de réfutation prévues au § 1.5. Le mot est choisi : *corroborées* sur le périmètre évalué, non prouvées en général. Le chapitre suivant précise les bornes de cette conclusion.

---

# Chapitre 6 — Discussion

## 6.1 Ce que montrent les résultats

Le résultat central est que la fiabilité par construction fonctionne : sur l'ensemble du protocole, aucun chiffre et aucun lien n'est sorti des sources — non parce que le modèle a été bien incité, mais parce que l'architecture ne lui laisse pas de canal pour le faire. L'écart de latence entre voies déterministes et voies génératives (5 ms contre 621 ms en médiane) chiffre le bénéfice de l'ordonnancement du pipeline : la majorité des besoins réels est servie cent fois plus vite que par un passage systématique au LLM, et à coût nul. Enfin, le profil d'erreur du routeur illustre un principe de conception que nous assumons : une erreur résiduelle est acceptable à condition d'en maîtriser la direction — ici, l'erreur donne un chiffre exact sans explication, jamais l'inverse.

## 6.2 Limites

- *Couverture de la voie SQL.* Les gabarits couvrent les formes usuelles ; une question chiffrée imprévue passe par le repli LLM, dont l'exactitude n'est pas garantie par construction.
- *Taille du corpus.* Environ 25 documents : la qualité des explications est bornée par ce périmètre, encore modeste au regard de la production de l'ANSD.
- *Classe HYBRID.* Rappel de 0,533 au premier niveau. L'arbitrage LLM comble l'écart en production, mais la référence seule ne suffit pas pour cette classe.
- *Robustesse aux fautes.* La correction des questions mal orthographiées passe par le LLM ; sans fournisseur rapide, elle n'est plus assurée — le cœur du service, lui, reste fonctionnel.
- *Français uniquement.* Ni anglais, ni langues nationales (wolof, pulaar…), pourtant décisives pour l'inclusion.
- *Une seule instance.* Le passage à plusieurs instances exige d'externaliser l'état de session ; ce chantier est identifié mais non réalisé.
- *Portails sans lien de fichier public.* Quand l'adresse directe d'un fichier n'est pas publiée, le système renvoie vers la page du portail vérifiée — un clic de plus pour l'usager, mais aucune adresse devinée : c'est P2 appliquée jusqu'au bout.

## 6.3 Menaces à la validité

- *Validité interne.* Le jeu gold est petit (26 cas). Trois précautions en limitent les biais : il a été défini à partir des publications officielles et non des sorties du système, il s'exécute de façon déterministe, et les preuves utilisées par le contrôle de fidélité ne contiennent pas la réponse attendue. Le risque restant — ajuster involontairement le système à ses cas — est réduit par la couverture par capacités, pas éliminé.
- *Validité externe.* Les résultats valent pour l'écosystème ANSD. L'architecture et le protocole sont transférables à un autre office statistique, mais chaque instanciation (schéma, corpus, catalogue, liens) est à refaire et à réévaluer.
- *Validité de construit.* Notre mesure de fidélité hors ligne est un substitut strict mais partiel : elle contrôle exactement P1 (les nombres), pas la fidélité sémantique de l'ensemble de la réponse, qui demande un LLM juge (RAGAS complet, prévu en production). De même, le jeu de routage a été étiqueté par le concepteur ; les définitions écrites des classes limitent ce biais sans le supprimer.
- *Validité de conclusion.* Avec 328 exemples, le test du χ² a largement la puissance nécessaire. En revanche, les proportions parfaites du gold (24/24) ont, à cet effectif, des intervalles de confiance larges — d'où la formulation prudente retenue au § 5.7.

## 6.4 Éthique

Le système ne collecte aucune donnée personnelle, ses journaux sont anonymes et il n'embarque aucun traceur. Conformément aux principes de la statistique officielle [Nations Unies, 2014], il ne formule aucune interprétation politique : les questions d'opinion, électorales ou prédictives sont refusées par une règle fixe, qu'aucune manipulation du modèle ne peut contourner puisque le refus précède tout appel au modèle. Les données restent la propriété de l'ANSD ; l'assistant cite et renvoie vers les sources officielles plutôt que de s'y substituer.

---

# Chapitre 7 — Conclusion et perspectives

Ce mémoire est parti d'une contradiction : le langage naturel est la meilleure interface d'accès aux statistiques publiques, et les modèles qui le comprennent sont précisément ceux dont on ne peut pas accepter les inventions. Nous avons montré que cette contradiction se résout par l'architecture. Dans RAMA, le modèle de langage comprend, reformule et rédige ; il ne produit jamais un chiffre ni un lien. Un routeur à deux niveaux envoie chaque question vers la voie adaptée ; trois garanties — ancrage des chiffres, adresses vérifiées, refus sûr — sont tenues par la structure du système et testées à chaque modification du code.

Les mesures répondent aux trois questions de recherche. Le routage explicite fonctionne et son erreur résiduelle est orientée du côté sûr (QR1 : exactitude 0,857, association hautement significative). Sur tout le protocole, aucun chiffre ni lien n'est sorti des sources, sans que la conversation en souffre (QR2 : 24/24, 4/4, 3/3). Des composants classiques et légers suffisent : cinq millisecondes de médiane hors LLM, aucune erreur sous charge, service maintenu en cas de panne du fournisseur (QR3). L'ensemble est documenté par 90 décisions justifiées et livré prêt au déploiement.

Les prolongements sont ordonnés du plus direct au plus ambitieux. Remplacer le premier niveau du routeur par DeBERTa affiné, en visant la classe HYBRID, et calibrer le seuil d'arbitrage τ sur des données d'usage réel. Élargir le jeu de test, passer à l'évaluation RAGAS complète avec juge, et conduire une étude d'utilisabilité SUS auprès d'usagers réels de l'ANSD. Enrichir le corpus et automatiser sa mise à jour. Ouvrir l'interface à l'anglais puis aux langues nationales. Externaliser l'état pour passer à plusieurs instances. Enfin, instancier l'architecture sur un second office statistique : c'est le vrai test de sa généralité.

---

# Bibliographie

1. **Asai, A., Wu, Z., Wang, Y., Sil, A., Hajishirzi, H.** (2023). *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection.* arXiv:2310.11511.
2. **Brooke, J.** (1996). *SUS: A "quick and dirty" usability scale.* In *Usability Evaluation in Industry*, Taylor & Francis.
3. **Dijkstra, E. W.** (1965). *Solution of a problem in concurrent programming control.* Communications of the ACM, 8(9).
4. **Es, S., James, J., Espinosa-Anke, L., Schockaert, S.** (2024). *RAGAS: Automated Evaluation of Retrieval Augmented Generation.* EACL.
5. **Fedus, W., Zoph, B., Shazeer, N.** (2022). *Switch Transformers: Scaling to Trillion Parameter Models with Simple and Efficient Sparsity.* JMLR, 23.
6. **Gao, Y., Xiong, Y., Gao, X., et al.** (2023). *Retrieval-Augmented Generation for Large Language Models: A Survey.* arXiv:2312.10997.
7. **Grice, H. P.** (1975). *Logic and Conversation.* In *Syntax and Semantics, vol. 3: Speech Acts*, Academic Press.
8. **He, P., Liu, X., Gao, J., Chen, W.** (2021). *DeBERTa: Decoding-enhanced BERT with Disentangled Attention.* ICLR.
9. **Hevner, A. R., March, S. T., Park, J., Ram, S.** (2004). *Design Science in Information Systems Research.* MIS Quarterly, 28(1).
10. **Horvitz, E.** (1999). *Principles of Mixed-Initiative User Interfaces.* CHI.
11. **ISO/IEC** (2011). *ISO/IEC 25010:2011 — Systems and software engineering — SQuaRE — System and software quality models.*
12. **Janssen, M., Charalabidis, Y., Zuiderwijk, A.** (2012). *Benefits, Adoption Barriers and Myths of Open Data and Open Government.* Information Systems Management, 29(4).
13. **Ji, Z., Lee, N., Frieske, R., et al.** (2023). *Survey of Hallucination in Natural Language Generation.* ACM Computing Surveys, 55(12).
14. **Karpukhin, V., Oğuz, B., Min, S., et al.** (2020). *Dense Passage Retrieval for Open-Domain Question Answering.* EMNLP.
15. **Katsogiannis-Meimarakis, G., Koutrika, G.** (2023). *A Survey on Deep Learning Approaches for Text-to-SQL.* The VLDB Journal, 32.
16. **Kohavi, R.** (1995). *A Study of Cross-Validation and Bootstrap for Accuracy Estimation and Model Selection.* IJCAI.
17. **Lewis, P., Perez, E., Piktus, A., et al.** (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.* NeurIPS.
18. **Liu, N. F., Lin, K., Hewitt, J., et al.** (2023). *Lost in the Middle: How Language Models Use Long Contexts.* TACL, 12.
19. **Malkov, Yu. A., Yashunin, D. A.** (2018). *Efficient and Robust Approximate Nearest Neighbor Search using Hierarchical Navigable Small World Graphs.* IEEE TPAMI, 42(4).
20. **Nations Unies, Assemblée générale** (2014). *Fundamental Principles of Official Statistics.* Résolution A/RES/68/261.
21. **OWASP Foundation.** *OWASP API Security Top 10* et *Web Security Testing Guide.*
22. **Pourreza, M., Rafiei, D.** (2023). *DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction.* NeurIPS.
23. **Rebedea, T., Dinu, R., Sreedhar, M., Parisien, C., Cohen, J.** (2023). *NeMo Guardrails: A Toolkit for Controllable and Safe LLM Applications with Programmable Rails.* EMNLP (System Demonstrations).
24. **Reimers, N., Gurevych, I.** (2019). *Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks.* EMNLP.
25. **Robertson, S., Zaragoza, H.** (2009). *The Probabilistic Relevance Framework: BM25 and Beyond.* Foundations and Trends in Information Retrieval, 3(4).
26. **Salton, G., Wong, A., Yang, C. S.** (1975). *A Vector Space Model for Automatic Indexing.* Communications of the ACM, 18(11).
27. **Stolcke, A., Ries, K., Coccaro, N., et al.** (2000). *Dialogue Act Modeling for Automatic Tagging and Recognition of Conversational Speech.* Computational Linguistics, 26(3).
28. **Vakulenko, S., Longpre, S., Tu, Z., Anantha, R.** (2021). *Question Rewriting for Conversational Question Answering.* WSDM.
29. **World Wide Web Consortium (W3C)** (2018). *Web Content Accessibility Guidelines (WCAG) 2.1.*
30. **Yan, S.-Q., Gu, J.-C., Zhu, Y., Ling, Z.-H.** (2024). *Corrective Retrieval Augmented Generation.* arXiv:2401.15884.
31. **Yu, T., Zhang, R., Yang, K., et al.** (2018). *Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task.* EMNLP.
32. **Zhong, V., Xiong, C., Socher, R.** (2017). *Seq2SQL: Generating Structured Queries from Natural Language using Reinforcement Learning.* arXiv:1709.00103.

*(Sources de données : ANSD — RGPH-5 2023, EHCVM II 2021/2022, notes ENES, IHPC, comptes nationaux ; ANADS ; SES. La provenance détaillée figure dans la matrice de traçabilité, annexe A.)*

---

# Annexes

## Annexe A — Matrice de traçabilité des décisions

90 décisions au format *choix, alternatives, justification, référence* : voir `docs/JUSTIFICATIONS.md`. Extrait de deux entrées, pour donner la forme :

- **Décision 39 — voie SQL par gabarits d'abord.** *Alternatives :* génération de la requête par LLM à chaque question. *Justification :* schéma fermé et maîtrisé ; exactitude d'exécution garantie, latence en millisecondes, aucune requête arbitraire exécutée. *Référence :* [Yu et al., 2018] ; § 2.6.
- **Décision 36 — client LLM qui ne lève jamais d'erreur.** *Alternatives :* laisser l'erreur du fournisseur remonter jusqu'à l'usager. *Justification :* un incident réel (compte fournisseur sans crédit) rendait le service entier indisponible ; le repli local préserve la disponibilité, couvert par un test. *Référence :* § 4.5.

## Annexe B — Protocole et jeu de test

Jeu gold (`data/eval/gold.jsonl`, 26 cas), harnais (`scripts/evaluate.py`), rapport généré (`docs/EVALUATION.md`, `data/eval/report.json`). Extrait d'un cas :

```json
{"id": "pop_2023", "q": "Quelle est la population du Sénégal en 2023 ?",
 "route": "SQL", "contains": ["18 126 390"], "cap": "chiffre"}
```

## Annexe C — Guide du code

Explication complète et structurée de l'implémentation : `docs/guide-du-code.html`.

## Annexe D — Reproduction

```bash
# Construire la base et le routeur, puis évaluer (déterministe, hors ligne)
cd backend
python scripts/seed_db.py && python scripts/train_router.py
python -m pytest tests/test_system.py -q
python app/evaluation/evaluate_router.py   # routeur : CV 5 plis, matrice, chi2
python scripts/evaluate.py                 # jeu gold : exactitude, sécurité, latence

# Déploiement
cp .env.example .env        # renseigner la clé LLM
docker compose up -d --build
```

---

<div align="center">

*Mémoire de Master en Informatique — Université Gaston Berger de Saint-Louis — 2025/2026*

</div>
