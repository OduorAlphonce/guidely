"""Day 8 — Formal Validation & Metrics Test Suite.

Runs every check from the Testing & Metrics table and produces a summary
report.  Uses the sentence-transformers fallback (no OpenAI key required).

Run from the repo root:
    python backend/tests/test_validation.py
"""

import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

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
from backend.services.stats import stats
from backend.services.vector_store import VectorStore

logging.getLogger().setLevel(logging.CRITICAL)

PASS = 0
FAIL = 0
FAILURES = []
METRICS = {}

SAMPLE_DIR = BACKEND_DIR / "data" / "sample-docs"
SAMPLE_NAMES = sorted(p.name for p in SAMPLE_DIR.glob("*.txt"))
CLIENT = TestClient(app)

TEST_QUERIES = [
    ("How many days per week can employees work remotely?", "policy.txt", ["remote", "days"]),
    ("What is the home office stipend amount?", "policy.txt", ["stipend", "500"]),
    ("What are the core work hours?", "policy.txt", ["10 AM", "3 PM"]),
    ("How do I report a security incident?", "policy.txt", ["security"]),
    ("What happens on the first policy violation?", "policy.txt", ["warning"]),
    ("How many PTO days do I get per year?", "faq.txt", ["PTO", "15"]),
    ("What is the 401(k) matching policy?", "faq.txt", ["401"]),
    ("How do I reset my password?", "faq.txt", ["password"]),
    ("What VPN client should I use?", "faq.txt", ["VPN"]),
    ("What are the company holidays?", "faq.txt", ["holiday"]),
    ("How do I enroll in health insurance?", "faq.txt", ["insurance"]),
    ("How do I submit an expense report?", "howto.txt", ["expense"]),
    ("What expenses require VP pre-approval?", "howto.txt", ["VP", "approval"]),
    ("What is the reimbursement schedule?", "howto.txt", ["payroll"]),
    ("What happens on Day 1 of onboarding?", "guide.txt", ["Day 1", "orientation"]),
    ("What tools do new hires use?", "guide.txt", ["Jira", "Confluence"]),
    ("When do I set up my development environment?", "guide.txt", ["development"]),
    ("What does a solid red LED mean on the WidgetPro 3000?", "manual.txt", ["red", "hardware"]),
    ("How do I fix Wi-Fi connection drops?", "manual.txt", ["Wi-Fi"]),
    ("How do I update the firmware?", "manual.txt", ["firmware"]),
]


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.model = "gpt-3.5-turbo"

    def generate_answer(self, question, context):
        self.calls.append({"question": question, "context": context})
        top_file = context[0]["filename"] if context else "unknown"
        top_snippet = context[0]["text"][:120] if context else ""
        return f"Answer from {top_file}: {top_snippet}..."


def check(description, condition, metric_key=None, value=None):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {description}")
    else:
        FAIL += 1
        FAILURES.append(description)
        print(f"  [FAIL] {description}")
    if metric_key and value is not None:
        METRICS[metric_key] = value


def seed_store(tmpdir):
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
        indexing.index_document(str(docs_dir / name))

    retrieval.vector_store = vector_store
    return vector_store, cache


# ── 1. Retrieval@3 ─────────────────────────────────────────────────────────
def test_retrieval_at3():
    print("\n1. Retrieval@3 (target >= 80%)")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_val_retk3_"))
    try:
        seed_store(tmpdir)
        hits = 0
        for question, expected_file, _ in TEST_QUERIES:
            results = retrieval.retrieve(question, k=3)
            filenames = [r["filename"] for r in results]
            if expected_file in filenames:
                hits += 1
        rate = hits / len(TEST_QUERIES) * 100
        print(f"    {hits}/{len(TEST_QUERIES)} queries ({rate:.0f}%)")
        check("Retrieval@3 >= 80%", rate >= 80.0, "retrieval_at3", f"{rate:.0f}%")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── 2. Answer reference coverage ───────────────────────────────────────────
def test_answer_reference_coverage():
    print("\n2. Answer reference coverage (target >= 90%)")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_val_ansref_"))
    try:
        seed_store(tmpdir)
        fake_llm = FakeLLM()
        search_route.retrieve = retrieval.retrieve
        search_route.llm = fake_llm

        covered = 0
        total = 0
        for question, expected_file, _ in TEST_QUERIES:
            resp = CLIENT.post("/api/search/", json={"question": question})
            if resp.status_code == 200:
                body = resp.json()
                answer_text = body.get("answer", "").lower()
                source_files = [s["file"].lower() for s in body.get("sources", [])]
                total += 1
                if expected_file.lower() in answer_text or expected_file.lower() in source_files:
                    covered += 1
        rate = covered / total * 100 if total else 0
        print(f"    {covered}/{total} queries ({rate:.0f}%)")
        check("Answer reference coverage >= 90%", rate >= 90.0, "answer_coverage", f"{rate:.0f}%")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── 3. Latency (warm cache) ────────────────────────────────────────────────
