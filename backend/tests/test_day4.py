"""Day 4 verification for issue #27 (edge cases) and issue #28 (auto-logging/stats).

Run from the repo root:
    python backend/tests/test_day4.py

Covers:
  #27
    1. Empty query -> 400 (still holds)
    2. No results -> graceful message (still holds)
    3. Missing OPENROUTER_API_KEY -> actionable 500 (still holds)
    4. Corrupted file upload -> HTTP 400 with a clear message
    5. Empty file upload -> HTTP 400 with a clear message
    6. Re-index reports a corrupted file as failed without crashing
    7. LLM timeout -> graceful 200 fallback with the retrieved snippets
  #28
    8. Embedding cache hits/misses are counted and logged during (re)indexing
    9. Error types/counts are tracked
    10. Every /search request increments the query counter
"""

import logging
import shutil
import sys
import tempfile
from pathlib import Path

# Force the offline sentence-transformers fallback so tests never touch OpenAI.
os_environ = __import__("os").environ
os_environ["OPENROUTER_API_KEY"] = ""

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
from backend.services.llm import LLMTimeoutError
from backend.services.stats import stats
from backend.services.vector_store import VectorStore

logging.getLogger().setLevel(logging.CRITICAL)

PASS = 0
FAIL = 0
FAILURES = []

CLIENT = TestClient(app)

SAMPLE_CHUNKS = [
    {
        "doc_id": "a",
        "chunk_id": "a:0",
        "filename": "policy.txt",
        "text": "Employees may work remotely up to two days per week.",
        "score": 0.91,
    },
    {
        "doc_id": "b",
        "chunk_id": "b:0",
        "filename": "howto.txt",
        "text": "Submit expense reports through the finance portal.",
        "score": 0.88,
    },
]


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
        self.calls = []
        self.model = "gpt-3.5-turbo"

    def generate_answer(self, question, context):
        self.calls.append({"question": question, "context": context})
        if self._error is not None:
            raise self._error
        return self._answer


class StubEmbedder:
    """Deterministic embedder so the cache tests never load a real model."""

    def __init__(self, dim=384):
        self._dim = dim
        self.batch_calls = 0

    def embed_batch(self, texts):
        self.batch_calls += 1
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


# ---------------------------------------------------------------- issue #27


def test_empty_query_still_rejected():
    print("\nTest 1: Empty query -> 400 (still holds)")
    resp = CLIENT.post("/api/search/", json={"question": "   "})
    check("returns HTTP 400", resp.status_code == 400)


def test_no_results_still_graceful():
    print("\nTest 2: No results -> graceful message (still holds)")
    search_route.retrieve = lambda question, k=5: []
    search_route.llm = FakeLLM()
    resp = CLIENT.post("/api/search/", json={"question": "How do I fold a taco?"})
    check("returns HTTP 200", resp.status_code == 200)
    check("graceful no-results message", resp.json()["answer"] == search_route.NO_RESULTS_MESSAGE)


def test_missing_api_key_still_actionable():
    print("\nTest 3: Missing OPENROUTER_API_KEY -> actionable 500 (still holds)")
    search_route.retrieve = lambda question, k=5: SAMPLE_CHUNKS
    search_route.llm = FakeLLM(error=ValueError(
        "OPENROUTER_API_KEY is not set. Add it to the .env file before asking questions."
    ))
    resp = CLIENT.post("/api/search/", json={"question": "How many remote days?"})
    check("returns HTTP 500", resp.status_code == 500)
    detail = resp.json()["detail"]
    check("error names OPENROUTER_API_KEY and remediation", "OPENROUTER_API_KEY" in detail and ".env" in detail)


def test_corrupted_file_upload_400():
    print("\nTest 4: Corrupted file upload -> HTTP 400")
    resp = CLIENT.post(
        "/api/documents/upload",
        files={"file": ("broken.txt", b"\x00\xff\x01\xfeMZ\x90", "text/plain")},
    )
    check("returns HTTP 400", resp.status_code == 400)
    check("message names the corruption", "corrupt" in resp.json()["detail"].lower())


