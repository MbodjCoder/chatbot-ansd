"""Voie documentaire : recherche des passages pertinents, puis réponse ancrée.

1. Découpage des documents par section, puis par fenêtres de 512 mots.
2. Recherche : index TF-IDF (TfidfRetriever), ou BGE-M3 et Qdrant si installés.
3. Rédaction à partir des seuls passages retenus.
"""
from __future__ import annotations
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.llm.client import LLMClient


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Fenêtre glissante sur les mots."""
    words = text.split()
    if not words:
        return []
    step = max(1, chunk_size - overlap)
    return [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), step)]


def chunk_document(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Découpe par section (titres markdown), puis par fenêtre si la section est
    longue : chaque passage reste sur un seul sujet."""
    # titres de niveau 1 à 3
    parts = re.split(r"\n(?=#{1,3}\s)", text)
    chunks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part.split()) <= chunk_size:
            chunks.append(part)
        else:
            chunks.extend(chunk_text(part, chunk_size, overlap))
    return chunks or chunk_text(text, chunk_size, overlap)


@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float


class Retriever(ABC):
    @abstractmethod
    def index(self, docs: dict[str, str]) -> None: ...
    @abstractmethod
    def search(self, query: str, k: int) -> list[RetrievedChunk]: ...


class TfidfRetriever(Retriever):
    """Recherche lexicale TF-IDF, similarité cosinus."""

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import FeatureUnion
        # mots (sens) et fragments de mots (fautes, variantes), sans accents
        self._vec = FeatureUnion([
            ("mots", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True,
                                     strip_accents="unicode")),
            ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                      strip_accents="unicode", sublinear_tf=True)),
        ])
        self._chunks: list[tuple[str, str]] = []
        self._matrix = None

    def index(self, docs: dict[str, str]) -> None:
        self._chunks = [
            (chunk, src)
            for src, text in docs.items()
            for chunk in chunk_document(text, settings.chunk_size, settings.chunk_overlap)
        ]
        corpus = [c for c, _ in self._chunks]
        self._matrix = self._vec.fit_transform(corpus)

    def search(self, query: str, k: int) -> list[RetrievedChunk]:
        from sklearn.metrics.pairwise import cosine_similarity
        qv = self._vec.transform([query])
        sims = cosine_similarity(qv, self._matrix)[0]
        order = sims.argsort()[::-1][:k]
        return [RetrievedChunk(self._chunks[i][0], self._chunks[i][1], float(sims[i]))
                for i in order]


class BGEQdrantRetriever(Retriever):
    """Recherche sémantique : plongements BGE-M3 et index Qdrant (optionnel)."""

    def __init__(self):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        from FlagEmbedding import BGEM3FlagModel
        self._model = BGEM3FlagModel(settings.embedding_model, use_fp16=True)
        self._client = QdrantClient(url=settings.qdrant_url)
        self._collection = settings.qdrant_collection
        self._Distance, self._VectorParams = Distance, VectorParams

    def index(self, docs: dict[str, str]) -> None:
        from qdrant_client.models import PointStruct
        chunks = [
            (chunk, src)
            for src, text in docs.items()
            for chunk in chunk_document(text, settings.chunk_size, settings.chunk_overlap)
        ]
        vectors = self._model.encode([c for c, _ in chunks])["dense_vecs"]
        # collection recréée à chaque indexation
        if self._client.collection_exists(self._collection):
            self._client.delete_collection(self._collection)
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=self._VectorParams(size=len(vectors[0]),
                                              distance=self._Distance.COSINE),
        )
        self._client.upsert(self._collection, points=[
            PointStruct(id=i, vector=v.tolist(),
                        payload={"text": c, "source": s})
            for i, (v, (c, s)) in enumerate(zip(vectors, chunks))
        ])

    def search(self, query: str, k: int) -> list[RetrievedChunk]:
        qv = self._model.encode([query])["dense_vecs"][0]
        res = self._client.query_points(self._collection, query=qv.tolist(),
                                        limit=k)
        return [RetrievedChunk(h.payload["text"], h.payload["source"], h.score)
                for h in res.points]


GROUNDED_SYSTEM = """GROUNDED_ANSWER - Tu es l'assistant statistique du Chatbot ANSD \
(données de l'Agence nationale de la Statistique et de la Démographie du Sénégal). \
Tu t'exprimes dans un français précis, pédagogique et neutre.

Règles :
1. Réponds uniquement à partir du <contexte>. N'invente jamais un chiffre.
2. Si l'information est absente du contexte, réponds exactement :
   "Information non disponible dans les sources ANSD."
3. Nomme l'opération statistique d'origine de chaque affirmation
   (ex. : "selon le RGPH-5 2023...", "d'après l'EHCVM II 2021/2022...").
4. Réponse directe d'abord, précisions ensuite ; **gras** pour les chiffres
   clés, listes à puces si plusieurs éléments.
5. Si un <historique> est fourni, tiens compte des tours précédents sans les répéter.
6. Termine, quand c'est pertinent, par une phrase orientant vers la
   publication officielle a consulter."""


@dataclass
class RAGResult:
    answer: str
    sources: list[dict] = field(default_factory=list)
    grounded: bool = True
    chunks: list = field(default_factory=list)  # passages retenus (preuve)


class RAGPipeline:
    def __init__(self, llm: LLMClient, retriever: Retriever | None = None):
        self.llm = llm
        self.retriever = retriever or TfidfRetriever()

    def ingest_directory(self, path: str | Path) -> int:
        docs = {p.name: p.read_text(encoding="utf-8")
                for p in sorted(Path(path).glob("*.md"))}
        self.retriever.index(docs)
        return len(docs)

    def _prepare(self, question: str) -> tuple[str, list]:
        """Recherche et construction de la consigne ; renvoie (consigne, passages)."""
        chunks = self.retriever.search(question, settings.top_k)
        # passages sous le seuil de pertinence écartés
        kept = [c for c in chunks if c.score >= settings.rerank_threshold]
        if not kept:
            return "", []
        # seuls les meilleurs passages sont transmis
        kept = kept[:settings.gen_context_chunks]
        contexte = "\n\n".join(f"[Source: {c.source}]\n{c.text}" for c in kept)
        return contexte, kept

    def answer(self, question: str, history: str = "", on_delta=None) -> RAGResult:
        """Réponse documentaire. `on_delta` reçoit les fragments au fil de la
        rédaction ; le texte complet est renvoyé pour le contrôle de fidélité."""
        contexte, kept = self._prepare(question)
        if not kept:
            return RAGResult("Information non disponible dans les sources ANSD.",
                             [], grounded=False)
        hist = f"<historique>{history}</historique>\n" if history else ""
        prompt = f"{hist}<contexte>{contexte}</contexte>\n<question>{question}</question>"
        sources = [{"document": c.source, "score": round(c.score, 3)} for c in kept]
        if on_delta is not None:
            morceaux = []
            for frag in self.llm.complete_stream(GROUNDED_SYSTEM, prompt,
                                                 temperature=settings.llm_temperature):
                morceaux.append(frag)
                on_delta(frag)
            return RAGResult(answer="".join(morceaux).strip(),
                             sources=sources, chunks=kept)
        resp = self.llm.complete(GROUNDED_SYSTEM, prompt,
                                 temperature=settings.llm_temperature)
        return RAGResult(answer=resp.text.strip(), sources=sources, chunks=kept)
