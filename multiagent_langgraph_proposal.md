# New Learning Loop — OpenTutorAI Multi-Agent LangGraph

> Architecture proposal to build a multi-agent system orchestrated by LangGraph, with a Hybrid Memory System (episodic + Knowledge Graph) and a full Context & Summarization pipeline.
>
> **Context :** The upstream codebase has no existing agent system — this is a fresh implementation, not a migration. The foundation is in place: FastAPI, SQLAlchemy, LangChain 0.3.7, ChromaDB 0.6.2, and OpenWebUI auth. What is missing: `langgraph`, `networkx`, the `opentutorai_memory` table, and all agent/router code.

---

## 1. Architecture Diagram

```
┌──────────────────────┐                                                          ┌──────────────────────────┐
│      FRONTEND        │                                                          │   OpenTutorAI Extensions │
│──────────────────────│                                                          │──────────────────────────│
│ • Text-based chat    │                                                          │ • Adaptive Content Gen.  │
│ • Avatar-based chat  │                                                          │ • Avatar Generation      │
│ • Learner Dashboard  │                                                          │ • Learning Knowledge     │
│ • Onboarding Module  │                                                          │ • Learning Analytics     │
└──────────┬───────────┘                                                          └──────────────────────────┘
           │ user_id + Topic                                                                   ▲
           ▼                                                                    session_chat_summary
┌──────────────────────────────────────────────────┐
│                  Gateway API                     │
│  user_profile : { id, name, first_name, role }   │
│  + topic + learning_objectives + language        │
│  + user_message (current learner input)          │
└──────────────────────────┬───────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            CONTEXT RETRIEVAL ENGINE                                                  │
│                                                                                                      │
│  Stable inputs (do not change during the session) ────────────────────────────────────────────────  │
│  ┌──────────────────────────────────┐   ┌───────────────────────┐   ┌──────────────────────────┐    │
│  │  User Profile                    │   │  User Message (query) │   │  ChromaDB                │    │
│  │  id, name, first_name, role      │   │  current learner text │   │  pedagogical_docs        │    │
│  │  topic, learning_objectives      │   │  fallback → topic     │   │  (RAG corpus)            │    │
│  │  language                        │   │                       │   │                          │    │
│  └──────────────┬───────────────────┘   └──────────┬────────────┘   └────────────┬─────────────┘    │
│                 └──────────────────────────────────┴────────────────────────────┘                   │
│                                                    │                                                 │
│  Processing ─────────────────────────────────────────────────────────────────────────────────────── │
│  ┌─────────────────────────────────────────────────▼─────────────────────────────────────────────┐  │
│  │  ContextManager.build_agent_context(user_id, topic, query=user_message or topic)              │  │
│  │  • rag_docs       : vector_similarity(query) ≥ 0.5, top_k = 5  [ChromaDB]                    │  │
│  │  • session_summary: SummarizationService.get_cached_summary(user_id, topic) [TTL 24h]         │  │
│  │  • budget control : trim to max_context_tokens (tiktoken)                                     │  │
│  │                                                                                               │  │
│  │  NB: memories and weak_concepts are NOT loaded here — responsibility of MemoryAgent           │  │
│  │      and KnowledgeAgent inside the graph (data that evolves during the session)               │  │
│  └─────────────────────────────────────────────────┬─────────────────────────────────────────────┘  │
│                                                    │                                                 │
│  Output : AgentContext ──────────────────────────── ▼─────────────────────────────────────────────  │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  { user_name, user_id, topic, language, learning_objectives,                                  │  │
│  │    user_message,                                                                               │  │
│  │    rag_docs: [...],        ← stable, driven by user_message                                   │  │
│  │    session_summary: "...", ← stable, TTL 24h cache                                            │  │
│  │    token_count: int }                                                                          │  │
│  └────────────────────────────────────────────────┬──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┼─────────────────────────────────────────────────┘
                                                     │ AgentContext → injected into TutorGraphState
                                                     ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                        RUNNER CORE                                                   │
│                                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              LangGraph StateGraph (TutorGraphState)                          │   │
│  │                                                                                              │   │
│  │   ┌───────────────────────┐                                                                  │   │
│  │   │     Checkpointer      │  restores / saves TutorGraphState (SQLite)                      │   │
│  │   └──────────┬────────────┘                                                                  │   │
│  │              │                                                                               │   │
│  │   ┌──────────▼───────────────────────────────────────────┐                                  │   │
│  │   │            OrchestratorAgent (LLM)                   │◀──────────────────┐              │   │
│  │   │  reads : feedback, weak_concepts, iteration          │                   │              │   │
│  │   └──┬──────────┬──────────┬───────────────────────────  ┘                   │              │   │
│  │      │          │          │                                                  │              │   │
│  │      ▼          ▼          ▼                                                  │              │   │
│  │  ┌────────┐ ┌─────────┐ ┌──────────┐                                         │              │   │
│  │  │Memory  │ │Know-    │ │Diagnos-  │  ◀── AgentContext (user_message,         │              │   │
│  │  │Agent   │ │ledge    │ │tics Agent│       rag_docs, session_summary)         │              │   │
│  │  │        │ │Agent    │ │          │                                         │              │   │
│  │  │R/W     │ │R+W      │ │R         │◀── retrieve_memory (SQL, always fresh)  │              │   │
│  │  │episodic│ │kg_graph │ │kg_graph  │◀── retrieve_rag (AgentContext.rag_docs) │              │   │
│  │  │        │ │R+W      │ │R mastery │                                         │              │   │
│  │  │        │ │mastery  │ │          │                                         │              │   │
│  │  └────┬───┘ └────┬────┘ └────┬─────┘                                         │              │   │
│  │       │          │           │                                                │              │   │
│  │       └──────────┴─────┬─────┘                                               │              │   │
│  │                        ▼                                                      │              │   │
│  │             ┌───────────────────┐                                             │              │   │
│  │             │   PlannerAgent    │◀── rag_docs (from AgentContext)             │              │   │
│  │             │  R kg_graph       │◀── search_web                              │              │   │
│  │             │  R+W strategy     │                                             │              │   │
│  │             └─────────┬─────────┘                                             │              │   │
│  │                       │                                                       │              │   │
│  │             ┌─────────▼─────────┐                                             │              │   │
│  │             │  ExerciseAgent    │◀── rag_docs (from AgentContext)             │              │   │
│  │             │  R procedural     │◀── live_code_evaluation (coding)           │              │   │
│  │             │  + tools routed   │◀── math_evaluator (math / science)         │              │   │
│  │             │  by (type,subject)│◀── generate_chart (math/science/history)   │              │   │
│  │             │                   │◀── grammar_checker (language)              │              │   │
│  │             │                   │◀── search_web (all — fact-check/enrich)    │              │   │
-│  │             └─────────┬─────────┘                                             │              │   │
│  │                       │                                                       │              │   │
│  │             ┌─────────▼─────────┐                                             │              │   │
│  │             │  VerifierAgent    │◀── rag_docs (from AgentContext)             │              │   │
│  │             │  R rag_docs       │                                             │              │   │
│  │             │  score KO ────────┼──────────────────────────────────────────────┘  re-plans  │   │
│  │             └─────────┬─────────┘                                                           │   │
│  │                       │ score OK                                                            │   │
│  │             ┌─────────▼─────────┐                                             │              │   │
│  │             │  FeedbackAgent    │◀── memories (from MemoryAgent)              │              │   │
│  │             │  W behavioral     │◀── user_name (personalisation)              │              │   │
│  │             │  W kg_graph       │  mastery updated                            │              │   │
│  │             │  W weak_concepts──┼──────────────────────────────────────────────┘  re-diagnose│  │
│  │             └─────────┬─────────┘                                                           │   │
│  │                       │                                                                     │   │
│  │             ┌─────────▼─────────┐                                                           │   │
│  │             │  persist_memory   │──── W episodic / behavioral / procedural                  │   │
│  │             │                   │──── invalidate SummarizationService cache                 │   │
│  │             └─────────┬─────────┘                                                           │   │
│  │                       ↓                                                                     │   │
│  │                      END ──────────────────────────────── Final Answer ──────────────────────────│
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                      │
│  ┌────────────────────────────────────┐                                                             │
│  │   LLM Provider & Local Runtime     │                                                             │
│  │   OpenAI (gpt-4o-mini, ...)        │                                                             │
│  │   Ollama (local models)            │                                                             │
│  └────────────────────────────────────┘                                                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
           │                                              │
           ▼                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                     CONTEXT & MEMORY  (isolated by user_id + topic)                                  │
│                                                                                                      │
│  ChromaDB                          Knowledge Graph (SQL)      opentutorai_memory (SQL)               │
│  ┌──────────────────────┐          ┌────────────────────┐     ┌──────────────────────┐               │
│  │ pedagogical_docs     │          │ kg_concept         │     │ Episodic             │               │
│  │ (RAG collection)     │          │ kg_relation        │     │ Behavioral           │               │
│  └──────────────────────┘          │ kg_user_mastery    │     │ Procedural           │               │
│           ▲                        └────────────────────┘     │ session_summary      │               │
│           │                                 ▲                 └──────────────────────┘               │
│           │                                 │                          ▲                             │
│           └─────────────────────────────────┴──────────────────────────┘                            │
│  Context Retrieval Engine reads : ChromaDB + session_summary cache  (pre-graph)                     │
│  MemoryAgent    reads/writes    : opentutorai_memory                 (inside graph)                  │
│  KnowledgeAgent reads/writes    : kg_concept, kg_relation, kg_user_mastery (inside graph)           │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌────────────────────┐    ┌──────────────────────────────┐    ┌─────────────────────────────────┐
│  Caching           │───▶│  Logs                        │───▶│  Monitoring                     │
│  model_metadata    │    │  Request logs / Error track  │    │  Latency / Usage / Health checks │
│  auxiliary_client  │    └──────────────────────────────┘    └─────────────────────────────────┘
└────────────────────┘

  R = read     W = write
  kg_graph = Knowledge Graph (concepts + relations)
  mastery  = kg_user_mastery (mastery level per concept per user)

  Context Retrieval Engine (pre-graph service, called by the router before graph.ainvoke)
    inputs  :  user_profile (id, name, first_name, role, language, learning_objectives)
               user_message (semantic query → fallback: topic)
               ChromaDB     (pedagogical_docs, top_k=5, vector_similarity ≥ 0.5)
               session_summary cache (SummarizationService, TTL 24h)
    output  :  AgentContext → { user_name, user_id, topic, language,
                                learning_objectives, user_message,
                                rag_docs, session_summary, token_count }

  NB: memories (episodic/behavioral/procedural) and weak_concepts are loaded
      by MemoryAgent and KnowledgeAgent INSIDE the graph — they are mutable during the session.

  Learning loops:
  VerifierAgent  score KO  → Orchestrator → PlannerAgent      (re-plans)
  FeedbackAgent  gaps      → Orchestrator → DiagnosticsAgent  (re-diagnoses)
```

