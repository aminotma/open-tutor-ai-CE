# Phase 4 — Summarization Layer

**Status :** ✅ Complete — 17/17 tests passing  
**Date :** 2026-05-28

---

## Objectives

Generate and cache session summaries to feed `MemoryAgent` and `FeedbackAgent` without replaying the full interaction history on each agent call.

1. **`SummarizationService`** — LLM-based sliding-window summarization with TTL cache.
2. **Cache storage** — summaries stored in `opentutorai_memory` with `memory_type="session_summary"`.
3. **`invalidate_cache()`** — called by `persist_memory` node at session end to clear stale summaries.
4. **Dual auto-trigger** — summarization fires automatically when the exchange count or total token volume exceeds configurable thresholds.

---

## Files Created / Modified

| File | Change |
|------|--------|
| `backend/open_tutorai/services/summarization.py` | `SummarizationService` — summarize, cache, invalidate, dual trigger |
| `backend/open_tutorai/config.py` | Added `auto_summarize_token_limit: 1200` to `summaries` config |
| `backend/tests/test_phase4_summarization.py` | 17 unit tests |

---

## How Summarization Works

### Role in the system

Summarization is the **semantic compression** layer of the context pipeline. It converts a potentially long exchange history into a concise paragraph (3–5 sentences) that can be injected into the agent's context without exceeding the token budget.

```
Raw exchanges (unbounded)          Session summary (~50 tokens)
──────────────────────────         ──────────────────────────────
User: "je bloque sur X"
AI:   "voici un exercice…"    →    "L'apprenant travaille sur la
User: "j'ai compris X"             récursion (niveau intermédiaire).
AI:   "excellent, passons…"        Gap identifié sur les cas de
User: "Y pose problème"            base. Progrès sur X confirmé."
…                                  
10 exchanges × ~60 tokens          1 summary × ~50 tokens
= ~600 tokens                      = compression ×12
```

### When it is triggered — dual condition

`should_summarize(exchanges)` returns `True` when **either** condition is met:

| Trigger | Condition | Config key | Default |
|---------|-----------|------------|---------|
| **Count** | `len(exchanges) >= N` | `exchanges_per_summary` | 5 exchanges |
| **Volume** | `total_tokens(exchanges) >= T` | `auto_summarize_token_limit` | **1 200 tokens** |

The volume trigger (1 200 tokens = 40 % of the 3 000-token budget) ensures summarization fires **before** the context window is saturated, even for sessions with few but very long messages.

```
Token budget breakdown (3 000 total)
──────────────────────────────────────
 1 200  ← auto-summarize threshold
 ─────  exchanges compressed into ~50-token summary
   750  RAG docs (5 × ~150 tokens)
   300  User profile + learning objectives
   200  Session summary (compressed)
 ─────
 1 250  Left for agent reasoning
```

### Lifecycle

```
Session N — end                        Session N+1 — start
────────────────────────               ───────────────────────────────
FeedbackAgent / persist_memory node    Router calls
                                       ContextManager.build_agent_context()
  should_summarize(exchanges)?                │
    → count >= 5  OR                         └── SummarizationService
    → tokens >= 1200                               .get_cached_summary()
        │                                               → summary (< 24h)
        ▼                                               → None (expired)
  invalidate_cache(user, topic)                         │
  summarize_session(exchanges, llm)         TutorGraphState.session_summary
    → sliding window (last 10)             injected before graph.ainvoke()
    → LLM call (gpt-4o-mini)
    → cache in opentutorai_memory
      (memory_type="session_summary")
```

### Sliding window

Only the last `sliding_window_size=10` exchanges are sent to the LLM — this caps the prompt regardless of session length.

```python
windowed = exchanges[-10:]   # always ≤ 10 exchanges
prompt   = SUMMARIZATION_PROMPT.format(exchanges=format(windowed))
summary  = llm.invoke(prompt)
```

