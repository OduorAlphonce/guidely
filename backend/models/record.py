from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    pending = "pending"
    indexing = "indexing"
    ready = "ready"
    error = "error"


class Document(BaseModel):
    id: str
    filename: str
    path: str
    size_bytes: int
    status: DocumentStatus = DocumentStatus.pending
    md5_hash: str = ""
    tags: list[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Chunk(BaseModel):
    id: str
    document_id: str
    document_filename: str
    index: int
    text: str
    token_count: int
    embedding: list[float] | None = None


class Query(BaseModel):
    question: str = Field(...)


class IndexStatus(str, Enum):
    indexed = "indexed"
    skipped = "skipped"
    failed = "failed"


class IndexResult(BaseModel):
    file: str
    status: IndexStatus
    doc_id: str = ""
    chunks: int = 0
    error: str = ""


class ReindexSummary(BaseModel):
    total: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[IndexResult] = []


class SourceRef(BaseModel):
    file: str
    snippet: str
    score: float
    text: str = ""


class Answer(BaseModel):
    question: str
    answer: str
    sources: list[SourceRef] = []
    latency_ms: float = 0.0


class Metrics(BaseModel):
    total_documents: int = 0
    total_chunks: int = 0
    total_queries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    error_counts: dict[str, int] = {}
