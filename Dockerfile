# Image du Chatbot ANSD : API FastAPI et interface servies ensemble.
# Contexte de construction : racine du dépôt. Port : $PORT (8000 par défaut).
FROM python:3.12-slim

WORKDIR /srv

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /srv/
COPY frontend/ /frontend/

# Base statistique et classifieur construits à partir des sources du dépôt
RUN python scripts/seed_db.py && python scripts/train_router.py

RUN mkdir -p /srv/data/logs \
    && useradd -m -u 10001 chatbot \
    && chown -R chatbot:chatbot /srv /frontend
USER chatbot

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