def test_latency():
    print("\n3. Latency — warm cache (target: median < 3s, p95 < 5s)")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_val_lat_"))
    try:
        seed_store(tmpdir)
        fake_llm = FakeLLM()
        search_route.retrieve = retrieval.retrieve
        search_route.llm = fake_llm

        latencies = []
        for question, _, _ in TEST_QUERIES:
            resp = CLIENT.post("/api/search/", json={"question": question})
            if resp.status_code == 200:
                latencies.append(resp.json()["latency_ms"])

        if latencies:
            med = statistics.median(latencies)
            p95 = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 2 else latencies[0]
            min_lat = min(latencies)
            max_lat = max(latencies)
            print(f"    min={min_lat:.1f}ms  median={med:.1f}ms  p95={p95:.1f}ms  max={max_lat:.1f}ms")
            check("Median latency < 3000ms", med < 3000, "latency_median_ms", f"{med:.1f}")
            check("P95 latency < 5000ms", p95 < 5000, "latency_p95_ms", f"{p95:.1f}")
        else:
            check("Latency measurement completed", False)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── 4. Embedding cache effectiveness ───────────────────────────────────────
def test_cache_effectiveness():
    print("\n4. Embedding cache effectiveness (target: 100% hits on repeat)")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_val_cache_"))
    try:
        docs_dir = tmpdir / "docs"
        docs_dir.mkdir()
        for f in SAMPLE_NAMES:
            shutil.copy(SAMPLE_DIR / f, docs_dir / f)

        cache = EmbeddingCache(str(tmpdir / "embedding_cache.json"))
        vs = VectorStore(str(tmpdir / "faiss_index"))
        indexing.cache = cache
        indexing.vector_store = vs
        indexing.embedder = retrieval.embedder

        stats.reset()

        for name in SAMPLE_NAMES:
            indexing.index_document(str(docs_dir / name))
        first_index_misses = stats.snapshot()["cache_misses"]

        for name in SAMPLE_NAMES:
            indexing.index_document(str(docs_dir / name))
        reindex_hits = stats.snapshot()["cache_hits"]

        hit_rate = reindex_hits / len(SAMPLE_NAMES) * 100 if SAMPLE_NAMES else 0
        print(f"    First index misses: {first_index_misses}")
        print(f"    Re-index hits: {reindex_hits}/{len(SAMPLE_NAMES)} ({hit_rate:.0f}%)")
        check("Cache hit rate on re-index is 100%", hit_rate == 100.0, "cache_hit_rate", f"{hit_rate:.0f}%")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── 5. Failure handling ────────────────────────────────────────────────────
def test_failure_handling():
    print("\n5. Failure handling (target: 4xx/5xx + clear messages)")
    passed = 0
    total_checks = 0

    total_checks += 1
    resp = CLIENT.post("/api/search/", json={"question": ""})
    if resp.status_code == 400 and "empty" in resp.json().get("detail", "").lower():
        passed += 1
        print("    [PASS] Empty query -> 400 with clear message")
    else:
        print("    [FAIL] Empty query -> 400 with clear message")

    total_checks += 1
    resp = CLIENT.post("/api/search/", json={"question": "   "})
    if resp.status_code == 400:
        passed += 1
        print("    [PASS] Whitespace query -> 400")
    else:
        print("    [FAIL] Whitespace query -> 400")

    total_checks += 1
    # Restore the real LLM (previous tests inject a FakeLLM) so the missing
    # API-key branch is exercised: generate_answer raises ValueError when the
    # key is unset, which the route surfaces as an actionable 500.
    from backend.services.llm import llm as real_llm
    search_route.llm = real_llm
    resp = CLIENT.post("/api/search/", json={"question": "test"})
    if resp.status_code == 500 and "OPENROUTER_API_KEY" in resp.json().get("detail", ""):
        passed += 1
        print("    [PASS] Missing API key -> 500 with actionable message")
    else:
        print("    [FAIL] Missing API key -> 500 with actionable message")

    total_checks += 1
    resp = CLIENT.post("/api/documents/upload", files={"file": ("empty.txt", b"", "text/plain")})
    if resp.status_code == 400:
        passed += 1
        print("    [PASS] Empty file upload -> 400")
    else:
        print("    [FAIL] Empty file upload -> 400")

    total_checks += 1
    resp = CLIENT.post("/api/documents/upload", files={"file": ("bad.exe", b"MZ\x00\x00", "application/octet-stream")})
    if resp.status_code == 400:
        passed += 1
        print("    [PASS] Unsupported file type -> 400")
    else:
        print("    [FAIL] Unsupported file type -> 400")

    total_checks += 1
    resp = CLIENT.post("/api/documents/upload", files={"file": ("corrupt.txt", b"\xff\xfe\xfd", "text/plain")})
    if resp.status_code == 400:
        passed += 1
        print("    [PASS] Corrupted file upload -> 400")
    else:
        print("    [FAIL] Corrupted file upload -> 400")

    rate = passed / total_checks * 100 if total_checks else 0
    print(f"    Failure handling: {passed}/{total_checks} ({rate:.0f}%)")
    check("Failure handling >= 80%", rate >= 80.0, "failure_handling", f"{rate:.0f}%")


