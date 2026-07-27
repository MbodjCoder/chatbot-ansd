---
title: RAMA — Assistant statistique ANSD
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
short_description: Assistant conversationnel des statistiques officielles du Sénégal (ANSD)
---

<!-- L'en-tête YAML ci-dessus est lu par Hugging Face Spaces (SDK Docker, port 8000).
     Il n'affecte pas les autres usages du dépôt. -->

# RAMA-ANSD — Chatbot hybride RAG + Text-to-SQL pour l'ANSD

Mémoire de Master en Informatique — Université Gaston Berger.
Système conversationnel fiable pour l'accès aux statistiques officielles du Sénégal
et la navigation dans les publications de l'ANSD.

## Architecture (4 composants + sessions)

```
Question ──► [Contextualisation conversationnelle (questions de suivi)]
        ──► [Guardrails entrée : topical / safety / injection]
        ──► [Orchestrateur f(q) ∈ {SQL, RAG, HYBRID}]
              niveau 1 : classifieur supervisé (DeBERTa-v3 / TF-IDF+LogReg en démo)
              niveau 2 : fallback LLM si confiance < 0,85
        ──► voie SQL : DIN-SQL (schema linking, few-shot, auto-correction, lecture seule)
        ──► voie RAG : chunking 512/128 → BGE-M3 → Qdrant/HNSW → génération ancrée
        ──► [Guardrail sortie : fidélité numérique (Self-RAG simplifié)]
        ──► Réponse + route + confiance + SQL + sources + données structurées
            (traçabilité complète, journalisée en JSONL pour l'évaluation)
```

## Données : officielles et vérifiées

La base `ansd_stats.db` (8 tables) et le corpus documentaire (23 documents : rédigés, FAQ, pages web et PDF récoltés — scripts `harvest_web.py`/`harvest_pdf.py`) sont
peuplés de **données officielles ANSD** collectées et triangulées depuis les
publications de l'agence :

- **RGPH-5 2023** (résultats définitifs) : population nationale 18 126 390 et
  par région — les sommes régionales égalent exactement les totaux officiels
  (assertions dans `seed_db.py`) ;
- **EHCVM II 2021/2022** (rapport final, tableau III-2) : pauvreté par région
  (P0, profondeur, sévérité, Gini, consommation moyenne) ;
- **ENES** : chômage trimestriel 2023-2025 ; **IHPC** : inflation 2019-2024 ;
  **comptes nationaux** : croissance du PIB 2022-2024 ;
- 26 indicateurs nationaux de référence (espérance de vie, fécondité,
  urbanisation, ménages, éducation…).

Règle de qualité (Principe 2, Nations Unies 2014) : une valeur non publiée par
l'ANSD reste `NULL`, jamais estimée. Provenance détaillée : `docs/JUSTIFICATIONS.md`.

## Démarrage rapide (mode démo, 100 % hors-ligne)

```bash
cd backend
pip install -r requirements.txt
python scripts/seed_db.py        # base SQLite (données officielles ANSD)
python scripts/train_router.py   # classifieur de routage (CV 5 plis, n=328)
python tests/test_system.py      # 41 tests unitaires + intégration
python tests/test_llm_integration.py  # 3 tests du client LLM production
uvicorn app.api.main:app --port 8000
# ouvrir http://localhost:8000  (interface web)   /docs (OpenAPI)
```

Ou depuis la racine : `make demo && make test && make run`.

## Interface web

Frontend autonome (zéro dépendance) : thème clair/sombre, sessions
conversationnelles multi-tours (« Et en 2023 ? »), **affichage en flux (SSE)**,
**tableaux HTML** + **graphiques** (courbe pour les séries temporelles, barres
pour les classements — palette validée en contraste, étiquettes directes),
**cartes de liens vers les publications officielles ANSD** (URLs vérifiées),
badges de traçabilité (route, confiance, latence, cache), requête SQL
dépliable, copier la réponse, feedback 👍/👎 (protocole SUS), export Markdown
avec tableaux et sources. Démonstration : `/?q=…&theme=dark`.

## API

| Endpoint | Rôle |
|---|---|
| `POST /api/chat` | question (+ `session_id` optionnel) → réponse tracée |
| `POST /api/chat/stream` | même contrat, réponse en flux SSE (méta → fragments → payload) |
| `POST /api/feedback` | retour utilisateur 👍/👎 → `data/logs/feedback.jsonl` |
| `GET /api/metrics` | métriques d'usage agrégées (voies, latence, refus, satisfaction) |
| `GET /api/health` | état du système |

Chaque interaction est journalisée dans `data/logs/interactions.jsonl`
(anonyme : question, route, confiance, latence, verdict des rails) pour
l'analyse quantitative du mémoire. Limitation de débit : 30 req/min/IP.
Cache LRU des questions autonomes (TTL 10 min, jamais les suivis de session).

