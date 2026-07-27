# Déploiement de RAMA — guide et checklist

Cible : **Docker Compose, une instance**, recherche **TF-IDF** (légère, sans
GPU ni base vectorielle). Le frontend est servi par l'API elle-même (même
origine → pas de CORS pour l'interface).

## 1. Prérequis

- Docker + Docker Compose
- Une clé API LLM (Groq recommandé : rapide et gratuit pour démarrer)
- (Production publique) un nom de domaine + un reverse-proxy TLS (nginx/caddy)

## 2. Configuration

```bash
cp .env.example .env
```

Renseigner dans `.env` (à côté de `docker-compose.yml`) :

| Variable | Rôle | Défaut |
|---|---|---|
| `ANSD_LLM_API_KEY` | **obligatoire** — clé du fournisseur | — |
| `ANSD_LLM_PROVIDER` | groq / deepseek / openai / mistral / openrouter / ollama | groq |
| `ANSD_LLM_GEN`, `ANSD_LLM_AUX` | `auto` (LLM si fournisseur rapide, sinon déterministe) | auto |
| `ANSD_CORS_ORIGINS` | domaines tiers autorisés (l'UI embarquée n'en a pas besoin) | domaines ANSD |
| `ANSD_TRUST_PROXY` | `true` **uniquement** derrière un proxy de confiance | false |

Le `.env` n'entre **jamais** dans l'image (`.dockerignore`) ni dans git
(`.gitignore`). Vérifié : l'image ne contient que `.env.example`.

## 3. Lancement

```bash
docker compose up -d --build
docker compose logs -f api        # doit afficher : LLM reel actif : groq / …
curl localhost:8000/api/health    # {"status":"ok","llm_ok":true,…}
```

L'application répond sur `http://SERVEUR:8000/` (UI) et `…/api/*` (API).

## 4. Mise en production (public)

Placer un reverse-proxy TLS devant l'API et poser `ANSD_TRUST_PROXY=true` :

```nginx
server {
  server_name rama.ansd.sn;
  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    # SSE : ne pas mettre en tampon les flux
    proxy_buffering off;
    proxy_read_timeout 300s;
  }
}
```

Puis TLS via `certbot --nginx -d rama.ansd.sn`.

## 5. Checklist avant ouverture

- [ ] `.env` renseigné, clé LLM valide (`/api/health` → `llm_ok: true`)
- [ ] TLS actif ; `ANSD_TRUST_PROXY=true` **seulement** derrière le proxy
- [ ] `ANSD_CORS_ORIGINS` limité aux domaines réels (si appels tiers)
- [ ] `docker compose ps` → conteneur `healthy`, `restart: unless-stopped`
- [ ] Volume `rama_logs` présent (journalisation persistante)
- [ ] Sauvegarde : le volume de logs ; la base SQLite est régénérée au build
- [ ] Quota du fournisseur LLM vérifié (une clé partagée = plafond global)

## 6. Exploitation

- **Logs applicatifs** : volume `rama_logs` (`interactions.jsonl`,
  `feedback.jsonl`). `GET /api/metrics` pour l'agrégat.
- **Mettre à jour le corpus** : déposer des `.md` dans
  `backend/data/documents/`, rebuild. Rafraîchir le catalogue ANADS :
  `python scripts/harvest_anads.py && python scripts/gen_anads_index.py`.
- **Redéployer** : `docker compose up -d --build`.

## 7. Limites connues / évolutions

- **Mono-instance** : sessions, cache et verrous sont en mémoire. Passer à
  plusieurs instances imposerait un état externe (Redis) — couche d'isolation
  déjà prévue (cf. décision #57).
- **Recherche** : TF-IDF par défaut. Un rappel supérieur est possible avec
  **BGE-M3 + Qdrant** (décommenter les dépendances production, ajouter le
  service Qdrant) — image plus lourde, GPU conseillé.
- **Routeur** : baseline TF-IDF (accuracy ≈ 0,86). Fine-tuning DeBERTa-v3
  disponible (`scripts/finetune_deberta.py`) pour la production.
