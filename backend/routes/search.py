import logging
import time

from fastapi import APIRouter, HTTPException

from backend.models.record import Answer, Query, SourceRef
from backend.services.llm import llm
from backend.services.retrieval import retrieve

logger = logging.getLogger(__name__)

router = APIRouter()

TOP_K = 5
SNIPPET_MAX_CHARS = 300
NO_RESULTS_MESSAGE = (
    "I couldn't find relevant docs for your question. "
    "Try rephrasing it or indexing more documents."
)


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= SNIPPET_MAX_CHARS:
        return text
    return text[:SNIPPET_MAX_CHARS].rstrip() + "..."


@router.post("/", response_model=Answer)
async def search(query: Query):
    start = time.perf_counter()

    chunks = retrieve(query.question, k=TOP_K)

    if not chunks:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info("No results for question, returning graceful message")
        return Answer(
            question=query.question,
            answer=NO_RESULTS_MESSAGE,
            sources=[],
            latency_ms=latency_ms,
        )

    try:
        answer_text = llm.generate_answer(query.question, chunks)
    except ValueError as e:
        logger.error("Answer generation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("LLM error while generating answer")
        raise HTTPException(status_code=500, detail=f"Answer generation failed: {e}")

    sources = [
        SourceRef(file=c["filename"], snippet=_snippet(c["text"]), score=c["score"])
        for c in chunks
    ]

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    return Answer(
        question=query.question,
        answer=answer_text,
        sources=sources,
        latency_ms=latency_ms,
    )