---

## 2. Knowledge Graph — replaces semantic memory

```
Nodes (Concepts)                    Edges (Relations)
─────────────────                   ──────────────────
id, name, topic                     requires →
difficulty                          extends →
last_seen                           related_to ↔
                                    part_of →

User overlay (per user_id)
──────────────────────────
mastery: float 0→1
attempts: int
last_error: str
last_seen: datetime
```

**Example for topic = "algorithms":**
```
[bubble_sort] ──requires──▶ [comparison]
[quick_sort]  ──extends───▶ [bubble_sort]
[recursion]   ──related───▶ [call_stack]
     ▲
     └── user mastery: 0.3 (gap detected)
```

Gaps in the graph directly drive the `PlannerAgent`.

---

## 3. The 8 agents and their tools

| Agent | Role | Tools |
|-------|------|-------|
| **OrchestratorAgent** | Routes to the right agent based on state + feedback | — |
| **MemoryAgent** | Retrieves and persists episodic/behavioral/procedural memory | `retrieve_memory`, `persist_memory` |
| **KnowledgeAgent** | Reads/updates the knowledge graph | `get_concept_graph`, `update_mastery`, `find_prerequisites` |
| **DiagnosticsAgent** | Assesses level, detects gaps via the graph | `retrieve_rag`, `assess_level_from_graph` |
| **PlannerAgent** | Targeted strategy on weak graph nodes | `retrieve_rag`, `search_web` |
| **ExerciseAgent** | Generates exercises on gap concepts; resolves subject via 3-source cascade, routes to the right tool by `(type, subject)` | `live_code_evaluation` (coding), `math_evaluator` (math/science), `generate_chart` (chart/timeline), `grammar_checker` (language), `search_web` (fact-check/enrich) |
| **VerifierAgent** | Verifies RAG consistency of generated content | `retrieve_rag` |
| **FeedbackAgent** | Interprets feedback, updates the graph | `update_mastery`, `persist_memory` |

