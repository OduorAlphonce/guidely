"""End-to-end Q&A tests (issues #14, #15, #16).

The LLM is mocked so no real OpenAI API key or network call is required.
End-to-end checks seed a real FAISS store with the sample docs using the
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
# even if a (stub) OPENROUTER_API_KEY is present in .env.
os.environ["OPENROUTER_API_KEY"] = ""

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

import logging
from backend.main import app
from backend.routes import search as search_route
from backend.services import indexing, retrieval
from backend.services.cache import EmbeddingCache
from backend.services.vector_store import VectorStore

# backend.main configures INFO logging for uvicorn; silence it here so the
# test output stays readable while we capture the search log line explicitly.
logging.getLogger().setLevel(logging.CRITICAL)

PASS = 0
FAIL = 0
FAILURES = []

SAMPLE_DIR = BACKEND_DIR / "data" / "sample-docs"
SAMPLE_NAMES = sorted(p.name for p in SAMPLE_DIR.glob("*.txt"))
CLIENT = TestClient(app)

CANNED_ANSWER = "Up to two days per week, per policy.txt."


class CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.messages = []

    def emit(self, record):
        self.messages.append(self.format(record))


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
        self.model = "gpt-3.5-turbo"

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


def seed_store(tmpdir):
    """Copy the sample docs and index them into a temp cache + FAISS store."""
    docs_dir = tmpdir / "docs"
    docs_dir.mkdir()
    for f in SAMPLE_NAMES:
        shutil.copy(SAMPLE_DIR / f, docs_dir / f)

    cache = EmbeddingCache(str(tmpdir / "embedding_cache.json"))
    vector_store = VectorStore(str(tmpdir / "faiss_index"))

    indexing.cache = cache
    indexing.vector_store = vector_store
    indexing.embedder = retrieval.embedder

    for name in SAMPLE_NAMES:
        result = indexing.index_document(str(docs_dir / name))
        check(f"indexed {name}", result["status"] == "indexed")

    retrieval.vector_store = vector_store
    return vector_store


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
    print("\nTest 3: Empty question is rejected with 400")
    resp = CLIENT.post("/api/search/", json={"question": ""})
    check("returns HTTP 400 for empty question", resp.status_code == 400)
    check("400 carries a clear message", "empty" in resp.json()["detail"].lower())

    resp = CLIENT.post("/api/search/", json={"question": "   "})
    check("returns HTTP 400 for whitespace-only question", resp.status_code == 400)

    resp = CLIENT.post("/api/search/", json={})
    check("returns HTTP 422 when question is missing", resp.status_code == 422)


def test_endpoint_validation_and_shape():
    print("\nTest 3b: Endpoint validation and response shape")
    search_route.retrieve = lambda question, k=5: sample_chunks()
    search_route.llm = FakeLLM()

    resp = CLIENT.post("/api/search/", json={"question": "How many remote days?"})
    check("returns HTTP 200", resp.status_code == 200)
    body = resp.json()
    check("response has exactly the Answer fields",
          set(body) == {"question", "answer", "sources", "latency_ms"})
    check("question is a string", isinstance(body["question"], str))
    check("answer is a string", isinstance(body["answer"], str))
    check("latency_ms is numeric", isinstance(body["latency_ms"], (int, float)))
    check("sources is a list", isinstance(body["sources"], list))
    check("every source has exactly file/snippet/score",
          all(set(s) == {"file", "snippet", "score"} for s in body["sources"]))
    check("every source file is a string", all(isinstance(s["file"], str) for s in body["sources"]))
    check("every source snippet is a string", all(isinstance(s["snippet"], str) for s in body["sources"]))
    check("every source score is a float", all(isinstance(s["score"], float) for s in body["sources"]))

    for bad in (123, ["question"], {"nested": "query"}, 3.14, None):
        resp = CLIENT.post("/api/search/", json={"question": bad})
        check(f"non-string question {bad!r} is rejected with 422", resp.status_code == 422)

    resp = CLIENT.post("/api/search/", json={"question": "ok?", "ignored": "extra"})
    check("extra request fields are ignored (200)", resp.status_code == 200)

    resp = CLIENT.post("/api/search/", json={"question": "\n \t "})
    check("whitespace-only question is rejected with 400", resp.status_code == 400)


def test_missing_api_key_is_actionable():
    print("\nTest 4: Missing OPENROUTER_API_KEY -> actionable 500")
    search_route.retrieve = lambda question, k=5: sample_chunks()
    search_route.llm = FakeLLM(error=ValueError(
        "OPENROUTER_API_KEY is not set. Add it to the .env file before asking questions."
    ))

    resp = CLIENT.post("/api/search/", json={"question": "How many remote days?"})

    check("returns HTTP 500", resp.status_code == 500)
    detail = resp.json()["detail"]
    check("error names OPENROUTER_API_KEY and remediation", "OPENROUTER_API_KEY" in detail and ".env" in detail)


def test_end_to_end_retrieval():
    print("\nTest 5: End-to-end Q&A with real FAISS store + fallback embedder")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_search_test_"))
    try:
        seed_store(tmpdir)
        search_route.retrieve = retrieval.retrieve
        search_route.llm = FakeLLM()

        resp = CLIENT.post(
            "/api/search/",
            json={"question": "How many days per week can employees work remotely?"},
        )

        check("returns HTTP 200", resp.status_code == 200)
        body = resp.json()
        check("response has shape question/answer/sources/latency_ms", {
            "question", "answer", "sources", "latency_ms"
        } <= set(body))
        check("answer is non-empty", body["answer"] != "")
        check("answer matches the generated answer", body["answer"] == CANNED_ANSWER)
        check("latency_ms is populated", body["latency_ms"] > 0)
        check("sources reference real sample-doc files", len(body["sources"]) > 0 and all(
            s["file"] in SAMPLE_NAMES for s in body["sources"]
        ))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_retrieval_correct_source_files():
    print("\nTest 7: Known-answer questions reference the correct file")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_search_known_"))
    try:
        seed_store(tmpdir)
        known_answers = [
            ("How many remote work days per week are allowed?", "policy.txt"),
            ("How do I submit an expense report?", "howto.txt"),
            ("How many PTO days do I get?", "faq.txt"),
        ]
        for question, expected in known_answers:
            results = retrieval.retrieve(question, k=5)
            check(f"{question!r} top-1 is {expected}", results and results[0]["filename"] == expected)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_no_documents_indexed_graceful():
    print("\nTest 8: No documents indexed -> graceful response")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_search_nodocs_"))
    try:
        retrieval.vector_store = VectorStore(str(tmpdir / "empty_faiss"))
        search_route.retrieve = retrieval.retrieve

        resp = CLIENT.post("/api/search/", json={"question": "How many remote days?"})

        check("returns HTTP 200", resp.status_code == 200)
        body = resp.json()
        check("graceful no-results message", body["answer"] == search_route.NO_RESULTS_MESSAGE)
        check("no sources returned", body["sources"] == [])
        check("latency_ms is populated", body["latency_ms"] > 0)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_latency_is_logged():
    print("\nTest 6: Every /search request is logged with total latency")
    handler = CapturingHandler()
    search_route.logger.addHandler(handler)
    search_route.logger.setLevel(logging.INFO)
    try:
        search_route.retrieve = lambda question, k=5: sample_chunks()
        search_route.llm = FakeLLM()
        resp = CLIENT.post("/api/search/", json={"question": "How many remote days?"})
        check("returns HTTP 200", resp.status_code == 200)

        request_lines = [m for m in handler.messages if "search request" in m]
        check("a search request log line was emitted", len(request_lines) == 1)
        line = request_lines[0] if request_lines else ""
        check("log includes total_ms", "total_ms=" in line)
        check("log includes retrieval_ms breakdown", "retrieval_ms=" in line)
        check("log includes llm_ms breakdown", "llm_ms=" in line)
        check("log includes source count", "sources=2" in line)
        check("log includes the model used", "model=gpt-3.5-turbo" in line)
        check("log includes the question", "How many remote days?" in line)
    finally:
        search_route.logger.removeHandler(handler)


def main():
    print("=" * 64)
    print("Guidely search endpoint — end-to-end Q&A (issues #14, #15, #16)")
    print("=" * 64)

    test_success_with_mocked_llm()
    test_no_results_message()
    test_empty_question_rejected()
    test_endpoint_validation_and_shape()
    test_missing_api_key_is_actionable()
    test_end_to_end_retrieval()
    test_latency_is_logged()
    test_retrieval_correct_source_files()
    test_no_documents_indexed_graceful()

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
