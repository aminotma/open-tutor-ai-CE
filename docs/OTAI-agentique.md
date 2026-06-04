# OTAI — Fully Agentic System Architecture

## Overview

The system is built on an 8-node LangGraph graph with LLM orchestration.
It is **fully agentic**: every agent makes its decisions via LLM with a deterministic fallback,
the orchestrator uses the LLM as the primary decision-maker, and 3 Human-in-the-Loop checkpoints
allow the learner to intervene at each critical step.

This document describes the 14 agentisation steps, organised in 4 phases — all implemented.

---

## Architecture Diagram (current state — fully agentic)

> **Legend:**  `★` agentic (LLM)  ·  `⬡` deterministic fallback  ·  `══►` main flow  ·  `──►` data  ·  `◄══` retry loop  ·  `⚡` Human-in-the-Loop

```
                     ┌──────────────────────────────┐
                     │          FRONTEND             │
                     │  · Text-based chat            │
                     │  · Learner Dashboard          │
                     └──────────────┬────────────────┘
                                    │
                          user_id + topic + message
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │         Gateway API           │
                     │  profile · objectives         │
                     │  language · user_message      │
                     └──────────────┬────────────────┘
                                    │
                                    ▼
╔═══════════════════════════════════════════════════════════════════╗
║             CONTEXT RETRIEVAL ENGINE  (unchanged)                ║
║                                                                   ║
║  · rag_docs        vector_similarity >= 0.5, top_k=5 [ChromaDB] ║
║  · session_summary SummarizationService [TTL 24h]                ║
║  · budget control  trim to max_context_tokens (tiktoken)          ║
║                                                                   ║
║  Output ══► AgentContext { rag_docs, session_summary }            ║
╚═══════════════════════════════════╤═══════════════════════════════╝
                                    │
                     AgentContext injected into TutorGraphState
                                    │
                                    ▼
╔═══════════════════════════════════════════════════════════════════════════════════╗
║                   RUNNER CORE  (LangGraph StateGraph)                            ║
║  SqliteSaver checkpointer — persists full state per user_id + topic              ║
║                                                                                   ║
║  ┌─────────────────────────────────────────────────────────────────────────────┐ ║
║  │  ★  ORCHESTRATOR  —  LLM PRIMARY  ·  ⬡ _route() fallback                   │ ║
║  │                                                                             │ ║
║  │  input  :  topic · level · weak_concepts · agent_trace · n_retries         │ ║
║  │            verification · memory_summary · human_feedback                  │ ║
║  │  output :  { next_agent · reasoning · confidence }  (JSON)                 │ ║
║  │  stop   :  qualitative LLM judgment  (hard ceiling = 15 iterations)        │ ║
║  │  trace  :  every decision tagged  [LLM]  or  [fallback]                    │ ║
║  └──────┬──────────────────┬────────────────────────────┬───────────────────┘  ║
║         │                  │                             │               ▲      ║
║    ══►  ▼             ══►  ▼                        ══►  ▼               ║      ║
║  ┌────────────┐  ┌──────────────┐  ┌────────────────────────────────────┐║      ║
║  │ ★ MEMORY   │  │  KNOWLEDGE   │  │  ★  DIAGNOSTICS AGENT              │║      ║
║  │   AGENT    │  │    AGENT     │  │                                    │║      ║
║  │            │  │              │  │  ★ LLM assesses level + gaps       │║      ║
║  │ · LLM      │  │ Deterministic│  │    from full learner profile:      │║      ║
║  │   selects  │  │ R/W KG       │  │    interactions · feedback         │║      ║
║  │   4-6 most │  │ (no LLM)     │  │    memory · KG · RAG              │║      ║
║  │   relevant │  │              │  │                                    │║      ║
║  │   memories │  │              │  │  output: { adjusted_level          │║      ║
║  │            │  │              │  │           difficulties             │║      ║
║  │  ⬡ top-6   │  │              │  │           reasoning }             │║      ║
║  └──────┬─────┘  └──────┬───────┘  │                                    │║      ║
║         │               │          │  ⬡ assess_current_level()          │║      ║
║         └───────┬────────┘          │    + detect_difficulties()        │║      ║
║                 │                   │  ★ LLM self-critique               │║      ║
║       memory + KG loaded            │                                    │║      ║
║                 └─────────────────► │  ⚡ P1 — Human-in-the-Loop        │║      ║
║                                     │  "Level=X, weak concepts=Y         │║      ║
║                                     │   Continue?" ══► human_feedback   │║      ║
║                                     └──────────────────┬────────────────┘║      ║
║                                                        │                  ║      ║
║                                    adjusted_level + difficulties          ║      ║
║                                                        │                  ║      ║
║                                                   ══►  ▼                  ║      ║
║                                     ┌──────────────────────────────────┐  ║      ║
║                                     │  ★  PLANNER AGENT                │  ║      ║
║                                     │                                  │  ║      ║
║                                     │  ★ LLM generates 3-5 steps from: │  ║      ║
║                                     │    difficulties · weak_concepts  │  ║      ║
║                                     │    RAG · memory · objectives     │  ║      ║
║                                     │                                  │  ║      ║
║                                     │  output: { decisions [           │  ║      ║
║                                     │    { id · action · rationale     │  ║      ║
║                                     │      · priority } ]              │  ║      ║
║                                     │    reasoning }                   │  ║      ║
║                                     │                                  │  ║      ║
║                                     │  ⬡ plan_learning_strategy()      │◄═╗║      ║
║                                     │  ★ search_web if RAG < 2 docs    │  ║║      ║
║                                     │  ★ reads verification_feedback   │  ║║      ║
║                                     │    on retry                      │  ║║      ║
║                                     │  ★ LLM self-critique             │  ║║      ║
║                                     └──────────────────┬───────────────┘  ║║      ║
║                                                        │                   ║║      ║
║                                                   ══►  ▼                   ║║      ║
║                                     ┌──────────────────────────────────┐   ║║      ║
║                                     │  ★  EXERCISE AGENT  (ReAct)      │   ║║      ║
║                                     │                                  │   ║║      ║
║                                     │  create_react_agent()            │   ║║      ║
║                                     │  Thought ══► Action ══► Obs      │   ║║      ║
║                                     │                                  │   ║║      ║
║                                     │  Tools:                          │   ║║      ║
║                                     │  ├─ live_code_evaluation (Python)│   ║║      ║
║                                     │  ├─ sql_evaluator  (SQL/SQLite)  │   ║║      ║
║                                     │  ├─ math_evaluator (sympy)       │   ║║      ║
║                                     │  ├─ generate_chart (plot)        │   ║║      ║
║                                     │  ├─ grammar_checker (language)   │   ║║      ║
║                                     │  └─ search_web (fact-check)      │   ║║      ║
║                                     │                                  │   ║║      ║
║                                     │  ⬡ deterministic type/subject    │   ║║      ║
║                                     │  ★ LLM self-critique             │   ║║      ║
║                                     └──────────────────┬───────────────┘   ║║      ║
║                                                        │                    ║║      ║
║                                                   ══►  ▼                    ║║      ║
║                                     ┌──────────────────────────────────┐    ║║      ║
║                                     │  ★  VERIFIER AGENT               │    ║║      ║
║                                     │                                  │    ║║      ║
║                                     │  ★ Structured LLM judgment       │    ║║      ║
║                                     │  output: { verdict · score       │    ║║      ║
║                                     │    · specific_feedback           │    ║║      ║
║                                     │    · unsupported_items }         │    ║║      ║
║                                     │                                  │    ║║      ║
║                                     │  ⬡ text overlap fallback         │    ║║      ║
║                                     │                                  │    ║║      ║
║                                     │  score KO ══► verification_      ├════╝║      ║
║                                     │  feedback ══► retry Planner      │  (loop)    ║
║                                     │                                  │            ║
║                                     │  ⚡ P2 — Human-in-the-Loop       │            ║
║                                     │  "Unverified items: [list]       │            ║
║                                     │   Continue?" ══► human_feedback  │            ║
║                                     └──────────────────┬───────────────┘            ║
║                                           score OK     │                             ║
║                                                   ══►  ▼                             ║
║                                     ┌──────────────────────────────────┐             ║
║                                     │  ★  FEEDBACK AGENT               │             ║
║                                     │                                  │             ║
║                                     │  ★ LLM decides what to memorise  │             ║
║                                     │    2-4 typed entries:            │             ║
║                                     │    behavioral · episodic         │             ║
║                                     │    procedural · semantic         │             ║
║                                     │    importance filter (high/med)  │             ║
║                                     │                                  │             ║
║                                     │  ⬡ hardcoded templates           │             ║
║                                     │  ★ LLM self-critique             │             ║
║                                     │  W kg_graph (mastery +0.05/gap)  │             ║
║                                     │                                  │             ║
║                                     │  ⚡ P3 — Human-in-the-Loop       │             ║
║                                     │  "Summary: [recap]               │             ║
║                                     │   Save to memory?" ══► feedback  │             ║
║                                     └──────────────────┬───────────────┘             ║
║                                                        │                              ║
║                                                   ══►  ▼                              ║
║                                              ┌──────────────┐                         ║
║                                              │     END      │ ══► Final Answer         ║
║                                              └──────────────┘                         ║
╚═══════════════════════════════════════════════════════════════════════════════════════╝
                                    │
                               ══►  ▼
╔═══════════════════════════════════════════════════════════════════════════════════════╗
║              CONTEXT & MEMORY  (isolated per user_id + topic)                        ║
║                                                                                       ║
║   ChromaDB                 Knowledge Graph (SQL)      opentutorai_memory (SQL)        ║
║  ┌──────────────────┐    ┌────────────────────┐    ┌─────────────────────────┐       ║
║  │ pedagogical_docs │    │ kg_concept         │    │ Episodic                │       ║
║  │ (RAG collection) │    │ kg_relation        │    │ Behavioral              │       ║
║  └──────────────────┘    │ kg_user_mastery    │    │ Procedural              │       ║
║                          └────────────────────┘    │ Semantic                │       ║
║                                                     │ session_summary         │       ║
║                                                     └─────────────────────────┘       ║
╚═══════════════════════════════════════════════════════════════════════════════════════╝

  ══►  main execution flow
  ──►  data / feedback flow
  ◄══  retry loop  (Verifier ══► verification_feedback ══► Planner)
  ⚡   Human-in-the-Loop interrupt
         P1 after DiagnosticsAgent  (level confirmation)
         P2 after VerifierAgent     (needs_review gate)
         P3 after FeedbackAgent     (memory validation)
  ★    LLM decision
  ⬡    deterministic fallback
```