---

## 4. LangGraph Pipeline

The `TutorGraphState` (shared TypedDict) carries the state across all agents: `user_id`, `topic`, `current_level`, `language`, `user_message`, `memory_context`, `session_summary`, `knowledge_graph`, `weak_concepts`, `pedagogical_context`, `adjusted_level`, `difficulties`, `strategy`, `exercises`, `verification`, `next_agent`, `iteration`, `agent_trace`.

The `StateGraph` registers 8 nodes (orchestrator, memory, knowledge, diagnostics, planner, exercise, verifier, feedback). The orchestrator routes dynamically via `next_agent`. All agents return to the orchestrator after execution. The entry point is the orchestrator. A `SqliteSaver` checkpoints the state per `(user_id, topic)`.

---

## 5. Implementation Plan

> The system is built in 6 phases. Each phase is independently testable and does not block the others from being started in parallel if resources allow.
> Dependency order: Phases 1 and 2 must complete before Phase 5. Phases 3 and 4 feed into Phase 5 at runtime but can be developed in parallel.

```
Phase 1 ──► Phase 5
Phase 2 ──► Phase 5
Phase 3 ──► Phase 5 (runtime dependency)
Phase 4 ──► Phase 5 (runtime dependency)
Phase 5 ──► Phase 6
```