## Brancher un vrai modèle (mode production)

Le client LLM accepte tout fournisseur à API compatible OpenAI. Copier
`backend/.env.example` vers `backend/.env` puis :

| Fournisseur | Variables | Note |
|---|---|---|
| **Ollama local (config. par défaut)** | `ANSD_LLM_PROVIDER=ollama`, `ANSD_LLM_MODEL=qwen2.5:3b` | gratuit, hors-ligne, souveraineté totale ; dimensionné CPU (7b téléchargé aussi, plus lent) |
| **Groq (puissance max gratuite)** | `ANSD_LLM_PROVIDER=groq`, `ANSD_LLM_API_KEY=gsk_…` | Llama-3.3-70B à ~500 tok/s ; clé **gratuite sans carte** sur console.groq.com/keys |
| DeepSeek-V3 (référence du mémoire) | `ANSD_LLM_PROVIDER=deepseek`, `ANSD_LLM_API_KEY=sk-…` | nécessite du **crédit** sur platform.deepseek.com (sinon erreur 402) |
| OpenAI / Mistral / OpenRouter | `ANSD_LLM_PROVIDER=…` + clé | presets intégrés |

**Mode éclair** (décision #43, actif par défaut sur Ollama local) : toutes
les voies servies par les moteurs déterministes — chiffres par gabarits SQL,
réponses documentaires par extraction ancrée pondérée IDF, suivis par
substitution d'entités. Latence moteur mesurée : **0-10 ms** par réponse,
fidélité 1,000. Avec une API distante rapide (Groq gratuit, DeepSeek...),
la rédaction abstractive par LLM se réactive automatiquement
(`ANSD_LLM_GEN=auto`).

**Résilience** : toute panne du LLM (solde épuisé, réseau, service arrêté)
bascule la requête sur le moteur déterministe local — l'usager reçoit
toujours une réponse, jamais une erreur (`FallbackLLM`, décision #36 ;
incident visible sur `/api/health`).

Sans clé, le système **se dégrade proprement** vers le mode démo (MockLLM
déterministe). La voie API est **prouvée fonctionnelle** par
`tests/test_llm_integration.py` : un serveur local implémente le contrat
OpenAI (complétion, streaming SSE, erreurs 500) et le client du système y est
exercé — 3/3 validés. En production, le système ajoute : réécriture LLM des
questions de suivi, synthèse HYBRID en un texte unique, historique de
conversation dans les prompts.

## Évaluation (protocole du mémoire — reproductible : `make eval`)

```bash
python app/evaluation/evaluate_sql.py     # Execution Accuracy : 15/15 (100 %)
python app/evaluation/evaluate_router.py  # accuracy 0,857, F1 macro 0,805, χ², matrice
python app/evaluation/evaluate_ragas.py   # fidélité 1,000 (proxy) / RAGAS en production
python scripts/scan_qualite.py            # scan de qualité : 29 questions, toutes voies
```

## Déploiement (Docker, mono-instance)

Recherche TF-IDF (aucune dépendance GPU/vectorielle). Le frontend est servi
par la même app (même origine).

```bash
cp .env.example .env          # renseigner ANSD_LLM_API_KEY (clé Groq/DeepSeek…)
docker compose up -d --build  # build image + lancement (port 8000)
curl localhost:8000/api/health
```

Détail complet, mise derrière reverse-proxy TLS, checklist de production et
options : voir **`docs/DEPLOIEMENT.md`**.

Chaque choix technique est justifié dans `docs/JUSTIFICATIONS.md` avec les
références du mémoire (83 décisions tracées ; audit qualité et élargissement du corpus détaillés dans `docs/EXPLICATIONS.md`).

## Catalogue ANADS intégré

Le catalogue complet de l'archive nationale des microdonnées (**285 études**,
récolté via l'API publique NADA — `scripts/harvest_anads.py`, reproductible)
est interrogeable en langage naturel : « Quelles enquêtes existent sur la
santé ? » renvoie les fiches exactes (titre, période, producteur) avec le
lien direct vers chaque étude, où se fait la demande officielle d'accès aux
microdonnées. Réponse composée verbatim des métadonnées (voie CATALOG, 4 ms).

## Conversation naturelle

Une couche d'actes sociaux traite salutations, remerciements, « qui es-tu ? »
et demandes d'aide sans passer par le pipeline (correction du défaut où
« salut » rejouait la réponse précédente). L'interface grand public est
épurée ; la traçabilité technique complète (voie, confiance, latence, SQL)
s'affiche avec `http://localhost:8000/?debug=1` (soutenance).
