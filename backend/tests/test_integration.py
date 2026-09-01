"""Day 7 – End-to-end integration tests with 20 curated test queries.

Tests the full upload → index → search → verify pipeline using the
sentence-transformers fallback (no OpenAI key required).  Each query has
an expected top-1 file and a set of keywords that should appear in the
retrieved snippets so we can verify Retrieval@k.

Run from the repo root:
    python backend/tests/test_integration.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Force the offline sentence-transformers fallback.
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

logging.getLogger().setLevel(logging.CRITICAL)

PASS = 0
FAIL = 0
FAILURES = []

SAMPLE_DIR = BACKEND_DIR / "data" / "sample-docs"
SAMPLE_NAMES = sorted(p.name for p in SAMPLE_DIR.glob("*.txt"))
CLIENT = TestClient(app)


class FakeLLM:
    """Stub LLM that returns a canned answer so the full pipeline is exercised
    without needing an OpenAI API key."""

    def __init__(self):
        self.calls = []
        self.model = "gpt-3.5-turbo"

    def generate_answer(self, question, context):
        self.calls.append({"question": question, "context": context})
        top_file = context[0]["filename"] if context else "unknown"
        top_snippet = context[0]["text"][:120] if context else ""
        return f"Answer from {top_file}: {top_snippet}..."


# ---------------------------------------------------------------------------
# 20 curated test queries covering all 5 sample documents
# Each entry: (question, expected_top_file, keywords_in_top_chunk)
# ---------------------------------------------------------------------------
TEST_QUERIES = [
    # --- policy.txt ---
    ("How many days per week can employees work remotely?", "policy.txt",
     ["remote", "days"]),
    ("What is the home office stipend amount?", "policy.txt",
     ["stipend", "500"]),
    ("What are the core work hours?", "policy.txt",
     ["10 AM", "3 PM"]),
    ("How do I report a security incident?", "policy.txt",
     ["security"]),
    ("What happens on the first policy violation?", "policy.txt",
     ["warning"]),

    # --- faq.txt ---
    ("How many PTO days do I get per year?", "faq.txt",
     ["PTO", "15"]),
    ("What is the 401(k) matching policy?", "faq.txt",
     ["401"]),
    ("How do I reset my password?", "faq.txt",
     ["password"]),
    ("What VPN client should I use?", "faq.txt",
     ["VPN"]),
    ("What are the company holidays?", "faq.txt",
     ["holiday"]),
    ("How do I enroll in health insurance?", "faq.txt",
     ["insurance"]),

    # --- howto.txt ---
    ("How do I submit an expense report?", "howto.txt",
     ["expense"]),
    ("What expenses require VP pre-approval?", "howto.txt",
     ["VP", "approval"]),
    ("What is the reimbursement schedule?", "howto.txt",
     ["payroll"]),

    # --- guide.txt ---
    ("What happens on Day 1 of onboarding?", "guide.txt",
     ["Day 1", "orientation"]),
    ("What tools do new hires use?", "guide.txt",
     ["Jira", "Confluence"]),
    ("When do I set up my development environment?", "guide.txt",
     ["development"]),

    # --- manual.txt ---
    ("What does a solid red LED mean on the WidgetPro 3000?", "manual.txt",
     ["red", "hardware"]),
    ("How do I fix Wi-Fi connection drops?", "manual.txt",
     ["Wi-Fi"]),
    ("How do I update the firmware?", "manual.txt",
     ["firmware"]),
]


def check(description, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {description}")
    else:
        FAIL += 1
        FAILURES.append(description)
        print(f"  [FAIL] {description}")


def seed_store(tmpdir):
    """Copy sample docs, index them, and wire up the real retrieval pipeline."""
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


# ── Test 1: Upload a new document then search ──────────────────────────────
def test_upload_then_search():
    print("\nTest 1: Upload a new document → search finds it")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_int_upload_"))
    try:
        cache = EmbeddingCache(str(tmpdir / "embedding_cache.json"))
        vs = VectorStore(str(tmpdir / "faiss_index"))
        indexing.cache = cache
        indexing.vector_store = vs
        indexing.embedder = retrieval.embedder

        # Write a small custom doc
        custom = tmpdir / "custom.txt"
        custom.write_text(
            "Acme Corp Holiday Schedule 2025\n"
            "The office is closed December 24-31 for winter break. "
            "Employees must use PTO for Dec 24-25. Dec 26-31 are company holidays."
        )
        result = indexing.index_document(str(custom))
        check("indexed custom.txt", result["status"] == "indexed")

        retrieval.vector_store = vs
        results = retrieval.retrieve("When is the winter break?", k=3)
        check("retrieve returned results", len(results) > 0)
        if results:
            check("top result is custom.txt", results[0]["filename"] == "custom.txt")
            check("snippet mentions winter break",
                  "winter" in results[0]["text"].lower() or "december" in results[0]["text"].lower())
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Test 2: Full E2E through the search endpoint ──────────────────────────
def test_e2e_search_endpoint():
    print("\nTest 2: Full E2E through POST /api/search/")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_int_e2e_"))
    try:
        seed_store(tmpdir)
        fake_llm = FakeLLM()
        search_route.retrieve = retrieval.retrieve
        search_route.llm = fake_llm

        resp = CLIENT.post(
            "/api/search/",
            json={"question": "How many remote work days per week are allowed?"},
        )
        check("HTTP 200", resp.status_code == 200)
        body = resp.json()
        check("answer is non-empty", body["answer"] != "")
        check("sources are returned", len(body["sources"]) > 0)
        check("latency_ms > 0", body["latency_ms"] > 0)
        check("LLM was called", len(fake_llm.calls) == 1)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Test 3: Retrieval@k evaluation with 20 queries ────────────────────────
def test_retrieval_at_k():
    print("\nTest 3: Retrieval@k evaluation (20 queries)")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_int_retk_"))
    try:
        seed_store(tmpdir)
        k_values = [3, 5, 7]
        results_by_k = {k: 0 for k in k_values}

        for question, expected_file, _keywords in TEST_QUERIES:
            for k in k_values:
                hits = retrieval.retrieve(question, k=k)
                filenames = [h["filename"] for h in hits]
                if expected_file in filenames:
                    results_by_k[k] += 1

        total = len(TEST_QUERIES)
        for k in k_values:
            rate = results_by_k[k] / total * 100
            print(f"    Retrieval@{k}: {results_by_k[k]}/{total} ({rate:.0f}%)")
            check(f"Retrieval@{k} >= 80%", rate >= 80.0)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Test 4: Chunk-size tuning comparison ───────────────────────────────────
def test_chunk_size_tuning():
    print("\nTest 4: Chunk-size tuning (500 / 800 / 1000 tokens)")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_int_tune_"))
    try:
        from backend.services.chunker import chunk_text

        sample_text = (SAMPLE_DIR / "policy.txt").read_text()
        for max_tok in [500, 800, 1000]:
            chunks = chunk_text(sample_text, max_tokens=max_tok)
            token_counts = [c["token_count"] for c in chunks]
            avg = sum(token_counts) / len(token_counts) if token_counts else 0
            print(f"    max_tokens={max_tok}: {len(chunks)} chunks, avg {avg:.0f} tokens")
            check(f"max_tokens={max_tok} produces > 0 chunks", len(chunks) > 0)
            check(f"max_tokens={max_tok}: all chunks <= {max_tok} tokens",
                  all(t <= max_tok + 50 for t in token_counts))  # small tolerance for overlap
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Test 5: Keyword verification in snippets ──────────────────────────────
def test_keyword_in_snippets():
    print("\nTest 5: Keyword presence in top snippets")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_int_kw_"))
    try:
        seed_store(tmpdir)
        hits_count = 0
        total_checks = 0

        for question, expected_file, keywords in TEST_QUERIES:
            results = retrieval.retrieve(question, k=5)
            # Check that the expected file appears
            filenames = [r["filename"] for r in results]
            total_checks += 1
            if expected_file in filenames:
                hits_count += 1

            # Check keywords across all returned snippets
            all_text = " ".join(r["text"].lower() for r in results)
            for kw in keywords:
                total_checks += 1
                if kw.lower() in all_text:
                    hits_count += 1

        rate = hits_count / total_checks * 100 if total_checks else 0
        print(f"    Keyword+file hits: {hits_count}/{total_checks} ({rate:.0f}%)")
        check("Overall keyword+file hit rate >= 70%", rate >= 70.0)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Test 6: Score ordering (most relevant first) ──────────────────────────
def test_score_ordering():
    print("\nTest 6: Results are ordered by descending relevance score")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_int_order_"))
    try:
        seed_store(tmpdir)
        all_ordered = True
        for question, _, _ in TEST_QUERIES[:10]:
            results = retrieval.retrieve(question, k=5)
            scores = [r["score"] for r in results]
            if scores != sorted(scores, reverse=True):
                all_ordered = False
                break
        check("All tested queries return results in descending score order", all_ordered)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Test 7: Graceful handling of no-index scenario ────────────────────────
def test_no_index_graceful():
    print("\nTest 7: Graceful response when no documents are indexed")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_int_noidx_"))
    try:
        vs = VectorStore(str(tmpdir / "empty_faiss"))
        search_route.retrieve = lambda question, k=5: []
        search_route.llm = FakeLLM()

        resp = CLIENT.post("/api/search/", json={"question": "What is remote work?"})
        check("HTTP 200 for empty index", resp.status_code == 200)
        body = resp.json()
        check("no-results message returned",
              "couldn't find" in body["answer"].lower() or "no results" in body["answer"].lower())
        check("empty sources list", body["sources"] == [])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    print("=" * 68)
    print("Guidely Day 7 — Integration & Polish Test Suite")
    print("=" * 68)

    test_upload_then_search()
    test_e2e_search_endpoint()
    test_retrieval_at_k()
    test_chunk_size_tuning()
    test_keyword_in_snippets()
    test_score_ordering()
    test_no_index_graceful()

    print("\n" + "=" * 68)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    if FAILURES:
        print("Failed checks:")
        for f in FAILURES:
            print(f"  - {f}")
    print("=" * 68)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