---

### Phase 1 — Hybrid Memory System (KG included)

**Goal :** Build the full memory persistence layer — the foundation every agent reads from and writes to.

**SQL tables** in `backend/open_tutorai/models/database.py` :
- `opentutorai_memory` — episodic, behavioral, procedural memories per `(user_id, topic)` — fields: `id` String PK, `user_id` String (indexed), `memory_type` String, `content` Text, `memory_metadata` JSONField, `created_at` DateTime, `updated_at` DateTime
- `opentutorai_kg_concept` — KG nodes: `id`, `name`, `topic`, `difficulty`, `last_seen`, `created_at`
- `opentutorai_kg_relation` — KG edges: `id`, `source_id` FK→concept (CASCADE), `target_id` FK→concept (CASCADE), `relation` (requires/extends/related_to/part_of) — unique on `(source_id, target_id, relation)`
- `opentutorai_kg_user_mastery` — user overlay: `id`, `user_id`, `concept_id` FK→concept (CASCADE), `mastery` Float 0→1, `attempts` Integer, `last_error` Text, `last_seen` DateTime — unique on `(user_id, concept_id)`

**New dependency :** `networkx>=3.0` in `requirements.txt`

**Service** `backend/open_tutorai/services/knowledge_graph.py` :
- `KnowledgeGraphService.build_graph(user_id, topic, db)` → `nx.DiGraph`
- `KnowledgeGraphService.get_weak_concepts(user_id, topic, db, threshold=0.4)` → `list[str]`
- `KnowledgeGraphService.upsert_concept(db, name, topic, difficulty)` → `KGConcept`
- `KnowledgeGraphService.add_relation(db, source, target, relation, topic)` → `KGRelation`
- `KnowledgeGraphService.update_mastery(db, user_id, concept, topic, delta, last_error)` → `KGUserMastery`
- `KnowledgeGraphService.find_prerequisites(concept, topic, db)` → `list[str]`

**Router** `backend/open_tutorai/routers/memories.py` :
- `GET  /api/v1/memories/` — list user memories (optional filter by `memory_type`)
- `POST /api/v1/memories/add` — create memory
- `POST /api/v1/memories/query` — search by text
- `PUT  /api/v1/memories/{id}` — update
- `DELETE /api/v1/memories/{id}` — delete (fixes broken frontend calls)

