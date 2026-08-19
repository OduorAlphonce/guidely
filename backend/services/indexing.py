import logging
from pathlib import Path

from backend.services.auto_tag import auto_tag
from backend.services.cache import EmbeddingCache
from backend.services.chunker import chunk_text
from backend.services.embedder import Embedder
from backend.services.parser import compute_md5, parse_file
from backend.services.stats import stats
from backend.services.tags import TagStore
from backend.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BACKEND_DIR / "data" / "uploads"
SAMPLE_DOCS_DIR = BACKEND_DIR / "data" / "sample-docs"

embedder = Embedder()
cache = EmbeddingCache()
vector_store = VectorStore()
tag_store = TagStore(str(BACKEND_DIR / "data" / "tags.json"))


def index_document(file_path: str) -> dict:
    """Index a single file end-to-end: parse -> chunk -> embed -> store -> cache.

    Returns a dict describing the outcome:
      {"file", "status" ("indexed" | "skipped"), "doc_id", "chunks"}
    """
    path = Path(file_path)
    md5 = compute_md5(file_path)

    if not cache.needs_update(file_path, md5):
        logger.info("Skipping unchanged file %s (cache hit)", file_path)
        return {"file": file_path, "status": "skipped", "doc_id": md5, "chunks": 0}

    try:
        result = _index_new(file_path, path, md5)
        existing_tags = tag_store.get_tags(md5)
        if not existing_tags:
            auto_tags = auto_tag(path.name)
            if auto_tags:
                tag_store.set_tags(md5, auto_tags)
                logger.info("Auto-tagged %s: %s", path.name, auto_tags)
        return result
    except Exception as e:
        error_count = stats.record_error(f"indexing:{type(e).__name__}")
        logger.exception(
            "Indexing %s failed (error_count=%d)", file_path, error_count
        )
        raise


def _index_new(file_path: str, path: Path, md5: str) -> dict:
    logger.info("Indexing %s (md5=%s)", file_path, md5)

    text = parse_file(file_path)
    chunks = chunk_text(text)
    logger.info("Chunked %s into %d chunks", file_path, len(chunks))

    vectors = embedder.embed_batch([c["text"] for c in chunks])
    logger.info("Embedded %s: %d vectors", file_path, len(vectors))

    metadata = [
        {
            "doc_id": md5,
            "chunk_id": f"{md5}:{c['index']}",
            "text": c["text"],
            "filename": path.name,
            "index": c["index"],
        }
        for c in chunks
    ]

    vector_store.add(vectors, metadata)
    vector_store.save()

    cached_chunks = [{**c, "embedding": vectors[i]} for i, c in enumerate(chunks)]
    cache.mark_indexed(file_path, md5, chunks=cached_chunks)

    logger.info("Finished indexing %s: %d chunks stored", file_path, len(chunks))
    return {"file": file_path, "status": "indexed", "doc_id": md5, "chunks": len(chunks)}
