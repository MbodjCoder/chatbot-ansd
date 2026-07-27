# Déployer RAMA en ligne avec Fly.io

Objectif : une URL publique testable **de partout**, avec des **performances
constantes** (région Paris proche du Sénégal, machine toujours active).

> À exécuter depuis le dossier `ansd-chatbot/` (là où se trouve `fly.toml`).
> La clé Groq reste **secrète** : jamais dans le code, jamais commit.

---

## 1. Installer flyctl (une fois)

**Windows (PowerShell)** :
```powershell
iwr https://fly.io/install.ps1 -useb | iex
```
Ferme puis rouvre PowerShell pour que `fly` soit dans le PATH.

## 2. Créer un compte / se connecter
```powershell
fly auth signup   # première fois (carte requise pour l'always-on, facturation à l'usage)
# ou
fly auth login
```

## 3. Choisir un nom d'app unique
Le nom `rama-ansd` est peut-être déjà pris. Choisis-en un (ex. `rama-ansd-mbodj`) :
```powershell
fly apps create rama-ansd-mbodj
```
Puis **remplace** la 1ʳᵉ ligne de `fly.toml` par ce nom :
```
app = "rama-ansd-mbodj"
```
Et adapte aussi `ANSD_CORS_ORIGINS = "https://rama-ansd-mbodj.fly.dev"`.

## 4. Poser la clé LLM en secret (jamais dans le code)
Récupère la valeur depuis `backend/.env` (variable `ANSD_LLM_API_KEY`) :
```powershell
fly secrets set ANSD_LLM_API_KEY="colle_ici_ta_cle_groq" -a rama-ansd-mbodj
```

## 5. Déployer
```powershell
fly deploy
```
Fly construit l'image (via `backend/Dockerfile`), crée la base SQLite + le
routeur au build, et démarre la machine à Paris.

## 6. Ouvrir et tester
```powershell
fly open                      # ouvre l'URL dans le navigateur
```
URL type : `https://rama-ansd-mbodj.fly.dev` — partageable, testable de partout.

Vérifier la santé :
```powershell
fly status
curl https://rama-ansd-mbodj.fly.dev/api/health
```
Attendu : `{"status":"ok","llm_ok":true,...}`

---

## Exploitation

| Action | Commande |
|---|---|
| Voir les logs | `fly logs` |
| Redéployer après modif | `fly deploy` |
| Changer une variable | éditer `[env]` de `fly.toml` puis `fly deploy` |
| Changer/renouveler la clé | `fly secrets set ANSD_LLM_API_KEY="..."` |
| Mettre en pause (stop facturation) | `fly scale count 0` |
| Reprendre | `fly scale count 1` |
| CPU dédié (perfs max) | `fly scale vm performance-1x` |

## Performances constantes — pourquoi ça tient
- **Voies déterministes** (chiffre, refus, catalogue) : quelques millisecondes CPU,
  identiques quel que soit le lieu de l'utilisateur.
- **Latence LLM** : portée par Groq (infra cloud homogène), pas par l'hébergeur.
- **Région Paris (CDG)** : faible latence réseau vers le Sénégal.
- **`min_machines_running = 1` + `auto_stop_machines = false`** : pas de démarrage
  à froid → la 1ʳᵉ requête est aussi rapide que les suivantes.

## Sécurité (déjà en place)
- `.dockerignore` exclut `**/.env` → la clé n'entre **jamais** dans l'image.
- La clé est injectée à l'exécution via `fly secrets` (chiffrée par Fly).
- Base SQLite en **lecture seule** ; journaux **anonymes** ; app en utilisateur non-root.

## Coût indicatif
`shared-cpu-1x` / 1 Go, toujours actif ≈ quelques dollars/mois (facturation Fly à
l'usage). Mettre `fly scale count 0` quand tu ne testes pas pour ne rien payer.
