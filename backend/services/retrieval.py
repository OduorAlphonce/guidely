import logging
import time

from backend.services.embedder import Embedder
from backend.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

embedder = Embedder()
vector_store = VectorStore()


def retrieve(question: str, k: int = 5) -> list[dict]:
    """Retrieve the top-k most relevant chunks for a question.

    Returns a list of dicts with {"doc_id", "chunk_id", "text", "filename", "score"},
    most relevant first. Returns [] when the index is empty (no docs indexed yet).
    Logs the embedding vs FAISS-search latency breakdown per call.
    """
    if vector_store.count() == 0:
        logger.info("Vector store is empty, nothing to retrieve")
        return []

    embed_start = time.perf_counter()
    query_vector = embedder.embed(question)
    embedding_ms = round((time.perf_counter() - embed_start) * 1000, 2)

    search_start = time.perf_counter()
    results = vector_store.search(query_vector, k=k)
    search_ms = round((time.perf_counter() - search_start) * 1000, 2)

    logger.info(
        "retrieve top-%d embedding_ms=%.2f search_ms=%.2f hits=%d",
        k,
        embedding_ms,
        search_ms,
        len(results),
    )
    return results
