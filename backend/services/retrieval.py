import logging

from backend.services.embedder import Embedder
from backend.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

embedder = Embedder()
vector_store = VectorStore()


def retrieve(question: str, k: int = 5) -> list[dict]:
    """Retrieve the top-k most relevant chunks for a question.

    Returns a list of dicts with {"doc_id", "chunk_id", "text", "filename", "score"},
    most relevant first. Returns [] when the index is empty (no docs indexed yet).
    """
    if vector_store.count() == 0:
        logger.info("Vector store is empty, nothing to retrieve")
        return []

    query_vector = embedder.embed(question)
    logger.info("Retrieved top-%d results for question", k)
    return vector_store.search(query_vector, k=k)
