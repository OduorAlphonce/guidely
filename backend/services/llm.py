import logging
import os

import openai

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-3.5-turbo"
SYSTEM_PROMPT = "Answer concisely using only the provided context. Cite source file names."
TIMEOUT_SECONDS = 30


class LLMTimeoutError(Exception):
    """Raised when the LLM call times out; callers should degrade gracefully."""


def build_prompt(question: str, context: list[dict]) -> str:
    """Build the user prompt from retrieved context snippets and the question."""
    snippets = "\n\n".join(
        f"[{i}] {c.get('filename', 'unknown')}:\n{c.get('text', '')}"
        for i, c in enumerate(context, 1)
    )
    return f"Context:\n{snippets}\n\nQuestion: {question}"


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
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except openai.APITimeoutError as e:
            logger.error(
                "LLM call timed out after %s seconds (model=%s)",
                TIMEOUT_SECONDS,
                self._model,
            )
            raise LLMTimeoutError(
                f"Answer model timed out after {TIMEOUT_SECONDS} seconds"
            ) from e
        answer = response.choices[0].message.content or ""
        logger.info("Generated answer with model=%s", self._model)
        return answer


llm = LLM()
