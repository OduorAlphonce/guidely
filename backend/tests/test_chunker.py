"""Unit tests for the text chunker (issue #31).

Covers token limits, overlap, separator handling, and edge cases such as
empty input, oversized single words, and custom separator lists.

Run from the repo root:
    python backend/tests/test_chunker.py
"""

import os
import sys
from pathlib import Path

os.environ["OPENAI_API_KEY"] = ""

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.chunker import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_OVERLAP_TOKENS,
    chunk_text,
    count_tokens,
)

PASS = 0
FAIL = 0
FAILURES = []

# ~10 tokens of lorem-style words, repeated to build larger inputs.
WORD = "organization consistency operational workflow documentation"

PARAGRAPH = "Each paragraph stands on its own within the document body."


def check(description, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {description}")
    else:
        FAIL += 1
        FAILURES.append(description)
        print(f"  [FAIL] {description}")


def test_count_tokens():
    print("\nTest 1: count_tokens")
    check("empty string has 0 tokens", count_tokens("") == 0)
    check("single word has at least 1 token", count_tokens("hello") >= 1)
    check("longer text has more tokens", count_tokens(WORD * 20) > count_tokens(WORD))


def test_empty_input():
    print("\nTest 2: empty/whitespace input produces no chunks")
    check("empty string -> []", chunk_text("") == [])
    check("whitespace -> []", chunk_text("   \n\t ") == [])
    check("only punctuation yields a single chunk", len(chunk_text("... ---")) == 1)


def test_single_short_chunk():
    print("\nTest 3: short text yields one well-formed chunk")
    chunks = chunk_text("The quick brown fox jumps over the lazy dog.")
    check("returns exactly 1 chunk", len(chunks) == 1)
    c = chunks[0]
    check("chunk has index/text/token_count keys", {"index", "text", "token_count"} <= set(c))
    check("chunk index is 0", c["index"] == 0)
    check("text is the input", c["text"] == "The quick brown fox jumps over the lazy dog.")
    check("token_count equals count_tokens(text)", c["token_count"] == count_tokens(c["text"]))
    check("token_count is a positive int", isinstance(c["token_count"], int) and c["token_count"] > 0)


def test_max_tokens_respected():
    print("\nTest 4: chunks stay within max_tokens when overlap is off")
    text = (WORD + " ") * 30
    chunks = chunk_text(text, max_tokens=20, overlap_tokens=0)
    check("long text splits into multiple chunks", len(chunks) > 1)
    check("every chunk is within the token budget", all(c["token_count"] <= 20 for c in chunks))
    check("indexes are sequential from 0", [c["index"] for c in chunks] == list(range(len(chunks))))
    check("text is preserved (concatenated in order)", " ".join(c["text"] for c in chunks) == text.strip())


def test_overlap_reuses_previous_tail():
    print("\nTest 5: overlap prepends the previous chunk's tail")
    text = (WORD + " ") * 30
    max_tokens = 40
    overlap = 5
    chunks = chunk_text(text, max_tokens=max_tokens, overlap_tokens=overlap)

    check("long text still splits", len(chunks) > 1)
    second = chunks[1]["text"]
    prev_tail = chunks[0]["text"].split()[-overlap:]
    check("chunk 1 begins with the previous chunk's tail", second.startswith(" ".join(prev_tail)))

    # Overlap may add up to `overlap` tokens past the budget; raw content still fits.
    check("no chunk exceeds budget plus overlap", all(c["token_count"] <= max_tokens + overlap for c in chunks))


def test_paragraph_separator():
    print("\nTest 6: splitting on paragraph separators")
    text = "\n\n".join([PARAGRAPH, PARAGRAPH, PARAGRAPH])
    chunks = chunk_text(text, max_tokens=1000, overlap_tokens=0, separators=["\n\n"])
    check("one chunk per paragraph", len(chunks) == 3)
    check("each chunk is a stripped paragraph", {c["text"] for c in chunks} == {PARAGRAPH})
    check("chunk order follows the source", chunks[0]["text"] == PARAGRAPH)


def test_sentence_separator():
    print("\nTest 7: splitting on sentence boundaries")
    sentences = [f"Sentence number {i} is fairly short." for i in range(6)]
    text = " ".join(sentences)
    chunks = chunk_text(text, max_tokens=50, overlap_tokens=0, separators=[". "])
    check("splits into multiple sentence chunks", len(chunks) > 1)
    check("no chunk mixes whole sentences", all(
        c["text"].split(". ") == [c["text"]] or c["text"].endswith(".")
        for c in chunks
    ))


def test_oversized_single_word():
    print("\nTest 8: an indivisible oversized word still yields a chunk")
    huge_word = "supercalifragilisticexpialidocious-" * 200
    chunks = chunk_text(huge_word, max_tokens=20, overlap_tokens=0)
    check("produces at least one chunk", len(chunks) >= 1)
    check("the word is preserved", any(huge_word in c["text"] for c in chunks))


def test_custom_separator_list():
    print("\nTest 9: custom and empty separator lists")
    text = (WORD + " ") * 20
    chunks = chunk_text(text, max_tokens=20, overlap_tokens=0, separators=[])
    check("empty separators fall back to token splitting", len(chunks) > 1)
    check("all chunks within budget", all(c["token_count"] <= 20 for c in chunks))

    one = chunk_text(text, max_tokens=10000, overlap_tokens=0, separators=["zzz"])
    check("unmatched separator yields a single chunk", len(one) == 1)


def test_defaults_are_sane():
    print("\nTest 10: defaults use the configured budgets")
    check("default max tokens > 0", DEFAULT_MAX_TOKENS > 0)
    check("default overlap is smaller than max", 0 <= DEFAULT_OVERLAP_TOKENS < DEFAULT_MAX_TOKENS)
    text = (WORD + " ") * 200
    chunks = chunk_text(text)
    check("defaults split long text", len(chunks) > 1)
    check("defaults keep chunks within budget + overlap", all(
        c["token_count"] <= DEFAULT_MAX_TOKENS + DEFAULT_OVERLAP_TOKENS for c in chunks
    ))


def main():
    print("=" * 64)
    print("Guidely chunker — unit tests (issue #31)")
    print("=" * 64)

    test_count_tokens()
    test_empty_input()
    test_single_short_chunk()
    test_max_tokens_respected()
    test_overlap_reuses_previous_tail()
    test_paragraph_separator()
    test_sentence_separator()
    test_oversized_single_word()
    test_custom_separator_list()
    test_defaults_are_sane()

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