### Two compression levels in the system

| Level | Component | Mechanism |
|-------|-----------|-----------|
| **Semantic** | `SummarizationService` | LLM rewrites N exchanges into 1 paragraph |
| **Volumetric** | `ContextManager._trim_to_budget()` | Drops lowest-scoring RAG docs if over token budget |

---

## `SummarizationService` — Public API

| Method | Description |
|--------|-------------|
| `should_summarize(exchanges)` | `True` if count ≥ 5 **or** tokens ≥ 1 200 |
| `summarize_session(user_id, topic, exchanges, llm, db, force=False)` | Returns cached summary if valid; otherwise calls LLM + caches result |
| `get_cached_summary(user_id, topic, db)` | Returns valid cached summary or `None` if TTL expired / not found |
| `cache_summary(user_id, topic, summary, db)` | Persists summary to `opentutorai_memory` |
| `invalidate_cache(user_id, topic, db)` | Deletes all cached summaries for this user+topic |

---

## Config keys (`CONTEXT_RETRIEVAL_CONFIG["summaries"]`)

| Key | Value | Description |
|-----|-------|-------------|
| `enabled` | `True` | Enable/disable the layer |
| `cache_ttl_hours` | `24` | Cache lifetime in hours |
| `exchanges_per_summary` | `5` | Count trigger threshold |
| `auto_summarize_token_limit` | `1200` | Volume trigger threshold (tokens) |

---

## Design Decisions

- **1 200-token volume threshold** — 40 % of the 3 000-token budget. Leaves room for RAG docs, profile, and agent reasoning before context is saturated. For average exchanges (~30 tokens/message), fires at ~40 messages; for long messages, can fire after only 2.
- **Topic filtering in Python** — `JSONField` (OpenWebUI) does not support SQLAlchemy JSON path operators. Rows fetched by `user_id + memory_type + TTL cutoff`, topic checked in Python.
- **`force=True`** — bypasses cache; used by `FeedbackAgent` after mastery updates.
- **LLM error fallback** — on failure, a minimal string is cached to prevent retry storms.
- **No new router** — pure service layer consumed by `MemoryAgent` (Phase 5) and `ContextManager` (Phase 3).

---

## Test Results

```
test_should_summarize_below_threshold          PASSED
test_should_summarize_at_count_threshold       PASSED
test_should_summarize_above_count_threshold    PASSED
test_should_summarize_by_volume_trigger        PASSED  ← new
test_should_summarize_volume_below_limit       PASSED  ← new
test_cache_and_retrieve_summary                PASSED
test_get_cached_summary_wrong_user_returns_none PASSED
test_get_cached_summary_wrong_topic_returns_none PASSED
test_get_cached_summary_expired_returns_none   PASSED
test_invalidate_cache_removes_entries          PASSED
test_invalidate_cache_only_affects_topic       PASSED
test_summarize_session_calls_llm               PASSED
test_summarize_session_returns_cache_on_second_call PASSED
test_summarize_session_empty_exchanges         PASSED
test_summarize_session_uses_sliding_window     PASSED
test_summarize_session_force_bypasses_cache    PASSED
test_summarize_session_llm_error_returns_fallback PASSED

17 passed in 2.10s
```

---

## Cumulative test count

| Phase | Tests |
|-------|-------|
| Phase 1 | 12 |
| Phase 2 | 15 |
| Phase 3 | 16 |
| Phase 4 | 17 |
| **Total** | **60** |

---

## Next Phase

**Phase 5 — Adaptive Tutor Engine** : implement the 8 LangGraph agents (`MemoryAgent`, `KnowledgeAgent`, `DiagnosticsAgent`, `PlannerAgent`, `ExerciseAgent`, `VerifierAgent`, `FeedbackAgent`, `OrchestratorAgent`) + `TutorGraphState` + `StateGraph` compilation with `SqliteSaver` checkpointer.
