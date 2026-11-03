# Chatbot ANSD

Assistant conversationnel d'accès aux statistiques du Sénégal. Il répond en français, à l'écrit ou à la voix, à partir des données et publications de l'Agence nationale de la Statistique et de la Démographie (ANSD), et renvoie vers la source officielle.

Prototype de recherche, Université Gaston Berger. Non validé par l'ANSD.

**[Démo en ligne](https://rama-sop5.onrender.com)** · **[Note « État et besoins »](docs/Chatbot_ANSD_Etat_et_Besoins.pdf)**

---

## Ce qu'il fait

- **Donne un chiffre** : « Combien de femmes vivent à Kolda ? », « Quel est le taux de chômage ? »
- **Compare et classe** : « Classe les régions par taux de pauvreté », avec tableau et graphique
- **Explique une méthode** : « Comment l'ANSD mesure-t-elle la pauvreté ? »
- **Oriente vers un document** : « Où télécharger le RGPH-5 ? », « Quelles enquêtes sur la santé ? »

Aucun chiffre n'est produit par l'intelligence artificielle : chaque valeur est lue dans la base de données, puis contrôlée avant affichage.

## Fonctionnement

```
question ─► correction ─► contrôle du domaine ─► choix de la voie
                                                   ├─ SQL      base d'indicateurs
                                                   ├─ RAG      publications
                                                   ├─ NAV      registre de liens
                                                   └─ CATALOG  fiches ANADS
         ─► contrôle de fidélité des chiffres ─► réponse + liens sources
```

## Données

| Données | Contenu | Source |
|---|---|---|
| [Base d'indicateurs](backend/scripts/seed_db.py) | Population (recensements 1976-2023), pauvreté par région, emploi, inflation, croissance, 26 indicateurs nationaux | RGPH-5, EHCVM II, ENES, IHPC, comptes nationaux |
| [Projections 2025](backend/data/sources) | Population par région, sexe, milieu et groupe d'âges (14 régions, 238 tranches) | Annuaire Population du Sénégal 2025 |
| [Publications](backend/data/documents) | 26 documents : fiches thématiques, pages du site, notes de synthèse | ansd.sn |
| [Catalogue ANADS](backend/data/anads_catalogue.json) | 285 fiches d'enquêtes et de recensements | API publique ANADS |
| [Registre de liens](backend/data/resources.json) | 32 adresses officielles vérifiées | ansd.sn |

Une valeur non publiée reste vide : le chatbot le dit au lieu de l'estimer. Les totaux sont contrôlés à chaque construction de la base.

## Modèles

| Fonction | Modèle |
|---|---|
| Rédaction des réponses | GPT-OSS 120B (modèle ouvert), via Groq ; tout fournisseur compatible OpenAI convient |
| Choix de la voie | TF-IDF et régression logistique, entraîné sur 328 questions annotées |
| Recherche documentaire | Index TF-IDF (mots et fragments de mots) |
| Saisie vocale | Reconnaissance du navigateur ; Whisper large-v3-turbo en repli |

Si le modèle de langage est indisponible, le chatbot continue avec des moteurs déterministes : chiffres et liens restent exacts.

## Qualité mesurée

| Contrôle | Résultat |
|---|---|
| Tests automatisés | 94 / 94 |
| Requêtes SQL de référence | 20 / 20 |
| Jeu de référence (exactitude, sécurité, fidélité) | 24 / 24, 4 / 4, 2 / 2 |
| Choix de la voie (328 questions) | 85,7 % |

## Lancer en local

```bash
cd backend
pip install -r requirements.txt
python scripts/seed_db.py && python scripts/train_router.py
uvicorn app.api.main:app --port 8000
```

Ouvrir http://localhost:8000. Sans clé API, le chatbot fonctionne en mode démonstration. Pour activer le modèle de langage, copier `backend/.env.example` en `backend/.env` et renseigner `ANSD_MODE=production` et `ANSD_LLM_API_KEY`.

Tests : `cd backend && ANSD_MODE=demo python -m pytest -q`

## Déployer

- **Render** : *New > Blueprint*, choisir ce dépôt ; la clé est demandée à la création ([render.yaml](render.yaml)).
- **Serveur** : copier `.env.example` en `.env`, renseigner la clé, puis `docker compose up -d`.

L'image contient l'interface et l'API (port 8000) ; la base est construite pendant la construction de l'image.

## Brancher les données de l'ANSD

La voie chiffrée interroge un contrat, [`SourceStatistique`](backend/app/sql/sources.py). Connecter la Plateforme Open Data ou une base interne revient à ajouter un adaptateur, sans modifier le reste du code ([exemple](backend/app/sql/odp.py)). Les besoins côté ANSD sont décrits dans la [note « État et besoins »](docs/Chatbot_ANSD_Etat_et_Besoins.pdf).

## Structure

```
backend/
  app/
    api/          API FastAPI
    core/         traitement d'une question, sessions, liens, suggestions
    sql/          voie chiffrée : gabarits, génération SQL, sources
    rag/          voie documentaire
    router/       choix de la voie
    guardrails/   contrôles d'entrée et de fidélité
    llm/          modèle de langage, transcription vocale
    evaluation/   évaluation SQL, routage, RAG
  data/           base, publications, catalogue, jeux d'évaluation
  scripts/        construction de la base, récolte des sources, évaluation
  tests/
frontend/         interface (HTML, CSS, JavaScript sans dépendance)
docs/             note « État et besoins »
```

---

Ahmadou Lamine Mbodj · Université Gaston Berger
