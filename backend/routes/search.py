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


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


@router.post("/", response_model=Answer)
async def search(query: Query):
    request_start = time.perf_counter()

    retrieve_start = time.perf_counter()
    chunks = retrieve(query.question, k=TOP_K)
    retrieval_ms = _ms(retrieve_start)

    if not chunks:
        total_ms = _ms(request_start)
        logger.info(
            "search request question=%r total_ms=%.2f retrieval_ms=%.2f "
            "llm_ms=0.00 sources=0 model=n/a status=no_results",
            query.question,
            total_ms,
            retrieval_ms,
        )
        return Answer(
            question=query.question,
            answer=NO_RESULTS_MESSAGE,
            sources=[],
            latency_ms=total_ms,
        )

    llm_start = time.perf_counter()
    try:
        answer_text = llm.generate_answer(query.question, chunks)
    except ValueError as e:
        total_ms = _ms(request_start)
        logger.error(
            "search request question=%r total_ms=%.2f retrieval_ms=%.2f "
            "status=error error=%s",
            query.question,
            total_ms,
            retrieval_ms,
            e,
        )
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        total_ms = _ms(request_start)
        logger.exception(
            "search request question=%r total_ms=%.2f retrieval_ms=%.2f "
            "status=error error=%s",
            query.question,
            total_ms,
            retrieval_ms,
            e,
        )
        raise HTTPException(status_code=500, detail=f"Answer generation failed: {e}")
    llm_ms = _ms(llm_start)

    sources = [
        SourceRef(file=c["filename"], snippet=_snippet(c["text"]), score=c["score"])
        for c in chunks
    ]

    total_ms = _ms(request_start)
    logger.info(
        "search request question=%r total_ms=%.2f retrieval_ms=%.2f llm_ms=%.2f "
        "sources=%d model=%s status=ok",
        query.question,
        total_ms,
        retrieval_ms,
        llm_ms,
        len(sources),
        llm.model,
    )
    return Answer(
        question=query.question,
        answer=answer_text,
        sources=sources,
        latency_ms=total_ms,
    )
