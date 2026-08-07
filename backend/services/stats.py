import threading


class Stats:
    """Process-wide operational counters for search, indexing, and errors.

    Thread-safe so the /metrics endpoint (and diagnostics) can read running
    totals while request and indexing workers are updating them concurrently.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._queries_served = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._error_counts: dict[str, int] = {}

    def record_query(self) -> int:
        with self._lock:
            self._queries_served += 1
            return self._queries_served

    def record_cache_hit(self) -> int:
        with self._lock:
            self._cache_hits += 1
            return self._cache_hits

    def record_cache_miss(self) -> int:
        with self._lock:
            self._cache_misses += 1
            return self._cache_misses

    def record_error(self, error_type: str) -> int:
        with self._lock:
            self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1
            return self._error_counts[error_type]

    @property
    def queries_served(self) -> int:
        with self._lock:
            return self._queries_served

    @property
    def cache_hits(self) -> int:
        with self._lock:
            return self._cache_hits

    @property
    def cache_misses(self) -> int:
        with self._lock:
            return self._cache_misses

    def get_error_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._error_counts)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total_queries": self._queries_served,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "error_counts": dict(self._error_counts),
            }

    def reset(self) -> None:
        with self._lock:
            self._queries_served = 0
            self._cache_hits = 0
            self._cache_misses = 0
            self._error_counts.clear()


stats = Stats()
