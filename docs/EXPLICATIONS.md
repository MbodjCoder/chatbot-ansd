# EXPLICATIONS — Améliorations vers un produit de qualité industrielle

> Ce document explique, de manière **claire, simple et scientifique**, les
> améliorations apportées au système RAMA-ANSD après l'audit complet du code,
> et **pourquoi** chacune est nécessaire. Il complète `JUSTIFICATIONS.md` (qui
> trace les décisions de conception) en se concentrant sur la **qualité
> logicielle, la performance et la robustesse** — les propriétés qui séparent
> un prototype fonctionnel d'un service prêt pour tous les usagers.

## Contexte : de la démonstration au service

Un prototype de mémoire doit prouver une idée ; un **service public** doit tenir
la charge de nombreux usagers simultanés, rester disponible, et offrir une
expérience fluide. L'audit a identifié un écart entre les deux. Les
améliorations ci-dessous comblent cet écart, classées par gravité (P0 = bloquant
en production, P1 = qualité importante, P2 = maturité produit).

Chaque amélioration suit le principe directeur du projet : **corriger une classe
entière de problèmes, pas un cas isolé**, et **ne jamais affaiblir les garanties
scientifiques** (anti-hallucination, déterminisme, dégradation gracieuse).

---

## P0 — Défauts bloquants en production

### P0-1. Sûreté d'accès concurrent (thread-safety)

**Le problème.** Le serveur (FastAPI/Uvicorn) traite les requêtes des usagers
dans un *pool de threads*. Or l'état partagé du chatbot — les sessions de
conversation, le cache de réponses, le compteur anti-abus — était stocké dans
des dictionnaires Python modifiés **sans protection**. Quand deux usagers
écrivent « en même temps » dans le même dictionnaire, Python peut lever
`RuntimeError: dictionary changed size during iteration` et faire tomber la
requête, ou corrompre le cache.

**Pourquoi c'est grave.** C'est précisément le scénario cible : « un chatbot pour
l'ensemble des utilisateurs ». Le défaut n'apparaît jamais en test mono-usager,
mais surgit dès la mise en service.

