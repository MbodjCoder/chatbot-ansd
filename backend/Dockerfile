# Image de production RAMA — API FastAPI + frontend statique servi par la même
# app (même origine → pas de CORS pour l'UI embarquée). Contexte de build =
# racine du dépôt (voir docker-compose.yml : context: .), ce qui permet de
# copier À LA FOIS backend/ et frontend/.
FROM python:3.12-slim

WORKDIR /srv

# 1) Dépendances (couche cachée tant que requirements ne change pas)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Code backend -> /srv , frontend -> /frontend (servi par main.py, parents[3])
COPY backend/ /srv/
COPY frontend/ /frontend/

# 3) Base SQLite (données officielles) + routeur TF-IDF, construits hors ligne
RUN python scripts/seed_db.py && python scripts/train_router.py

# 4) Exécution en utilisateur non privilégié (défense en profondeur).
#    On crée data/logs AVANT le chown : le volume nommé monté à cet endroit
#    héritera de l'appartenance à `rama` (sinon volume root -> écriture refusée).
RUN mkdir -p /srv/data/logs \
    && useradd -m -u 10001 rama \
    && chown -R rama:rama /srv /frontend
USER rama

EXPOSE 8000
# Mono-instance : UN worker (sessions/cache/verrous en mémoire partagée).
# Le passage multi-instances nécessiterait un état externe (Redis) — cf. #57.
# Forme shell pour honorer $PORT injecté par les PaaS (Render/Cloud Run/HF/
# Railway) ; défaut 8000 (Fly, docker-compose, local).
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
