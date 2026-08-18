import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from backend.models.record import Document, DocumentStatus, IndexResult, IndexStatus, ReindexSummary
from backend.services.indexing import SAMPLE_DOCS_DIR, UPLOADS_DIR, cache, index_document, vector_store
from backend.services.parser import SUPPORTED_EXTENSIONS, get_file_metadata

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=list[Document])
async def list_documents():
    docs = []
    for path_key, entry in cache.list_files().items():
        path = Path(path_key)
        md5 = entry.get("md5", "")
        chunks = entry.get("chunks") or []
        indexed_at = entry.get("indexed_at")
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        docs.append(Document(
            id=md5,
            filename=path.name,
            path=str(path),
            size_bytes=size,
            status=DocumentStatus.ready,
            md5_hash=md5,
            updated_at=datetime.fromisoformat(indexed_at) if indexed_at else datetime.utcnow(),
        ))
    docs.sort(key=lambda d: d.updated_at, reverse=True)
    return docs


@router.post("/upload", response_model=Document)
async def upload_document(request: Request, file: UploadFile = File(...)):
    request_id = getattr(request.state, "request_id", "-")
    filename = Path(file.filename or "").name or "upload.txt"
    if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS_DIR / filename

    try:
        contents = await file.read()
    except Exception as e:
        logger.exception("upload request_id=%s file=%s failed to read", request_id, filename)
        raise HTTPException(status_code=400, detail=f"Failed to read upload: {e}")

    try:
        dest.write_bytes(contents)
    except OSError as e:
        logger.exception("upload request_id=%s file=%s failed to save %s", request_id, filename, dest)
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")

    try:
        index_document(str(dest))
    except ValueError as e:
        dest.unlink(missing_ok=True)
        logger.warning("upload request_id=%s file=%s rejected: %s", request_id, filename, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        dest.unlink(missing_ok=True)
        logger.exception("upload request_id=%s file=%s indexing failed", request_id, filename)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {e}")

    meta = get_file_metadata(str(dest))
    return Document(
        id=meta["md5_hash"],
        filename=filename,
        path=str(dest),
        size_bytes=meta["size_bytes"],
        status=DocumentStatus.ready,
        md5_hash=meta["md5_hash"],
    )


@router.post("/reindex", response_model=ReindexSummary)
async def reindex_all(request: Request):
    request_id = getattr(request.state, "request_id", "-")
    files = []
    for folder in (SAMPLE_DOCS_DIR, UPLOADS_DIR):
        if not folder.exists():
            continue
        files.extend(
            sorted(
                p for p in folder.rglob("*")
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
            )
        )

    results = []
    for path in files:
        try:
            result = index_document(str(path))
            results.append(IndexResult(**result))
        except Exception as e:
            logger.exception("reindex request_id=%s failed to index %s", request_id, path)
            results.append(IndexResult(file=str(path), status="failed", error=str(e)))

    return ReindexSummary(
        total=len(files),
        indexed=sum(1 for r in results if r.status == IndexStatus.indexed),
        skipped=sum(1 for r in results if r.status == IndexStatus.skipped),
        failed=sum(1 for r in results if r.status == IndexStatus.failed),
        results=results,
    )


@router.get("/{doc_id}/content")
async def get_document_content(request: Request, doc_id: str):
    request_id = getattr(request.state, "request_id", "-")
    for path_key, entry in cache.list_files().items():
        if entry.get("md5") == doc_id:
            path = Path(path_key)
            if not path.exists():
                raise HTTPException(status_code=404, detail="File not found on disk")
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_bytes().decode("latin-1")
            return {"content": content, "filename": path.name}
    raise HTTPException(status_code=404, detail=f"No document found with id {doc_id}")


@router.delete("/{doc_id}")
async def delete_document(request: Request, doc_id: str):
    request_id = getattr(request.state, "request_id", "-")
    removed_vectors = vector_store.remove_document(doc_id)
    removed_cache = cache.remove_by_md5(doc_id)
    if removed_vectors == 0 and removed_cache == 0:
        raise HTTPException(status_code=404, detail=f"No document found with id {doc_id}")
    logger.info(
        "delete request_id=%s doc=%s removed (%d vectors, %d cache entries)",
        request_id,
        doc_id,
        removed_vectors,
        removed_cache,
    )
    return {
        "message": f"Document {doc_id} deleted",
        "removed_vectors": removed_vectors,
        "removed_cache_entries": removed_cache,
    }
