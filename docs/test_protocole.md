# Test Protocol — OpenTutorAI

## Chosen approach: Python automation + human validation

The protocol relies on two complementary layers:

- **Python** executes the scenarios, measures the metrics, and generates a structured report.
- **The human** reads the report and confirms pedagogical quality on cases that cannot be reduced to a metric.

---

## General principle

```
Python code                    Human observation
──────────────────────────────────────────────────
Executes the scenario          Reads the generated report
Measures the metrics           Confirms quality
Generates an HTML/JSON report  Rates the responses (1–5)
Flags anomalies                Decides if it is acceptable
```

---

## Breakdown by scenario

| Scenario | Python automates | Human confirms |
|---|---|---|
| S1 — Acquisition | API call, latency measurement, Faithfulness, verifies memory is written | Response Appropriateness (1–5), qualitative Learning Gain |
| S2 — Memory | Reads memory store, verifies 3 fields + Memory Precision + Memory Freshness | Nothing — 100% automatable |
| S3 — Adaptation | Launches 2 calls (beginner vs advanced), compares lexical complexity, Difficulty Calibration | Pedagogical relevance of simplification (1–5) |
| S4 — RAG | Computes Precision@k, Recall@k, MRR, NDCG@k, Faithfulness, Context Relevance, Answer Relevance | Nothing — 100% automatable |
| S5 — Compression | Counts tokens before/after, computes Compression Ratio | Nothing — 100% automatable |
| S6 — Longitudinal | Chains the 4 sessions, verifies memory + Learning Gain (pre/post test) | Pedagogical thread coherence (1–5) |
| S7 — Routing (fallback) | Parses `_route()` logic, verifies deterministic sequence, Task Completion Rate, Fallback Rate | Nothing — 100% automatable |
| S8 — Memory conflict | Verifies `level` update, Memory Conflict Rate, Memory Freshness | Nothing — 100% automatable |
| S9 — Post-compression | Measures Information Retention + Compression Ratio | Post-compression response coherence (1–5) |
| S10 — BKT | Verifies P(mastery) evolution, BKT Calibration, Threshold Detection | Nothing — 100% automatable |
| S11 — LLM Routing | Tests `_llm_route()` (LLM-first path): valid JSON→used, invalid JSON→fallback, confidence logged, agent_reasoning populated | Nothing — 100% automatable |
| S12 — Verifier→Planner loop | Verifies `verification_feedback` propagation, planner retry on `needs_review`, `MAX_PLAN_RETRIES` respected | Nothing — 100% automatable |
| S13 — Multi-provider LLM | Tests `get_llm()` for OpenAI vs Ollama: model detection, `base_url`, `api_key` distinction | Nothing — 100% automatable |

**9 scenarios are 100% automatable. 4 require human confirmation.**

> **Note S7 vs S11**: S7 covers the *deterministic fallback* (`_route()`). S11 covers the *LLM-primary path* (`_llm_route()`). Both are exercised in `test_routing.py`.

---

## Test file structure

```
backend/
└── tests/
    ├── automated/
    │   ├── conftest.py             # DB in-memory + ChromaDB ephemeral fixtures
    │   ├── test_rag.py             # S4  — Recall@k, Faithfulness, latency
    │   ├── test_memory.py          # S2, S8 — memory read/write, conflict
    │   ├── test_compression.py     # S5, S9 — ratio + retention
    │   ├── test_routing.py         # S7 (fallback _route) + S11 (LLM _llm_route)
    │   ├── test_agentic.py         # S12 (Verifier→Planner) + agent_reasoning
    │   ├── test_multi_provider.py  # S13 — OpenAI vs Ollama provider selection
    │   └── test_bkt.py             # S10 — P(mastery) evolution
    ├── test_phase1_memory_kg.py    # Phase 1 integration — Memory + Knowledge Graph
    ├── test_phase2_context_retrieval.py  # Phase 2 — ChromaDB indexing & retrieval
    ├── test_phase3_context_manager.py    # Phase 3 — ContextManager assembly
    ├── test_phase4_summarization.py      # Phase 4 — SummarizationService
    ├── test_phase5_agents.py             # Phase 5 — individual agent nodes
    ├── test_phase6_pipeline.py           # Phase 6 — end-to-end LangGraph pipeline
    └── manual/
        └── evaluation_grid.md      # S1, S3, S6, S9 — human rating grid (1–5)
```

> **Phase tests** (`test_phase*.py`) are integration-level tests for the full pipeline. They are run before each demo and once per sprint. The `automated/` tests are unit/scenario-level and run on every commit (CI).

