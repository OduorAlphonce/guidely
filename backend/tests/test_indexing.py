"""End-to-end verification of the Day 2 indexing pipeline.

Run from the repo root:
    python backend/tests/test_indexing.py

Covers the four required test cases:
  1. First-time indexing of the 5 sample docs
  2. Re-indexing (cache hit) with zero new embeddings
  3. Partial re-indexing (cache miss) re-embeds only the modified file
  4. Edge cases: empty file, unsupported type, large file

All pipeline artifacts (cache, FAISS index) are written to a temp directory
so the real backend/data artifacts are never touched.
"""

import shutil
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services import indexing
from backend.services.cache import EmbeddingCache
from backend.services.parser import parse_file
from backend.services.vector_store import VectorStore

MAX_CHUNK_TOKENS = 1000
SAMPLE_DIR = BACKEND_DIR / "data" / "sample-docs"
SAMPLE_NAMES = sorted(p.name for p in SAMPLE_DIR.glob("*.txt"))

PASS = 0
FAIL = 0
FAILURES = []
METRICS = {}


class CountingEmbedder:
    """Wraps the real embedder so we can prove when embeddings are (not) generated."""

    def __init__(self, real):
        self._real = real
        self.batch_calls = 0

    def embed_batch(self, texts):
        self.batch_calls += 1
        return self._real.embed_batch(texts)


