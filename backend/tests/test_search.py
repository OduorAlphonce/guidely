"""Tests for the search endpoint (issue #14).

The LLM is mocked so no real OpenAI API key or network call is required.
One end-to-end check seeds a real FAISS store with the sample docs using the
sentence-transformers fallback embedder, so retrieval is exercised for real.

Run from the repo root:
    python backend/tests/test_search.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Force the offline sentence-transformers fallback so tests never touch OpenAI,
# even if a (stub) OPENAI_API_KEY is present in .env.
os.environ["OPENAI_API_KEY"] = ""

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

from backend.main import app
from backend.routes import search as search_route
from backend.services import indexing, retrieval
from backend.services.cache import EmbeddingCache
from backend.services.vector_store import VectorStore

PASS = 0
FAIL = 0
FAILURES = []

SAMPLE_DIR = BACKEND_DIR / "data" / "sample-docs"
SAMPLE_NAMES = sorted(p.name for p in SAMPLE_DIR.glob("*.txt"))
CLIENT = TestClient(app)

CANNED_ANSWER = "Up to two days per week, per policy.txt."


def check(description, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {description}")
    else:
        FAIL += 1
        FAILURES.append(description)
        print(f"  [FAIL] {description}")


class FakeLLM:
    def __init__(self, answer=CANNED_ANSWER, error=None):
        self._answer = answer
        self._error = error
        self.calls = []

    def generate_answer(self, question, context):
        self.calls.append({"question": question, "context": context})
        if self._error is not None:
            raise self._error
        return self._answer


def sample_chunks():
    return [
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


def test_success_with_mocked_llm():
    print("\nTest 1: Successful search with mocked LLM")
    fake = FakeLLM()
    search_route.retrieve = lambda question, k=5: sample_chunks()
    search_route.llm = fake

    resp = CLIENT.post("/api/search/", json={"question": "How many remote days?"})

    check("returns HTTP 200", resp.status_code == 200)
    body = resp.json()
    check("echoes the question", body["question"] == "How many remote days?")
    check("returns the generated answer", body["answer"] == CANNED_ANSWER)
    check("latency_ms is populated", body["latency_ms"] > 0)

    sources = body["sources"]
    check("returns 2 sources", len(sources) == 2)
    check("sources reference the retrieved files", {s["file"] for s in sources} == {"policy.txt", "howto.txt"})
    check("every source has a non-empty snippet", all(s["snippet"] for s in sources))
    check("every source has a numeric score", all(isinstance(s["score"], float) for s in sources))

    called = fake.calls[0]
    check("LLM received the question", called["question"] == "How many remote days?")
    check("LLM received the retrieved chunks as context", called["context"] == sample_chunks())


def test_no_results_message():
    print("\nTest 2: No results -> graceful message")
    search_route.retrieve = lambda question, k=5: []
    search_route.llm = FakeLLM()

    resp = CLIENT.post("/api/search/", json={"question": "How do I fold a taco?"})

    check("returns HTTP 200", resp.status_code == 200)
    body = resp.json()
    check("graceful no-results message", body["answer"] == search_route.NO_RESULTS_MESSAGE)
    check("no sources returned", body["sources"] == [])
    check("latency_ms is populated", body["latency_ms"] > 0)


def test_empty_question_rejected():
    print("\nTest 3: Empty question is rejected")
    resp = CLIENT.post("/api/search/", json={"question": ""})
    check("returns HTTP 422 for empty question", resp.status_code == 422)


def test_missing_api_key_is_actionable():
    print("\nTest 4: Missing OPENAI_API_KEY -> actionable 500")
    search_route.retrieve = lambda question, k=5: sample_chunks()
    search_route.llm = FakeLLM(error=ValueError(
        "OPENAI_API_KEY is not set. Add it to the .env file before asking questions."
    ))

    resp = CLIENT.post("/api/search/", json={"question": "How many remote days?"})

    check("returns HTTP 500", resp.status_code == 500)
    detail = resp.json()["detail"]
    check("error names OPENAI_API_KEY and remediation", "OPENAI_API_KEY" in detail and ".env" in detail)


def test_end_to_end_retrieval():
    print("\nTest 5: End-to-end retrieval with real FAISS store + fallback embedder")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_search_test_"))
    try:
        docs_dir = tmpdir / "docs"
        docs_dir.mkdir()
        for f in SAMPLE_NAMES:
            shutil.copy(SAMPLE_DIR / f, docs_dir / f.name)

        cache = EmbeddingCache(str(tmpdir / "embedding_cache.json"))
        vector_store = VectorStore(str(tmpdir / "faiss_index"))

        indexing.cache = cache
        indexing.vector_store = vector_store
        indexing.embedder = retrieval.embedder

        for name in SAMPLE_NAMES:
            result = indexing.index_document(str(docs_dir / name))
            check(f"indexed {name}", result["status"] == "indexed")

        retrieval.vector_store = vector_store
        search_route.llm = FakeLLM()

        resp = CLIENT.post(
            "/api/search/",
            json={"question": "How many days per week can employees work remotely?"},
        )

        check("returns HTTP 200", resp.status_code == 200)
        body = resp.json()
        check("answer generated", body["answer"] == CANNED_ANSWER)
        check("latency_ms is populated", body["latency_ms"] > 0)
        check("sources reference real sample-doc files", len(body["sources"]) > 0 and all(
            s["file"] in SAMPLE_NAMES for s in body["sources"]
        ))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    print("=" * 64)
    print("Guidely search endpoint — verification (issue #14)")
    print("=" * 64)

    test_success_with_mocked_llm()
    test_no_results_message()
    test_empty_question_rejected()
    test_missing_api_key_is_actionable()
    test_end_to_end_retrieval()

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
