"""In-memory query log with CSV export.

Stores every search query with timestamp, latency, and sourced documents
so admins can export a CSV for analysis.
"""

import csv
import io
import threading
import time
from datetime import datetime, timezone


class QueryLog:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: list[dict] = []

    def record(
        self,
        question: str,
        answer: str,
        sources: list[str],
        latency_ms: float,
        status: str = "ok",
    ):
        with self._lock:
            self._entries.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "question": question,
                "answer_preview": answer[:200],
                "sources": "; ".join(sources),
                "source_count": len(sources),
                "latency_ms": round(latency_ms, 2),
                "status": status,
            })

    def entries(self) -> list[dict]:
        with self._lock:
            return list(self._entries)

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def export_csv(self) -> str:
        with self._lock:
            if not self._entries:
                return ""
            buf = io.StringIO()
            fieldnames = [
                "timestamp", "question", "answer_preview",
                "sources", "source_count", "latency_ms", "status",
            ]
            writer = csv.DictWriter(buf, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self._entries)
            return buf.getvalue()


query_log = QueryLog()
