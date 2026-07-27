demo:
	cd backend && python scripts/seed_db.py && python scripts/train_router.py
test:
	cd backend && python tests/test_system.py && python tests/test_llm_integration.py
eval:
	cd backend && python app/evaluation/evaluate_sql.py && python app/evaluation/evaluate_router.py && python app/evaluation/evaluate_ragas.py
run:
	cd backend && uvicorn app.api.main:app --port 8000