---

## Phase A — LLM Orchestration

> **Goal**: replace trace-counting routing with a reasoned LLM decision.

### Step 1 — Define the 2 missing configuration functions

In `config.py`, define `get_openai_api_key()` and `get_openai_base_url()` reading
the `OPENAI_API_KEY` and `OPENAI_BASE_URL` environment variables.

These functions are already called in `orchestrator._llm_route()` but did not exist
in the codebase — this was the only technical blocker to enabling LLM orchestration.

> Alternative: replace `ChatOpenAI` with `ChatAnthropic` (SDK already installed) to
> avoid any dependency on OpenAI.

### Step 2 — Enable the LLM orchestration flag

In `config.py`, set `orchestrator_use_llm` to `True`.

From this point, `_llm_route()` is called for every routing decision.
`_route()` is kept only as a safety fallback.

### Step 3 — Enrich the orchestrator LLM prompt

The prompt now provides the LLM with:

- Full `agent_trace` (decision history)
- `verification.unsupported_items` (what the Verifier rejected)
- `memory_context` summary (what the learner has already seen)
- `n_retries` per agent (how many times each agent has already run)

### Step 4 — Switch to structured JSON output

Instead of asking the LLM to "reply with just the agent name", the prompt now requests:
`{ "next_agent": "...", "reasoning": "...", "confidence": 0.0-1.0 }`.

