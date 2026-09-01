"""Day 4 verification for issue #29 (/metrics) and issue #30 (request-id).

Run from the repo root:
    python backend/tests/test_metrics.py

Covers:
  #30
    1. Every /search response carries a request id
    2. Incoming X-Request-ID is propagated back (optional forwarding)
    3. Fresh ids are generated per request
    4. Error responses still carry the request id
    5. Request ids appear in search log output
    6. /documents responses carry the request id
  #29
    7. /metrics returns live doc count, chunk count, query count, cache
       hits/misses, and error counts from real state
"""

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Force the offline sentence-transformers fallback so tests never touch OpenAI.
os.environ["OPENROUTER_API_KEY"] = ""

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

from backend.main import app
from backend.routes import documents as documents_route
from backend.routes import search as search_route
from backend.services import indexing
from backend.services.cache import EmbeddingCache
from backend.services.stats import stats
from backend.services.vector_store import VectorStore

logging.getLogger().setLevel(logging.CRITICAL)

PASS = 0
FAIL = 0
FAILURES = []

CLIENT = TestClient(app)


class CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.messages = []

    def emit(self, record):
        self.messages.append(self.format(record))


class FakeLLM:
    def __init__(self, answer="Canned answer", error=None):
        self._answer = answer
        self._error = error
        self.model = "gpt-3.5-turbo"

    def generate_answer(self, question, context):
        if self._error is not None:
            raise self._error
        return self._answer


class StubEmbedder:
    """Deterministic embedder so the metrics test never loads a real model."""

    def __init__(self, dim=384):
        self._dim = dim

    def embed_batch(self, texts):
        return [[float(i) / 10.0] * self._dim for i in range(len(texts))]


def check(description, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {description}")
    else:
        FAIL += 1
        FAILURES.append(description)
        print(f"  [FAIL] {description}")


# ---------------------------------------------------------------- issue #30


def test_search_response_carries_request_id():
    print("\nTest 1: /search response carries X-Request-ID")
    search_route.retrieve = lambda question, k=5: []
    search_route.llm = FakeLLM()

    resp = CLIENT.post("/api/search/", json={"question": "remote days?"})

    check("returns HTTP 200", resp.status_code == 200)
    check("response has a non-empty X-Request-ID", bool(resp.headers.get("X-Request-ID")))


def test_incoming_request_id_is_propagated():
    print("\nTest 2: incoming X-Request-ID is propagated back")
    search_route.retrieve = lambda question, k=5: []
    search_route.llm = FakeLLM()

    resp = CLIENT.post(
        "/api/search/",
        json={"question": "remote days?"},
        headers={"X-Request-ID": "trace-abc-123"},
    )

    check("response echoes the supplied id", resp.headers.get("X-Request-ID") == "trace-abc-123")


def test_new_request_ids_differ():
    print("\nTest 3: each request gets a distinct id when none is supplied")
    search_route.retrieve = lambda question, k=5: []
    search_route.llm = FakeLLM()

    id1 = CLIENT.post("/api/search/", json={"question": "q1"}).headers.get("X-Request-ID")
    id2 = CLIENT.post("/api/search/", json={"question": "q2"}).headers.get("X-Request-ID")

    check("ids are non-empty and differ", bool(id1) and bool(id2) and id1 != id2)


def test_error_response_carries_request_id():
    print("\nTest 4: error responses carry X-Request-ID")
    resp = CLIENT.post("/api/search/", json={"question": ""})

    check("returns HTTP 400", resp.status_code == 400)
    check("400 response has X-Request-ID", bool(resp.headers.get("X-Request-ID")))


def test_request_id_in_search_logs():
    print("\nTest 5: request id appears in search log output")
    handler = CapturingHandler()
    search_route.logger.addHandler(handler)
    search_route.logger.setLevel(logging.INFO)
    try:
        search_route.retrieve = lambda question, k=5: []
        search_route.llm = FakeLLM()
        CLIENT.post(
            "/api/search/",
            json={"question": "remote days?"},
            headers={"X-Request-ID": "trace-log-9"},
        )
        lines = [m for m in handler.messages if "request_id=trace-log-9" in m]
        check("a log line carries the request id", len(lines) >= 1)
    finally:
        search_route.logger.removeHandler(handler)


def test_documents_response_carries_request_id():
    print("\nTest 6: /documents responses carry X-Request-ID")
    resp = CLIENT.get("/api/documents/")

    check("returns HTTP 200", resp.status_code == 200)
    check("documents response has X-Request-ID", bool(resp.headers.get("X-Request-ID")))


# ---------------------------------------------------------------- issue #29


def _seed_one_doc(tmpdir):
    """Point singletons at temp storage and index a single document."""
    original = (indexing.cache, indexing.vector_store, indexing.embedder)
    doc = tmpdir / "policy.txt"
    doc.write_text(
        "Guidely policy: employees may work remotely up to two days per week. "
        "Expense reports require itemized receipts.\n\n"
        "Travel bookings must be made through the approved portal.\n" * 20
    )
    indexing.cache = EmbeddingCache(str(tmpdir / "embedding_cache.json"))
    indexing.vector_store = VectorStore(str(tmpdir / "faiss_index"))
    indexing.embedder = StubEmbedder()
    indexing.index_document(str(doc))
    return original


def test_metrics_returns_real_state():
    print("\nTest 7: /metrics returns live doc/chunk/query/cache/error stats")
    stats.reset()
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_metrics_test_"))
    original = _seed_one_doc(tmpdir)
    try:
        search_route.retrieve = lambda question, k=5: [{
            "filename": "policy.txt",
            "text": "Employees may work remotely up to two days per week.",
            "score": 0.91,
        }]
        search_route.llm = FakeLLM(error=ValueError(
            "OPENROUTER_API_KEY is not set. Add it to the .env file before asking questions."
        ))
        CLIENT.post("/api/search/", json={"question": "missing key"})

        search_route.llm = FakeLLM()
        CLIENT.post("/api/search/", json={"question": "remote days?"})

        resp = CLIENT.get("/metrics")
        check("returns HTTP 200", resp.status_code == 200)
        body = resp.json()
        check("total_documents populated", body["total_documents"] == 1)
        check("total_chunks populated", body["total_chunks"] > 0)
        check("total_queries counted", body["total_queries"] == 2)
        check("cache stats populated", body["cache_hits"] == 0 and body["cache_misses"] >= 1)
        check("error_counts populated", body["error_counts"].get("search:ValueError") == 1)
    finally:
        indexing.cache, indexing.vector_store, indexing.embedder = original
        shutil.rmtree(tmpdir, ignore_errors=True)
        stats.reset()


def main():
    print("=" * 64)
    print("Guidely Day 4 — /metrics (#29) and request-id (#30)")
    print("=" * 64)

    test_search_response_carries_request_id()
    test_incoming_request_id_is_propagated()
    test_new_request_ids_differ()
    test_error_response_carries_request_id()
    test_request_id_in_search_logs()
    test_documents_response_carries_request_id()
    test_metrics_returns_real_state()

    print("\n" + "=" * 64)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    if FAILURES:
        print("Failed checks:")
        for f in FAILURES:
            print(f"  - {f}")
    print("=" * 64)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
