# Texte de la présentation — RAMA (soutenance)

> Ce texte se lit d'un seul trait, du début à la fin : chaque diapo reprend le fil exact où la
> précédente l'a laissé. Il est aussi intégré, diapo par diapo, dans les **notes du présentateur**
> du fichier `Soutenance_RAMA.pptx`. Durée cible : 20 minutes + questions.
> Les diapos 28 à 31 sont des diapos de secours pour la séance de questions.

---

## Diapo 1 — Titre *(30 s)*

Monsieur le Professeur, Mesdames et Messieurs, bonjour, et merci de votre présence. Le travail que je vous présente s'appelle RAMA : un assistant conversationnel fiable pour l'accès aux statistiques publiques du Sénégal, construit sur les données de l'ANSD, sous la direction du Professeur Talibouya Diop. Il est né d'une ambition simple : que n'importe quel citoyen puisse demander un chiffre officiel aussi naturellement qu'il pose une question à un ami — et qu'il puisse, toujours, faire confiance à la réponse.

## Diapo 2 — Plan *(30 s)*

Pour vous convaincre que cette ambition est tenue, je suivrai le chemin même de la démarche scientifique : je poserai d'abord le problème et le verrou qui le rend difficile ; j'en tirerai des questions et des hypothèses réfutables ; je choisirai mes fondements méthodologiques en les comparant ; je vous montrerai la conception du système, puis le système lui-même, en direct ; et je terminerai par ce qui donne son poids à l'ensemble — l'évaluation. Commençons donc là où tout commence : le problème.

## Diapo 3 — Contexte *(1 min)*

Le Sénégal dispose, avec l'ANSD, d'une statistique publique remarquablement riche : des recensements, des enquêtes ménages, l'emploi, les prix, les comptes nationaux, et une archive de 285 opérations statistiques. Mais cette richesse a un revers : elle est dispersée — entre des rapports PDF, des portails, des fiches techniques. Si bien qu'aujourd'hui, pour trouver un chiffre, il faut déjà savoir comment le système statistique est organisé : la charge de la découverte pèse tout entière sur l'usager. L'idée vient alors d'elle-même — laissons-le poser sa question en français, à une intelligence artificielle. Et c'est ici, précisément, que le vrai problème commence.

## Diapo 4 — Le verrou : l'hallucination *(1 min 30)*

Car les modèles de langage — la technologie qui fait ChatGPT — portent une faille, et elle est rédhibitoire pour la statistique publique : l'hallucination. Ces programmes, entraînés sur d'immenses textes à prédire la suite la plus probable d'une phrase, écrivent admirablement ; mais quand ils ignorent la réponse, ils en fabriquent une — fluide, plausible, et fausse. Voyez l'exemple à l'écran : interrogé sur la population du Sénégal, un modèle seul répond « environ 17,2 millions » — sans source, invérifiable, peut-être périmé. RAMA répond 18 126 390 habitants : le chiffre exact du recensement de 2023, le RGPH-5, source à l'appui. La différence entre ces deux réponses, c'est tout l'enjeu de ce mémoire — un assistant public qui invente désinforme sous les couleurs de l'État. Voilà le verrou ; et de ce verrou découle directement ma question centrale.

## Diapo 5 — Question centrale et questions de recherche *(45 s)*

Comment rendre les statistiques accessibles en langage naturel, tout en garantissant — de façon vérifiable — que chaque chiffre et chaque lien provient d'une source officielle ? Cette question, je l'ai déclinée en trois questions de recherche : des voies de traitement spécialisées améliorent-elles la fiabilité ? peut-on garantir zéro hallucination par des mécanismes que l'on peut vérifier ? et le système peut-il rester rapide, robuste, sans matériel coûteux ? À chacune j'ai associé une hypothèse — car une hypothèse, en science, ne vaut que si l'on peut dire ce qui la réfuterait.

## Diapo 6 — Hypothèses falsifiables *(45 s)*