**La correction.** Un **verrou de réentrance** (`threading.RLock`) protège toute
lecture/écriture de l'état partagé. C'est le mécanisme d'exclusion mutuelle
classique (Dijkstra, 1965) : une seule section critique s'exécute à la fois,
garantissant la cohérence. Le verrou est de granularité fine (il n'entoure que
les accès à l'état, pas le calcul de la réponse) pour ne pas sérialiser tout le
trafic.

**Limite assumée et voie d'industrialisation.** Un verrou en mémoire suffit pour
un déploiement **mono-instance**. Pour plusieurs instances (montée en charge
horizontale), l'état doit être externalisé dans un magasin partagé (Redis). Le
code isole l'état derrière une petite couche (`SessionStore`) pour rendre cette
substitution triviale — application du principe d'inversion de dépendance.

### P0-2. Streaming réel des réponses

**Le problème.** L'affichage « progressif » simulait le flux : le serveur
calculait la réponse **complète**, puis la découpait artificiellement. Avec un
modèle rapide distant, l'usager subissait un silence égal au temps de génération
totale avant le moindre mot.

**Pourquoi ça compte.** Le *délai avant le premier mot* (time-to-first-token) est
le déterminant n°1 de la latence **perçue** (Nielsen, limites de temps de
réponse). Les assistants de référence streament les mots réels dès qu'ils sont
produits.

**La correction — et sa subtilité scientifique.** Streamer les mots d'un LLM
*avant* vérification entrerait en conflit avec notre garantie anti-hallucination
(un chiffre faux ne doit jamais s'afficher, même une seconde). La solution
respecte les deux exigences :

- Les **chiffres** proviennent de la voie SQL déterministe : ils sont calculés
  et **validés** avant tout affichage (inchangé).
- Seule la **prose méthodologique abstractive** (voie RAG en mode production) est
  streamée mot à mot, car elle ne contient pas de statistique brute non vérifiée.
- Le rail de fidélité numérique s'applique au texte assemblé ; en cas d'échec,
  le client remplace le texte par le message de prudence (streaming *optimiste*
  avec repli).

Sur configuration locale lente (mode éclair), les réponses sont déjà instantanées
(déterministes) : le streaming réel bénéficie surtout aux fournisseurs rapides
(Groq, DeepSeek). Le comportement s'adapte donc automatiquement au fournisseur.

---

## P1 — Qualité et robustesse

### P1-3. Élimination du retrieval redondant

**Le problème.** Sur chaque question documentaire, la recherche de passages
s'exécutait **deux fois** : une fois pour générer la réponse, une fois pour
constituer la preuve du rail de fidélité. Coût doublé pour un résultat identique.

**La correction.** Le pipeline RAG renvoie désormais les passages qu'il a
utilisés ; la preuve réutilise ces passages. Un seul calcul. Gain direct de
latence et de coût sur toute la voie RAG, sans changer le résultat.

### P1-4. Guardrail de domaine plus intelligent

**Le problème.** Le filtre qui garde le chatbot « dans son domaine » reposait sur
une **liste de mots-clés**. Deux défauts classiques :
1. *Faux négatifs* : une question légitime sans mot-clé listé était rejetée
   (« Combien de naissances en 2020 ? » — « naissances » n'était pas listé).
2. *Faux positifs* par sous-chaîne (« parasite » contient « site »).

**La correction.** Approche **hybride, défense en profondeur** : la liste de
mots (rappel élevé, précision faible) est complétée par le **classifieur de
routage** déjà entraîné. Une question est acceptée si elle contient un indice de
domaine **ou** si le routeur la classe avec une confiance suffisante vers une
voie statistique. On combine ainsi rappel et précision. Le matching se fait sur
mots entiers (fin des faux positifs par sous-chaîne).

### P1-5. Persistance de la conversation

**Le problème.** Au rafraîchissement de la page, toute la conversation
disparaissait — rupture d'expérience.

**La correction.** La conversation et l'identifiant de session sont conservés
côté navigateur (`localStorage`) et restaurés au chargement. Aucune donnée
personnelle n'est stockée (Principe 6 de la statistique officielle), seulement le
fil de questions/réponses de l'usager, sur son propre appareil.

---

## P2 — Maturité produit

### P2-6. Intégration continue (CI)

Un flux d'intégration continue (GitHub Actions) exécute automatiquement, à chaque
modification, la suite de tests, le scan de qualité et l'évaluation SQL. Principe
d'ingénierie : **aucune régression ne doit atteindre la branche principale sans
être détectée**. Cela transforme les garanties ponctuelles en garanties
permanentes.

### P2-7. Observabilité (endpoint de métriques)

Un service se pilote par la mesure. Un endpoint `/api/metrics` agrège la
télémétrie déjà collectée : nombre d'interactions, répartition des voies,
latence, taux de refus des guardrails, satisfaction (👍/👎). Ces indicateurs
alimentent directement l'évaluation quantitative du mémoire (et le protocole
SUS).

### P2-8. Protection de l'endpoint de feedback

Le point d'entrée des retours utilisateurs était sans limite de débit : un
script pouvait polluer le journal. La même limitation par fenêtre glissante que
les autres endpoints y est appliquée (bonnes pratiques OWASP API Security).

### P2-9. Modernisation du chemin de production

Le retriever de production (BGE-M3 + Qdrant) utilisait un appel déprécié
(`recreate_collection`). Il est remplacé par l'API à jour, afin que la bascule
vers la production reste réellement fonctionnelle et non seulement théorique.

---

## Correctif de latence — le dernier appel LLM non borné

**Le symptôme.** Certaines questions étaient anormalement lentes (60-90 s) pour
finir sur « aucune donnée » — par exemple « Quelle est le premier président du
Sénégal ? » (une question historique, pas une statistique).

**La cause.** Cette question passe le filtre de domaine (elle contient
« Sénégal »), est routée vers la voie SQL, mais ne correspond à aucun gabarit.
La voie SQL basculait alors sur la **génération LLM** (DIN-SQL). Or, sur un
modèle local lent (Ollama sur processeur), cet appel prend une minute — pour
produire une requête sans résultat. C'était le **seul** appel LLM du pipeline
qui ignorait le « mode éclair » : toutes les autres voies (documentaire,
routage, réécriture, synthèse) l'appliquaient déjà.

**La correction.** La voie SQL respecte désormais le même principe : sur un
fournisseur local lent, elle n'utilise que ses **gabarits déterministes** ;
si aucun ne correspond, elle répond immédiatement par un message honnête
(« Je n'ai pas trouvé cette information dans la base de données. Reformulez… »).
Mesuré : **20 ms** au lieu de 60-90 s. Sur un fournisseur rapide (Groq), le
repli DIN-SQL reste actif pour couvrir les formulations rares.

**Effet de bord bénéfique.** Après ce correctif, **toutes** les voies sont
déterministes sur la configuration locale : le chatbot répond uniformément en
quelques millisecondes à n'importe quelle question. La rédaction abstractive
par LLM ne s'active qu'avec un fournisseur rapide (Groq/DeepSeek), comme prévu
par la décision #43.

## Élargissement de la base de connaissance

**Le problème signalé.** « Où se trouve l'ANSD ? » répondait « Information non
disponible » alors que l'adresse figure dans le corpus, et proposait un lien
sans rapport (un rapport EHCVM). Plus largement, la base couvrait peu de
contenu face à l'écosystème ANSD/ANADS réel.

**Les causes (trois défauts distincts).**
1. *Récupération trop faible sur les questions courtes* : le TF-IDF par mots
   ne trouvait pas l'adresse (« où se trouve l'ANSD » partage peu de mots avec
   « Rocade Fann Bel-Air »).
2. *Chunks incohérents* : la FAQ, découpée par simple fenêtre de mots, mélangeait
   plusieurs sujets dans un même morceau → l'extraction piochait des phrases
   hors sujet.
3. *Lien dérivé d'un document rejeté* : quand l'extraction échouait, le système
   proposait quand même un lien tiré du document non pertinent.

**Les corrections.**
- **Récupération renforcée** : on combine désormais les n-grammes de *mots* et
  de *caractères* (comme le routeur), avec repli d'accents — robuste aux
  questions courtes et aux variantes d'écriture.
- **Chunking sémantique** : les documents sont découpés d'abord par *section*
  (titres), de sorte que chaque sujet forme une unité cohérente.
- **Extraction fiabilisée** : on écarte les titres-questions d'une FAQ (qui
  matchent la requête sans porter la réponse), on rejoint les lignes coupées par
  la mise en forme (sinon la réponse était tronquée : « se trouve à… »), et on
  ne propose aucun lien si l'extraction échoue.
- **Récolte de contenu réel** : deux scripts reproductibles ajoutent au corpus
  le contenu véritable du site (`harvest_web.py` : 8 pages nettoyées de leur
  menu/pied de page) et de PDF officiels (`harvest_pdf.py` : 3 notes en prose,
  via pypdf). Chaque document garde son URL source. Le corpus passe de 12 à
  **23 documents** ; les 285 études de l'ANADS restent couvertes par le
  catalogue (voie CATALOG).

**Résultat.** « Où se trouve l'ANSD ? » répond désormais « L'ANSD… se trouve à
Dakar, au Sénégal » avec le lien Contact ; « Comment contacter l'ANSD ? » donne
le téléphone et l'email. La qualité rédactionnelle optimale sur les questions
**libres** du contenu élargi s'obtient avec un LLM rapide (Groq) ; en mode
déterministe local, les voies structurées (chiffres SQL, navigation, catalogue,
FAQ) restent fiables et instantanées.

## Compréhension des questions mal écrites (fautes de frappe, orthographe, grammaire)

**Le besoin.** Un service public reçoit des questions telles qu'elles sont
tapées : « cé koi la BDEF », « coment lansd mesure la pauvrete », « kel é le to
de chaumage a dakr ». Le système doit les comprendre.

**La solution.** Avec un fournisseur rapide (Groq), une étape de
**normalisation** corrige la question **avant** tout le reste du pipeline :
elle passe par le LLM avec une consigne stricte (corriger uniquement les
fautes, préserver le sens, ne pas répondre). Exemples réels obtenus :
- « kel é le to de chaumage a dakr en 2024 » → « Quel est le taux de chômage à Dakar en 2024 ? »
- « cé koi la BDEF » → « Qu'est-ce que la BDEF ? »
- « ou se trouv l'ansd » → « Où se trouve l'ANSD ? »

**Pourquoi en amont.** Corriger la question une seule fois, tôt, rend
**l'ensemble** du pipeline robuste (filtre de domaine, routage, gabarits SQL,
récupération documentaire) — au lieu de durcir chaque composant séparément.
Des garde-fous encadrent le LLM (contrôle de longueur, rejet d'une réponse
« méta », repli sur la question d'origine en cas de doute). L'étape est
désactivée sur un modèle local lent, pour ne pas ajouter de latence.

**Effet sur le style.** Le même LLM (Groq) rédige désormais les réponses
documentaires : structurées, en gras sur les chiffres clés, dans un français
soigné, à partir du contenu réel récolté. La réponse à « cé koi la BDEF »,
impossible en mode déterministe, devient une synthèse claire. Streaming réel
des mots confirmé de bout en bout (253 fragments en temps réel sur une
question à fautes).

## Durcissement : forte charge, réseau faible, sécurité

Audit ciblé sur trois scénarios de service réel : **beaucoup d'usagers en même
temps**, **réseau faible**, et **failles de sécurité**. Huit correctifs.

### Forte charge (montée en usage)

- **Mémoire bornée (S1/S2).** Les dictionnaires de sessions et du rate-limiter
  pouvaient croître sans limite si un client envoyait des milliers d'identifiants
  ou d'IP uniques (déni de service par épuisement mémoire). Désormais : cap dur
  des sessions (éviction LRU), purge des IP inactives, et validation de
  l'identifiant de session fourni par le client. L'empreinte mémoire est finie
  (vérifié par un test qui inonde au-delà du cap).
- **Concurrence sur la même session (S1).** Deux requêtes simultanées d'un même
  usager (double-clic, flux + requête) pouvaient corrompre son historique. Les
  mutations passent maintenant par une section critique verrouillée.
- **Sémaphore LLM (S5).** Sous forte charge, un nombre illimité d'appels
  simultanés au fournisseur (Groq) déclencherait une avalanche de rejets (429).
  Un sémaphore borne les appels distants simultanés (6 par défaut) ; l'excédent
  attend brièvement, et si la saturation persiste, le repli local prend le relais.
- **Résultat mesuré** : sous 40 requêtes simultanées, 30 servies et 10 limitées
  proprement (429, comportement voulu du rate-limit par IP), **zéro erreur 500,
  zéro plantage**.

### Réseau faible

- **Repli rapide (S3).** Le timeout du LLM était de 60 s, répété plusieurs fois
  (jusqu'à ~3 minutes d'attente avant de basculer en local). Réduit à **20 s et
  une seule tentative** : sur réseau faible, le repli local intervient en
  quelques secondes (mesuré < 12 s) au lieu de faire patienter l'usager.
- **Minuteur côté navigateur (S8).** Une requête qui n'aboutit pas est
  abandonnée après un délai, avec un message clair (« connexion lente ou
  indisponible ») plutôt qu'un chargement infini. Pendant un flux en cours,
  chaque fragment reçu relance le minuteur — on ne coupe jamais une réponse qui
  progresse.

### Sécurité

- **Aucune fuite d'information (S4/S7).** Un gestionnaire d'exception global
  garantit qu'aucune erreur inattendue ne renvoie de trace interne ou de code
  500 brut : l'usager reçoit un message neutre, l'incident est journalisé côté
  serveur. `/health` n'expose qu'un booléen de santé du LLM, pas le détail de
  l'erreur (URL, pile).
- **CORS et proxy (S6).** Les origines autorisées sont configurables (à
  restreindre au domaine ANSD en production). L'en-tête `X-Forwarded-For` n'est
  pris en compte que derrière un proxy de confiance déclaré — sinon un client
  pourrait usurper son IP pour contourner le rate-limit.

Chaque correctif est couvert par un test (`test_system.py`,
`test_llm_integration.py`) et n'affecte pas les garanties existantes.

## Refonte de l'interface (qualité produit)

**L'état de départ.** L'accueil affichait une carte plate en haut à gauche,
laissant un grand vide au centre, et des suggestions en pilules génériques —
fonctionnel mais loin d'un produit soigné.

**La refonte.** L'écran d'accueil devient un **hero centré** : logo, accroche
« Bonjour, je suis RAMA », sous-titre explicatif, et **quatre cartes d'amorce**
(icône + titre + indice) qui présentent d'un coup d'œil ce que le système sait
faire — un chiffre, une comparaison, une méthode, un document. Cliquer une
carte lance la question. La typographie, les ombres (deux niveaux), un léger
halo et une pastille de statut donnent de la profondeur ; le champ de saisie
est plus proéminent. Les thèmes clair et sombre sont affinés et cohérents, et
la mise en page est responsive (les cartes s'empilent sur mobile).

**Pourquoi.** La première impression et la lisibilité influent sur la confiance
et l'usage autant que la fonction (effet esthétique-utilisabilité). Un état
vide **guidé** réduit le coût de démarrage : l'usager voit immédiatement quoi
demander. L'accessibilité est préservée (focus visibles, `prefers-reduced-motion`,
attributs ARIA, contrastes validés). La logique métier n'est pas touchée : la
refonte est purement présentationnelle.

## Liens cliquables au fil du texte (entity linking)

**Le besoin.** Quand une réponse cite « l'Annuaire statistique du Sénégal »,
« la plateforme Open Data », « ANADS » ou « contacter l'ANSD », ces noms
devraient être **cliquables** et mener directement à la page ou au document
correspondant — pas seulement figurer en cartes séparées sous la réponse.

**La solution.** Un post-traitement transforme les mentions de ressources
officielles en liens : il repère les noms connus (motifs tolérants aux
accents) et les relie aux **URLs vérifiées** de `resources.json`. Règles :
première occurrence de chaque entité, sans chevauchement, sans jamais retoucher
un lien que le modèle a lui-même produit, et **jamais un chiffre**. Le frontend
rend ces liens en vert accentué avec une icône « ↗ ». Exemple réel obtenu :
dans la réponse sur la pêche, « ANADS », « microdonnées », « Plateforme Open
Data », « Annuaire statistique du Sénégal », « site officiel de l'ANSD » et
« www.ansd.sn » sont tous devenus cliquables.

**Pourquoi c'est sûr.** Le lien n'est jamais inventé : il provient toujours de
la base de liens vérifiés (HTTP 200). C'est le prolongement, au fil du texte,
de la garantie « aucune URL hallucinée » des cartes de liens. Cette
fonctionnalité **complète** les cartes (elle ne les remplace pas).

## Ce qui n'a PAS changé (et pourquoi)

Les fondations validées par l'encadrant restent intactes : architecture hybride
RAG + Text-to-SQL, garanties anti-hallucination, routage à deux niveaux,
dégradation gracieuse. Les améliorations ci-dessus sont **périphériques au cœur
scientifique** : elles renforcent la qualité de service sans toucher aux choix de
conception justifiés dans `JUSTIFICATIONS.md`.

---

*Chaque amélioration est vérifiée par la suite de tests (`test_system.py`), le
scanner de qualité (`scan_qualite.py`) et, le cas échéant, un test de
non-régression dédié. Journal détaillé des vérifications à la fin de ce
document.*

## Bonus sécurité : protection de la clé API

Constat pendant l'audit : `backend/.env` contient une clé API réelle. Un fichier
`.gitignore` a été ajouté pour **exclure `.env` de tout dépôt** (tout en gardant
`.env.example`), ainsi que les artefacts générés (base, logs, modèle). Publier une
clé dans un dépôt Git est une fuite de secret classique et grave ; la protection
est désormais structurelle.

## Journal de vérification

Toutes les vérifications ci-dessous en **mode démo** (déterministe, reproductible).

| Amélioration | Test / vérification | Résultat |
|---|---|---|
| P0-1 thread-safety | `test_concurrence_thread_safe` (12 threads × 15 req) + stress 600 req | 0 erreur |
| P0-2 streaming réel | `test_streaming_voie_abstractive` (12 fragments RAG, 0 en SQL) + SSE HTTP | flux réel confirmé |
| P1-3 double retrieval | `answer()` renvoie les chunks, preuve réutilisée | 1 seul retrieval |
| P1-4 guardrail hybride | `test_guardrail_domaine_hybride` (13 cas : légitimes acceptés, hors-domaine + « parasite » rejetés) | 13/13 |
| P1-5 persistance | `restaure()` rebuild du transcript (localStorage), `?q=` = conversation fraîche | JS OK, UI intacte |
| P2-6 CI + .gitignore | `.github/workflows/ci.yml` (tests+scan+EA), `.env` ignoré | pipeline défini |
| P2-7 métriques | `GET /api/metrics` (voies, latence p50/p90/p99, refus, satisfaction) | agrégation OK |
| P2-8 rate-limit feedback | `_rate_limit` appliqué à `/api/feedback` | protégé |
| P2-9 Qdrant modernisé | `create_collection` / `query_points` (fin des appels dépréciés) | API à jour |
| Non-régression globale | `test_system.py` (34 tests), `test_llm_integration.py` (4), `scan_qualite.py`, EA | 34/34, 4/4, SCAN PROPRE, EA 15/15 |

**Bilan** : les 9 améliorations de l'audit sont implémentées et vérifiées, sans
aucune régression sur les garanties scientifiques existantes.