**Validation :**
- All 4 tables created on app startup via `init_database()`
- `GET /api/v1/memories/` returns `[]` for a new user (no 404)
- `KnowledgeGraphService.get_weak_concepts()` returns concept names correctly

---

### Phase 2 — Context Retrieval Engine

**Goal :** Set up ChromaDB and expose a unified retrieval service for pedagogical documents (RAG) used by DiagnosticsAgent, PlannerAgent, ExerciseAgent, and VerifierAgent.

**Dependencies :** `sentence-transformers==3.3.1` already present, `chromadb==0.6.2` already present.

**Service** `backend/open_tutorai/services/context_retrieval.py` :
- `get_chroma_client()` → persistent ChromaDB client at `data/vector_db/`
- `get_or_create_collection(name="pedagogical_documents")` → Chroma collection
- `index_document(file_path, metadata, user_id)` — chunk + embed + upsert into ChromaDB
- `retrieve_pedagogical_documents(user_id, query, top_k=5)` → `list[dict]` with `content`, `metadata`, `vector_score`
- `retrieve_internal_memory(user_id, query, memory_types, limit, db)` → `list[dict]` from `opentutorai_memory`

**Router** `backend/open_tutorai/routers/context_retrieval.py` :
- `POST /api/v1/context/index` — index an uploaded document into ChromaDB
- `POST /api/v1/context/retrieve` — semantic search over pedagogical corpus
- `GET  /api/v1/context/collections` — list indexed documents

**Validation :**
- Index a PDF → retrieve top-3 chunks by query → scores > 0.5
- `retrieve_internal_memory()` returns correctly typed dicts from SQL

---

### Phase 3 — Dynamic Context Manager

**Goal :** Control what context is injected into each agent call — filter by relevance, recency, topic, and context window budget. Prevents irrelevant memories and oversized prompts.

**Service** `backend/open_tutorai/services/context_manager.py` :
- `ContextManager.build_agent_context(user_id, topic, query, db)` → `AgentContext`
  - Calls `retrieve_internal_memory()` → filters by `min_relevance`, `max_age_days`, topic
  - Calls `retrieve_pedagogical_documents()` → filters by `min_vector_score`
  - Merges and ranks by combined relevance + recency score
  - Trims to `max_context_tokens` budget (via `tiktoken`)
- `AgentContext` dataclass: `memories: list`, `rag_docs: list`, `summary: str`, `token_count: int`

**Config** in `CONTEXT_RETRIEVAL_CONFIG` — key `filtering`: `relevance_threshold=0.4`, `recency_threshold=0.3`, `max_age_days=14`, `max_context_tokens=3000`.

**Validation :**
- `build_agent_context()` never exceeds `max_context_tokens`
- Memories outside the topic scope are excluded
- Returns empty context gracefully when no data exists

---

### Phase 4 — Summarization Layer

**Goal :** Generate and cache session summaries to feed `MemoryAgent` and `FeedbackAgent` without replaying full interaction history on each call.

**Service** `backend/open_tutorai/services/summarization.py` :
- `SummarizationService.summarize_session(user_id, topic, exchanges, llm)` → `str`
  - Sliding window: summarizes last N exchanges (configurable `sliding_window_size=10`)
  - Calls LLM with a dedicated summarization prompt
- `SummarizationService.get_cached_summary(user_id, topic)` → `str | None`
  - Cache stored in `opentutorai_memory` with `memory_type="session_summary"`
  - TTL = `cache_ttl_hours` (default 24h)
- `SummarizationService.invalidate_cache(user_id, topic)` — clears stale summary on session end

**Config** in `CONTEXT_RETRIEVAL_CONFIG` — key `summaries`: `enabled=True`, `cache_ttl_hours=24`, `exchanges_per_summary=5`; key `summarization`: `enabled=True`, `sliding_window_size=10`, `forget_irrelevant=True`.

**Validation :**
- Summary generated from 10 exchanges is < 300 tokens
- Cached summary returned on second call (no LLM invocation)
- Cache invalidated after TTL expires

---

### Phase 5 — Adaptive Tutor Engine

**Goal :** Implement the 8 LangGraph agents and wire the `StateGraph`. This phase depends on Phases 1–4 being available at runtime.

