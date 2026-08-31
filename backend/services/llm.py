import logging
import os
import time

import openrouter

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-3.5-turbo"
SYSTEM_PROMPT = "Answer concisely using only the provided context. Cite source file names."
TIMEOUT_SECONDS = 30
MAX_RETRIES = 2
RETRY_DELAY = 1.0


class LLMTimeoutError(Exception):
    """Raised when the LLM call times out; callers should degrade gracefully."""


class LLMRateLimitError(Exception):
    """Raised when the OpenAI quota is exceeded; callers should degrade gracefully."""


def build_prompt(question: str, context: list[dict]) -> str:
    """Build the user prompt from retrieved context snippets and the question."""
    snippets = "\n\n".join(
        f"[{i}] {c.get('filename', 'unknown')}:\n{c.get('text', '')}"
        for i, c in enumerate(context, 1)
    )
    return f"Context:\n{snippets}\n\nQuestion: {question}"


def _deduplicate_chunks(chunks: list[dict]) -> list[dict]:
    """Remove near-duplicate chunks based on text similarity."""
    if not chunks:
        return []
    seen = []
    unique = []
    for chunk in chunks:
        text = chunk.get("text", "").strip()
        if not text:
            continue
        is_duplicate = False
        for seen_text in seen:
            if text[:100] == seen_text[:100]:
                is_duplicate = True
                break
        if not is_duplicate:
            seen.append(text)
            unique.append(chunk)
    return unique


def _truncate_text(text: str, max_chars: int = 400) -> str:
    """Truncate text to a reasonable length for display."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def build_fallback_answer(chunks: list[dict]) -> str:
    """Build a fallback answer from retrieved context when LLM is unavailable."""
    if not chunks:
        return "No relevant context found."
    unique_chunks = _deduplicate_chunks(chunks)
    if not unique_chunks:
        return "No relevant context found."
    snippets = "\n\n".join(
        f"[{i}] {c.get('filename', 'unknown')}:\n{_truncate_text(c.get('text', ''))}"
        for i, c in enumerate(unique_chunks[:3], 1)
    )
    return (
        "The AI model is temporarily unavailable. "
        "Here are the most relevant passages from your documents:\n\n"
        f"{snippets}"
    )


class LLM:
    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self._client = openai.OpenAI(api_key=api_key, timeout=TIMEOUT_SECONDS)
        else:
            logger.warning("OPENAI_API_KEY not set; answer generation will fail until it is configured")
            self._client = None

    @property
    def model(self) -> str:
        return self._model

    def generate_answer(self, question: str, context: list[dict]) -> str:
        if self._client is None:
            raise ValueError(
                "OPENAI_API_KEY is not set. Add it to the .env file before asking questions."
            )
        user_prompt = build_prompt(question, context)
        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                answer = response.choices[0].message.content or ""
                logger.info("Generated answer with model=%s", self._model)
                return answer
            except openai.RateLimitError as e:
                last_error = e
                error_msg = str(e)
                if "insufficient_quota" in error_msg:
                    logger.error("OpenAI quota exceeded: %s", e)
                    raise LLMRateLimitError(
                        "OpenAI API quota exceeded. Please check your billing details."
                    ) from e
                if attempt < MAX_RETRIES:
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    logger.warning(
                        "Rate limit hit (attempt %d/%d), retrying in %.1fs",
                        attempt + 1,
                        MAX_RETRIES,
                        wait_time,
                    )
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries reached for rate limit error")
                    raise LLMRateLimitError(
                        "Too many requests. Please try again later."
                    ) from e
            except openai.APITimeoutError as e:
                logger.error(
                    "LLM call timed out after %s seconds (model=%s)",
                    TIMEOUT_SECONDS,
                    self._model,
                )
                raise LLMTimeoutError(
                    f"Answer model timed out after {TIMEOUT_SECONDS} seconds"
                ) from e
            except openai.APIError as e:
                logger.error("OpenAI API error: %s", e)
                raise LLMRateLimitError(
                    f"AI service error: {e}"
                ) from e
        raise last_error


llm = LLM()
