from fastapi import APIRouter, HTTPException, UploadFile, File
from backend.models.record import Document, DocumentStatus
from backend.services.parser import compute_md5, get_file_metadata

router = APIRouter()


@router.get("/", response_model=list[Document])
async def list_documents():
    return []


@router.post("/upload", response_model=Document)
async def upload_document(file: UploadFile = File(...)):
    return Document(
        id="",
        filename=file.filename or "unknown",
        path="",
        size_bytes=0,
        status=DocumentStatus.ready,
    )


@router.post("/reindex")
async def reindex_all():
    return {"message": "Re-indexing triggered", "status": "pending"}


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    return {"message": f"Document {doc_id} deleted"}
