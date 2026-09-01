"""Tests for the Day 3 LLM service (issue #13).

The OpenAI client is mocked so no real API key or network call is
required to run these checks.

Run from the repo root:
    python backend/tests/test_llm.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from unittest import mock

from backend.services.llm import LLM, LLMRateLimitError, SYSTEM_PROMPT, build_fallback_answer, build_prompt, llm

PASS = 0
FAIL = 0
FAILURES = []

SAMPLE_CONTEXT = [
    {"filename": "policy.txt", "text": "Employees may work remotely up to two days per week.", "score": 0.91},
    {"filename": "howto.txt", "text": "Submit expense reports through the finance portal.", "score": 0.88},
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


class FakeCompletions:
    def __init__(self, content):
        self._content = content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


def test_build_prompt():
    print("\nTest 1: Prompt construction")
    prompt = build_prompt("How many remote days?", SAMPLE_CONTEXT)

    check("includes the question", "How many remote days?" in prompt)
    check("includes every source file name", "policy.txt" in prompt and "howto.txt" in prompt)
    check("includes every snippet text", SAMPLE_CONTEXT[0]["text"] in prompt and SAMPLE_CONTEXT[1]["text"] in prompt)
    check("snippets are numbered", "[1]" in prompt and "[2]" in prompt)

    check("empty context is handled", build_prompt("q?", []) != "")


def test_generate_answer_success():
    print("\nTest 2: generate_answer with mocked OpenAI client")
    fake = FakeCompletions("Two days per week, per policy.txt.")
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))

    answer = llm.generate_answer("How many remote days?", SAMPLE_CONTEXT)

    check("returns the generated answer", answer == "Two days per week, per policy.txt.")

    create_kwargs = fake.calls[0]
    check("uses the configured model", create_kwargs["model"] == llm._model)
    messages = create_kwargs["messages"]
    check("sends a system message with the exact prompt", messages[0] == {"role": "system", "content": SYSTEM_PROMPT})
    check("sends a user message with the built prompt", messages[1]["role"] == "user")
    check("user prompt embeds context + question", "policy.txt" in messages[1]["content"] and "How many remote days?" in messages[1]["content"])


def test_missing_api_key():
    print("\nTest 3: Missing OPENROUTER_API_KEY is actionable")
    with mock.patch("backend.services.llm.os.getenv", return_value=None):
        fresh = LLM()
    try:
        fresh.generate_answer("How many remote days?", SAMPLE_CONTEXT)
        check("raises when no API key is configured", False)
    except ValueError as e:
        check("raises when no API key is configured", True)
        check("error message names OPENROUTER_API_KEY and remediation", "OPENROUTER_API_KEY" in str(e) and ".env" in str(e))
    except Exception:
        check("raises when no API key is configured", False)


def test_build_fallback_answer():
    print("\nTest 4: build_fallback_answer with context")
    fallback = build_fallback_answer(SAMPLE_CONTEXT)
    check("includes AI model unavailable message", "AI model is temporarily unavailable" in fallback)
    check("includes source filenames", "policy.txt" in fallback or "howto.txt" in fallback)
    check("snippets are numbered", "[1]" in fallback)


def test_build_fallback_answer_empty():
    print("\nTest 5: build_fallback_answer with empty context")
    fallback = build_fallback_answer([])
    check("handles empty context", "No relevant context found" in fallback)


def test_rate_limit_error():
    print("\nTest 6: LLMRateLimitError for quota exceeded")
    fake = FakeCompletions("test")
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))

    import openai
    error_response = mock.MagicMock()
    error_response.status_code = 429
    error_response.json.return_value = {"error": {"message": "You exceeded your current quota", "type": "insufficient_quota", "param": None, "code": "insufficient_quota"}}

    with mock.patch.object(llm._client.chat.completions, 'create', side_effect=openai.RateLimitError(
        message="You exceeded your current quota",
        response=error_response,
        body={"error": {"message": "You exceeded your current quota", "type": "insufficient_quota", "param": None, "code": "insufficient_quota"}}
    )):
        try:
            llm.generate_answer("How many remote days?", SAMPLE_CONTEXT)
            check("raises LLMRateLimitError for quota exceeded", False)
        except LLMRateLimitError as e:
            check("raises LLMRateLimitError for quota exceeded", True)
            check("error message mentions quota", "quota" in str(e).lower())
        except Exception as e:
            check("raises LLMRateLimitError for quota exceeded", False)


def main():
    print("=" * 64)
    print("Guidely LLM service — verification (Day 3, issue #13)")
    print("=" * 64)

    test_build_prompt()
    test_generate_answer_success()
    test_missing_api_key()
    test_build_fallback_answer()
    test_build_fallback_answer_empty()
    test_rate_limit_error()

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
