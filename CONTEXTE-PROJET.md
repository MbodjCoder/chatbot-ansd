# Contexte projet — RAMA (chatbot ANSD)

> Fiche de contexte persistante du projet. **À maintenir à jour** après chaque
> évolution notable.

## Le projet en une phrase

**RAMA** (chatbot de l'ANSD, anciennement SAGE-ANSD) : chatbot hybride
**RAG + Text-to-SQL** pour le site de l'ANSD (Agence Nationale de la Statistique
et de la Démographie du Sénégal), ANADS et sites partenaires. Sujet de mémoire
de Master en Informatique, Université Gaston Berger (UGB).

## Exigence encadrant (IMPÉRATIF)

Encadrant scientifiquement très exigeant. **Toute décision technique doit être
justifiée scientifiquement** dans `docs/JUSTIFICATIONS.md` (matrice Choix →
Alternatives écartées → Justification → Référence) et, pour les évolutions,
dans `docs/EXPLICATIONS.md` (le « pourquoi » clair et pédagogique).

## Où sont les choses

```
ansd-chatbot/
  backend/
    app/
      api/main.py            # FastAPI : /api/chat, /api/chat/stream (VRAI streaming), /api/feedback, /api/health, /api/metrics
                             # thread-safe (RLock), rate-limit chat+feedback
      core/
        chatbot.py           # ORCHESTRATEUR CENTRAL : ask() enchaîne toutes les voies
        config.py            # Settings pydantic, préfixe ANSD_, lit .env
        smalltalk.py         # actes sociaux (salut/merci/qui es-tu) AVANT le pipeline
        catalogue.py         # recherche dans les 285 fiches ANADS
        resources.py         # appariement liens officiels vérifiés
        followups.py         # suggestions de questions contextuelles
        telemetry.py         # journal JSONL (lock fichier)
      guardrails/rails.py    # rails entrée (topical/injection/politique) + sortie (fidélité num.)
      llm/client.py          # multi-fournisseurs OpenAI-compat + MockLLM + FallbackLLM + gabarits SQL démo
      rag/pipeline.py        # TfidfRetriever (démo) / BGEQdrantRetriever (prod) + génération ancrée
      router/orchestrator.py # routage 2 niveaux : classifieur TF-IDF/DeBERTa + fallback LLM
      sql/pipeline.py        # DIN-SQL : gabarits d'abord, LLM en repli ; verbalisation humaine
      sql/templates.py       # gabarits SQL déterministes (rapides, sûrs)
      evaluation/            # evaluate_sql.py (EA), evaluate_router.py, evaluate_ragas.py
    data/
      documents/*.md         # 11 docs corpus RAG (contenus extraits des vraies pages)
      resources.json         # liens officiels ANSD vérifiés HTTP 200
      anads_catalogue.json   # 285 fiches ANADS (via scripts/harvest_anads.py)
      datasets/              # routing_dataset.csv, sql_test_set.json
      router_demo.joblib     # artefact routeur entraîné
      logs/*.jsonl           # télémétrie
    scripts/
      seed_db.py             # crée ansd_stats.db (données officielles vérifiées)
      train_router.py        # entraîne le routeur (CV 5 plis)
      harvest_anads.py       # récolte le catalogue ANADS (API NADA, pagination `page`)
      harvest_web.py         # récolte le contenu des pages ANSD (curl, nettoie l'habillage) -> data/documents/web_*.md
      harvest_pdf.py         # récolte + extrait le texte des PDF ANSD (pypdf) -> data/documents/pdf_*.md
      scan_qualite.py        # SCANNER QUALITÉ : 29 questions accentuées, détecte défauts
    tests/
      test_system.py         # 31 tests (FORCE ANSD_MODE=demo en tête)
      test_llm_integration.py # 4 tests client LLM (faux serveur OpenAI local)
  frontend/index.html        # SPA autonome (zéro dépendance), thème clair/sombre, SSE
  docs/
    JUSTIFICATIONS.md        # matrice des décisions (référence encadrant)
    EXPLICATIONS.md          # justification pédagogique des évolutions
```

## Voies de traitement (ordre dans chatbot.ask())