Chacune porte donc son critère de réfutation, affiché sur sa carte. H1 : router chaque question vers une voie spécialisée réduit l'erreur — elle tombe si le routeur ne fait pas mieux que le hasard. H2 : ancrer chaque fait dans une source structurée maintient l'hallucination à zéro — elle tombe au premier chiffre, au premier lien sorti des sources. H3 : des composants légers et déterministes suffisent — elle tombe si une panne du fournisseur d'IA emporte le service. L'évaluation, en fin d'exposé, rendra son verdict sur chacune. Mais pour bâtir, il faut d'abord choisir ses outils : trois fondements, que je vais définir, comparer, puis choisir au regard de notre contexte. Le premier répond à la plus élémentaire des questions — comment retrouver le bon document ?

## Diapo 7 — Fondement 1 : retrouver un document, TF-IDF *(1 min 30)*

La réponse classique s'appelle TF-IDF, et son idée est d'une élégante simplicité : le poids d'un mot, c'est sa fréquence dans le document multipliée par sa rareté dans la collection — la collection étant l'ensemble des documents où l'on cherche, pour nous les 285 fiches de l'archive ANADS. Regardez l'exemple : dans « je cherche les données sur la pêche au Sénégal », le mot « pêche » n'apparaît que dans quelques fiches — rare, il pèse lourd, et désigne exactement les bonnes ; le mot « Sénégal », présent presque partout, voit son poids tomber vers zéro. La méthode sait donc, d'elle-même, séparer ce qui compte de ce qui encombre. Face à elle, la recherche dense encode le sens des phrases en vecteurs : elle reconnaît les synonymes, mais réclame un modèle neuronal, un processeur graphique, et ses décisions s'expliquent mal. Notre contexte tranche sans hésitation — corpus petit, vocabulaire stable, pas de GPU : ce sera TF-IDF, enrichi d'expansions thématiques pour couvrir les synonymes. Nous savons désormais retrouver le bon document ; encore faut-il en tirer une réponse rédigée — c'est l'affaire du deuxième fondement.

## Diapo 8 — Fondement 2 : le RAG *(1 min)*

Le RAG — la génération augmentée par la récupération — procède en deux temps : un récupérateur extrait de la base documentaire les passages pertinents, puis le modèle rédige en s'appuyant uniquement sur eux, et en les citant. Le renversement est décisif : le modèle ne répond plus de mémoire, il répond documents en main. Le schéma le montre sur une vraie question — « comment mesure-t-on la pauvreté ? » : deux passages remontent du corpus, et la réponse s'écrit à partir d'eux, pas ailleurs. Retenez surtout ceci, car tout mon dispositif de sûreté en découle : ces passages sont conservés comme preuves, et un garde-fou vérifiera que chaque nombre de la réponse y figure. Le RAG sait expliquer ; mais pour livrer un chiffre exact, il faut une garantie plus forte encore — et c'est le troisième fondement.

## Diapo 9 — Fondement 3 : le Text-to-SQL par gabarits *(1 min)*

Le chiffre exact vit dans une base de données ; SQL est le langage qui l'interroge ; le Text-to-SQL traduit la question française en requête. L'état de l'art confie cette traduction au modèle lui-même — indispensable quand la base est immense et inconnue. Mais la nôtre est tout l'inverse : petite, fermée, entièrement maîtrisée. Alors j'ai fait le choix des gabarits : des requêtes à trous, écrites et testées à l'avance. Suivez le chemin à l'écran : la forme « population de telle région en telle année » est reconnue, les paramètres extraits, la requête pré-écrite s'exécute en lecture seule, et le résultat exact est mis en phrase. Exactitude garantie, vitesse, sécurité — tout à la fois. Voilà mes trois fondements posés. Restait à décider lequel employer ; et la réponse honnête est : aucun ne suffit seul.

## Diapo 10 — Positionnement *(45 s)*

Le tableau en fait la démonstration, en croisant chaque architecture candidate avec nos exigences. Le modèle seul écrit bien, mais invente — la fiabilité s'effondre. Le RAG seul explique bien, mais ne garantit ni les chiffres ni les liens. Le Text-to-SQL seul donne le chiffre exact, mais n'explique rien. Chaque brique possède précisément la force qui manque aux autres — et c'est là que réside l'apport de RAMA : non pas inventer une brique de plus, mais les composer, avec des garanties par construction et une évaluation reproductible. Voici cette composition.

