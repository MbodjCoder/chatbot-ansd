"""
Pipeline RAG (Retrieval-Augmented Generation).

Fondement : Lewis et al. (2020). Le pipeline suit les 4 etapes canoniques
documentees dans le memoire (sect. 4.2.2) :
  1. Segmentation : 512 tokens, chevauchement 128 (Gao et al., 2023)
  2. Vectorisation : BGE-M3 (Chen et al./BAAI, 2024) - dense + sparse
  3. Indexation : Qdrant / HNSW (Malkov & Yashunin, 2018)
  4. Generation ancree ("grounded generation", Asai et al., 2023)

Deux implementations du retriever derriere une interface unique :
  - BGEQdrantRetriever (production) : embeddings denses BGE-M3 + Qdrant
  - TfidfRetriever (demo)           : TF-IDF + similarite cosinus (Salton, 1975)
La substitution demo/production ne change ni l'API ni le protocole
d'evaluation : seule la qualite du retrieval varie (mesuree par RAGAS).
"""
from __future__ import annotations
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.llm.client import LLMClient


# ---------------------------------------------------------------- chunking
def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Segmentation par fenetre glissante sur les mots (proxy des tokens).

    Gao et al. (2023) : des chunks trop grands diluent la pertinence,
    trop petits perdent le contexte. 512/128 est la configuration validee.
    """
    words = text.split()
    if not words:
        return []
    step = max(1, chunk_size - overlap)
    return [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), step)]


def chunk_document(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Chunking SEMANTIQUE : segmentation d'abord par SECTION (titres markdown
    ## / #), puis fenetre glissante DANS chaque section si elle est trop longue.

    Justification : un chunk doit etre topiquement coherent. Decouper une FAQ
    ou un document multi-themes par simple fenetre de mots melange des sujets
    dans un meme chunk -> l'extraction pioche des phrases hors sujet (defaut
    constate : "contacter l'ANSD" renvoyait la phrase sur le Directeur general).
    Aligner les frontieres de chunks sur les frontieres de sections resout ce
    probleme a la racine (chunking structurel, Gao et al. 2023)."""
    # decoupe sur les titres de niveau 1-3 en debut de ligne
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


# ---------------------------------------------------------------- retrievers
class Retriever(ABC):
    @abstractmethod
    def index(self, docs: dict[str, str]) -> None: ...
    @abstractmethod
    def search(self, query: str, k: int) -> list[RetrievedChunk]: ...


class TfidfRetriever(Retriever):
    """Baseline lexicale (mode demo) - modele vectoriel de Salton et al. (1975).
    Sert aussi de BASELINE dans le protocole d'evaluation (comparaison
    retrieval lexical vs dense, cf. Karpukhin et al., 2020)."""

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import FeatureUnion
        # Deux vues complementaires (meme principe que le routeur) :
        #  - mots (1-2 grammes) : capte le sens lexical ;
        #  - caracteres (3-5 grammes) : robustesse aux variantes morphologiques,
        #    fautes et questions courtes ou l'overlap de mots est faible
        #    (defaut constate : "ou se trouve l'ANSD" ne retrouvait pas
        #    l'adresse). strip_accents : usagers avec accents, corpus sans.
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
    """Retriever de production : BGE-M3 (dense) + Qdrant (HNSW).

    BGE-M3 : support de 100+ langues dont le francais, representation
    dense + sparse (Chen et al., 2024). Qdrant : HNSW (Malkov & Yashunin,
    2018), filtrage hybride vecteur + metadonnees.
    """

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
        # P2-9 : recreate_collection est deprecie dans qdrant-client recent.
        # On supprime puis cree explicitement (API a jour, idempotente).
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
        # P2-9 : query_points remplace search() deprecie
        res = self._client.query_points(self._collection, query=qv.tolist(),
                                        limit=k)
        return [RetrievedChunk(h.payload["text"], h.payload["source"], h.score)
                for h in res.points]


# ---------------------------------------------------------------- pipeline
GROUNDED_SYSTEM = """GROUNDED_ANSWER - Tu es RAMA, l'assistant statistique officiel de \
l'ANSD (Agence Nationale de la Statistique et de la Demographie du Senegal). \
Tu es expert en statistique publique et tu t'exprimes dans un francais precis, \
pedagogique et neutre (Principe 1 de la statistique officielle : impartialite).

Regles imperatives (guardrails factuels) :
1. Reponds UNIQUEMENT a partir du <contexte>. N'invente jamais un chiffre.
2. Si l'information est absente du contexte, reponds exactement :
   "Information non disponible dans les sources ANSD."
3. Nomme l'operation statistique d'origine de chaque affirmation
   (ex. : "selon le RGPH-5 2023...", "d'apres l'EHCVM II 2021/2022...").
4. Structure : reponse directe d'abord, precisions ensuite ; utilise **gras**
   pour les chiffres cles et des listes a puces si plusieurs elements.
5. Si un <historique> est fourni, assure la coherence conversationnelle
   (resous les references aux tours precedents) sans le re-citer.
6. Termine, quand c'est pertinent, par une phrase orientant vers la
   publication officielle a consulter."""


@dataclass
class RAGResult:
    answer: str
    sources: list[dict] = field(default_factory=list)
    grounded: bool = True
    chunks: list = field(default_factory=list)  # passages retenus (preuve, P1-3)


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
        """Recuperation + construction du prompt. Renvoie (prompt, chunks
        retenus). Factorise pour eviter le DOUBLE retrieval (P1-3) : les
        chunks retournes servent AUSSI de preuve au rail de fidelite, sans
        relancer la recherche."""
        chunks = self.retriever.search(question, settings.top_k)
        # Filtrage type CRAG (Yan et al., 2024) : ecarter les passages
        # dont la pertinence est sous le seuil -> reduit le bruit injecte.
        kept = [c for c in chunks if c.score >= settings.rerank_threshold]
        if not kept:
            return "", []
        # limitation du contexte de generation (Lost in the Middle, Liu et
        # al. 2023) : les passages les mieux classes suffisent, les autres
        # diluent l'attention et alourdissent l'inference locale
        kept = kept[:settings.gen_context_chunks]
        contexte = "\n\n".join(f"[Source: {c.source}]\n{c.text}" for c in kept)
        return contexte, kept

    def answer(self, question: str, history: str = "", on_delta=None) -> RAGResult:
        """Genere la reponse documentaire ancree.

        Si `on_delta` est fourni (P0-2, streaming reel), les fragments du LLM
        sont transmis au fur et a mesure via ce callback ; le texte complet est
        neanmoins assemble et renvoye pour que le rail de fidelite s'applique en
        aval (streaming optimiste, validation a posteriori). Sans `on_delta`,
        comportement bloquant classique."""
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
