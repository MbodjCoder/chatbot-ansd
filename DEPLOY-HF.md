# Déployer RAMA sur Hugging Face Spaces (gratuit, sans carte, URL stable)

Objectif : une URL publique **testable à distance** par d'autres personnes,
qui reste en ligne même PC éteint. Aucun moyen de paiement requis.

> La clé Groq n'est **JAMAIS** téléversée : elle se pose comme **Secret** du Space.
> Le script d'upload exclut `backend/.env` (le Space est public).

---

## 1. Compte + jeton (une fois)
1. Crée un compte sur https://huggingface.co (email suffit, pas de carte).
2. Jeton d'écriture : https://huggingface.co/settings/tokens → **New token** →
   rôle **Write** → copie-le.
3. Installe l'outil et connecte-toi (PowerShell) :
   ```powershell
   pip install -U "huggingface_hub[cli]"
   huggingface-cli login
   ```
   Colle le jeton quand c'est demandé.

## 2. Créer le Space + téléverser le code
Depuis `C:\Users\dell\Downloads\SAGE-ANSD\ansd-chatbot`, lance ce script Python
(remplace `TON_USER` par ton identifiant Hugging Face) :

```powershell
python -c "from huggingface_hub import HfApi; api=HfApi(); repo='TON_USER/rama-ansd'; api.create_repo(repo, repo_type='space', space_sdk='docker', exist_ok=True); api.upload_folder(folder_path='.', repo_id=repo, repo_type='space', ignore_patterns=['.env','*.env','**/.env','backend/.env','**/__pycache__/**','**/*.pyc','**/data/logs/**','.git/**','**/.git*','docs/**','**/node_modules/**','**/.DS_Store']); print('OK ->', 'https://huggingface.co/spaces/'+repo)"
```

- `ignore_patterns` **exclut `**/.env`** (clé jamais publiée) et `docs/` (inutile
  à l'app, allège l'upload).
- L'URL de test finale sera : `https://TON_USER-rama-ansd.hf.space`.

## 3. Poser la clé + variables (dans l'interface du Space)
Space → **Settings** → *Variables and secrets* :

| Type | Nom | Valeur |
|---|---|---|
| **Secret** | `ANSD_LLM_API_KEY` | *(la clé Groq lue dans `backend/.env`)* |
| Variable | `ANSD_MODE` | `production` |
| Variable | `ANSD_LLM_PROVIDER` | `groq` |
| Variable | `ANSD_TRUST_PROXY` | `true` |

Après ajout des variables, le Space **reconstruit** automatiquement.

## 4. Vérifier
- Onglet **Logs** du Space : attendre `Application startup complete`.
- Ouvrir `https://TON_USER-rama-ansd.hf.space` → poser une question.
- Santé : `https://TON_USER-rama-ansd.hf.space/api/health` → `{"status":"ok",...}`.

## Mettre à jour plus tard
Relance simplement le `upload_folder` de l'étape 2 (mêmes `ignore_patterns`) :
le Space se reconstruit.

## Notes
- Le `Dockerfile` **racine** (port fixe 8000 = `app_port`) est celui que HF
  construit. `backend/Dockerfile` reste pour Fly/autres PaaS.
- Image légère (FastAPI + scikit-learn, pas de GPU) : build en quelques minutes
  sur le CPU gratuit du Space.
- Sécurité inchangée : SQLite en lecture seule, journaux anonymes, non-root,
  clé injectée en Secret (jamais dans l'image, jamais dans le dépôt).
