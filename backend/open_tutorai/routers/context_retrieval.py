import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional

from open_webui.utils.auth import get_verified_user
from open_tutorai.services.context_retrieval import (
    get_or_create_collection,
    index_document,
    retrieve_pedagogical_documents,
    COLLECTION_NAME,
)

router = APIRouter(tags=["context"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class RetrieveRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5
    collection_name: Optional[str] = COLLECTION_NAME


class DocumentResult(BaseModel):
    id: str
    content: str
    metadata: dict
    vector_score: float


class IndexResponse(BaseModel):
    chunks_indexed: int
    filename: str


class CollectionInfo(BaseModel):
    name: str
    count: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/context/index", response_model=IndexResponse)
async def index_file(
    file: UploadFile = File(...),
    title: Optional[str] = None,
    user=Depends(get_verified_user),
):
    """Upload and index a document (PDF or plain text) into ChromaDB."""
    suffix = os.path.splitext(file.filename or "doc.txt")[1] or ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        metadata = {"title": title or file.filename or "", "user_id": user.id}
        count = index_document(tmp_path, metadata, user_id=user.id)
    finally:
        os.unlink(tmp_path)

    if count == 0:
        raise HTTPException(status_code=422, detail="No text could be extracted from the file.")
    return IndexResponse(chunks_indexed=count, filename=file.filename or "")


@router.post("/context/retrieve", response_model=list[DocumentResult])
async def retrieve_docs(
    body: RetrieveRequest,
    user=Depends(get_verified_user),
):
    """Semantic search over the pedagogical corpus."""
    docs = retrieve_pedagogical_documents(
        user_id=user.id,
        query=body.query,
        top_k=body.top_k or 5,
        collection_name=body.collection_name or COLLECTION_NAME,
    )
    return [DocumentResult(**d) for d in docs]


@router.get("/context/collections", response_model=list[CollectionInfo])
async def list_collections(user=Depends(get_verified_user)):
    """List all ChromaDB collections with their document count."""
    client_collections = get_or_create_collection().metadata  # ensure collection exists
    from open_tutorai.services.context_retrieval import get_chroma_client
    collections = get_chroma_client().list_collections()
    return [
        CollectionInfo(name=c.name, count=c.count())
        for c in collections
    ]
