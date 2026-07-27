"""
Configuration centrale du systeme RAMA-ANSD
(Systeme d'Acces Guide aux Statistiques - ANSD).

Deux modes d'execution :
  - "production" : DeepSeek-V3 (API), BGE-M3 + Qdrant, DeBERTa-v3 fine-tune
  - "demo"       : composants locaux legers (TF-IDF, SQLite, LLM simule)
    permettant de demontrer l'architecture de bout en bout sans GPU ni API.

Justification scientifique des valeurs par defaut : voir docs/JUSTIFICATIONS.md
"""
from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # --- Mode ---
    mode: str = "demo"  # "demo" | "production"

    # --- LLM : tout fournisseur a API compatible OpenAI -------------------
    # Fournisseurs preconfigures : deepseek (defaut), openai, groq, mistral,
    # openrouter, ollama (local). llm_base_url / llm_model permettent de
    # surcharger n'importe quel preset.
    llm_provider: str = "deepseek"
    llm_api_key: str = ""            # cle API du fournisseur choisi
    llm_base_url: str = ""           # surcharge optionnelle du preset
    llm_model: str = ""              # surcharge optionnelle du preset
    # Reseau faible : timeout court + peu de tentatives pour un repli LOCAL
    # rapide plutot qu'une longue attente (worst case ~ timeout x (retries+1)).
    llm_timeout_s: float = 20.0
    llm_max_retries: int = 1         # nouvelles tentatives sur 429/5xx/timeout
    # Concurrence : nb max d'appels LLM distants simultanes (protege le quota
    # du fournisseur sous forte charge ; l'exces attend brievement).
    llm_max_concurrency: int = 6

    # --- Securite / deploiement ---
    # Origines CORS autorisees ("*" en dev ; en prod, lister le domaine ANSD).
    cors_origins: str = "*"
    # Faire confiance a l'en-tete X-Forwarded-For (a activer SEULEMENT derriere
    # un proxy de confiance : nginx). Sinon un client pourrait usurper son IP.
    trust_proxy: bool = False
    # retrocompatibilite (anciens noms de variables)
    deepseek_api_key: str = ""
    llm_temperature: float = 0.0     # determinisme requis pour stats officielles
    llm_max_tokens: int = 1024

    # Etapes auxiliaires (reecriture des suivis, synthese HYBRID) :
    #   "llm"  : toujours par LLM (qualite max, +1 appel par etape)
    #   "fast" : toujours deterministes (latence minimale)
    #   "auto" : LLM si API distante rapide, deterministe si Ollama local
    llm_aux: str = "auto"
    # Generation des reponses documentaires (voie RAG) et fallback du routeur:
    #   "llm"  : redaction par LLM (abstractive)
    #   "fast" : extraction ancree deterministe (~ms, fidelite 1,000)
    #   "auto" : LLM si API distante rapide, extraction si Ollama local lent
    llm_gen: str = "auto"

    # --- Cache de reponses (questions identiques, hors suivi de session) ---
    cache_enabled: bool = True
    cache_ttl_s: int = 600
    cache_max_entries: int = 200

    # --- RAG ---
    chunk_size: int = 512        # tokens - Gao et al. (2023)
    chunk_overlap: int = 128     # tokens
    top_k: int = 5               # nb de passages recuperes
    # nb max de passages injectes dans le prompt de generation : au-dela,
    # les passages surnumeraires diluent l'attention ("Lost in the Middle",
    # Liu et al. 2023) et alourdissent l'inference locale sur CPU
    gen_context_chunks: int = 2
    embedding_model: str = "BAAI/bge-m3"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "ansd_documents"
    rerank_threshold: float = 0.05   # seuil de pertinence minimale (CRAG, Yan et al. 2024)

    # --- Text-to-SQL ---
    database_path: str = str(BASE_DIR / "data" / "ansd_stats.db")
    sql_max_retries: int = 2     # auto-correction DIN-SQL (Pourreza & Rafiei, 2023)

    # --- Routage ---
    router_model: str = "microsoft/deberta-v3-base"
    router_confidence_threshold: float = 0.85  # en dessous -> fallback LLM
    router_artifact: str = str(BASE_DIR / "data" / "router_demo.joblib")

    # --- Guardrails ---
    max_query_length: int = 500
    faithfulness_check: bool = True

    class Config:
        env_prefix = "ANSD_"
        env_file = ".env"


settings = Settings()
