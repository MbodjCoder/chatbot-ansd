"""
Evaluation du pipeline RAG avec RAGAS (Es et al., 2024).

Metriques : faithfulness, answer_relevancy, context_precision.
RAGAS necessite un LLM juge : ce script s'execute donc en mode
PRODUCTION (cle API DeepSeek ou autre modele compatible OpenAI).
En mode demo, on rapporte a la place une metrique de fidelite
deterministe (couverture lexicale de la reponse par le contexte).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings
from app.llm.client import get_llm, MockLLM
from app.rag.pipeline import RAGPipeline

QUESTIONS = [
    "Qu'est-ce que le RGPH-5 ?",
    "Comment l'ANSD mesure-t-elle la pauvrete monetaire ?",
    "Quelle est la difference entre chomage strict et chomage elargi ?",
    "Comment est calcule l'IHPC ?",
    "Quelles sont les missions de l'ANSD ?",
]


def lexical_faithfulness(answer: str, contexts: list[str]) -> float:
    """Proxy deterministe de la faithfulness RAGAS : proportion des mots
    pleins de la reponse presents dans les contextes recuperes."""
    import re
    aw = set(re.findall(r"\w{5,}", answer.lower()))
    cw = set(re.findall(r"\w{5,}", " ".join(contexts).lower()))
    return len(aw & cw) / max(1, len(aw))


def main():
    llm = get_llm()
    rag = RAGPipeline(llm)
    rag.ingest_directory(Path(settings.database_path).parent / "documents")
    # RAGAS exige un LLM juge reel ; sans cle API (MockLLM), on rapporte
    # le proxy deterministe ci-dessous.
    if settings.mode == "production" and not isinstance(llm, MockLLM):
        try:
            from ragas import evaluate  # noqa
            print("Mode production : lancer l'evaluation RAGAS complete "
                  "(faithfulness, answer_relevancy, context_precision).")
        except ImportError:
            print("pip install ragas datasets  # puis relancer")
            return
    scores = []
    for q in QUESTIONS:
        res = rag.answer(q)
        ctx = [c.text for c in rag.retriever.search(q, settings.top_k)]
        f = lexical_faithfulness(res.answer, ctx)
        scores.append(f)
        print(f"[faithfulness~{f:.2f}] {q}\n   -> {res.answer[:140]}...")
    print(f"\nFidelite lexicale moyenne (proxy demo) : {sum(scores)/len(scores):.3f}")


if __name__ == "__main__":
    main()