`reasoning` and `confidence` are stored in `agent_trace` at each iteration,
creating full traceability of agentic decisions.

### Step 5 — Replace the stop condition with a qualitative judgment

`MAX_ITERATIONS = 10` is no longer the sole stopping mechanism.
The LLM orchestrator decides `END` when pedagogical quality is sufficient
(satisfactory verification score, weak concepts addressed, objectives covered).
A hard safety ceiling of 15 remains to prevent infinite loops.

---

## Phase B — ReAct Agents

> **Goal**: give each agent the ability to choose its tools through reasoning,
> not predefined metadata.

### Step 6 — Migrate ExerciseAgent to the ReAct pattern

Tools were previously invoked in `_run_tool_for_exercise()` based on hardcoded
`type` and `subject` fields (if/elif logic).

Replaced by `create_react_agent()` from LangGraph (>= 0.2.0).
The agent receives 6 tools and a context prompt (topic, level, weak_concepts).
It autonomously decides which tools to invoke, in what order, and why —
via a Thought -> Action -> Observation loop.

### Step 7 — Give PlannerAgent access to search_web

The PlannerAgent now calls `search_web` to enrich the strategy with real-world
resources when the topic is poorly covered by RAG documents (< 2 docs).

### Step 8 — Enrich TutorGraphState with agentic signals

