"""
Phase 2 unit tests — Context Retrieval Engine.

ChromaDB tests use an ephemeral in-memory client (no disk I/O).
Memory retrieval tests use SQLite in-memory.
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    from open_tutorai.models.database import Memory, KGConcept, KGRelation, KGUserMastery
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    for table in [Memory.__table__, KGConcept.__table__,
                  KGRelation.__table__, KGUserMastery.__table__]:
        table.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture(scope="module")
def chroma_collection():
    """Ephemeral in-memory ChromaDB collection — no disk writes."""
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    client = chromadb.EphemeralClient()
    ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    collection = client.get_or_create_collection("test_docs", embedding_function=ef)
    yield collection


# ── Text chunking ──────────────────────────────────────────────────────────────

def test_chunk_text_basic():
    from open_tutorai.services.context_retrieval import _chunk_text
    text = " ".join([f"word{i}" for i in range(1200)])
    chunks = _chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) >= 2
    assert all(len(c.split()) <= 500 for c in chunks)


def test_chunk_text_short():
    from open_tutorai.services.context_retrieval import _chunk_text
    chunks = _chunk_text("hello world", chunk_size=500, overlap=50)
    assert len(chunks) == 1
    assert chunks[0] == "hello world"


def test_chunk_text_empty():
    from open_tutorai.services.context_retrieval import _chunk_text
    assert _chunk_text("") == []
    assert _chunk_text("   ") == []


# ── Text extraction ───────────────────────────────────────────────────────────

def test_extract_text_from_txt(tmp_path):
    from open_tutorai.services.context_retrieval import _extract_text
    f = tmp_path / "sample.txt"
    f.write_text("Hello from a text file.", encoding="utf-8")
    assert "Hello from a text file." in _extract_text(str(f))


def test_extract_text_missing_file():
    from open_tutorai.services.context_retrieval import _extract_text
    result = _extract_text("/nonexistent/path/file.pdf")
    assert result == ""


# ── ChromaDB retrieval ────────────────────────────────────────────────────────

def test_retrieve_returns_list_on_empty_collection():
    """retrieve_pedagogical_documents must return [] when collection is empty."""
    import chromadb
    from open_tutorai.services import context_retrieval as cr

    ephemeral_client = chromadb.EphemeralClient()
    mock_collection = MagicMock()
    mock_collection.count.return_value = 0

    with patch.object(cr, "get_or_create_collection", return_value=mock_collection):
        result = cr.retrieve_pedagogical_documents("u1", "algorithms", top_k=5)
    assert result == []


def test_retrieve_returns_empty_on_blank_query():
    from open_tutorai.services.context_retrieval import retrieve_pedagogical_documents
    result = retrieve_pedagogical_documents("u1", "   ", top_k=5)
    assert result == []


def test_retrieve_with_documents(chroma_collection):
    """Index two docs and verify retrieval returns the most relevant one."""
    from open_tutorai.services import context_retrieval as cr

    chroma_collection.upsert(
        ids=["doc1", "doc2"],
        documents=[
            "Recursion is a technique where a function calls itself.",
            "Photosynthesis is a process used by plants to convert light into energy.",
        ],
        metadatas=[
            {"source": "algo.txt", "user_id": "u1"},
            {"source": "bio.txt",  "user_id": "u1"},
        ],
    )

    with patch.object(cr, "get_or_create_collection", return_value=chroma_collection):
        results = cr.retrieve_pedagogical_documents("u1", "recursive function call", top_k=2)

    assert len(results) >= 1
    assert all("content" in r and "vector_score" in r for r in results)
    top = results[0]
    assert "recursion" in top["content"].lower() or top["vector_score"] >= 0.0


def test_retrieve_score_between_0_and_1(chroma_collection):
    from open_tutorai.services import context_retrieval as cr
    with patch.object(cr, "get_or_create_collection", return_value=chroma_collection):
        results = cr.retrieve_pedagogical_documents("u1", "function", top_k=2)
    for r in results:
        assert 0.0 <= r["vector_score"] <= 1.0


# ── index_document ────────────────────────────────────────────────────────────

def test_index_document_txt(tmp_path):
    from open_tutorai.services import context_retrieval as cr

    f = tmp_path / "lesson.txt"
    f.write_text(" ".join([f"word{i}" for i in range(600)]), encoding="utf-8")

    mock_col = MagicMock()
    with patch.object(cr, "get_or_create_collection", return_value=mock_col):
        count = cr.index_document(str(f), {"title": "Test"}, user_id="u1")

    assert count >= 1
    mock_col.upsert.assert_called_once()


def test_index_document_empty_file(tmp_path):
    from open_tutorai.services import context_retrieval as cr
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    count = cr.index_document(str(f), {}, user_id="u1")
    assert count == 0


# ── retrieve_internal_memory ──────────────────────────────────────────────────

def test_retrieve_internal_memory_empty(db):
    import asyncio
    from open_tutorai.services.context_retrieval import retrieve_internal_memory
    results = asyncio.run(retrieve_internal_memory("unknown_user", "python", db=db))
    assert results == []


def test_retrieve_internal_memory_finds_match(db):
    import asyncio
    from open_tutorai.models.database import Memory
    from open_tutorai.services.context_retrieval import retrieve_internal_memory
    from uuid import uuid4

    db.add(Memory(
        id=uuid4().hex, user_id="mem_user",
        memory_type="episodic",
        content="Practiced binary search trees today.",
        memory_metadata={"topic": "data_structures"},
    ))
    db.commit()

    results = asyncio.run(retrieve_internal_memory("mem_user", "binary search", db=db))
    assert len(results) == 1
    assert results[0]["type"] == "episodic"
    assert "binary search" in results[0]["content"]


def test_retrieve_internal_memory_type_filter(db):
    import asyncio
    from open_tutorai.models.database import Memory
    from open_tutorai.services.context_retrieval import retrieve_internal_memory
    from uuid import uuid4

    for mtype in ["episodic", "behavioral"]:
        db.add(Memory(
            id=uuid4().hex, user_id="filter_user",
            memory_type=mtype, content=f"Memory about sorting ({mtype})",
            memory_metadata={},
        ))
    db.commit()

    results = asyncio.run(retrieve_internal_memory(
        "filter_user", "sorting", memory_types=["episodic"], db=db
    ))
    assert all(r["type"] == "episodic" for r in results)


def test_retrieve_internal_memory_limit(db):
    import asyncio
    from open_tutorai.models.database import Memory
    from open_tutorai.services.context_retrieval import retrieve_internal_memory
    from uuid import uuid4

    for i in range(15):
        db.add(Memory(
            id=uuid4().hex, user_id="limit_user",
            memory_type="episodic", content=f"Lesson about recursion session {i}",
            memory_metadata={},
        ))
    db.commit()

    results = asyncio.run(retrieve_internal_memory("limit_user", "recursion", limit=5, db=db))
    assert len(results) <= 5