**New dependencies :** `langgraph>=0.2.0`, `langgraph-checkpoint-sqlite>=0.1.0`

**File structure to create :**
```
backend/open_tutorai/agents/
├── langgraph/
│   ├── __init__.py
│   ├── state.py          ← TutorGraphState TypedDict (+ tool_results field)
│   ├── graph.py          ← StateGraph compiled + SqliteSaver checkpointer
│   ├── orchestrator.py   ← OrchestratorAgent (deterministic fast-path + optional LLM)
│   └── agents/
│       ├── memory.py       ← MemoryAgent      : calls ContextManager + SummarizationService
│       ├── knowledge.py    ← KnowledgeAgent   : calls KnowledgeGraphService
│       ├── diagnostics.py  ← DiagnosticsAgent : assess_level + detect_gaps from KG
│       ├── planner.py      ← PlannerAgent     : strategy on weak_concepts + RAG
│       ├── exercise.py     ← ExerciseAgent    : generate exercises + route to tool by (type,subject)
│       ├── verifier.py     ← VerifierAgent    : RAG consistency check → re-plan if KO
│       └── feedback.py     ← FeedbackAgent    : update KG mastery + persist memories

backend/open_tutorai/tools/            ← Exercise Tools package (Phase 5 addition)
├── __init__.py
├── live_code_evaluation.py  ← coding exercises    — subprocess Python sandbox (timeout 5s)
├── math_evaluator.py        ← math/science        — sympy symbolic eval + numeric fallback
├── generate_chart.py        ← chart/timeline      — matplotlib PNG→base64 (line/bar/scatter/function/timeline)
├── search_web.py            ← all subjects        — DuckDuckGo snippets for fact-check/enrich
└── grammar_checker.py       ← language exercises  — OpenAI LLM, returns errors+corrected_text+explanation
```

**Exercise tool routing (in `_run_tool_for_exercise()`) :**

| Exercise `type` | `subject` | Tool called | Trigger condition |
|---|---|---|---|
| `coding` | `cs` / any | `live_code_evaluation` | `starter_code` present |
| `math` | `math` / `science` | `math_evaluator` | `expression` or `answer` present |
| `chart` | any | `generate_chart` | `chart_type` + `chart_payload` present |
| `dictation`, `writing` | `language` | `grammar_checker` | `sample_text` or `answer` present |
| `mcq`, `explain` | any | `search_web` | `search_query` present |

See [docs/exercises_tools.md](../../docs/exercises_tools.md) for full field schemas and payload examples.

**`TutorGraphState`** extends the TypedDict in §4 with context fields from Phases 1–4: `memory_context` (MemoryAgent), `session_summary` (SummarizationLayer), `knowledge_graph` (KnowledgeAgent), `pedagogical_context` (RAG), `web_search_results`, `user_message`, `user_name`, plus output fields (`adjusted_level`, `weak_concepts`, `difficulties`, `strategy`, `exercises`, `tool_results`, `verification`) and control fields (`next_agent`, `iteration`, `agent_trace`).

Two subject fields drive tool activation:
- `subject` (Gateway input) — declared by the user or the frontend at session start
- `detected_subject` (DiagnosticsAgent output) — inferred from `topic` + `weak_concepts` via `detect_subject()`

ExerciseAgent resolves the active subject via a **3-source cascade**: `subject` → `detected_subject` → local `detect_subject()` heuristic. When a subject is resolved, `generate_typed_exercises()` is called instead of the generic `generate_exercises()`, producing exercises with tool-trigger fields (`starter_code`, `expression`, `chart_payload`, `sample_text`, `search_query`). `tool_results` accumulates one entry per exercise that triggered a tool call.

**Orchestrator routing logic (deterministic fast-path, LLM only for ambiguous cases) :**
```
no memory_context      → memory
no knowledge_graph     → knowledge
no difficulties        → diagnostics
no strategy            → planner
no exercises           → exercise
no verification        → verifier
verdict=needs_review   → planner      (re-plan loop)
weak_concepts remain   → feedback
else                   → END
MAX_ITERATIONS guard   → END
```