Added to `state.py`:

- `agent_reasoning: dict` — internal reasoning of each agent (key = agent name)
- `tool_selection_log: list` — log `{ agent, tool, rationale, result }` per tool call
- `verification_feedback: list` — targeted Verifier feedback forwarded to Planner (Phase C)
- `human_feedback: str` — human response injected at interrupt checkpoints (Phase D)

These fields allow the LLM orchestrator to reason over the full history of
what has been attempted, not just trace counters.

---

## Phase C — Self-Evaluation and Feedback Loop

> **Goal**: agents evaluate the quality of their own output and pass targeted
> feedback to each other during retries.

### Step 9 — Replace VerifierAgent text scoring with LLM judgment

The VerifierAgent previously computed a text overlap score via `is_text_supported()`.

Replaced by a structured LLM call: the LLM receives the generated exercises, the strategy,
and the RAG documents, and returns:

`{ verdict, score, specific_feedback: list[str], unsupported_items: list[str] }`

### Step 10 — Route specific_feedback to PlannerAgent on retries

The Verifier's feedback is stored in `verification_feedback` (field added in Step 8).

On retry, the PlannerAgent reads this field and constrains its generation:
"avoid exercises on X (unsupported), prioritise Y according to sources".

### Step 11 — Add a self-critique step to every agent

Before returning output to the orchestrator, each agent executes an internal mini-LLM call:

> "Is my output coherent with the pedagogical objective, the learner's level,
> and the current state? If not, I correct it before handing off."

This mechanism adds 1 LLM call per agent per iteration and prevents low-quality
outputs from propagating to downstream agents.

---

## Phase D — Human-in-the-Loop

> **Goal**: suspend the graph at 3 critical points to allow human validation
> or correction before continuing.

### Step 12 — Identify the 3 critical pause points

| Point | Trigger | Question asked to the learner |
|-------|---------|-------------------------------|
| **P1** | After `DiagnosticsAgent` | "Your level has been assessed as X, weak concepts: Y. Continue?" |
| **P2** | After `VerifierAgent` with verdict `needs_review` | "These items could not be verified: [list]. Continue anyway?" |
| **P3** | After `FeedbackAgent` | "Session summary: [recap]. Save to persistent memory?" |

### Step 13 — Inject interrupt() at these 3 points

LangGraph 0.2.0+ provides `interrupt()` natively — the graph suspends, serialises
its full state into the already-configured SQLite checkpointer, and waits for
`Command(resume=...)` from the API layer.

No new dependency required: `interrupt()` and `Command` are in `langgraph.types`,
already installed.

### Step 14 — Consume human_feedback in agent reasoning

The human response is injected into `human_feedback` (`TutorGraphState` field, added
in Step 8) when the graph resumes via `Command(resume=body.human_feedback)`.

This field plays **three distinct roles** depending on which agent reads it:

#### Role 1 — Binary control signal (yes / no)

Each agent that emitted an `interrupt()` reads `human_feedback` immediately after
resuming and makes a branching decision:

