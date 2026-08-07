import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

from backend.services.stats import stats

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = str(Path(__file__).resolve().parent.parent / "data" / "embedding_cache.json")


class EmbeddingCache:
    """Disk-persisted cache of chunks + embeddings keyed by file content hash.

    Lets the indexing pipeline skip re-embedding (and re-chunking) files whose
    content has not changed since they were last indexed.
    """

    def __init__(self, cache_path: str = DEFAULT_CACHE_PATH):
        self._cache_path = Path(cache_path)
        self._lock = threading.RLock()
        self._data = {"files": {}}
        self.load()

    def needs_update(self, file_path: str, current_md5: str) -> bool:
        """Return True when the file has no cached entry or its content changed.

        Records and logs an embedding-cache hit/miss so re-indexing behaviour
        is visible in uvicorn output (Day 4, issue #28).
        """
        entry = self._data["files"].get(self._normalize_path(file_path))
        if entry is not None and entry.get("md5") == current_md5:
            hits = stats.record_cache_hit()
            logger.info("embedding cache hit file=%s hits=%d", file_path, hits)
            return False
        misses = stats.record_cache_miss()
        logger.info("embedding cache miss file=%s misses=%d", file_path, misses)
        return True

    def mark_indexed(self, file_path: str, md5: str, chunks: list[dict] | None = None) -> None:
        """Record that a file was indexed, along with its chunks/embeddings."""
        with self._lock:
            self._data["files"][self._normalize_path(file_path)] = {
                "md5": md5,
                "chunks": chunks or [],
                "indexed_at": datetime.utcnow().isoformat(),
            }
        self.save()

    def get_cached_chunks(self, file_path: str) -> list[dict] | None:
        """Return cached chunks (with embeddings) for an unchanged file, else None."""
        entry = self._data["files"].get(self._normalize_path(file_path))
        if entry is None:
            return None
        return entry.get("chunks")

    def remove(self, file_path: str) -> None:
        """Drop the cached entry for a single file."""
        key = self._normalize_path(file_path)
        with self._lock:
            if key in self._data["files"]:
                del self._data["files"][key]
        self.save()

    def remove_by_md5(self, md5: str) -> int:
        """Drop every cached entry whose content hash matches; return count removed."""
        removed = 0
        with self._lock:
            for key, entry in list(self._data["files"].items()):
                if entry.get("md5") == md5:
                    del self._data["files"][key]
                    removed += 1
        if removed:
            self.save()
        return removed

    def list_files(self) -> dict:
        """Return the cached file entries keyed by normalized path."""
        return dict(self._data["files"])

    def clear(self) -> None:
        """Drop every cached entry."""
        with self._lock:
            self._data = {"files": {}}
        self.save()

    def file_count(self) -> int:
        return len(self._data["files"])

    def save(self) -> None:
        with self._lock:
            payload = json.dumps(self._data, indent=2)
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._cache_path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self._cache_path)
        logger.info("Saved embedding cache (%d files) to %s", len(self._data["files"]), self._cache_path)

    def load(self) -> None:
        if not self._cache_path.exists():
            return
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load cache %s: %s", self._cache_path, e)
            return
        if isinstance(data, dict) and isinstance(data.get("files"), dict):
            self._data = data
            logger.info("Loaded embedding cache (%d files) from %s", len(self._data["files"]), self._cache_path)
        else:
            logger.warning("Invalid cache file %s, starting empty", self._cache_path)

    @staticmethod
    def _normalize_path(file_path: str) -> str:
        return os.path.abspath(os.path.normpath(file_path))
