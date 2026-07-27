# Dockerfile RACINE — utilisé par les PaaS qui construisent le `Dockerfile` à la
# racine du dépôt (Render, Koyeb, Back4App...). Écoute sur $PORT injecté par la
# plateforme (défaut 8000 en local). Contexte de build = racine du dépôt ->
# on copie backend/ ET frontend/.
FROM python:3.12-slim

WORKDIR /srv

# 1) Dépendances (couche cachée tant que requirements ne change pas)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Code backend -> /srv , frontend -> /frontend (servi par main.py)
COPY backend/ /srv/
COPY frontend/ /frontend/

# 3) Base SQLite (données officielles) + routeur TF-IDF, construits hors ligne
RUN python scripts/seed_db.py && python scripts/train_router.py

# 4) Exécution en utilisateur non privilégié (défense en profondeur)
RUN mkdir -p /srv/data/logs \
    && useradd -m -u 10001 rama \
    && chown -R rama:rama /srv /frontend
USER rama

EXPOSE 8000
# Forme shell pour honorer $PORT injecté par la plateforme (Render/Koyeb/Cloud
# Run...) ; défaut 8000 en local.
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