| Agent | "yes" value | "no" / other value |
|-------|------------|-------------------|
| **DiagnosticsAgent P1** | Passes control to PlannerAgent | Same (value forwarded to next agent) |
| **VerifierAgent P2** | Considers the plan validated despite gaps | Triggers a PlannerAgent retry |
| **FeedbackAgent P3** | Writes to persistent memory | Skips memory persistence |

#### Role 2 — Free-form pedagogical constraint

If the P1 response is not "yes" but free text
(e.g. *"I'd rather start with JOINs"*), the **PlannerAgent** adds it to its
`difficulties` list to orient the learning strategy.

```python
# planner.py
if human_feedback and human_feedback.lower().strip() not in ("oui", "yes", "y", "o", ""):
    difficulties = difficulties + [f"Human feedback: {human_feedback[:100]}"]
```

#### Role 3 — Signal for the LLM orchestrator

The orchestrator includes `human_feedback` in its prompt at every routing decision.
It can therefore adapt the next agent based on what the learner expressed,
even if that agent did not emit the `interrupt()`.

#### Full API flow

```
POST /adaptive/plan
  -- graph starts, human_feedback = ""
     DiagnosticsAgent ==> interrupt() P1 ==> client: interrupted=true

POST /adaptive/resume { session_id, human_feedback: "yes" }
  -- Command(resume="yes") ==> human_feedback injected into LangGraph state
     PlannerAgent reads "yes" ==> no constraint added
     VerifierAgent ==> interrupt() P2 if needs_review ==> client

POST /adaptive/resume { session_id, human_feedback: "no" }
  -- VerifierAgent resumes "no" ==> PlannerAgent retry with verification_feedback
```

---

## Step Dependencies

```
Step 1 --> Step 2 --> Step 3 --> Step 4 --> Step 5
           (LLM active before enriching its prompt and output)

Step 6 --> Step 7 --> Step 8
           (ReAct before enriching state with agentic signals)

Step 8 --> Step 9 --> Step 10 --> Step 11
           (state fields needed before routing feedback)

Step 12 --> Step 13 --> Step 14
            (identify points before injecting interrupt() and consuming the response)
```

---

## Before / After Summary

| Dimension | Before | After (fully agentic) |
|-----------|--------|----------------------|
| **Orchestration** | Deterministic `_route()` first, LLM as override | **LLM as primary driver**, `_route()` as fallback only |
| **Stop condition** | `MAX_ITERATIONS = 10` | Qualitative LLM judgment (safety ceiling = 15) |
| **Level assessment** | Score thresholds + hardcoded keywords | **LLM reasons** over full profile |
| **Learning strategy** | if/elif templates by level | **LLM generates** 3-5 contextualised steps |
| **Tool selection** | Exercise metadata (type/subject) | Autonomous ReAct (6 tools incl. `sql_evaluator`) |
| **Verification** | Text overlap score | Structured LLM judgment + `specific_feedback` |
| **Planner retry** | Blind replay | Constrained by `verification_feedback` |
| **Persisted memory** | Hardcoded f-strings | **LLM decides** what to memorise (type + importance) |
| **Memory filter** | Deterministic `ContextManager.filter_memories()` | **LLM selects** the 4-6 most relevant memories |
| **Self-evaluation** | None | Internal mini-LLM call per agent (self-critique) |
| **Human-in-the-Loop** | No checkpoint | 3 `interrupt()` at critical points (P1/P2/P3) |
| **Traceability** | String list in `agent_trace` | Reasoning + confidence + tool log + `[LLM]`/`[fallback]` tag |

---

## Degraded Mode (LangGraph fallback)

### Problem

The `/adaptive/plan` pipeline calls LangGraph unconditionally. If LangGraph or
the LLM is unavailable (service down, expired API key, network error), the route
previously returned an HTTP 500 with no pedagogical response.

### Solution — `_fallback_response`

A degraded mode has been added in `backend/open_tutorai/routers/adaptive.py`.
When LangGraph raises an exception unrelated to an `interrupt()`, the system
automatically switches to a minimal pipeline that calls helpers directly, **without LLM**:

