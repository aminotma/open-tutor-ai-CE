# Phase 2 — Context Retrieval Engine

**Status :** ✅ Complete — 15/15 tests passing  
**Date :** 2026-05-28

---

## Objectives

Wire ChromaDB as the RAG backend and expose two retrieval surfaces used by all agents:

1. **Pedagogical document retrieval** — semantic search over indexed files (PDF, text) via ChromaDB + sentence-transformers embeddings.
2. **Internal memory retrieval** — text-based search over `opentutorai_memory` SQL rows.
3. **REST endpoints** — index documents, retrieve docs, list collections.

---

## Files Created

| File | Role |
|------|------|
| `backend/open_tutorai/services/context_retrieval.py` | ChromaDB client, chunking, indexing, RAG retrieval, SQL memory retrieval |
| `backend/open_tutorai/routers/context_retrieval.py` | REST endpoints for index / retrieve / list |
| `backend/tests/test_phase2_context_retrieval.py` | 15 unit tests |

---

## Files Modified

### `backend/open_tutorai/main.py`
- Imported `context_retrieval` router
- Registered under `/api/v1`

### `backend/requirements.txt`
- Added `langgraph>=0.2.0`, `langgraph-checkpoint-sqlite>=0.1.0`, `networkx>=3.0`

---

## `ContextRetrievalService` — Public API

| Function | Description |
|----------|-------------|
| `get_chroma_client()` | Lazy singleton — `PersistentClient` at `data/vector_db/` |
| `get_or_create_collection(name)` | Create/get a ChromaDB collection with `SentenceTransformerEmbeddingFunction` |
| `index_document(file_path, metadata, user_id)` | Extract text → chunk (500 words, 50 overlap) → embed → upsert. Returns chunk count. |
| `retrieve_pedagogical_documents(user_id, query, top_k)` | Semantic search, returns `{id, content, metadata, vector_score}` list |
| `retrieve_internal_memory(user_id, query, memory_types, limit, db)` | SQL substring search on `opentutorai_memory` |
| `_chunk_text(text, chunk_size, overlap)` | Word-level sliding window chunker |
| `_extract_text(file_path)` | Reads `.pdf` (via pypdf) or plain text files |

---

## REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/context/index` | Upload file (PDF/txt), index into ChromaDB. Returns `{chunks_indexed, filename}` |
| `POST` | `/api/v1/context/retrieve` | Semantic search. Body: `{query, top_k, collection_name}` |
| `GET` | `/api/v1/context/collections` | List ChromaDB collections with document counts |

---

## Design Decisions

- **Embedding model:** `all-MiniLM-L6-v2` (configurable via `EMBED_MODEL` env var) — fast, good quality, already installed via `sentence-transformers`.
- **Distance → score:** ChromaDB returns L2 distance; converted to `score = max(0, 1 - dist/2)` so all scores are in `[0, 1]`.
- **Chunk size:** 500 words / 50-word overlap — balances context richness and embedding precision.
- **Memory retrieval** is synchronous substring match (no embeddings) — fast and sufficient for the 10-memory context window used by agents.
- **Lazy client:** `get_chroma_client()` initializes on first call, avoids startup cost.

---

## Test Results

```
test_chunk_text_basic                              PASSED
test_chunk_text_short                              PASSED
test_chunk_text_empty                              PASSED
test_extract_text_from_txt                         PASSED
test_extract_text_missing_file                     PASSED
test_retrieve_returns_list_on_empty_collection     PASSED
test_retrieve_returns_empty_on_blank_query         PASSED
test_retrieve_with_documents                       PASSED
test_retrieve_score_between_0_and_1                PASSED
test_index_document_txt                            PASSED
test_index_document_empty_file                     PASSED
test_retrieve_internal_memory_empty                PASSED
test_retrieve_internal_memory_finds_match          PASSED
test_retrieve_internal_memory_type_filter          PASSED
test_retrieve_internal_memory_limit                PASSED

15 passed, 1 warning in 9.38s
```

---

## Next Phase

**Phase 3 — Dynamic Context Manager** : `ContextManager.build_agent_context()` merges RAG docs + memories + session summary into a single `AgentContext` dict, filtered by relevance, recency (`max_age_days=14`) and token budget (`max_context_tokens=3000`).