**Validation :**
- `tutor_graph.ainvoke(initial_state)` reaches `END` with `next_agent="END"`
- `agent_trace` contains all 7 agents in expected order
- `verification.verdict` is `"supported"` or `"disabled"` (never missing)
- `feedback_node` updates `kg_user_mastery` and creates memories in SQL

---

### Phase 6 — Global Pipeline Integration

**Goal :** Expose the engine via FastAPI, connect to the existing OpenWebUI auth, and wire the frontend.

**Router** `backend/open_tutorai/routers/adaptive_tutor.py` — 3 endpoints :

- `POST /api/v1/adaptive/plan` — receives `AdaptiveTutorRequest` (`topic`, `current_level`, `user_message`, `recent_interactions`, `feedback_comments`, `learning_objectives`, `preferred_language`), calls `graph.ainvoke()` with `thread_id = user_id:topic`, returns `AdaptiveTutorResponse` (`adjusted_level`, `detected_difficulties`, `suggested_exercises`, `strategy`, `verification`, `agent_trace`).
- `GET /api/v1/adaptive/knowledge-graph/{topic}` — returns nodes, edges and `weak_concepts` from the KG for the current user.
- `POST /api/v1/adaptive/plan/stream` *(optional)* — SSE: emits `{agent, status: start|done}` for each graph node, ends with `[DONE]`.

**`main.py`** — include the 3 new routers: `memories_router`, `context_router`, `adaptive_tutor_router` under the `/api/v1` prefix.

**Frontend wiring :**
- `src/lib/apis/memories/index.ts` — already declared, now has a working backend
- Add `src/lib/apis/adaptive/index.ts` — calls `POST /api/v1/adaptive/plan`
- Add `src/lib/apis/adaptive/knowledge-graph.ts` — calls `GET /api/v1/adaptive/knowledge-graph/{topic}`

**Validation :**
- `POST /api/v1/adaptive/plan` returns `AdaptiveTutorResponse` with `suggested_exercises` non-empty
- `GET /api/v1/adaptive/knowledge-graph/{topic}` returns nodes after a session
- `GET /api/v1/memories/` returns persisted memories after a session
- Frontend memory panel no longer returns 404

---

## 6. Dependency Graph Between Phases

```
Phase 1 (Hybrid Memory + KG)
    │
    ├──────────────────────► Phase 5 (MemoryAgent reads opentutorai_memory)
    │                        Phase 5 (KnowledgeAgent reads kg_* tables)
    │                        Phase 5 (FeedbackAgent writes kg_user_mastery)
    │
Phase 2 (Context Retrieval Engine)
    │
    ├──────────────────────► Phase 3 (ContextManager calls retrieve_*)
    │                        Phase 5 (DiagnosticsAgent, PlannerAgent, VerifierAgent call retrieve_rag)
    │
Phase 3 (Dynamic Context Manager)
    │
    └──────────────────────► Phase 5 (MemoryAgent calls ContextManager.build_agent_context)
    │
Phase 4 (Summarization Layer)
    │
    └──────────────────────► Phase 5 (MemoryAgent calls SummarizationService.get_cached_summary)
    │
Phase 5 (Adaptive Tutor Engine)
    │
    └──────────────────────► Phase 6 (graph.ainvoke called by router)
```

---

## 7. Summary of Gains

| | Upstream baseline | Target (LangGraph) |
|---|---|---|
| Agent system | None | 8 specialized agents, explicit transitions |
| Memory | No `opentutorai_memory` table | Episodic + Behavioral + Procedural in SQL |
| Semantic knowledge | None | Knowledge Graph with mastery overlay |
| Context injection | None | Dynamic Context Manager + Summarization |
| RAG | ChromaDB present, not wired | Context Retrieval Engine + VerifierAgent |
| Routing | None | OrchestratorAgent (deterministic + optional LLM) |
| Feedback adaptability | None | FeedbackAgent → KG mastery update → re-diagnose |
| Targeted gaps | None | Weak nodes in KG (`mastery < 0.4`) drive PlannerAgent |
| Session continuity | None | SqliteSaver checkpointer per `(user_id, topic)` |
| Frontend memory panel | 404 (no backend) | Working via `/api/v1/memories/` router |