| Step | Function called | Role |
|------|----------------|------|
| 1 | `assess_current_level()` | Adjusts declared level based on recent interactions |
| 2 | `detect_difficulties()` | Detects knowledge gaps from topic and feedback |
| 3 | `plan_learning_strategy()` | Builds a prioritised strategy based on difficulties |
| 4 | `generate_exercises()` | Generates 3 exercises adapted to level and language |

### Decision flow

```
_invoke_graph()
    |-- LangGraph OK          ==> full agentic response
    |-- LangGraph interrupt() ==> Human-in-the-Loop (unchanged)
    +-- LangGraph other error
            |-- fallback OK   ==> degraded response  (agent_trace: "[FALLBACK] ...")
            +-- fallback KO   ==> HTTP 500 with both error messages
```

### Client-side detection

The fallback response is identical to a normal response (`AdaptivePlanResponse`).
The client can detect degraded mode by inspecting:

```json
"agent_trace": ["[FALLBACK] LangGraph unavailable: <reason truncated to 120 chars>"]
"verification": {"verdict": "skipped", "reason": "fallback mode"}
```

### Fallback limitations

- No agent self-critique (no LLM)
- No semantic verification (`VerifierAgent` skipped)
- No web enrichment (`search_web` not called)
- No Human-in-the-Loop (no `interrupt()`)

---

## Exercise Tools — Complete Reference

The `ExerciseAgent` has 6 tools, selected by the ReAct agent based on exercise type:

| Tool | File | Trigger | What it does |
|------|------|---------|-------------|
| `live_code_evaluation` | `tools/live_code_evaluation.py` | `type=coding`, `code_language=python` | Executes Python code in an isolated subprocess (5 s timeout) |
| `sql_evaluator` | `tools/sql_evaluator.py` | `type=sql` or SQL topic detected | Executes a SELECT query on an in-memory SQLite DB with W3Schools tables |
| `math_evaluator` | `tools/math_evaluator.py` | `type=math` or `subject=math/science` | Evaluates an expression via sympy (numeric eval fallback) |
| `generate_chart` | `tools/generate_chart.py` | `type=chart` | Generates a graph (function, timeline, bar) |
| `grammar_checker` | `tools/grammar_checker.py` | `type=dictation` or `subject=language` | Checks grammar of a text sample |
| `search_web` | `tools/search_web.py` | `type=mcq/explain` or insufficient RAG | Enriches the plan with real web results |

### `sql_evaluator` — details

- **Available tables**: `Customers`, `Products`, `Orders`, `Employees` (W3Schools sample data)
- **Allowed statements**: `SELECT`, `WITH`, `EXPLAIN` only — all write operations are blocked
- **Auto-detection**: if the topic contains `sql`, `select`, `query`, `join`, `database`... CS exercises are generated with `type=sql` instead of `type=coding`
- **No dependency**: uses Python's built-in `sqlite3` module

---

## human_feedback — Role in the Architecture

The `human_feedback` field (`TutorGraphState`) is injected via `Command(resume=body.human_feedback)`
when the graph resumes after an `interrupt()`. It plays three roles:

### Binary control (yes/no) at each checkpoint

| Checkpoint | "yes" | "no" / other |
|-----------|-------|-------------|
| **P1** DiagnosticsAgent | Forwards to PlannerAgent | Same (value propagated) |
| **P2** VerifierAgent | Validates plan despite gaps | Triggers PlannerAgent retry |
| **P3** FeedbackAgent | Writes to persistent memory | Skips memory write |

### Free-form pedagogical constraint (P1)

Free text from the learner (e.g. *"start with JOINs please"*) is appended to
`difficulties` by the PlannerAgent to steer the strategy.

### LLM orchestrator signal

The orchestrator includes `human_feedback` in its prompt on every routing call,
allowing it to adapt routing based on learner intent across the full session.

---

## Required Dependencies

**None.** All features used (LangGraph `interrupt()`, `Command`,
`create_react_agent`, `ChatAnthropic`, `ChatOpenAI`, `sqlite3`) are already
present in the installed stack.
