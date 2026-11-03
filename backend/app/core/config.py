"""Configuration du chatbot, lue depuis l'environnement (préfixe ANSD_) ou backend/.env.

  production : modèle de langage distant (clé API requise)
  demo       : tout en local et déterministe, sans réseau
"""
from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    mode: str = "demo"               # "demo" ou "production"

    # Modèle de langage : groq, mistral, deepseek, openai, openrouter ou ollama
    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_base_url: str = ""           # remplace l'adresse par défaut du fournisseur
    llm_model: str = ""              # remplace le modèle par défaut
    # délai court et peu de tentatives : repli local rapide sur réseau faible
    llm_timeout_s: float = 20.0
    llm_max_retries: int = 1
    # appels simultanés au fournisseur
    llm_max_concurrency: int = 6

    # Déploiement
    # origines autorisées, séparées par des virgules ("*" en développement)
    cors_origins: str = "*"
    # lire l'IP réelle dans X-Forwarded-For (uniquement derrière un proxy de confiance)
    trust_proxy: bool = False
    # ancien nom de variable, conservé
    deepseek_api_key: str = ""
    llm_temperature: float = 0.0     # réponses reproductibles
    llm_max_tokens: int = 1024

    # Étapes auxiliaires (correction, suivis, synthèse) et rédaction documentaire :
    #   "llm" toujours par le modèle, "fast" toujours déterministe,
    #   "auto" modèle si l'API est rapide, déterministe avec Ollama en local
    llm_aux: str = "auto"
    llm_gen: str = "auto"

    # Cache des réponses (questions identiques, hors suivis)
    cache_enabled: bool = True
    cache_ttl_s: int = 600
    cache_max_entries: int = 200

    # Recherche documentaire
    chunk_size: int = 512        # taille d'un passage
    chunk_overlap: int = 128
    top_k: int = 5               # passages récupérés
    # passages transmis au modèle (au-delà, la réponse se dilue)
    gen_context_chunks: int = 2
    embedding_model: str = "BAAI/bge-m3"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "ansd_documents"
    rerank_threshold: float = 0.05   # pertinence minimale d'un passage

    # Requêtes SQL
    database_path: str = str(BASE_DIR / "data" / "ansd_stats.db")
    sql_max_retries: int = 2     # corrections après une erreur d'exécution

    # Choix de la voie
    router_model: str = "microsoft/deberta-v3-base"
    router_confidence_threshold: float = 0.85  # en dessous, le modèle tranche
    router_artifact: str = str(BASE_DIR / "data" / "router_demo.joblib")

    # Contrôles
    max_query_length: int = 500
    faithfulness_check: bool = True

    class Config:
        env_prefix = "ANSD_"
        env_file = ".env"


settings = Settings()
