# Commandes courantes (depuis la racine du dépôt)
donnees:
	cd backend && python scripts/seed_db.py && python scripts/train_router.py
tests:
	cd backend && ANSD_MODE=demo python -m pytest -q
evaluation:
	cd backend && ANSD_MODE=demo python -m app.evaluation.evaluate_sql && ANSD_MODE=demo python scripts/evaluate.py
lancer:
	cd backend && uvicorn app.api.main:app --port 8000