def check(description, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {description}")
    else:
        FAIL += 1
        FAILURES.append(description)
        print(f"  [FAIL] {description}")


def record(name, value):
    METRICS[name] = value
    print(f"  [DATA] {name} = {value}")


def isolate(tmpdir):
    """Point the pipeline's singletons at temp cache/index files."""
    cache_path = tmpdir / "embedding_cache.json"
    index_path = tmpdir / "faiss_index"
    indexing.cache = EmbeddingCache(str(cache_path))
    indexing.vector_store = VectorStore(str(index_path))
    indexing.embedder = CountingEmbedder(indexing.embedder)
    return cache_path, index_path


def run_index_all(docs_dir):
    return [indexing.index_document(str(p)) for p in sorted(docs_dir.glob("*.txt"))]


def test_first_time_indexing(docs_dir):
    print("\nTest 1: First-time indexing")
    start = time.perf_counter()
    results = run_index_all(docs_dir)
    elapsed = time.perf_counter() - start
    record("first_index_time_s", round(elapsed, 2))

    check("all 5 sample files indexed", len(results) == 5 and all(r["status"] == "indexed" for r in results))
    check("every file produced >= 2 chunks", all(r["chunks"] >= 2 for r in results))

    total_chunks = sum(r["chunks"] for r in results)
    record("files_indexed", len(results))
    record("total_chunks", total_chunks)

    cached_chunks = []
    for name in SAMPLE_NAMES:
        cached_chunks.extend(indexing.cache.get_cached_chunks(str(docs_dir / name)) or [])
    check("every chunk has a token count in 1..1000", all(0 < c["token_count"] <= MAX_CHUNK_TOKENS for c in cached_chunks))
    check("embeddings generated for every chunk", all(len(c.get("embedding") or []) > 0 for c in cached_chunks))
    check(f"vector_store.count() == total chunks ({total_chunks})", indexing.vector_store.count() == total_chunks)
    check("cache file written with 5 entries", indexing.cache.file_count() == 5)

    faiss_file = docs_dir.parent / "faiss_index.faiss"
    meta_file = docs_dir.parent / "faiss_index.meta.json"
    check("FAISS index saved to disk", faiss_file.exists() and meta_file.exists())

    record("embedding_batch_calls", indexing.embedder.batch_calls)
    return total_chunks


def test_reindex_cache_hit(docs_dir, total_chunks):
    print("\nTest 2: Re-indexing (cache hit)")
    calls_before = indexing.embedder.batch_calls
    count_before = indexing.vector_store.count()
    results = run_index_all(docs_dir)

    check("all 5 files skipped (cache hit)", all(r["status"] == "skipped" for r in results))
    check("no new embeddings generated", indexing.embedder.batch_calls == calls_before)
    check("vector count unchanged", indexing.vector_store.count() == count_before)
    check("vector count still equals total chunks", indexing.vector_store.count() == total_chunks)
    hits = sum(1 for r in results if r["status"] == "skipped")
    record("reindex_cache_hit_rate", f"{100 * hits / len(results):.0f}%")


def test_partial_reindex(docs_dir):
    print("\nTest 3: Partial re-indexing (cache miss)")
    policy = docs_dir / "policy.txt"
    policy.write_text(
        policy.read_text()
        + "\n\nNew section: all travel reimbursement claims require itemized receipts "
          "and pre-approval from finance before booking.\n" * 40
    )

    calls_before = indexing.embedder.batch_calls
    count_before = indexing.vector_store.count()
    results = {Path(r["file"]).name: r for r in run_index_all(docs_dir)}

    check("only policy.txt re-indexed", results["policy.txt"]["status"] == "indexed")
    check("other 4 files skipped (cache hit)", all(
        results[name]["status"] == "skipped" for name in SAMPLE_NAMES if name != "policy.txt"
    ))
    check("exactly 1 embedding batch call", indexing.embedder.batch_calls == calls_before + 1)
    check(
        "vector count grew by policy chunk count",
        indexing.vector_store.count() == count_before + results["policy.txt"]["chunks"],
    )
    record("policy_chunks_after_edit", results["policy.txt"]["chunks"])


def test_edge_cases(docs_dir):
    print("\nTest 4: Edge cases")

    empty = docs_dir / "empty.txt"
    empty.write_text("")
    try:
        indexing.index_document(str(empty))
        check("empty file fails gracefully", False)
    except ValueError as e:
        check("empty file fails gracefully", "empty" in str(e).lower())
    except Exception:
        check("empty file fails gracefully", False)

    bad = docs_dir / "malware.exe"
    bad.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00")
    try:
        indexing.index_document(str(bad))
        check("unsupported file type fails gracefully", False)
    except ValueError as e:
        check("unsupported file type fails gracefully", "unsupported" in str(e).lower())
    except Exception:
        check("unsupported file type fails gracefully", False)

    paragraph = (
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
        "omicron pi rho sigma tau upsilon phi chi psi omega " * 400
    )
    large = docs_dir / "large.txt"
    large.write_text("\n\n".join([paragraph] * 40))

    result = indexing.index_document(str(large))
    check("large file indexed successfully", result["status"] == "indexed")
    check("large file produced >= 30 chunks", result["chunks"] >= 30)
    cached = indexing.cache.get_cached_chunks(str(large)) or []
    token_counts = [c["token_count"] for c in cached]
    check("large file chunks within 1..1000 tokens", all(0 < t <= MAX_CHUNK_TOKENS for t in token_counts))
    check("large file has chunks in 500..1000 range", any(500 <= t <= MAX_CHUNK_TOKENS for t in token_counts))
    record("large_file_chunks", result["chunks"])
    record("large_file_max_tokens", max(token_counts, default=0))


def main():
    print("=" * 64)
    print("Guidely indexing pipeline — end-to-end verification (Day 2)")
    print("=" * 64)

    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_indexing_test_"))
    try:
        docs_dir = tmpdir / "docs"
        docs_dir.mkdir()
        for f in sorted(SAMPLE_DIR.glob("*.txt")):
            shutil.copy(f, docs_dir / f.name)
        isolate(tmpdir)
        total_chunks = test_first_time_indexing(docs_dir)
        test_reindex_cache_hit(docs_dir, total_chunks)
        test_partial_reindex(docs_dir)
        test_edge_cases(docs_dir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "=" * 64)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    if FAILURES:
        print("Failed checks:")
        for f in FAILURES:
            print(f"  - {f}")
    print("-" * 64)
    print("METRICS:")
    for key, value in METRICS.items():
        print(f"  {key}: {value}")
    print("=" * 64)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