## Diapo 11 — Architecture *(1 min)*

Cinq couches, de haut en bas : l'interface web, où l'usager écrit ; l'API, qui protège le service ; l'orchestrateur, qui déroule le traitement ; six voies de réponse spécialisées, adossées à un client d'IA interchangeable ; et, tout en bas, ce sur quoi repose la fiabilité entière du système — les données d'ancrage : une base SQLite en lecture seule, un corpus de documents, le catalogue des 285 fiches, des liens vérifiés. Trois principes gouvernent l'ensemble : emprunter d'abord le chemin le plus sûr et le moins coûteux ; ne jamais laisser le modèle toucher aux faits ; superposer les défenses. Le premier de ces principes mérite d'être vu en action — c'est le pipeline.

## Diapo 12 — Pipeline *(1 min)*

Toute question, sans exception, traverse la même chaîne de neuf étapes, ordonnée du traitement le moins coûteux au plus coûteux. Un simple « bonjour » — l'acte social — sort dès la première étape, en une milliseconde. Viennent ensuite la correction des fautes, la résolution des questions de suivi, le garde-fou d'entrée, le cache, la détection des demandes de données, le routage, le garde-fou de sortie, l'enrichissement des liens. Et voyez les sorties anticipées, en bas du schéma : elles règlent la majorité des requêtes sans un seul appel au modèle. Au centre de cette chaîne se joue la décision la plus importante — vers quelle voie envoyer la question ? C'est le rôle du routeur.

## Diapo 13 — Routeur : formalisation *(1 min 15)*

Trois classes s'offrent à lui : SQL quand on attend un chiffre, RAG quand on attend une explication, HYBRID quand on attend les deux. Son fonctionnement tient en deux mouvements : la question est vectorisée par TF-IDF — le même outil que tout à l'heure, appliqué aux mots et aux fragments de mots, ce qui le rend robuste aux fautes — puis une régression logistique, un classifieur statistique simple, attribue une confiance à chaque classe. La règle de décision est à l'écran : si la confiance maximale atteint le seuil τ = 0,85, la classe est retenue ; sinon, un arbitrage par le modèle, à réponse contrainte, tranche. Ce seuil, je l'ai fixé a priori ; et l'expérience montrera — nous le verrons — que l'incertitude se concentre exactement là où cet arbitrage a de la valeur. Le routeur choisit donc la voie. Mais ce qui rend chaque voie sûre, ce sont trois garanties — et nous touchons ici au cœur de ce mémoire.

## Diapo 14 — Garanties P1–P3 *(1 min 15)*

P1, l'ancrage des chiffres : tout nombre de la réponse figure dans les preuves. P2, aucune adresse inventée : toute URL appartient aux 31 ressources vérifiées ou aux 285 fiches du catalogue. P3, le refus sûr : une question hors périmètre ou malveillante est refusée avant tout appel au modèle. Mais l'essentiel n'est pas leur énoncé — c'est la manière dont elles sont tenues : par construction, et non par espérance. Les chiffres sont copiés depuis la source, puis mis en phrase : le générateur ne calcule jamais. Les liens sont injectés après la génération, par un composant qui ne puise que dans les sources vérifiées : le modèle n'a, littéralement, aucun canal pour émettre une adresse. On n'espère pas que le système soit fiable — on l'a construit pour qu'il ne puisse pas être autre chose. Telle est la conception ; sa réalisation obéit à une règle unique.

## Diapo 15 — Réalisation *(45 s)*

Chaque composant est le plus simple qui satisfasse l'exigence. Python et FastAPI pour le service, scikit-learn pour le routeur, SQLite en lecture seule, une page web unique sans dépendance externe, un client d'IA au standard ouvert — les fournisseurs sont interchangeables. Au total : deux mille lignes de cœur en modules à responsabilité unique, quarante-six tests, zéro secret dans l'image Docker, et quatre-vingt-dix décisions techniques tracées — pour chacune, le choix, les alternatives, la justification, la référence. Cette simplicité n'est pas une coquetterie : elle sert un but — un système public doit continuer de servir, même quand tout va mal.

