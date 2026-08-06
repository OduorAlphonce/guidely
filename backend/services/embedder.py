import logging
import os
import threading
import time

import openai
import tiktoken
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

OPENAI_MODEL = "text-embedding-ada-002"
FALLBACK_MODEL = "all-MiniLM-L6-v2"
MAX_RETRIES = 2
RETRY_DELAY = 1.0

_model_lock = threading.Lock()
_transformer = None
_transformer_model = None


def _get_transformer(model: str) -> SentenceTransformer:
    """Return a process-wide shared SentenceTransformer, loaded lazily on first use.

    The model is expensive to load (torch + tokenizer), so every Embedder
    instance shares one copy instead of each loading its own on construction.
    """
    global _transformer, _transformer_model
    if _transformer is not None and _transformer_model == model:
        return _transformer
    with _model_lock:
        if _transformer is None or _transformer_model != model:
            logger.info("Loading fallback embedding model %s", model)
            _transformer = SentenceTransformer(model, device="cpu")
            _transformer_model = model
    return _transformer


class Embedder:
    def __init__(self):
        self._encoding = tiktoken.get_encoding("cl100k_base")
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self._client = openai.OpenAI(api_key=api_key)
            self._model = OPENAI_MODEL
        else:
            logger.info("OPENAI_API_KEY not set, using fallback model %s", FALLBACK_MODEL)
            self._model = FALLBACK_MODEL

    def embed(self, text: str) -> list[float]:
        if self._model == OPENAI_MODEL:
            return self._embed_with_retry(lambda: self._embed_openai(text), lambda: self._embed_fallback(text))
        return self._embed_fallback(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self._model == OPENAI_MODEL:
            return self._embed_with_retry(lambda: self._embed_batch_openai(texts), lambda: self._embed_batch_fallback(texts))
        return self._embed_batch_fallback(texts)

    def _embed_with_retry(self, openai_fn, fallback_fn):
        for attempt in range(MAX_RETRIES + 1):
            try:
                return openai_fn()
            except (openai.RateLimitError, openai.APITimeoutError) as e:
                if attempt < MAX_RETRIES:
                    logger.warning("OpenAI error (attempt %d/%d): %s", attempt + 1, MAX_RETRIES, e)
                    time.sleep(RETRY_DELAY * (2 ** attempt))
                else:
                    logger.warning("Max retries reached, falling back to %s", FALLBACK_MODEL)
                    self._switch_to_fallback()
                    return fallback_fn()
            except openai.APIError as e:
                logger.warning("OpenAI API error: %s, falling back to %s", e, FALLBACK_MODEL)
                self._switch_to_fallback()
                return fallback_fn()

    def _switch_to_fallback(self):
        self._model = FALLBACK_MODEL

    def _embed_openai(self, text: str) -> list[float]:
        response = self._client.embeddings.create(model=OPENAI_MODEL, input=text)
        token_count = len(self._encoding.encode(text))
        logger.info("model=%s tokens=%d count=1", self._model, token_count)
        return response.data[0].embedding

    def _embed_batch_openai(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=OPENAI_MODEL, input=texts)
        total_tokens = sum(len(self._encoding.encode(t)) for t in texts)
        logger.info("model=%s tokens=%d count=%d", self._model, total_tokens, len(texts))
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [d.embedding for d in sorted_data]

    def _embed_fallback(self, text: str) -> list[float]:
        embedding = _get_transformer(self._model).encode(text)
        token_count = len(self._encoding.encode(text))
        logger.info("model=%s tokens=%d count=1", self._model, token_count)
        return embedding.tolist()

    def _embed_batch_fallback(self, texts: list[str]) -> list[list[float]]:
        embeddings = _get_transformer(self._model).encode(texts)
        total_tokens = sum(len(self._encoding.encode(t)) for t in texts)
        logger.info("model=%s tokens=%d count=%d", self._model, total_tokens, len(texts))
        return [emb.tolist() for emb in embeddings]
