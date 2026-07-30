import json
import logging
from pathlib import Path

import faiss
import numpy as np

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self, index_path: str = "data/faiss_index"):
        self._index_path = Path(index_path)
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._index = None
        self._metadata = []
        self.load()

    def add(self, vectors: list[list[float]], metadata: list[dict]):
        if not vectors:
            return
        if self._index is None:
            dim = len(vectors[0])
            self._index = faiss.IndexFlatIP(dim)
        vectors_np = np.array(vectors, dtype=np.float32)
        faiss.normalize_L2(vectors_np)
        self._index.add(vectors_np)
        self._metadata.extend(metadata)

    def search(self, query_vector: list[float], k: int = 5) -> list[dict]:
        if self._index is None or self._index.ntotal == 0:
            return []
        query_np = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(query_np)
        scores, indices = self._index.search(query_np, min(k, self._index.ntotal))
        results = []
        for score, idx in zip(scores[0], indices[0]):
            meta = self._metadata[idx]
            results.append({
                "doc_id": meta["doc_id"],
                "chunk_id": meta["chunk_id"],
                "text": meta["text"],
                "filename": meta["filename"],
                "score": float(score),
            })
        return results

    def save(self):
        if self._index is None:
            return
        faiss.write_index(self._index, str(self._index_path.with_suffix(".faiss")))
        with open(self._index_path.with_suffix(".meta.json"), "w") as f:
            json.dump(self._metadata, f)
        logger.info("Saved index with %d vectors to %s", self._index.ntotal, self._index_path)

    def load(self):
        index_file = self._index_path.with_suffix(".faiss")
        meta_file = self._index_path.with_suffix(".meta.json")
        if index_file.exists() and meta_file.exists():
            self._index = faiss.read_index(str(index_file))
            with open(meta_file) as f:
                self._metadata = json.load(f)
            logger.info("Loaded index with %d vectors from %s", self._index.ntotal, self._index_path)

    def count(self) -> int:
        return self._index.ntotal if self._index is not None else 0

    def clear(self):
        self._index = None
        self._metadata = []
        index_file = self._index_path.with_suffix(".faiss")
        meta_file = self._index_path.with_suffix(".meta.json")
        index_file.unlink(missing_ok=True)
        meta_file.unlink(missing_ok=True)
