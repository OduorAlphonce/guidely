"""Unit tests for the embedding service (issue #31).

Covers OpenAI-vs-fallback model selection and the batch-vs-single path
for both backends. The OpenAI client is mocked so no real API key or
network call is required; the fallback path uses the real local
sentence-transformers model.

Run from the repo root:
    python backend/tests/test_embedder.py
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ["OPENROUTER_API_KEY"] = ""

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.embedder import FALLBACK_MODEL, OPENAI_MODEL, Embedder

PASS = 0
FAIL = 0
FAILURES = []

VECTOR_A = [0.1] * 16
VECTOR_B = [0.2] * 16


class FakeOpenAIClient:
    """Minimal stand-in for openai.OpenAI that records the input."""

    def __init__(self, vectors):
        self.vectors = vectors
        self.calls = []
        self.embeddings = FakeEmbeddings(self)


class FakeEmbeddings:
    def __init__(self, owner):
        self._owner = owner

    def create(self, model, input):
        self._owner.calls.append(input)
        if isinstance(input, str):
            data = [SimpleNamespace(index=0, embedding=self._owner.vectors[0])]
        else:
            data = [SimpleNamespace(index=i, embedding=v) for i, v in enumerate(self._owner.vectors)]
        return SimpleNamespace(data=data)


def check(description, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {description}")
    else:
        FAIL += 1
        FAILURES.append(description)
        print(f"  [FAIL] {description}")


def build_openai_embedder(fake_client):
    """Build an Embedder that selects the OpenAI path with a mocked client."""
    with mock.patch("backend.services.embedder.os.getenv", return_value="sk-test"):
        with mock.patch("backend.services.embedder.openai.OpenAI", return_value=fake_client):
            embedder = Embedder()
    embedder._client = fake_client
    return embedder


def test_model_selection():
    print("\nTest 1: OpenAI vs fallback model selection")
    fake = FakeOpenAIClient([VECTOR_A])
    openai_embedder = build_openai_embedder(fake)
    check("key present -> OpenAI model", openai_embedder._model == OPENAI_MODEL)

    with mock.patch("backend.services.embedder.os.getenv", return_value=None):
        fallback_embedder = Embedder()
    check("no key -> fallback model", fallback_embedder._model == FALLBACK_MODEL)


def test_openai_single_embed():
    print("\nTest 2: OpenAI path embeds a single text")
    fake = FakeOpenAIClient([VECTOR_A])
    embedder = build_openai_embedder(fake)

    vec = embedder.embed("hello world")
    check("returns a vector of the expected dimension", vec == VECTOR_A)
    check("client received the text", fake.calls == ["hello world"])
    check("model stays OpenAI after success", embedder._model == OPENAI_MODEL)


def test_openai_batch_consistency():
    print("\nTest 3: OpenAI batch returns vectors in input order")
    fake = FakeOpenAIClient([VECTOR_A, VECTOR_B])
    embedder = build_openai_embedder(fake)

    vectors = embedder.embed_batch(["first", "second"])
    check("batch returns one vector per input", len(vectors) == 2)
    check("batch order matches input order", vectors == [VECTOR_A, VECTOR_B])
    check("client received the list of texts", fake.calls == [["first", "second"]])


def test_openai_fallback_on_api_error():
    print("\nTest 4: OpenAI API error falls back and still returns a vector")
    from backend.services import embedder as embedder_module

    class ErrorEmbeddings:
        def create(self, model, input):
            raise embedder_module.openai.APIError(
                "boom", request=None, body=None
            )

    class ErrorClient:
        def __init__(self):
            self.embeddings = ErrorEmbeddings()

    embedder = build_openai_embedder(ErrorClient())
    check("starts on the OpenAI path", embedder._model == OPENAI_MODEL)

    vec = embedder.embed("fallback please")
    check("embed still returns a vector", isinstance(vec, list) and len(vec) == 384)
    check("model switched to fallback", embedder._model == FALLBACK_MODEL)


def test_fallback_real_embed():
    print("\nTest 5: fallback path produces real vectors of consistent shape")
    with mock.patch("backend.services.embedder.os.getenv", return_value=None):
        embedder = Embedder()

    vec = embedder.embed("the quick brown fox")
    check("embed returns a float list", isinstance(vec, list) and all(isinstance(x, float) for x in vec))
    check("fallback dimension is 384", len(vec) == 384)

    batch = embedder.embed_batch(["the quick brown fox", "lazy dog"])
    check("batch returns one vector per input", len(batch) == 2)
    check("every batch vector has the same dimension", all(len(v) == 384 for v in batch))
    check("batch[0] matches the single embed", all(abs(a - b) < 1e-5 for a, b in zip(batch[0], vec)))


def main():
    print("=" * 64)
    print("Guidely embedder — unit tests (issue #31)")
    print("=" * 64)

    test_model_selection()
    test_openai_single_embed()
    test_openai_batch_consistency()
    test_openai_fallback_on_api_error()
    test_fallback_real_embed()

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
