# Phase 8 — Open WebUI Tools Integration (Chat Function Calling)

## Objective

Make OpenTutorAI's pedagogical tools (`generate_chart`, `math_evaluator`,
`live_code_evaluation`, `search_web`) accessible from the **standard chat** via
Open WebUI's function calling mechanism — not only from the LangGraph pipeline
(ExerciseAgent).

## Problem solved

Before this phase, asking `"plot y = x² - 8"` in the chat produced
a text response (value table + advice to use GeoGebra) because the LLM
had no access to tools. The chart was only generated via the
`/adaptive/plan` pipeline.

---

## Architecture

```
BEFORE (Phase 7)
───────────────
Standard chat  →  LLM responds in text  →  ❌ no tools
Adaptive pipeline  →  ExerciseAgent  →  generate_chart  →  ✅ chart

AFTER (Phase 8)
───────────────
Standard chat  →  LLM + function calling  →  otai_generate_chart  →  ✅ chart
                                          →  otai_math_evaluator  →  ✅ calculation
                                          →  otai_live_code       →  ✅ execution
                                          →  otai_search_web      →  ✅ search
Adaptive pipeline  →  ExerciseAgent  →  LangChain tools (unchanged)  →  ✅
```

---

## New files

### `backend/open_tutorai/tools/owui_tools.py`

Defines the **source code** of the 4 tools in Open WebUI format (`Tools` class with
documented methods). This code is stored in the database and executed
dynamically by Open WebUI when the LLM makes a call.

| Constant | Tool ID | Display name | LLM methods |
|-----------|---------|-------------|--------------|
| `GENERATE_CHART_CODE` | `otai_generate_chart` | OpenTutorAI — Chart | `plot_function()`, `plot_timeline()` |
| `MATH_EVALUATOR_CODE` | `otai_math_evaluator` | OpenTutorAI — Symbolic Calculation | `evaluate_expression()` |
| `LIVE_CODE_CODE` | `otai_live_code` | OpenTutorAI — Code Execution | `run_python()` |
| `SEARCH_WEB_CODE` | `otai_search_web` | OpenTutorAI — Web Search | `search()` |

Each method:
- has a clear docstring for the LLM (usage conditions, parameters)
- wraps the existing LangChain tool (`open_tutorai.tools.*`)
- returns a markdown result (base64 image for charts)

### `backend/open_tutorai/tools/tools_registrar.py`

Registers or updates OTAI tools in the Open WebUI database at startup.

**Functions:**

| Function | Role |
|----------|------|
| `register_otai_tools()` | Entry point — configures `DATABASE_URL` if absent, orchestrates the upsert of each tool |
| `_get_admin(Users)` | Dynamically finds an admin: 1) first created user, 2) scan of first 20 users, 3) any user |
| `_upsert_tool(...)` | Creates the tool if it doesn't exist, updates it if it already does |
| `_extract_specs(...)` | Executes the tool's code and extracts the OpenAI function calling schema via `get_tools_specs()` |

**Robustness:**
- `DATABASE_URL` automatically configured from `DATA_DIR` if absent (avoids empty DB outside the server)
- All errors are silent — a failure does not prevent startup
- Idempotent upsert: re-running does not create duplicates

---

## Modified files

### `backend/open_tutorai/main.py`

Addition in `startup_db_client()`:

```python
# Passes DATA_DIR to the registrar, then registers the tools
if not os.getenv("DATA_DIR"):
    os.environ["DATA_DIR"] = os.path.abspath(".../data")
from open_tutorai.tools.tools_registrar import register_otai_tools
register_otai_tools()
```

### `backend/open_tutorai/agents/helpers.py`

Fix in `generate_typed_exercises()` for math:
- **Before**: `type="math"` → `math_evaluator` for all math exercises
- **After**: detects visualization keywords (`parabola`, `curve`, `graph`, `plot`…) → `type="chart"` → `generate_chart`

### `backend/open_tutorai/agents/langgraph/prompt_builder.py`

ExerciseAgent JSON schema enriched with **type selection rules**:
```
type="chart"     → plot/visualize a curve, parabola, function, timeline
type="math"      → calculate/solve without a graph
type="coding"    → programming exercise
type="dictation" → grammar/language
type="mcq"       → web-based fact checking
```

---

## Activation flow (one-time)

After starting the server, in Open WebUI:

1. **Workspace → Tools** → the 4 OTAI tools appear automatically
2. In the **model settings** → enable the desired tools (or globally)
3. Or in the chat: click `+` in the message bar → select the tool

---

## Outlook — Toward a true Full Agentic

1. **100% LLM orchestrator** — remove `_route()`, the LLM decides alone
2. **Dynamic sub-agent spawning** — an agent delegates to a specialized sub-agent
3. **Autonomous reflective loop** — agents restart without going through the orchestrator
4. **Auto memory update during session** — DB write during the pipeline
5. **Multi-step planning (ReAct / Tree-of-Thought)** — multi-session reasoning
6. **Autonomous mastery evaluation** — without a fixed hardcoded delta