## Diapo 16 — Dégradation gracieuse *(45 s)*

J'en ai fait un contrat : le client d'IA ne lève jamais d'erreur. Le fournisseur tombe, le quota s'épuise ? Le système bascule vers le fournisseur de secours, puis vers un moteur local déterministe. Un sémaphore borne les appels simultanés ; un mode éclair coupe le superflu dès que le fournisseur ralentit. Et surtout, retenez ceci : les garanties P1 à P3 ne dépendent d'aucun appel au modèle. Une panne dégrade le confort — jamais la fiabilité. Mais tout cela reste des schémas ; le plus convaincant est encore de voir le système répondre.

## Diapo 17 — Démonstration *(5 min)*

Huit questions, chacune choisie pour démontrer un mécanisme : le salut, qui sort en une milliseconde ; le chiffre exact, ancré dans la base ; le suivi conversationnel — « et à Thiès ? » ; les données de la pêche, avec leurs fiches cliquables vérifiées ; le refus d'une question électorale, prononcé avant tout appel au modèle ; le refus d'une injection ; la correction d'une question truffée de fautes ; et une explication sourcée. Puis, pour finir, je couperai la clé du fournisseur d'IA — et vous verrez le service continuer. À ce stade, le système fonctionne ; il reste à le prouver, avec la même rigueur que tout le reste. C'est l'évaluation.

## Diapo 18 — Protocole d'évaluation *(1 min)*

Son protocole tient sur trois instruments, tous rejouables à l'identique. Un jeu de test de 26 cas, construit à partir des publications officielles — jamais à partir des sorties du système : aucune circularité. La validation croisée du routeur, que le schéma rappelle : les questions sont partagées en cinq parts, et chacune est testée, une fois, par un modèle qui ne l'a jamais vue. Un test de charge, enfin. Et l'ensemble est branché sur l'intégration continue : la moindre régression bloque la livraison — l'évaluation n'est pas une photographie, c'est un invariant du projet. Avant de lire les résultats, assurons-nous de parler le même langage : que mesurent exactement ces métriques ?

## Diapo 19 — Métriques : définitions *(1 min)*

La précision d'une classe : parmi les questions envoyées vers elle, la part qui lui appartenait vraiment. Le rappel : parmi les questions de la classe, la part qui lui est bien parvenue. Le F1 combine les deux, et n'est élevé que si les deux le sont ; sa moyenne macro donne le même poids aux trois classes — indispensable, car la plus rare est aussi la plus difficile. Pour la voie SQL, l'exactitude d'exécution : la requête produit-elle le même résultat que la référence ? Pour la vitesse, la médiane et le 95ᵉ centile. Armés de ces définitions, lisons les résultats — le routeur d'abord.

## Diapo 20 — Résultats : routeur *(1 min 15)*

Sur 328 questions en validation croisée : une exactitude de 0,857 — six questions sur sept — et un F1 macro de 0,805. Le test du khi-deux écarte le hasard avec une valeur p de l'ordre de 10 puissance moins 75 : cette performance ne doit rien à la chance. La matrice de confusion, elle, localise l'erreur : RAG et SQL sont bien séparées ; HYBRID n'est reconnue qu'une fois sur deux. Et ce résultat, loin de m'embarrasser, est instructif : « un chiffre et une explication à la fois » est un caractère que les mots seuls ne montrent pas. La conception y répond déjà, deux fois : l'arbitrage du second niveau est posé exactement sur cette zone, et un modèle plus fin — DeBERTa — remplacera le premier niveau en production. Notons enfin que l'erreur résiduelle penche du bon côté : HYBRID confondue avec SQL donne le chiffre exact sans l'explication — jamais l'inverse. Après le routeur, le système complet.

## Diapo 21 — Résultats : système complet *(1 min)*

Sur le jeu de test : 24 sur 24 en exactitude fonctionnelle, 4 sur 4 en sécurité, 3 sur 3 en fidélité, 15 sur 15 en exécution SQL. Sous une charge de 40 requêtes simultanées : zéro erreur — l'excédent est refusé proprement, sans jamais faire tomber le service. Et sur l'ensemble du protocole, pas un chiffre, pas un lien n'est sorti des sources : P1, P2 et P3 tiennent. Reste une dernière mesure — la vitesse.

