"""Verification of the retrieval service (issue #17).

Exercises `backend.services.retrieval.retrieve()` against a real FAISS store
seeded with the sample docs, using the sentence-transformers fallback
embedder (no OpenAI API key required). A mocked OpenAI client covers the
OpenAI embedding path.

Run from the repo root:
    python backend/tests/test_retrieval.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# Force the offline sentence-transformers fallback so tests never touch OpenAI,
# even if a (stub) OPENAI_API_KEY is present in .env.
os.environ["OPENAI_API_KEY"] = ""

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services import indexing, retrieval
from backend.services.cache import EmbeddingCache
from backend.services.embedder import Embedder, OPENAI_MODEL
from backend.services.vector_store import VectorStore

PASS = 0
FAIL = 0
FAILURES = []

SAMPLE_DIR = BACKEND_DIR / "data" / "sample-docs"
SAMPLE_NAMES = sorted(p.name for p in SAMPLE_DIR.glob("*.txt"))

# Questions whose answers are known to live in a specific sample file.
KNOWN_ANSWERS = [
    ("How many remote work days per week are allowed?", "policy.txt"),
    ("How do I submit an expense report?", "howto.txt"),
    ("How many PTO days do I get?", "faq.txt"),
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


def isolate(tmpdir, docs_dir):
    """Point the pipeline singletons at temp cache/index files and index sample docs."""
    cache = EmbeddingCache(str(tmpdir / "embedding_cache.json"))
    vector_store = VectorStore(str(tmpdir / "faiss_index"))
    indexing.cache = cache
    indexing.vector_store = vector_store
    indexing.embedder = retrieval.embedder
    for name in SAMPLE_NAMES:
        result = indexing.index_document(str(docs_dir / name))
        assert result["status"] == "indexed", f"failed to index {name}"
    retrieval.vector_store = vector_store


def test_empty_index():
    print("\nTest 1: Empty index returns []")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_retrieval_empty_"))
    try:
        retrieval.vector_store = VectorStore(str(tmpdir / "empty_faiss"))
        results = retrieval.retrieve("How many remote days?")
        check("returns [] when nothing is indexed", results == [])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_result_shape_and_order():
    print("\nTest 2: Result shape, ordering, and top-k limit")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_retrieval_store_"))
    try:
        docs_dir = tmpdir / "docs"
        docs_dir.mkdir()
        for f in SAMPLE_NAMES:
            shutil.copy(SAMPLE_DIR / f, docs_dir / f)
        isolate(tmpdir, docs_dir)

        results = retrieval.retrieve("How many remote work days per week?", k=5)

        check("returns results", len(results) > 0)
        check(
            "every result has doc_id/chunk_id/text/filename/score",
            all({"doc_id", "chunk_id", "text", "filename", "score"} <= set(r) for r in results),
        )
        check("snippets are non-empty", all(r["text"] for r in results))
        check("scores are numeric", all(isinstance(r["score"], float) for r in results))
        check("results are ordered best-first", all(
            results[i]["score"] >= results[i + 1]["score"] for i in range(len(results) - 1)
        ))

        limited = retrieval.retrieve("How many remote work days per week?", k=3)
        check("respects k=3 (returns at most 3)", len(limited) <= 3)
        check("top-3 matches the first 3 of top-5", [r["chunk_id"] for r in limited] == [r["chunk_id"] for r in results[:3]])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_correct_source_files():
    print("\nTest 3: Known-answer questions reference the correct file")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_retrieval_relevance_"))
    try:
        docs_dir = tmpdir / "docs"
        docs_dir.mkdir()
        for f in SAMPLE_NAMES:
            shutil.copy(SAMPLE_DIR / f, docs_dir / f)
        isolate(tmpdir, docs_dir)

        for question, expected in KNOWN_ANSWERS:
            results = retrieval.retrieve(question, k=5)
            filenames = [r["filename"] for r in results]
            check(
                f"{question!r} returns {expected} in top results",
                results and expected in filenames,
            )
            check(
                f"{question!r} top-1 is {expected}",
                results and results[0]["filename"] == expected,
            )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_openai_embedding_path():
    print("\nTest 4: OpenAI embedding path works with a mocked client")
    fake_client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=lambda model, input: SimpleNamespace(
                data=[SimpleNamespace(index=0, embedding=[0.1] * 16)]
            )
        )
    )
    with mock.patch("backend.services.embedder.os.getenv", return_value="sk-test"):
        with mock.patch("backend.services.embedder.openai.OpenAI", return_value=fake_client):
            embedder = Embedder()
    check("uses the OpenAI model when a key is present", embedder._model == OPENAI_MODEL)

    vec = embedder.embed("hello")
    check("embed returns a vector via the OpenAI path", isinstance(vec, list) and len(vec) == 16)


def main():
    print("=" * 64)
    print("Guidely retrieval service — verification (issue #17)")
    print("=" * 64)

    test_empty_index()
    test_result_shape_and_order()
    test_correct_source_files()
    test_openai_embedding_path()

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