# ── 6. Source precision ────────────────────────────────────────────────────
def test_source_precision():
    print("\n6. Source precision (target >= 80%)")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_val_srcprec_"))
    try:
        seed_store(tmpdir)
        fake_llm = FakeLLM()
        search_route.retrieve = retrieval.retrieve
        search_route.llm = fake_llm

        precise = 0
        total = 0
        for question, expected_file, _ in TEST_QUERIES:
            resp = CLIENT.post("/api/search/", json={"question": question})
            if resp.status_code == 200:
                sources = resp.json().get("sources", [])
                source_files = [s["file"] for s in sources]
                total += 1
                if source_files and expected_file in source_files:
                    precise += 1
        rate = precise / total * 100 if total else 0
        print(f"    {precise}/{total} queries ({rate:.0f}%)")
        check("Source precision >= 80%", rate >= 80.0, "source_precision", f"{rate:.0f}%")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── 7. Indexing throughput ─────────────────────────────────────────────────
def test_indexing_throughput():
    print("\n7. Indexing throughput (target: completes, skips unchanged)")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_val_idx_"))
    try:
        docs_dir = tmpdir / "docs"
        docs_dir.mkdir()
        for f in SAMPLE_NAMES:
            shutil.copy(SAMPLE_DIR / f, docs_dir / f)

        cache = EmbeddingCache(str(tmpdir / "embedding_cache.json"))
        vs = VectorStore(str(tmpdir / "faiss_index"))
        indexing.cache = cache
        indexing.vector_store = vs
        indexing.embedder = retrieval.embedder

        stats.reset()

        start = time.time()
        for name in SAMPLE_NAMES:
            indexing.index_document(str(docs_dir / name))
        first_time = time.time() - start

        stats_after_first = stats.snapshot()
        first_misses = stats_after_first["cache_misses"]

        start2 = time.time()
        for name in SAMPLE_NAMES:
            indexing.index_document(str(docs_dir / name))
        second_time = time.time() - start2

        stats_after_second = stats.snapshot()
        second_hits = stats_after_second["cache_hits"]

        print(f"    First indexing: {first_time:.2f}s ({len(SAMPLE_NAMES)} files)")
        print(f"    Re-index (cache): {second_time:.4f}s ({second_hits} hits)")
        check("First indexing completes", first_time > 0, "first_index_time_s", f"{first_time:.2f}")
        check("All files indexed on first pass", first_misses == len(SAMPLE_NAMES))
        check("All files skipped on re-index (cache hit)", second_hits == len(SAMPLE_NAMES), "cache_skip_rate", "100%")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Summary ────────────────────────────────────────────────────────────────
def main():
    print("=" * 68)
    print("Guidely Day 8 — Formal Validation & Metrics")
    print("=" * 68)

    test_retrieval_at3()
    test_answer_reference_coverage()
    test_latency()
    test_cache_effectiveness()
    test_failure_handling()
    test_source_precision()
    test_indexing_throughput()

    print("\n" + "=" * 68)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    if FAILURES:
        print("Failed checks:")
        for f in FAILURES:
            print(f"  - {f}")

    print("\n── Metrics Summary Table ──")
    print(f"| Metric                              | Value      |")
    print(f"|-------------------------------------|------------|")
    for key, val in METRICS.items():
        print(f"| {key:<37} | {val:>10} |")
    print("=" * 68)

    report_path = ROOT_DIR / "backend" / "data" / "validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({"passed": PASS, "failed": FAIL, "failures": FAILURES, "metrics": METRICS}, f, indent=2)
    print(f"\nReport saved to {report_path}")

    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
