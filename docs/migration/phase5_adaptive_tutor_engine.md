# Phase 5 — Adaptive Tutor Engine

## Goal

Wire eight LangGraph agent nodes into a compiled `StateGraph` that drives a full adaptive tutoring session end-to-end, without any LLM dependency (pure-computation fast path) and with an optional LLM override in the orchestrator.

## Architecture

```
                         ┌─────────────────┐
                         │  OrchestratorAgent│ ←── entry point
                         └────────┬────────┘
          deterministic _route()  │  (optional LLM override)
                                  │
     ┌──────────┬─────────┬───────┴───────┬──────────┬─────────┬──────────┐
     ▼          ▼         ▼               ▼          ▼         ▼          ▼
  memory   knowledge  diagnostics      planner   exercise  verifier   feedback
     │          │         │               │          │         │          │
     └──────────┴─────────┴───────────────┴──────────┴─────────┴──────────┘
                                    back to orchestrator
```

- **Entry point**: `orchestrator` (always first).
- **All agents** return unconditionally to `orchestrator`.
- **Orchestrator** reads `next_agent` from state and routes via `add_conditional_edges`.
- **End condition**: `next_agent == "END"` or `iteration >= MAX_ITERATIONS (3)`.

## Files created

| File | Purpose |
|------|---------|
| `backend/open_tutorai/agents/__init__.py` | Package marker |
| `backend/open_tutorai/agents/helpers.py` | Pure helper functions (no I/O) |
| `backend/open_tutorai/agents/langgraph/__init__.py` | Package marker |
| `backend/open_tutorai/agents/langgraph/state.py` | `TutorGraphState` TypedDict |
| `backend/open_tutorai/agents/langgraph/orchestrator.py` | `orchestrator_node` + `_route` |
| `backend/open_tutorai/agents/langgraph/graph.py` | `build_graph()` + `tutor_graph` singleton |
| `backend/open_tutorai/agents/langgraph/agents/memory.py` | `memory_node` |
| `backend/open_tutorai/agents/langgraph/agents/knowledge.py` | `knowledge_node` |
| `backend/open_tutorai/agents/langgraph/agents/diagnostics.py` | `diagnostics_node` |
| `backend/open_tutorai/agents/langgraph/agents/planner.py` | `planner_node` |
| `backend/open_tutorai/agents/langgraph/agents/exercise.py` | `exercise_node` |
| `backend/open_tutorai/agents/langgraph/agents/verifier.py` | `verifier_node` |
| `backend/open_tutorai/agents/langgraph/agents/feedback.py` | `feedback_node` |
| `backend/tests/test_phase5_agents.py` | 29 unit tests (all passing) |

## TutorGraphState key fields

| Field | Set by | Description |
|-------|--------|-------------|
| `user_id`, `topic`, `current_level` | Gateway (input) | Session identity |
| `rag_docs`, `session_summary` | Pre-loaded (ContextManager/Phase 3-4) | Injected before graph starts |
| `memory_context` | `memory_node` | Episodic/behavioral/procedural memories |
| `knowledge_graph`, `weak_concepts` | `knowledge_node` | KG summary + mastery < 0.4 |
| `adjusted_level`, `difficulties` | `diagnostics_node` | Level after scoring + gap list |
| `strategy`, `strategy_decisions` | `planner_node` | Prioritised action plan |
| `exercises` | `exercise_node` | Structured exercise list |
| `verification` | `verifier_node` | `{verdict, support_score, …}` |
| `next_agent`, `iteration`, `agent_trace` | Orchestrator / all nodes | Control flow |

## Agent responsibilities

### OrchestratorAgent (`orchestrator.py`)
- Deterministic `_route()`: gates on which state fields are populated, sends to the first missing step.
- Optional `_llm_route()` invoked when `CONTEXT_RETRIEVAL_CONFIG["langchain"]["orchestrator_use_llm"] == True`.
- Guards against infinite loops with `MAX_ITERATIONS = 3`.

### MemoryAgent (`memory.py`)
- Calls `retrieve_internal_memory` + `ContextManager.filter_memories`.
- Falls back to `memory_context = []` on any exception (graceful degradation).

### KnowledgeAgent (`knowledge.py`)
- Calls `KnowledgeGraphService.get_weak_concepts` + `build_graph`.
- Produces `knowledge_graph` dict with `{nodes, edges, weak_concepts, node_count, edge_count}`.

### DiagnosticsAgent (`diagnostics.py`)
- Calls `assess_current_level`, `detect_difficulties`, `extract_memory_signals` from `helpers.py`.
- Enriches `difficulties` with KG weak-concept hints.
- Produces `adjusted_level`, `difficulties`.

### PlannerAgent (`planner.py`)
- Calls `plan_learning_strategy` from `helpers.py`.
- Re-focuses on `unsupported_items` when verifier verdict is `needs_review`.
- Produces `strategy`, `strategy_decisions`.

### ExerciseAgent (`exercise.py`)
- Calls `generate_exercises` from `helpers.py`.
- Prioritises exercises on `weak_concepts` before generic `learning_objectives`.
- Produces `exercises` (list of `{id, difficulty, question, hint, answer, skill_target}`).

### VerifierAgent (`verifier.py`)
- Checks that exercises and strategy are textually supported by `rag_docs` using `is_text_supported`.
- Verdicts: `supported`, `needs_review`, `no_sources`, `disabled`.
- Threshold from `CONTEXT_RETRIEVAL_CONFIG["rag"]["verification_threshold"]` (default 0.65).

### FeedbackAgent (`feedback.py`)
- Updates KG mastery (`+0.05` delta) for each weak concept exercised.
- Persists a `procedural` memory summarising the session.
- Gracefully skips persistence on DB errors.

## helpers.py — pure computation

| Function | Description |
|----------|-------------|
| `assess_current_level(level, interactions, feedback)` | Upgrades/downgrades learner level based on scores and keywords |
| `detect_difficulties(topic, interactions, feedback, objectives)` | Returns up to 5 difficulty signals |
| `extract_memory_signals(topic, memories)` | Extracts negative signals from past memories |
| `generate_exercises(topic, level, objectives, count)` | Returns `count` structured exercises (cycles objectives if fewer than count) |
| `plan_learning_strategy(topic, level, difficulties, feedback, memory)` | Returns prioritised strategy decisions |
| `is_text_supported(text, corpus, threshold)` | Term-overlap check for RAG verification |

## Graph persistence

`build_graph(use_checkpointer=True)` wires a `SqliteSaver` at `data/langgraph_checkpoints.sqlite` (configurable via `LANGGRAPH_CHECKPOINT_DB` env var). Tests use `use_checkpointer=False`.

## Test results

```
29 passed, 0 failed
```

All tests are purely in-memory (no DB, no LLM, no ChromaDB).

## Phase 6 integration

`tutor_graph` singleton is imported by Phase 6's `/adaptive/plan` router, which:
1. Pre-loads `rag_docs` and `session_summary` via `ContextManager`.
2. Builds the initial `TutorGraphState`.
3. Calls `tutor_graph.invoke(state, config={"configurable": {"thread_id": session_id}})`.
4. Returns the final `exercises`, `strategy`, and `agent_trace` to the frontend.