1. **CHAT** (smalltalk) — salut/merci/qui-es-tu → réponse directe, pas de pipeline
2. Contextualisation des suivis (« Et en 2023 ? ») par substitution d'entités
3. Guardrails d'entrée (rejet hors-domaine/injection/politique)
4. Cache (questions autonomes)
5. **CATALOG** — « quelles enquêtes sur X ? » → fiches ANADS verbatim
6. **NAV** — « où télécharger X ? » → base de liens vérifiés (jamais d'extraction)
7. **Routage** → **SQL** | **RAG** | **HYBRID**
8. Rail de fidélité numérique en sortie
9. Liens + suggestions contextuelles

## Robustesse & sécurité (décisions #73-76, docs/EXPLICATIONS.md)

- **Mémoire bornée** : cap LRU dur des sessions (MAX_SESSIONS), purge IP du
  rate-limiter, session_id client validé (regex). Anti-DoS mémoire.
- **Concurrence** : verrou global (sessions/cache) + `_remember()` verrouillé
  (mutations d'historique). Testé 12-40 threads, 0 erreur.
- **Réseau faible** : llm_timeout_s=20, max_retries=1 → repli local < 12 s ;
  sémaphore llm_max_concurrency=6 (anti-tempête 429). Frontend : AbortController.
- **Sécurité** : exception handler global (pas de 500/trace), CORS via
  ANSD_CORS_ORIGINS, X-Forwarded-For seulement si ANSD_TRUST_PROXY, /health
  = booléen llm_ok (pas de détail). SQL en lecture seule (mode=ro).
- Rate-limit 30 req/min/IP (chat + feedback). Vérifié : 30 servies + 10×429, 0 crash.

## Garanties scientifiques (NE PAS CASSER)

- **Anti-hallucination numérique** : les chiffres viennent TOUJOURS de la base
  (verbalisation SQL déterministe) ou des documents (extraction ancrée), jamais
  d'un LLM libre. Le rail de fidélité vérifie que tout nombre de la réponse
  existe dans les preuves. Preuve ≠ réponse (pas d'auto-validation circulaire).
- **Déterminisme** : température 0, mode démo reproductible (MockLLM).
- **Dégradation gracieuse** : panne LLM → repli local, jamais d'erreur 500
  (`FallbackLLM`). API sans clé → mode démo automatique.

## Modes & LLM

- `ANSD_MODE=demo` : 100% hors-ligne, déterministe (MockLLM). **Les tests le forcent.**
- `ANSD_MODE=production` + `ANSD_LLM_PROVIDER` (deepseek/openai/groq/mistral/openrouter/ollama)
- Config active (`backend/.env`) : Ollama local `qwen2.5:3b` (CPU lent) OU Groq (gratuit, rapide).
- `ANSD_LLM_GEN=auto` / `ANSD_LLM_AUX=auto` : sur Ollama lent → moteurs déterministes ;
  sur API rapide → rédaction LLM. **Mode éclair** = tout déterministe = ~10 ms.
- **Groq ACTIF** (clé de l'utilisateur en place) : provider=groq, llama-3.3-70b-versatile,
  ~0.6-2 s/réponse, streaming réel. Débloque : rédaction abstractive soignée,
  normalisation des fautes, réécriture des suivis, synthèse HYBRID.
- Normalisation LLM des fautes de frappe/orthographe (`_normalize_query`,
  décision #72) : active uniquement si use_llm_aux (fournisseur rapide) ; no-op en démo.
- DeepSeek : clé sans crédit (402) — commenté. Ollama : local lent — commenté.

## Lancer / tester (TOUJOURS depuis backend/)

```bash
cd backend
python scripts/seed_db.py            # une fois : base
python scripts/train_router.py       # une fois : routeur
python -m uvicorn app.api.main:app --port 8000   # serveur → http://localhost:8000
python tests/test_system.py          # 31 tests → "TOUS LES TESTS PASSENT"
python tests/test_llm_integration.py # 4 tests client LLM
python scripts/scan_qualite.py       # scan qualité → "SCAN PROPRE" (À LANCER APRÈS TOUT CHANGEMENT)
python app/evaluation/evaluate_sql.py    # EA 15/15
```

Interface debug (soutenance) : `http://localhost:8000/?debug=1` (traçabilité visible).

## Pièges connus / conventions

- **Toujours `cd backend`** avant de lancer python (imports `app.*`).
- **Port 8000 souvent occupé** par un serveur zombie : `taskkill //F //PID <pid>`
  (trouver via `netstat -ano | grep :8000 | grep LISTENING`).
- **Windows** : shell PowerShell principal + Bash dispo. Sorties console : forcer
  UTF-8 (`io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')`).
- **Captures Edge** : `msedge --headless --timeout=15000 --screenshot=... URL`
  (le `--virtual-time-budget` ne suit pas le flux SSE réel).
- **Accents** : usagers écrivent avec, corpus sans → `strip_accents="unicode"`
  partout (retriever, routeur) + `_fold()` avant matching d'intentions.
- **Corriger par CLASSE de problème, jamais au cas par cas** (leçon récurrente).
- Après tout changement fonctionnel : `test_system` + `scan_qualite` + relancer serveur.

## État & métriques (mettre à jour)

- 40 tests système + 6 tests LLM, EA 15/15 (100%), fidélité proxy 1,000, scan qualité 29/29
- Routeur TF-IDF : accuracy 0,857 / F1 0,805 (CV 5 plis, n=328)
- **23 docs corpus** (11 rédigés + FAQ + 8 web récoltés + 3 PDF), 27 liens vérifiés, 285 fiches ANADS
- Retriever : union mots(1-2g)+chars(3-5g) strip_accents ; chunking par section (chunk_document)
- Corpus reproductible : `python scripts/harvest_web.py && python scripts/harvest_pdf.py` (nécessite réseau)
- Décisions tracées : JUSTIFICATIONS.md (#1→#65) + docs/EXPLICATIONS.md (audit qualité)
- **Audit qualité fait (P0/P1/P2)** : thread-safety (RLock), vrai streaming SSE,
  double-retrieval fusionné, guardrail domaine hybride, persistance localStorage,
  CI GitHub Actions, /api/metrics, rate-limit feedback, Qdrant modernisé, .gitignore (clé API)
- CI : `.github/workflows/ci.yml` (force ANSD_MODE=demo)
- Reste théorique (jamais exécuté sur vraie machine) : BGE-M3+Qdrant, fine-tuning DeBERTa, RAGAS complet, étude SUS
- Industrialisation multi-instance : externaliser sessions/cache vers Redis (couche déjà isolée)

## Voir aussi

- `docs/JUSTIFICATIONS.md` — matrice des 56+ décisions (pour l'encadrant)
- `docs/EXPLICATIONS.md` — le « pourquoi » pédagogique des évolutions