---

## Generated report format

The Python code produces a report that the human reads in one pass, without re-running the tests:

```
REPORT — OpenTutorAI Test Suite
═══════════════════════════════════════════════════════════════════════
S2  Memory             ✅ PASS   Accuracy=100%
S4  RAG                ✅ PASS   Recall=1.0  Faithfulness=0.91
S5  Compression        ✅ PASS   Retention=82%
S7  Routing (fallback) ✅ PASS   TCR=100%  Latency=1.8s
S8  Memory conflict    ✅ PASS   Accuracy=100%
S10 BKT                ✅ PASS   Calibration=OK  P(mastery)=0.65
S11 LLM Routing        ✅ PASS   LLM used=True  Fallback=OK  Reasoning=OK
S12 Verifier→Planner   ✅ PASS   Feedback propagated  MAX_RETRIES respected
S13 Multi-provider     ✅ PASS   OpenAI=OK  Ollama=OK  base_url=OK

─── Human validation required ──────────────────────────────────────────
S1  Acquisition        ⚠️  REVIEW  LearningGain=0.38  [rate 1–5]
S3  Adaptation         ⚠️  REVIEW  [compare the 2 responses]
S6  Longitudinal       ⚠️  REVIEW  LearningGain=0.42  [rate 1–5]
S9  Post-compression   ⚠️  REVIEW  Retention=82%  [rate 1–5]
═══════════════════════════════════════════════════════════════════════
```

The human intervenes only on the 4 `REVIEW` lines, with the responses already displayed in the report.

---

## Recommended execution frequency

| When | What |
|---|---|
| On every commit (CI) | `automated/` tests only (S2–S13) |
| Before each demo | Full suite: `automated/` + `test_phase*.py` + human validation |
| Once per sprint | Manual grid review (S1, S3, S6, S9) |

---

## Global success criteria

### v1 — 10 essential metrics

| Dimension | Metric | Threshold | Automatable |
|---|---|---|:---:|
| RAG retrieval | `Recall@k` | ≥ 0.80 | ✅ |
| RAG quality | `Faithfulness` | ≥ 0.85 | ✅ |
| Memory | `Memory Retrieval Accuracy` | 100% | ✅ |
| Agentic — routing | `Task Completion Rate` | 100% | ✅ |
| Agentic — LLM routing | `LLM Routing Accuracy` | ≥ 80% (valid agent without fallback) | ✅ |
| Agentic — retry | `verification_feedback` propagated | 100% | ✅ |
| Compression | `Information Retention` | ≥ 80% | ✅ |
| Pedagogy | `Learning Gain` | ≥ 0.30 | ✅ |
| BKT | `BKT Calibration` | Consistent | ✅ |
| System | `End-to-end latency` | < 3s | ✅ |

### v2 — metrics to add once v1 is stable

| Dimension | Metrics |
|---|---|
| RAG | `Precision@k`, `NDCG@k`, `Context Relevance`, `Answer Relevance` |
| Memory | `Memory Precision`, `Memory Freshness`, `Memory Conflict Rate` |
| Agentic | `Agent Efficiency`, `Fallback Rate`, `confidence` score distribution |
| Pedagogy | `Difficulty Calibration`, `Response Appropriateness` (human) |
| Multi-provider | `provider_switch_latency`, behavior parity OpenAI vs Ollama |

### Human metrics (v1)

| Metric | Threshold |
|---|---|
| Average human rating (S1, S3, S6, S9) | ≥ 4 / 5 |

---

## Architecture reference (as of 2026-06)

The LangGraph pipeline exposed in `backend/open_tutorai/agents/langgraph/`:

```
Entry → orchestrator (LLM-first via _llm_route, fallback _route)
            ↓ next_agent
    memory → knowledge → diagnostics → planner → exercise → verifier
                                           ↑______________|  (needs_review retry, ≤ MAX_PLAN_RETRIES)
            ↓
        feedback → orchestrator → END
```

Key state fields tested by each scenario:

| Field | Set by | Tested in |
|---|---|---|
| `agent_trace` | All nodes | S7, S11 |
| `agent_reasoning` | Orchestrator (LLM) | S11 |
| `verification_feedback` | VerifierAgent | S12 |
| `human_feedback` | VerifierAgent interrupt() | S12 |
| `llm_model` | Frontend request | S13 |
| `tool_selection_log` | ExerciseAgent | v2 |
| `weak_concepts` | KnowledgeAgent | S10 |
| `memory_context` | MemoryAgent | S2, S8 |
| `rag_docs` | ContextManager (ChromaDB) | S4 |