def test_empty_file_upload_400():
    print("\nTest 5: Empty file upload -> HTTP 400")
    resp = CLIENT.post(
        "/api/documents/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    check("returns HTTP 400", resp.status_code == 400)
    check("message names the empty file", "empty" in resp.json()["detail"].lower())


def test_reindex_reports_corrupted_file_as_failed():
    print("\nTest 6: Re-index reports a corrupted file as failed, continues others")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_day4_reindex_"))
    original = (documents_route.SAMPLE_DOCS_DIR, documents_route.UPLOADS_DIR)
    try:
        (tmpdir / "corrupted.txt").write_bytes(b"\x00\xff\x01MZ\x90 binary garbage")
        documents_route.SAMPLE_DOCS_DIR = tmpdir
        documents_route.UPLOADS_DIR = tmpdir / "uploads"

        resp = CLIENT.post("/api/documents/reindex")

        check("returns HTTP 200", resp.status_code == 200)
        body = resp.json()
        check("reports exactly 1 file total", body["total"] == 1)
        check("marks it failed", body["failed"] == 1 and body["results"][0]["status"] == "failed")
        check("failure carries the corruption message", "corrupt" in body["results"][0]["error"].lower())
    finally:
        documents_route.SAMPLE_DOCS_DIR, documents_route.UPLOADS_DIR = original
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_llm_timeout_fallback():
    print("\nTest 7: LLM timeout -> graceful fallback with retrieved snippets")
    stats.reset()
    search_route.retrieve = lambda question, k=5: SAMPLE_CHUNKS
    search_route.llm = FakeLLM(error=LLMTimeoutError("Answer model timed out after 30 seconds"))

    resp = CLIENT.post("/api/search/", json={"question": "How many remote days?"})

    check("returns HTTP 200 (not 500)", resp.status_code == 200)
    body = resp.json()
    check("explains the timeout", "timed out" in body["answer"].lower())
    check("includes the retrieved snippets", "policy.txt" in body["answer"] and "howto.txt" in body["answer"])
    check("still returns sources", len(body["sources"]) == 2)
    check("latency_ms is populated", body["latency_ms"] > 0)


# ---------------------------------------------------------------- issue #28


def test_cache_hits_misses_counted_and_logged():
    print("\nTest 8: Cache hits/misses counted and logged during (re)indexing")
    stats.reset()

    handler = CapturingHandler()
    cache_logger = logging.getLogger("backend.services.cache")
    cache_logger.addHandler(handler)
    cache_logger.setLevel(logging.INFO)

    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_day4_cache_"))
    original = (indexing.cache, indexing.vector_store, indexing.embedder)
    try:
        doc = tmpdir / "policy.txt"
        doc.write_text(
            "Guidely policy: employees may work remotely up to two days per week. "
            "Expense reports require itemized receipts and pre-approval.\n\n"
            "Travel bookings must be made through the approved portal.\n" * 30
        )

        indexing.cache = EmbeddingCache(str(tmpdir / "embedding_cache.json"))
        indexing.vector_store = VectorStore(str(tmpdir / "faiss_index"))
        indexing.embedder = StubEmbedder()

        first = indexing.index_document(str(doc))
        second = indexing.index_document(str(doc))

        check("first pass indexed the file", first["status"] == "indexed")
        check("second pass was a cache hit (skipped)", second["status"] == "skipped")
        check("exactly 1 cache miss recorded", stats.cache_misses == 1)
        check("exactly 1 cache hit recorded", stats.cache_hits == 1)

        messages = "\n".join(handler.messages)
        check("cache miss logged in uvicorn output", "embedding cache miss file=" in messages)
        check("cache hit logged in uvicorn output", "embedding cache hit file=" in messages)
    finally:
        indexing.cache, indexing.vector_store, indexing.embedder = original
        cache_logger.removeHandler(handler)
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_error_counts_tracked():
    print("\nTest 9: Error types/counts tracked")
    stats.reset()

    search_route.retrieve = lambda question, k=5: SAMPLE_CHUNKS
    search_route.llm = FakeLLM(error=LLMTimeoutError("timeout"))
    CLIENT.post("/api/search/", json={"question": "timeout case"})
    check("LLM timeout counted", stats.get_error_counts().get("search:LLMTimeoutError") == 1)

    search_route.llm = FakeLLM(error=ValueError("OPENROUTER_API_KEY is not set. Add it to the .env file."))
    CLIENT.post("/api/search/", json={"question": "missing key case"})
    check("missing-key ValueError counted", stats.get_error_counts().get("search:ValueError") == 1)

    search_route.llm = FakeLLM(error=RuntimeError("boom"))
    CLIENT.post("/api/search/", json={"question": "generic failure"})
    check("generic failure counted", stats.get_error_counts().get("search:RuntimeError") == 1)

    before = dict(stats.get_error_counts())
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_day4_err_"))
    original = (documents_route.SAMPLE_DOCS_DIR, documents_route.UPLOADS_DIR)
    try:
        (tmpdir / "corrupted.txt").write_bytes(b"\x00\xff\x01MZ\x90")
        documents_route.SAMPLE_DOCS_DIR = tmpdir
        documents_route.UPLOADS_DIR = tmpdir / "uploads"
        CLIENT.post("/api/documents/reindex")
        after = dict(stats.get_error_counts())
        check("indexing error counted", after.get("indexing:ValueError", 0) == before.get("indexing:ValueError", 0) + 1)
    finally:
        documents_route.SAMPLE_DOCS_DIR, documents_route.UPLOADS_DIR = original
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_query_counter_increments():
    print("\nTest 10: Every /search request increments the query counter")
    stats.reset()
    search_route.retrieve = lambda question, k=5: []
    search_route.llm = FakeLLM()

    CLIENT.post("/api/search/", json={"question": "first"})
    CLIENT.post("/api/search/", json={"question": "second"})
    CLIENT.post("/api/search/", json={"question": ""})

    check("query counter == 3 (incl. rejected empty query)", stats.queries_served == 3)


def main():
    print("=" * 64)
    print("Guidely Day 4 — edge cases (#27) and auto-logging/stats (#28)")
    print("=" * 64)

    test_empty_query_still_rejected()
    test_no_results_still_graceful()
    test_missing_api_key_still_actionable()
    test_corrupted_file_upload_400()
    test_empty_file_upload_400()
    test_reindex_reports_corrupted_file_as_failed()
    test_llm_timeout_fallback()
    test_cache_hits_misses_counted_and_logged()
    test_error_counts_tracked()
    test_query_counter_increments()

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
