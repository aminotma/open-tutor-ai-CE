# Phase 1 — Hybrid Memory System (KG included)

**Status :** ✅ Complete — 12/12 tests passing  
**Date :** 2026-05-28

---

## Objectives

Build the full memory persistence layer that every agent reads from and writes to:

1. Persistent user memories (episodic, behavioral, procedural, session summaries) in SQL.
2. Knowledge Graph (KG) tables to track concepts, their relations, and per-user mastery levels.
3. A `KnowledgeGraphService` to read/write the graph via NetworkX + SQLAlchemy.
4. A REST router exposing the memory tables to the frontend (fixes broken 404 calls).

---

## Files Created

| File | Role |
|------|------|
| `backend/open_tutorai/services/__init__.py` | Package marker for the new services layer |
| `backend/open_tutorai/services/knowledge_graph.py` | `KnowledgeGraphService` — all KG read/write logic |
| `backend/open_tutorai/routers/memories.py` | REST CRUD for `opentutorai_memory` |
| `backend/tests/__init__.py` | Package marker for the test suite |
| `backend/tests/test_phase1_memory_kg.py` | 12 unit tests for models + service |

---

## Files Modified

### `backend/open_tutorai/models/database.py`

**Imports added:** `Float`, `UniqueConstraint`

**Models added:**

- **`Memory`** (`opentutorai_memory`) — stores user memories.
  - Fields: `id` (PK), `user_id` (indexed), `memory_type` (episodic/behavioral/procedural/session_summary), `content`, `memory_metadata` (JSON), `created_at`, `updated_at`

- **`KGConcept`** (`opentutorai_kg_concept`) — KG node, one concept per topic.
  - Fields: `id` (PK), `name` (indexed), `topic` (indexed), `difficulty`, `last_seen`, `created_at`
  - Relationships: `relations_from`, `relations_to`, `masteries` (all cascade delete)

- **`KGRelation`** (`opentutorai_kg_relation`) — KG edge between two concepts.
  - Fields: `id` (PK), `source_id` FK→KGConcept (CASCADE), `target_id` FK→KGConcept (CASCADE), `relation`
  - Constraint: `UNIQUE(source_id, target_id, relation)`

- **`KGUserMastery`** (`opentutorai_kg_user_mastery`) — per-user mastery overlay.
  - Fields: `id` (PK), `user_id` (indexed), `concept_id` FK→KGConcept (CASCADE), `mastery` (Float 0→1), `attempts` (Integer), `last_error`, `last_seen`, `created_at`
  - Constraint: `UNIQUE(user_id, concept_id)`

### `backend/open_tutorai/main.py`

- Imported `memories_router` from `open_tutorai.routers.memories`
- Registered it under prefix `/api/v1`

### `requirements.txt`

- Added `networkx>=3.0`

---

## `KnowledgeGraphService` — Public API

| Method | Description |
|--------|-------------|
| `build_graph(user_id, topic, db)` | Returns a `nx.DiGraph` with mastery overlay per node |
| `get_weak_concepts(user_id, topic, db, threshold=0.4)` | Returns concept names where mastery < threshold |
| `find_prerequisites(concept_name, topic, db)` | Returns direct prerequisites via `requires` edges |
| `upsert_concept(db, name, topic, difficulty)` | Create-or-get a KGConcept |
| `add_relation(db, source, target, relation, topic)` | Add an edge, idempotent |
| `update_mastery(db, user_id, concept, topic, delta, last_error)` | Increment mastery (capped at 1.0) |

---

## Memory Router — Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/memories/` | List user memories (optional `memory_type` filter) |
| `POST` | `/api/v1/memories/add` | Create a new memory |
| `POST` | `/api/v1/memories/query` | Text search across memories |
| `PUT` | `/api/v1/memories/{id}` | Update content or metadata |
| `DELETE` | `/api/v1/memories/{id}` | Delete a single memory |

---

## Design Decisions

- `mastery` stored as `Float` (not `String`) — matches the `float 0→1` semantic and avoids explicit casts.
- `user_id` has **no FK** to `user.id` — consistent with the existing OpenTutorAI convention (`Support.user_id`, `SupportFile` patterns).
- `KGRelation` and `KGUserMastery` use `ondelete="CASCADE"` on their FKs so deleting a concept automatically cleans up its edges and mastery rows.
- `UniqueConstraint` on `KGRelation(source_id, target_id, relation)` and `KGUserMastery(user_id, concept_id)` prevents duplicate rows under concurrent requests.

---

## Test Results

```
tests/test_phase1_memory_kg.py::test_models_importable          PASSED
tests/test_phase1_memory_kg.py::test_upsert_concept_creates     PASSED
tests/test_phase1_memory_kg.py::test_upsert_concept_idempotent  PASSED
tests/test_phase1_memory_kg.py::test_add_relation               PASSED
tests/test_phase1_memory_kg.py::test_add_relation_idempotent    PASSED
tests/test_phase1_memory_kg.py::test_update_mastery_creates_row PASSED
tests/test_phase1_memory_kg.py::test_update_mastery_increments  PASSED
tests/test_phase1_memory_kg.py::test_mastery_capped_at_1        PASSED
tests/test_phase1_memory_kg.py::test_get_weak_concepts          PASSED
tests/test_phase1_memory_kg.py::test_build_graph_nodes          PASSED
tests/test_phase1_memory_kg.py::test_find_prerequisites         PASSED
tests/test_phase1_memory_kg.py::test_memory_create              PASSED

12 passed, 1 warning in 1.98s
```

---

## Next Phase

**Phase 2 — Context Retrieval Engine** : wire ChromaDB for RAG document indexing and retrieval, expose `retrieve_pedagogical_documents()` and `retrieve_internal_memory()`.
