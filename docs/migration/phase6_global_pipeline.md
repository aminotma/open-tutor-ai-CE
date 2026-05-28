# Phase 6 — Global Pipeline Integration

## Goal

Wire the Phase 5 `tutor_graph` into the FastAPI application via two new routers:
- `adaptive` — runs the full LangGraph tutoring pipeline per session
- `knowledge-graph` — exposes the user's knowledge graph (read + write)

## Files created / modified

| File | Change |
|------|--------|
| `backend/open_tutorai/routers/adaptive.py` | New — `POST /api/v1/adaptive/plan`, `GET /api/v1/adaptive/session/{id}` |
| `backend/open_tutorai/routers/knowledge_graph.py` | New — `GET/POST/PUT/DELETE /api/v1/knowledge-graph/{topic}/…` |
| `backend/open_tutorai/main.py` | Register `adaptive_router` + `kg_router` |
| `backend/tests/test_phase6_pipeline.py` | 17 unit tests (all passing) |

## API surface

### Adaptive Tutor (`/api/v1/adaptive/`)

#### `POST /api/v1/adaptive/plan`

Run a full adaptive tutoring session.

**Request body** (`AdaptivePlanRequest`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `topic` | str | required | Learning topic |
| `current_level` | str | `"intermediate"` | `beginner` / `intermediate` / `advanced` |
| `language` | str | `"en"` | ISO language code |
| `user_message` | str | `""` | Latest message from the learner |
| `recent_interactions` | list | `[]` | Recent scored interactions |
| `feedback_comments` | list | `[]` | Learner's free-text feedback |
| `learning_objectives` | list | `[]` | Session objectives |
| `preferred_exercise_types` | list | `[]` | Learner preferences |
| `session_id` | str | auto-generated | Thread ID for LangGraph checkpointer |

**Response** (`AdaptivePlanResponse`):

| Field | Description |
|-------|-------------|
| `session_id` | Checkpointer thread ID (pass back to resume) |
| `topic` | Echo of input topic |
| `adjusted_level` | Level after DiagnosticsAgent |
| `exercises` | List of generated exercises |
| `strategy` | Prioritised strategy decisions |
| `verification` | `{verdict, support_score, …}` from VerifierAgent |
| `agent_trace` | Step-by-step execution log |

**Pipeline flow:**

```
1. SummarizationService.get_cached_summary(user, topic) → session_summary
2. ContextManager.build_agent_context(user, topic, query) → rag_docs
3. Build TutorGraphState (all fields pre-populated)
4. tutor_graph.invoke(state, config={thread_id}) → final_state
5. Return exercises, strategy, verification, adjusted_level, agent_trace
```

**Error handling:**
- Context pre-loading failures are caught silently; graph runs with `rag_docs=[]`.
- Graph execution errors return HTTP 500 with detail.

#### `GET /api/v1/adaptive/session/{session_id}`

Replay / retrieve the last saved checkpoint for a session.

- Returns 404 if `session_id` is unknown or belongs to a different user.
- Reads from the SQLite checkpointer at `data/langgraph_checkpoints.sqlite`.

---

### Knowledge Graph (`/api/v1/knowledge-graph/`)

#### `GET /api/v1/knowledge-graph/{topic}`

Returns the full knowledge graph for the authenticated user and topic.

**Response** (`KGResponse`):
```json
{
  "topic": "algorithms",
  "nodes": [{"name": "recursion", "difficulty": "intermediate", "mastery": 0.3}],
  "edges": [{"source": "recursion", "target": "sorting", "relation": "requires"}],
  "weak_concepts": ["recursion"]
}
```

#### `POST /api/v1/knowledge-graph/{topic}/concepts`

Add a concept (and optional relation to an existing concept).

**Request** (`ConceptAddRequest`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | str | required | Concept name |
| `difficulty` | str | `"intermediate"` | Difficulty level |
| `relation_to` | str | `null` | Target concept to link to |
| `relation_type` | str | `"relates_to"` | Edge type (e.g. `requires`) |

Returns HTTP 201 + `ConceptNode`.

#### `PUT /api/v1/knowledge-graph/{topic}/mastery`

Increment / decrement mastery for one concept.

**Request** (`MasteryUpdateRequest`):
```json
{"concept_name": "recursion", "delta": 0.1, "last_error": null}
```

**Response:**
```json
{"concept": "recursion", "mastery": 0.45, "attempts": 4}
```

#### `DELETE /api/v1/knowledge-graph/{topic}/mastery`

Reset all mastery scores for the authenticated user on a topic. Returns HTTP 204.

---

## main.py registration

```python
from open_tutorai.routers import adaptive as adaptive_router
from open_tutorai.routers import knowledge_graph as kg_router

app.include_router(adaptive_router.router, prefix="/api/v1", tags=["adaptive"])
app.include_router(kg_router.router,       prefix="/api/v1", tags=["knowledge-graph"])
```

## Test results

```
17 passed, 0 failed
```

All tests run without DB, LLM, or ChromaDB. FastAPI endpoints tested via `TestClient` with mocked dependencies (`AsyncMock` for `ContextManager.build_agent_context`).

## End-to-end integration with Phase 5

The `tutor_graph` singleton (compiled in `graph.py`) is imported lazily inside the endpoint function to avoid startup overhead. The `thread_id` from `session_id` is passed as a LangGraph `configurable`, enabling multi-turn sessions with the SQLite checkpointer.
