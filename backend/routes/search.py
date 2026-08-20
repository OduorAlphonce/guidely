import logging
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from backend.models.record import Answer, Query, SourceRef
from backend.services.llm import LLMRateLimitError, LLMTimeoutError, build_fallback_answer, llm
from backend.services.query_log import query_log
from backend.services.retrieval import retrieve
from backend.services.stats import stats

logger = logging.getLogger(__name__)

router = APIRouter()

TOP_K = 5
SNIPPET_MAX_CHARS = 300
NO_RESULTS_MESSAGE = (
    "I couldn't find relevant docs for your question. "
    "Try rephrasing it or indexing more documents."
)
TIMEOUT_FALLBACK_MESSAGE = (
    "The answer model timed out before responding. "
    "Here are the most relevant passages I found:"
)
RATE_LIMIT_FALLBACK_MESSAGE = (
    "The AI service quota has been exceeded. "
    "Here are the most relevant passages from your documents:"
)


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= SNIPPET_MAX_CHARS:
        return text
    return text[:SNIPPET_MAX_CHARS].rstrip() + "..."


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


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


def _timeout_fallback_answer(chunks: list[dict]) -> str:
    unique_chunks = _deduplicate_chunks(chunks)
    if not unique_chunks:
        return TIMEOUT_FALLBACK_MESSAGE
    snippets = "\n\n".join(
        f"[{i}] {c['filename']}: {_snippet(c['text'])}" for i, c in enumerate(unique_chunks[:3], 1)
    )
    return f"{TIMEOUT_FALLBACK_MESSAGE}\n\n{snippets}"


@router.post("/", response_model=Answer)
async def search(query: Query, request: Request):
    request_start = time.perf_counter()
    request_id = getattr(request.state, "request_id", "-")
    stats.record_query()

    if not query.question.strip():
        logger.warning("search request_id=%s status=rejected_empty_question", request_id)
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    retrieve_start = time.perf_counter()
    chunks = retrieve(query.question, k=TOP_K)
    retrieval_ms = _ms(retrieve_start)

    if not chunks:
        total_ms = _ms(request_start)
        logger.info(
            "search request_id=%s question=%r total_ms=%.2f retrieval_ms=%.2f "
            "llm_ms=0.00 sources=0 model=n/a status=no_results",
            request_id,
            query.question,
            total_ms,
            retrieval_ms,
        )
        query_log.record(
            question=query.question,
            answer=NO_RESULTS_MESSAGE,
            sources=[],
            latency_ms=total_ms,
            status="no_results",
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
    except LLMTimeoutError:
        total_ms = _ms(request_start)
        error_count = stats.record_error("search:LLMTimeoutError")
        unique_chunks = _deduplicate_chunks(chunks)
        sources = [
            SourceRef(file=c["filename"], snippet=_snippet(c["text"]), score=c["score"])
            for c in unique_chunks[:3]
        ]
        logger.warning(
            "search request_id=%s question=%r total_ms=%.2f retrieval_ms=%.2f "
            "status=llm_timeout sources=%d error_count=%d",
            request_id,
            query.question,
            total_ms,
            retrieval_ms,
            len(sources),
            error_count,
        )
        query_log.record(
            question=query.question,
            answer=_timeout_fallback_answer(chunks),
            sources=[s.file for s in sources],
            latency_ms=total_ms,
            status="llm_timeout",
        )
        return Answer(
            question=query.question,
            answer=_timeout_fallback_answer(chunks),
            sources=sources,
            latency_ms=total_ms,
        )
    except LLMRateLimitError as e:
        total_ms = _ms(request_start)
        error_count = stats.record_error("search:LLMRateLimitError")
        unique_chunks = _deduplicate_chunks(chunks)
        sources = [
            SourceRef(file=c["filename"], snippet=_snippet(c["text"]), score=c["score"])
            for c in unique_chunks[:3]
        ]
        fallback_answer = build_fallback_answer(chunks)
        logger.warning(
            "search request_id=%s question=%r total_ms=%.2f retrieval_ms=%.2f "
            "status=rate_limit_fallback sources=%d error_count=%d error=%s",
            request_id,
            query.question,
            total_ms,
            retrieval_ms,
            len(sources),
            error_count,
            e,
        )
        query_log.record(
            question=query.question,
            answer=fallback_answer,
            sources=[s.file for s in sources],
            latency_ms=total_ms,
            status="rate_limit_fallback",
        )
        return Answer(
            question=query.question,
            answer=fallback_answer,
            sources=sources,
            latency_ms=total_ms,
        )
    except ValueError as e:
        total_ms = _ms(request_start)
        error_count = stats.record_error(f"search:{type(e).__name__}")
        logger.error(
            "search request_id=%s question=%r total_ms=%.2f retrieval_ms=%.2f "
            "status=error error=%s error_count=%d",
            request_id,
            query.question,
            total_ms,
            retrieval_ms,
            e,
            error_count,
        )
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        total_ms = _ms(request_start)
        error_count = stats.record_error(f"search:{type(e).__name__}")
        logger.exception(
            "search request_id=%s question=%r total_ms=%.2f retrieval_ms=%.2f "
            "status=error error=%s error_count=%d",
            request_id,
            query.question,
            total_ms,
            retrieval_ms,
            e,
            error_count,
        )
        raise HTTPException(status_code=500, detail=f"Answer generation failed: {e}")
    llm_ms = _ms(llm_start)

    sources = [
        SourceRef(file=c["filename"], snippet=_snippet(c["text"]), score=c["score"])
        for c in chunks
    ]

    total_ms = _ms(request_start)
    logger.info(
        "search request_id=%s question=%r total_ms=%.2f retrieval_ms=%.2f llm_ms=%.2f "
        "sources=%d model=%s status=ok",
        request_id,
        query.question,
        total_ms,
        retrieval_ms,
        llm_ms,
        len(sources),
        llm.model,
    )
    query_log.record(
        question=query.question,
        answer=answer_text,
        sources=[s.file for s in sources],
        latency_ms=total_ms,
        status="ok",
    )
    return Answer(
        question=query.question,
        answer=answer_text,
        sources=sources,
        latency_ms=total_ms,
    )


@router.get("/log")
async def get_query_log():
    """Return the query log as JSON."""
    return {"entries": query_log.entries(), "count": query_log.count()}


@router.get("/log/export")
async def export_query_log():
    """Export the query log as a CSV download."""
    csv_content = query_log.export_csv()
    if not csv_content:
        raise HTTPException(status_code=404, detail="No query log entries to export.")
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=query_log.csv"},
    )