## Diapo 22 — Latence *(45 s)*

Une milliseconde pour les salutations et les refus ; trois à cinq pour les voies documentaires et SQL ; treize pour le RAG. Médiane globale : cinq millisecondes sans fournisseur d'IA, contre 621 avec. Deux ordres de grandeur d'écart — et c'est la justification chiffrée de l'ordre du pipeline : le moins coûteux d'abord. Toutes les mesures sont désormais sur la table ; confrontons-les aux hypothèses.

## Diapo 23 — Verdicts *(45 s)*

H1 : le routage fait significativement mieux que le hasard, et aucune question chiffrée n'a été déviée — corroborée. H2 : aucun chiffre, aucun lien hors des sources — corroborée. H3 : des millisecondes sans modèle, un service maintenu sous charge comme en panne — corroborée. Et je pèse le mot : corroborées sur le périmètre évalué, non prouvées en général — les menaces à la validité sont discutées au chapitre 6 du mémoire. De ces verdicts, je tire trois apports.

## Diapo 24 — Ce qui distingue RAMA *(45 s)*

D'abord, des garanties par construction, et non par espérance : le modèle n'a aucun canal pour produire un fait. Ensuite, des preuves, et non des promesses : chaque chiffre de cet exposé provient d'une exécution que vous pouvez rejouer. Enfin, une ingénierie argumentée : quatre-vingt-dix décisions tracées, quarante-six tests, un déploiement sans GPU. Mais dire ce qui distingue oblige, en science, à dire aussi ce qui limite.

## Diapo 25 — Limites *(45 s)*

Et ces limites, je les assume, car elles sont bornées. La couverture SQL s'arrête aux gabarits — la longue traîne passe par le repli. Le rappel de la classe HYBRID plafonne à 0,533 au premier niveau. Le corpus compte environ 25 documents ; le français est la seule langue ; une seule instance tourne. Côté validité : le jeu de test est modeste, mais indépendant ; les résultats sont propres à l'ANSD, même si l'architecture est transférable ; la fidélité est approchée par les nombres — RAGAS, le cadre d'évaluation complet, viendra en production. Ces limites posées, je peux conclure.

## Diapo 26 — Conclusion *(45 s)*

Ce mémoire montre qu'une contradiction apparente — le langage naturel d'un côté, la rigueur statistique de l'autre — se résout par l'architecture. Dans RAMA, le modèle comprend, reformule, rédige ; il ne produit jamais un chiffre, jamais un lien. Et les résultats le confirment : 0,857 au routage, 24 sur 24 au jeu de test, zéro hallucination observée, cinq millisecondes de médiane. Le système est conteneurisé, documenté, prêt à être déployé. Il ne reste qu'à regarder devant.

## Diapo 27 — Perspectives et remerciements *(30 s)*

Du plus proche au plus ambitieux : DeBERTa sur la classe HYBRID et la calibration du seuil ; une évaluation élargie — RAGAS, et une étude auprès d'usagers réels ; un corpus enrichi ; l'anglais, puis les langues nationales ; le passage à plusieurs instances ; et, un jour, l'instanciation sur un second office statistique — le véritable test de généralité. Monsieur le Professeur, Mesdames et Messieurs, merci de votre attention.

---

## Diapos de secours (séance de questions)

- **28 — Algorithme du pipeline** : les dix lignes telles qu'implémentées, à ouvrir si la discussion porte sur l'ordonnancement, le cache ou la concurrence.
- **29 — Garantie P2 dans le code** : l'extrait de la liaison automatique, à ouvrir si l'on demande « comment être sûr qu'aucune URL n'est inventée ? ».
- **30 — Chiffres complets** : résultats par capacité et latences par voie, avec les commandes de reproduction.
- **31 — Base et fichiers de données** : le schéma réel de la base et l'arborescence des fichiers, à ouvrir si l'on demande d'où viennent les données.
