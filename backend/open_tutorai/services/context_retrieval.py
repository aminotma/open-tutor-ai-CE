from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "data/vector_db")
COLLECTION_NAME = "pedagogical_documents"
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


# ── ChromaDB client (lazy singleton) ─────────────────────────────────────────

_chroma_client = None


def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        Path(CHROMA_PATH).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _chroma_client


def get_or_create_collection(name: str = COLLECTION_NAME):
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    client = get_chroma_client()
    ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    return client.get_or_create_collection(name=name, embedding_function=ef)


# ── Text chunking ─────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE,
                overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i: i + chunk_size]))
        i += chunk_size - overlap
    return [c for c in chunks if c.strip()]


# ── Document indexing ─────────────────────────────────────────────────────────

def index_document(file_path: str, metadata: dict, user_id: str) -> int:
    """
    Read a text/PDF file, chunk it, embed and upsert into ChromaDB.
    Returns the number of chunks indexed.
    """
    text = _extract_text(file_path)
    if not text.strip():
        return 0

    chunks = _chunk_text(text)
    collection = get_or_create_collection()

    ids, documents, metadatas = [], [], []
    for idx, chunk in enumerate(chunks):
        ids.append(f"{uuid.uuid4().hex}")
        documents.append(chunk)
        metadatas.append({
            "user_id": user_id,
            "source": os.path.basename(file_path),
            "chunk_index": idx,
            **{k: str(v) for k, v in metadata.items()},
        })

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return len(chunks)


def _extract_text(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            return ""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


# ── RAG retrieval from ChromaDB ───────────────────────────────────────────────

def retrieve_pedagogical_documents(
    user_id: str,
    query: str,
    top_k: int = 5,
    collection_name: str = COLLECTION_NAME,
) -> list[dict]:
    """
    Semantic search over the pedagogical corpus.
    Returns list of dicts: {id, content, metadata, vector_score}.
    """
    if not query.strip():
        return []
    try:
        collection = get_or_create_collection(collection_name)
        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, max(1, collection.count())),
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    docs = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        # ChromaDB returns L2 distance; convert to a 0-1 similarity score
        score = max(0.0, 1.0 - dist / 2.0)
        docs.append({
            "id": meta.get("source", ""),
            "content": doc,
            "metadata": meta,
            "vector_score": round(score, 4),
        })
    return docs


# ── Memory retrieval from SQL ─────────────────────────────────────────────────

def retrieve_internal_memory_sync(
    user_id: str,
    query: str,
    memory_types: Optional[list[str]] = None,
    limit: int = 10,
    db=None,
) -> list[dict]:
    """
    Synchronous text-based retrieval from opentutorai_memory.
    Safe to call from any context (sync or async thread).
    """
    from open_tutorai.models.database import Memory

    q = db.query(Memory).filter(Memory.user_id == user_id)
    if memory_types:
        q = q.filter(Memory.memory_type.in_(memory_types))

    query_lower = query.lower()
    results = [
        m for m in q.order_by(Memory.created_at.desc()).limit(limit * 3).all()
        if not query_lower or query_lower in m.content.lower()
    ]

    return [
        {
            "id": m.id,
            "type": m.memory_type,
            "content": m.content,
            "metadata": m.memory_metadata or {},
        }
        for m in results[:limit]
    ]


async def retrieve_internal_memory(
    user_id: str,
    query: str,
    memory_types: Optional[list[str]] = None,
    limit: int = 10,
    db=None,
) -> list[dict]:
    """Async wrapper — delegates to the synchronous implementation."""
    return retrieve_internal_memory_sync(
        user_id=user_id, query=query,
        memory_types=memory_types, limit=limit, db=db,
    )
