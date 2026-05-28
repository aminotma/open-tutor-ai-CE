# Phase 3 — Dynamic Context Manager

**Status :** ✅ Complete — 16/16 tests passing  
**Date :** 2026-05-28

---

## Objectives

Control what context is injected into each agent call — filter by relevance, recency, topic, and token budget. Prevents irrelevant memories and oversized prompts.

1. `CONTEXT_RETRIEVAL_CONFIG` — single config dict for all phases (filtering, memory, RAG, summarization, langchain).
2. `AgentContext` dataclass — typed container for pre-session context passed to the LangGraph `TutorGraphState`.
3. `ContextManager.build_agent_context()` — assembles RAG docs + session summary within token budget.
4. `ContextManager.filter_memories()` — topic + recency filter called by `MemoryAgent` inside the graph.

---

## Files Created

| File | Role |
|------|------|
| `backend/open_tutorai/services/context_manager.py` | `AgentContext` dataclass + `ContextManager` class + helpers |
| `backend/tests/test_phase3_context_manager.py` | 16 unit tests |

---

## Files Modified

### `backend/open_tutorai/config.py`

Added `CONTEXT_RETRIEVAL_CONFIG` dict with 6 sections:

| Key | Contents |
|-----|----------|
| `filtering` | `relevance_threshold=0.4`, `recency_threshold=0.3`, `max_age_days=14`, `max_context_tokens=3000` |
| `memory` | `enabled`, `top_k=10`, `memory_types` list |
| `rag` | `enabled`, `top_k_documents=5`, `min_vector_similarity=0.5`, `verification_threshold=0.65` |
| `summaries` | `cache_ttl_hours=24`, `exchanges_per_summary=5` |
| `summarization` | `sliding_window_size=10`, `forget_irrelevant=True` |
| `langchain` | `llm_model`, `llm_temperature`, `orchestrator_use_llm=False` |

---

## `ContextManager` — Public API

| Method | Description |
|--------|-------------|
| `build_agent_context(user_id, topic, query, db, ...)` → `AgentContext` | Fetches RAG docs (filtered by `min_score`), gets session summary, trims to `max_context_tokens`. Memories and weak_concepts excluded — handled inside graph. |
| `filter_memories(memories, topic, max_age_days)` → `list[dict]` | Filters a memory list by topic and recency. Called by `MemoryAgent` after SQL fetch. |

## `AgentContext` — Fields

| Field | Type | Source |
|-------|------|--------|
| `user_name`, `user_id` | str | Gateway API |
| `topic`, `language`, `learning_objectives` | str / list | Gateway API |
| `user_message` | str | Current learner input (also used as RAG query) |
| `rag_docs` | list[dict] | ChromaDB, filtered by `relevance_threshold` |
| `session_summary` | str | SummarizationService cache (passed in) |
| `token_count` | int | tiktoken count of all injected text |

## Internal Helpers

| Function | Description |
|----------|-------------|
| `_fetch_rag_docs(...)` | Calls `retrieve_pedagogical_documents`, filters by `min_score` |
| `_count_tokens(text)` | tiktoken `cl100k_base` — fallback to word count |
| `_trim_to_budget(docs, max_tokens, summary)` | Drops lowest-scoring docs until within budget |

---

## Design Decisions

- **Memories excluded from pre-graph build** — they change during the session (FeedbackAgent writes new ones), so loading them once would produce stale data. `MemoryAgent` loads them fresh at the start of each graph run and `ContextManager.filter_memories()` is called on that fresh list.
- **`max_age_days=14`** — tighter than the initially proposed 365 days; ensures only recent and relevant context is used.
- **`AsyncMock`** used in tests for async helpers (Python 3.8+ standard library, no extra plugin).

---

## Test Results

```
test_filter_memories_same_topic                    PASSED
test_filter_memories_no_topic_kept                 PASSED
test_filter_memories_wrong_topic_excluded          PASSED
test_filter_memories_recency_recent_kept           PASSED
test_filter_memories_recency_old_excluded          PASSED
test_filter_memories_invalid_date_kept             PASSED
test_filter_memories_empty_list                    PASSED
test_count_tokens_nonzero                          PASSED
test_count_tokens_empty                            PASSED
test_trim_keeps_high_score_docs                    PASSED
test_trim_respects_budget                          PASSED
test_build_agent_context_returns_agent_context     PASSED
test_build_agent_context_empty_query_falls_back    PASSED
test_build_agent_context_no_rag_graceful           PASSED
test_build_agent_context_token_count_within_budget PASSED
test_build_agent_context_carries_session_summary   PASSED

16 passed in 0.41s
```

---

## Next Phase

**Phase 4 — Summarization Layer** : `SummarizationService` with sliding-window LLM summarization, cache stored in `opentutorai_memory` with `memory_type="session_summary"`, TTL 24h, `invalidate_cache()` called by `persist_memory` node.
