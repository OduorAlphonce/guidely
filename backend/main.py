# backend/main.py
import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
load_dotenv()

# Import your modular routes
from backend.routes import documents, search
from backend.models.record import Metrics
from backend.services import indexing
from backend.services.stats import stats

# Ensure uploads directory exists before the app serves requests
Path(__file__).resolve().parent.joinpath("data", "uploads").mkdir(parents=True, exist_ok=True)

# Initialize the core FastAPI application
app = FastAPI(
    title="Mwongozo API",
    description="Backend service for searching and managing guidance documents",
    version="1.0.0"
)

# Configure CORS — allow the Vercel frontend and local dev
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def auto_index():
    """Index all sample docs and uploads on startup so search works immediately."""
    from backend.services.indexing import SAMPLE_DOCS_DIR, UPLOADS_DIR
    from backend.services.parser import SUPPORTED_EXTENSIONS

    logger = logging.getLogger("startup")
    for folder in (SAMPLE_DOCS_DIR, UPLOADS_DIR):
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                try:
                    result = indexing.index_document(str(path))
                    if result["status"] == "indexed":
                        logger.info("auto-index: indexed %s (%d chunks)", path.name, result["chunks"])
                    elif result["status"] == "skipped":
                        logger.info("auto-index: cached %s (unchanged)", path.name)
                except Exception as e:
                    logger.warning("auto-index: failed %s: %s", path.name, e)


# Connect your sub-routers to the main application
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Welcome to the Mwongozo API. Visit /docs for interactive documentation."
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/metrics", response_model=Metrics)
async def get_metrics():
    return Metrics(
        total_documents=indexing.cache.file_count(),
        total_chunks=indexing.cache.total_chunks(),
        total_queries=stats.queries_served,
        cache_hits=stats.cache_hits,
        cache_misses=stats.cache_misses,
        error_counts=stats.get_error_counts(),
    )
