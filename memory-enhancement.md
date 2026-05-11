# memory-enhancement.md — Memory System Correction Log

## Initial State

Agentic ReAct system with:
- `AdaptiveTutorAgent` (LangChain, `create_react_agent`)
- 10 tools: `tool_retrieve_memory`, `tool_retrieve_rag`, `tool_search_web`, `tool_diagnose`, `tool_plan`, `tool_generate_exercises`, `tool_verify`, `tool_reflect`, `tool_persist_memory`, `tool_final_answer`
- Immutable `AdaptiveTutorState` shared via `state_registry`
- 4 memory types: episodic, semantic, procedural, behavioral
- OpenWebUI hooks: `chat_memory.py` + `openwebui_chat_patch.py`

### Initial memory creation helpers (`tools/__init__.py`)

Three helpers created at first implementation:
- `_create_episodic_memory()` — stores specific interaction snapshots
- `_create_semantic_memory()` — stores learned concepts
- `_create_procedural_memory()` — stores methods and strategies

`tool_persist_memory()` called these helpers to automatically create:
- Episodic memory: session summary
- Semantic memories: concepts derived from learning objectives
- Procedural memory: teaching strategies used

### Initial `retrieve_internal_memory` scoring algorithm

```
Combined score = (semantic_score × 0.7) + (importance_score × 0.3)

importance_score = (type_weight × 0.4) + (recency × 0.3) + (quality × 0.3)

type_weight: semantic=1.2, procedural=1.1, episodic=1.0, behavioral=0.9
recency: exponential decay over 30 days
quality: content length / 500 (capped at 1.0)
```

Fallback: if no keyword match, retrieve the 15×limit most recent memories.

### Initial hook approach (superseded by Fix 1)

- `hooks/chat_memory.py` — hook logic for memory persistence on each message
- `patches/openwebui_chat_patch.py` — monkey-patched `open_webui.utils.chat.chat_completed` and `chat_action` at startup
- `main.py` — called `initialize_patches()` on startup to inject the DB session into hooks

This approach was fragile (silently broke on OpenWebUI updates) and impossible to test in isolation. Replaced entirely by the dedicated endpoint in Fix 1.

---

## Corrections

---

### Fix 1 — Dedicated chat capture endpoint (replaces fragile OpenWebUI patch)

**Problem:** Memory persistence relied on monkey-patching `open_webui.utils.chat` functions
(`chat_completed`, `chat_action`) at startup. This approach breaks silently when OpenWebUI
updates its internals and is impossible to test in isolation.

**Solution:** A clean FastAPI endpoint that receives each question/answer pair explicitly
and creates the appropriate memories directly in the database.

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/routers/chat_capture.py` | **Created** — new dedicated router |
| `backend/open_tutorai/main.py` | Import + register new router; remove patch initialization from startup |

#### New endpoint

```
POST /api/v1/chat/capture
Authorization: Bearer <token>   (get_verified_user)
```

**Request body**
```json
{
  "user_message": "What is gradient descent?",
  "assistant_response": "Gradient descent is an optimisation algorithm...",
  "chat_id": "abc123",
  "topic": "machine learning",      // optional
  "metadata": {}                    // optional extra fields
}
```

**Response**
```json
{ "created": ["episodic", "semantic", "behavioral"], "chat_id": "abc123" }
```

#### Memory creation logic

| Type | Condition | Content |
|---|---|---|
| `episodic` | Always | Learner message (truncated at 200 chars) |
| `semantic` | Response contains concept keywords (`signifie`, `definition`, `refers to`, …) | Extracted concept + tutor explanation |
| `procedural` | Response contains method/step keywords (`method`, `step`, `how to`, …) | Extracted method name + numbered steps |
| `behavioral` | Always | Full exchange summary (`Q: … \| A: …`, 150 chars each) |

---

### Fix 2 — Connect frontend to the capture endpoint

**Problem:** The capture endpoint created in Fix 1 was never called from the UI.
Memory persistence only happened through the now-removed OpenWebUI patch.

**Solution:** After each complete tutor response, `Chat.svelte` calls `captureChatExchange`
fire-and-forget — the UI never blocks on memory persistence.

#### Files changed

| File | Change |
|---|---|
| `src/lib/apis/context/index.ts` | Added `captureChatExchange()` + `ChatCapturePayload` / `ChatCaptureResult` interfaces |
| `src/lib/components/student/tutor/Chat.svelte` | Import + non-blocking call inside the `if (done)` block |

#### Call site (Chat.svelte — inside `if (done)` block, after `chatCompletedHandler`)

```typescript
const _userContent = history.messages[message.parentId]?.content ?? '';
if (_userContent && message.content && $chatId) {
    let _topic = '';
    try {
        _topic = JSON.parse(localStorage.getItem('pendingSupportData') ?? '{}')?.title ?? '';
    } catch { /* ignore */ }
    captureChatExchange(localStorage.token, {
        user_message: _userContent,
        assistant_response: message.content,
        chat_id: $chatId,
        topic: _topic
    });
    // No await — fire-and-forget
}
```

#### Design decisions

- **No `await`** — memory persistence never blocks the chat flow or the UI.
- **Error swallowed in `captureChatExchange`** — `.catch(() => null)` means a backend failure is silent; the user experience is unaffected.
- **Topic resolution** — reads `pendingSupportData.title` from `localStorage` (set when a support session is started); falls back to empty string.
- **Guard conditions** — only fires when `_userContent`, `message.content`, and `$chatId` are all non-empty, preventing spurious calls on error or empty messages.

---

---

### Fix 3 — Make `tool_persist_memory` mandatory in the ReAct loop

**Problem:** `mandatory_tools` existed in `config.py` but was **never read or enforced** —
it was effectively a dead comment. The LLM could skip `tool_persist_memory` without
consequence, leaving sessions with no memory trace.

**Solution:**
1. Add `tool_persist_memory` to the `mandatory_tools` list in config.
2. Implement actual enforcement in `_enforce_mandatory_tools()` — called after the ReAct
   loop (success *or* error fallback) before the final trace is written.

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/config.py` | Added `"tool_persist_memory"` to `mandatory_tools` |
| `backend/open_tutorai/agents/adaptive_tutor_agent.py` | Import `tool_persist_memory` + `tool_final_answer`; added `_enforce_mandatory_tools()`; call it in `_execute()` |

#### Enforcement logic (`_enforce_mandatory_tools`)

```
For each tool in ["tool_persist_memory", "tool_final_answer"]:
    if tool is in mandatory_tools AND was NOT called by the LLM:
        → tool_persist_memory : build summary from current state, call .invoke()
        → tool_final_answer   : call .invoke() only if is_complete is still False

For other mandatory tools (tool_diagnose, tool_generate_exercises):
    → cannot be enforced retroactively — write WARNING to agent_trace
```

#### Why this order matters

`tool_persist_memory` is enforced **before** `tool_final_answer` so that the memories
are in the DB before the session is marked complete. If `tool_final_answer` was already
called (`is_complete = True`), it is skipped — no double-finalisation.

#### What was NOT changed

The `mandatory_tools` check for `tool_diagnose` / `tool_generate_exercises` remains
detection-only (trace warning). Calling those retroactively would require LLM reasoning
over the learner's data, which is outside the scope of a post-loop enforcement pass.

---

### Fix 4 — Fresh DB session per persistence call (replaces stale startup session)

**Problem:** `AdaptiveTutorAgent` received a `db` session from `Depends(get_db)` at request
time and stored it in the `state_registry` for the entire duration of the ReAct loop.
`tool_retrieve_memory` and `tool_persist_memory` both called `registry.get_db(run_id)` to
get that same session. On a long loop (up to 10 iterations) the connection could be closed
by the DB server, causing `tool_persist_memory` to fail silently or raise on commit.

**Root cause:** SQLAlchemy sessions are not safe to hold across long async operations —
the underlying connection can be reclaimed by the pool or closed server-side.

**Solution:** Remove the `db` session from the registry entirely. Each tool that needs the
database opens its own fresh context-managed session with `get_db()`.

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/agents/state_registry.py` | Removed `db` from registry dict; removed `get_db()` accessor; updated `register()` signature |
| `backend/open_tutorai/agents/adaptive_tutor_agent.py` | Removed `db` parameter from `__init__`; removed `self.db`; updated `registry.register()` call |
| `backend/open_tutorai/routers/adaptive_tutor.py` | Removed `db=Depends(get_db)` from endpoint; removed `db=db` from agent constructor |
| `backend/open_tutorai/agents/tools/__init__.py` | Added `from open_webui.internal.db import get_db`; replaced `registry.get_db()` with `with get_db() as db:` in `tool_retrieve_memory` and `tool_persist_memory` |

#### Session lifecycle — before vs after

```
BEFORE
  request → get_db() → session stored in registry → held for 10+ iterations → commit (maybe stale)

AFTER
  request → no db in registry
  tool_retrieve_memory  → with get_db() as db: ... (closed on exit)
  tool_persist_memory   → with get_db() as db: ... db.commit() (closed on exit)
```

#### Why `db.rollback()` was removed from `tool_persist_memory`

The `with get_db() as db:` context manager handles rollback automatically on exception
(standard SQLAlchemy context manager contract). The explicit `db.rollback()` in the
`except` block was therefore redundant and has been removed.

---

### Fix 5 — LLM-based memory classification (replaces keyword heuristics)

**Problem:** `chat_capture.py` detected memory types by scanning the assistant response for
hardcoded French/English keywords (`"c'est"`, `"méthode"`, `"step"`, …). This produced
many false positives (any message mentioning "pour" was flagged procedural) and missed
cases where the signal was implicit (no trigger word, but clearly a concept explanation).
The regex-based concept/method extractors were equally brittle.

**Solution:** A single async LLM call (`gpt-4o-mini`, `temperature=0`) classifies the
exchange and extracts the key content using pedagogical reasoning. The heuristic helpers
(`_extract_concept`, `_extract_method_and_steps`) are removed entirely.

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/routers/chat_capture.py` | Full rewrite of classification logic — removed regex helpers, added `MemoryClassification` schema + `_classify_exchange()` async function |

#### LLM classifier design

**Prompt (system):**
> You are a pedagogical memory classifier. Given a tutor-learner exchange, decide which
> memory types to create and extract the key content.
> - **semantic** : the tutor defines a concept or explains what something IS
> - **procedural**: the tutor describes HOW to do something — steps, method, algorithm
> Both can be true simultaneously. Both can also be false.

**Structured output schema (`MemoryClassification`):**
```python
class MemoryClassification(BaseModel):
    memory_types: List[Literal["semantic", "procedural"]]
    concept: Optional[str]   # filled when semantic
    method:  Optional[str]   # filled when procedural
    steps:   Optional[List[str]]  # filled when procedural
```
LangChain `with_structured_output()` enforces schema compliance — no JSON parsing needed.

#### Truncation

| Field | Limit |
|---|---|
| `user_message` sent to LLM | 300 chars |
| `assistant_response` sent to LLM | 600 chars |

Keeps token cost minimal (gpt-4o-mini) while preserving enough signal for classification.

#### Graceful degradation

If `_classify_exchange()` raises for any reason (API timeout, auth error, …),
it returns `MemoryClassification(memory_types=[])`. The endpoint continues normally —
`episodic` and `behavioral` are still created; only semantic/procedural are skipped.

#### Response change

`ChatCaptureResponse` now includes a `classification` field (the LLM output as dict)
so callers can inspect what was detected without querying the DB.

```json
{
  "created": ["episodic", "semantic", "behavioral"],
  "chat_id": "abc123",
  "classification": {
    "memory_types": ["semantic"],
    "concept": "gradient descent",
    "method": null,
    "steps": null
  }
}
```

---

### Fix 6 — Learner context injected into system prompt before each LLM call

**Problem:** The tutor LLM had no awareness of the learner's past interactions or uploaded
knowledge base. Each message was answered from scratch — no memory of what was already
explained, what difficulties were identified, or what documents the learner provided.

**Solution:** In `sendPromptSocket`, just before building the `messages` array sent to the
LLM, call `GET /api/v1/context/retrieve` with the current user message as query. Format
the top-5 results as a `## Learner Context` section appended to the system prompt.

#### Files changed

| File | Change |
|---|---|
| `src/lib/components/student/tutor/Chat.svelte` | Added `retrieveContext` to import; added context retrieval block before `messages` array; updated system content to include `_learnerContextSection` |

#### Injection point (inside `sendPromptSocket`)

```typescript
// Between baseSystemContent construction and the messages array
let _learnerContextSection = '';
try {
    const _userMsgContent = _history.messages[responseMessage?.parentId]?.content ?? '';
    if (_userMsgContent) {
        const _ctx = await retrieveContext(localStorage.token, {
            query: _userMsgContent.slice(0, 300),
            max_results: 5
        });
        if (_ctx && _ctx.length > 0) {
            const _lines = _ctx
                .map((c) => `- [${c.source}] ${c.content_preview.slice(0, 150)}`)
                .join('\n');
            _learnerContextSection = `\n\n## Learner Context (memory & knowledge base)\n${_lines}`;
        }
    }
} catch { /* non-blocking */ }

// System message now includes learner context
content: (combinedSystemPrompt || baseSystemContent) + _learnerContextSection
```

#### Injected section format (example)

```
## Learner Context (memory & knowledge base)
- [memory] Past interaction: "What is gradient descent?" → "Gradient descent is an opt...
- [memory] Concept: overfitting — occurs when a model learns noise rather than signal...
- [pedagogical] Python ML Course: Supervised learning requires labelled training data...
```

#### Design decisions

- **Query**: last user message (`.parentId` lookup), truncated to 300 chars — sufficient signal for semantic search
- **Limit**: max 5 items, 150 chars preview each — keeps the prompt addition under ~1 000 chars
- **Non-blocking**: entire block wrapped in `try/catch` — a retrieval failure never breaks the chat
- **Always active**: context is retrieved for every message, not just when a support session is open, so learners benefit from their memory history even in general chats

---

#### What was removed

- `initialize_patches()` call removed from `startup_db_client()` in `main.py`.
- `openwebui_chat_patch.py` and `hooks/chat_memory.py` are **kept but no longer active**
  (patch is never initialized). They can be deleted in a future cleanup pass.

---

### Fix — ChromaDB infrastructure & document indexing improvements

**Context:** These corrections were applied to `context_retrieval.py` to stabilise the
ChromaDB integration and improve document ingestion reliability.

#### 1. ChromaDB client stability

**Problem:** Restarting the backend raised `ValueError: An instance of Chroma already exists
for <path>` because ChromaDB's internal singleton was not cleared between process restarts.

**Fix:** Added `_get_chroma_client()` with a module-level cache (`_chroma_client = None`).
On `ValueError`, calls `SharedSystemClient.clear_system_cache()` then retries — resolves the
singleton conflict without requiring a process kill.

```python
try:
    _chroma_client = chromadb.PersistentClient(path=str(db_path), settings=settings)
except ValueError:
    SharedSystemClient.clear_system_cache()
    _chroma_client = chromadb.PersistentClient(path=str(db_path), settings=settings)
```

#### 2. Shared vectorstore in LangChain

`get_vectorstore()` now uses a global `_vectorstore` object and constructs the LangChain
`Chroma` instance with `client=_get_chroma_client()` — guarantees both the raw client and
the LangChain retriever point to the same backend.

#### 3. `doc_id` preserved in ChromaDB metadata

`index_document_to_chromadb()` now stores `doc_id` in each chunk's metadata, enabling
reliable retrieval and document identification from the vector store.

#### 4. `_extract_text_from_file()` — multi-format text extraction

Added a dedicated extractor supporting: PDF, DOCX, PPTX, TXT, MD, JSON, CSV, PY, YAML.
Falls back to binary UTF-8 read if the format is unrecognised.
Used by `index_uploaded_document_to_chromadb()` replacing a naive single-read approach.

#### 5. Richer metadata on indexed uploads

`index_uploaded_document_to_chromadb()` now stores: `file_name`, `file_path`, `file_type`,
`indexed_at`, `doc_id`. Improves traceability and enables future filtering by file type.

#### 6. Document interaction endpoint

Added `POST /context/documents/{doc_id}/interaction` — increments `interaction_count`,
`answered_questions`, and `last_updated` in ChromaDB metadata, and creates a behavioral
memory for each interaction event.

`GET /context/stats` extended to return: `total_memories`, `behavioral_memories`,
`pedagogical_document_count`.

#### 7. Initial engagement score fix for pedagogical items

`calculate_engagement_score()` updated to give a baseline score of 0.2 to `"pedagogical"`
items, with an additional +0.1 boost for `uploaded_document` / `local_document` / `document`
subtypes, and incremental bonuses for `answered_questions` and `interaction_count` metadata.

*(The `"summary"` type was still unhandled at this stage — corrected in Fix 11.)*

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/routers/context_retrieval.py` | `_get_chroma_client()` + singleton fix; shared `_vectorstore`; `doc_id` in metadata; `_extract_text_from_file()`; richer upload metadata; interaction endpoint; engagement score for pedagogical |

---

### Fix 7 — LLM-based summarization (replaces mechanical sentence extraction)

**Problem:** `summarize_interactions()` in `context_retrieval.py` compressed long memory or
document content by extracting exactly three sentences: the first, the middle, and the last.
This produced incoherent, query-irrelevant summaries — important pedagogical content in the
middle was silently discarded, and the "summary" had no relation to what the learner actually
asked.

**Solution:** Replace the mechanical function with an async LLM call (`gpt-4o-mini`,
`temperature=0`) that receives the learner's query and produces a coherent, focused summary.
The old logic is kept as `_summarize_mechanical` and used as a graceful fallback.

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/routers/context_retrieval.py` | Renamed old function to `_summarize_mechanical`; added `_SUMMARIZE_PROMPT` + async `summarize_interactions(content, query, max_tokens)`; made `apply_summarization_layer` async; updated all 3 call sites |

#### New `summarize_interactions` design

```python
async def summarize_interactions(content: str, query: str = "", max_tokens: int = 500) -> str:
    # Short-circuit: if content already fits, return as-is (no LLM call)
    # Build prompt: "QUERY: {query}\n\nCONTENT:\n{content[:2000]}"
    # Call gpt-4o-mini with temperature=0
    # Enforce token budget on output via tiktoken
    # Fallback to _summarize_mechanical on any exception
```

**Prompt (system):**
> You are a pedagogical context summarizer. Summarize the content below as concisely as
> possible, focusing on what is most relevant to the learner's query. Return only the
> summary text — no preamble, no headings.

#### Call sites updated

| Location | Before | After |
|---|---|---|
| `apply_summarization_layer` (line ~690) | `summarize_interactions(content, max_tokens=…)` | `await summarize_interactions(content, query=query, max_tokens=…)` |
| `retrieve_internal_memory` (line ~971) | `summarize_interactions(content, max_tokens=100)` | `await summarize_interactions(content, query=query, max_tokens=100)` |
| Summary generation block (line ~1597) | `summarize_interactions(content, max_tokens=300)` | `await summarize_interactions(content, query=request.query, max_tokens=300)` |
| Caller of `apply_summarization_layer` (line ~1648) | `apply_summarization_layer(…)` | `await apply_summarization_layer(…)` |

#### Design decisions

- **Query-aware**: the learner's original query is threaded through to the LLM, so the
  summary is focused on what the learner actually needs to know.
- **Input capped at 2 000 chars** sent to the LLM — keeps token cost minimal while
  preserving the most relevant content.
- **Token-budget enforcement**: tiktoken checks the LLM output and truncates if it exceeds
  `max_tokens`, maintaining the same contract as the old function.
- **Graceful fallback**: any LLM error (timeout, auth, network) silently falls back to
  `_summarize_mechanical` — the pipeline never breaks.
- **Short-circuit**: if the content already fits in `max_tokens`, the LLM is never called.

---

### Fix 8 — Automatic session summary cache population

**Problem:** `retrieve_generated_summaries` read from `backend/data/cache/summaries/*.json` but
nothing ever wrote to that directory. The function always returned an empty list, so the
"STEP 1: summaries" branch of the context retrieval pipeline was permanently dead.

**Solution:**
1. After every `N` exchanges (configurable, default 5), `capture_chat_exchange` fires a
   background task that queries all behavioral memories for the current chat, builds a
   numbered transcript, and calls the LLM to produce a coherent session summary.
2. The summary is written as `{user_id}_{chat_id}_{ts}.json` in the cache directory.
3. `retrieve_generated_summaries` is updated to glob `{user_id}_*.json` so each user only
   sees their own summaries, and files are returned newest-first.

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/config.py` | Added `"exchanges_per_summary": 5` to `summaries` config |
| `backend/open_tutorai/routers/chat_capture.py` | Added imports (`asyncio`, `json`, `Path`); added `_SESSION_SUMMARY_PROMPT` + `_generate_session_summary()`; added trigger logic after `db.commit()` |
| `backend/open_tutorai/routers/context_retrieval.py` | Updated `retrieve_generated_summaries` to filter files by `{user_id}_*.json` and sort newest-first |

#### `_generate_session_summary` logic

```
1. Open a fresh DB session (independent of the request lifecycle)
2. Query all behavioral memories for this user, filter by chat_id in Python
3. Build a numbered transcript from the last 20 exchanges
4. Call gpt-4o-mini (temperature=0.2) with the transcript + topic
5. Write {user_id}_{chat_id}_{ts}.json to backend/data/cache/summaries/
6. Any exception → silently swallowed (fire-and-forget)
```

#### Trigger in the endpoint

```python
# After db.commit(), count behavioral memories for this chat
trigger = CONTEXT_RETRIEVAL_CONFIG["summaries"]["exchanges_per_summary"]  # 5
chat_count = count of behavioral memories where metadata.chat_id == form.chat_id
if chat_count % trigger == 0:
    asyncio.create_task(_generate_session_summary(user_id, form.chat_id, topic))
```

#### Cache file format

```json
{
  "id": "hex uuid",
  "user_id": "abc",
  "chat_id": "xyz",
  "text": "LLM-generated summary paragraph",
  "source_conversation": "xyz",
  "topic": "machine learning",
  "created_at": 1715000000
}
```

#### `retrieve_generated_summaries` change

| Before | After |
|---|---|
| `glob("*.json")` — all users mixed | `glob(f"{user_id}_*.json")` sorted newest-first |

#### Design decisions

- **Trigger is count-based, not time-based** — fires reliably regardless of session gaps.
- **Last 20 exchanges sent to LLM** — caps token cost; older context is already captured in
  earlier summary files.
- **Fresh DB session in background task** — the request's `db` is closed by the time the
  task runs; opening a fresh `with get_db() as db:` avoids stale-connection errors.
- **Filename prefix = user_id** — simple isolation without subdirectories; compatible with
  the existing `cache_ttl_hours` TTL logic.
- **Multiple files per session is normal** — a session with 10 exchanges produces 2 files
  (triggered at exchange 5 and exchange 10), a session with 15 produces 3, and so on.
  Each file is a progressively richer snapshot of the same session. At retrieval time,
  `retrieve_generated_summaries` scores all of them by relevance and returns only the
  top `limit` — so redundancy is handled automatically without any cleanup needed.

---

### Fix 9 — Memory deduplication before insertion

**Problem:** Every chat exchange created a fresh memory row unconditionally. Repeated questions
on the same topic within a session caused the DB to accumulate dozens of near-identical
episodic, semantic, procedural, and behavioral records, degrading both retrieval quality and
query performance.

**Solution:** A synchronous guard function `_is_duplicate_memory()` is called at the top of
each `_create_*` helper. It queries recent memories for the same user+type and returns `True`
if a matching record already exists within the last 24 hours, causing the helper to return
`None` without calling `db.add()`.

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/agents/tools/__init__.py` | Added `difflib` + `timedelta` imports; added `_is_duplicate_memory()`; guarded `_create_episodic_memory`, `_create_semantic_memory`, `_create_procedural_memory`; added new `_create_behavioral_memory()` helper |
| `backend/open_tutorai/routers/chat_capture.py` | Imported `_create_behavioral_memory`; replaced inline `db.add(Memory(...))` for behavioral with `_create_behavioral_memory()`; the `created` list only appends `"behavioral"` when insertion was not skipped |

#### `_is_duplicate_memory` logic

```
Two checks applied in order (short-circuit on first match):

1. Key match (semantic / procedural only)
   If `key` is provided, compare it case-insensitively to metadata.concept or metadata.method
   of each existing record in the window.  Catches re-worded duplicates of the same concept.

2. Content similarity
   difflib.SequenceMatcher ratio >= threshold (default 0.85, 0.95 for behavioral).
   Catches verbatim or near-verbatim re-submissions.
```

#### Thresholds

| Type | Key match | Content threshold | Rationale |
|---|---|---|---|
| episodic | — | 0.85 | Fuzzy — same learner message with minor typo variation |
| semantic | concept name | 0.85 | Key match fires first; content fallback for renamed concepts |
| procedural | method name | 0.85 | Key match fires first; content fallback for renamed methods |
| behavioral | — | 1.0 (exact) | `difflib` scores structurally similar Q/A templates very high even when content differs — fuzzy matching causes false positives. Only exact retransmissions (double frontend call, refresh) are blocked. |

#### Return value contract

All `_create_*` helpers now return `None` when the insertion was skipped, and the `Memory`
object when it was inserted. Call sites that appended to `created` are guarded with `if result:`.

#### What was NOT changed

- The `tool_persist_memory` ReAct tool calls `_create_episodic_memory` directly — it
  benefits from deduplication automatically with no extra changes.
- The inactive `hooks/chat_memory.py` is not updated (it is not called at runtime).

---

### Cleanup + smoke test (post-Fix 9)

#### Action 1 — Dead code removal

`patches/openwebui_chat_patch.py` and `hooks/chat_memory.py` were no longer called after
Fix 1 but were still loaded at server startup via `patches/__init__.py`. Removed:
- `patches/openwebui_chat_patch.py` — deleted
- `hooks/chat_memory.py` — deleted
- `patches/__init__.py` — removed `from . import openwebui_chat_patch` and its `__all__` entry

The bootstrap logic in `patches/__init__.py` (DATA_DIR configuration, custom_print) is
preserved and continues to be loaded by `main.py`.

#### Action 2 — Smoke test findings and fix

Running a smoke test on the memory creation + deduplication pipeline revealed one bug:

**Bug:** `_create_behavioral_memory` used `similarity_threshold=0.95`. The `difflib.SequenceMatcher`
scores structurally similar `"Q: ... | A: ..."` templates very high (0.96+) even when the actual
questions and answers are completely different, causing false-positive deduplication.

**Root cause:** Short, template-format strings share a large common prefix/suffix. Two entries on
different topics can score 0.96 because `"Q: "`, `" | A: "`, and common words account for
most of the character mass.

**Fix:** Raised behavioral threshold to `1.0` (exact match only). Behavioral duplicates in
practice are exact retransmissions (double frontend call, page refresh) — these have ratio 1.0.

#### Action 3 — Relevance-based sorting in `retrieve_generated_summaries`

**Problem:** Files were sorted by `st_mtime` (newest first) and truncated to `limit` *before*
relevance was computed. The most recent summaries were returned regardless of whether they
matched the learner's current query.

**Fix:** Scan a wider candidate pool (`limit × 4` most recent files), compute relevance for
all of them, filter out irrelevant ones (score ≤ 0.1), then sort by `summary_score` descending
and return the top `limit`.

| Before | After |
|---|---|
| Top `limit` files by date → relevance filter | Top `limit × 4` files by date → relevance score → sort → top `limit` |

**Validated:** With 6 cache files where the 3 oldest are about gradient descent and the 3
newest are about LSTM/CNN/Transformer, a query for "gradient descent optimisation" correctly
returns the 3 older, relevant files — not the 3 newest ones.

---

### Fix 10 — Course-based memory isolation

**Problem:** All memories for a given user were stored in one flat pool and retrieved
together regardless of which course the learner was currently attending. An apprenant
following two courses simultaneously would receive context from both courses mixed in every
system prompt, causing irrelevant or contradictory hints.

**Decision:** Separate buckets per course, plus a `"general"` bucket (empty topic) for
interactions outside any active course.

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/routers/context_retrieval.py` | Added `topic` field to `ContextRetrievalRequest`; added `topic` param to `retrieve_internal_memory` + Python-side filter; added `topic` param to `retrieve_generated_summaries` + JSON field filter; endpoint passes `request.topic` to both |
| `backend/open_tutorai/agents/tools/__init__.py` | Added `topic` param to `_is_duplicate_memory`; filters candidate memories to same topic bucket before key/content comparison; each `_create_*` helper passes `metadata.topic` through |
| `src/lib/apis/context/index.ts` | Added `topic?: string` to `ContextRetrievalRequest` interface |
| `src/lib/components/student/tutor/Chat.svelte` | Reads `pendingSupportData.title` and passes it as `topic` in the `retrieveContext` call |

#### Bucket logic

```
topic = "Python"            → only Python memories + Python summaries
topic = "Machine Learning"  → only ML memories + ML summaries
topic = "" / None           → "general" bucket (no active course)
```

The `topic` is already stored in `memory_metadata` for every memory since Fix 1 (`meta_base`
includes `"topic": form.topic or ""`). No data migration needed.

#### Deduplication scope

`_is_duplicate_memory` now compares only against memories in the same topic bucket.
**Before:** "What is a function?" in Python blocked the same question from being stored in ML.
**After:** each course has its own dedup window — the same concept can be stored once per course.

#### What is NOT course-isolated

- Pedagogical documents (RAG / ChromaDB): document retrieval is query-based and shared across
  courses by design — the learner's uploaded materials are always available.
- The `tool_persist_memory` ReAct tool writes memories with whatever topic is in the current
  state; it already passes through the metadata chain correctly.

---

### Runtime Bug Fix A — `_GeneratorContextManager` has no attribute `query`

**Error (at runtime):**
```
AttributeError: '_GeneratorContextManager' object has no attribute 'query'
```

**Root cause:** OpenWebUI's `get_db` is decorated with `@contextmanager`. FastAPI's
`Depends(get_db)` does not unwrap it — it passes the context manager object directly as the
`db` argument. Calling `db.query(...)` or `db.add(...)` on the context manager object raises
`AttributeError`. The original code in `chat_capture.py` used `db: Session = Depends(get_db)`.

**Fix:** Removed `db: Session = Depends(get_db)` from the `capture_chat_exchange` signature.
All DB operations are now wrapped in `with get_db() as db:` blocks inside the function body.

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/routers/chat_capture.py` | Removed `db: Session = Depends(get_db)` from endpoint signature; all DB ops moved into `with get_db() as db:` block; removed `from sqlalchemy.orm import Session` import |

---

### Runtime Bug Fix B — `api_key client option must be set`

**Error (at runtime):**
```
openai.OpenAIError: The api_key client option must be set either by passing api_key
to the client or by setting the OPENAI_API_KEY environment variable
```

**Root cause:** OpenWebUI stores API keys entered in the admin UI in
`app.state.config.OPENAI_API_KEYS` (populated at server startup). `ChatOpenAI` from LangChain
only checks the `OPENAI_API_KEY` environment variable. The env var is not set, so the key is
not found.

**Fix:** Added two helpers to `config.py` that read the live `app.state.config` at call time
(not at import time, which would fail before server startup). Passed to all `ChatOpenAI`
instantiations via `api_key=` and `base_url=` keyword arguments.

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/config.py` | Added `get_openai_api_key()` + `get_openai_base_url()` reading from `app.state.config` with env var fallback |
| `backend/open_tutorai/routers/chat_capture.py` | Both `ChatOpenAI(...)` calls pass `api_key=get_openai_api_key(), base_url=get_openai_base_url()` |
| `backend/open_tutorai/routers/context_retrieval.py` | `ChatOpenAI(...)` in `summarize_interactions` passes `api_key=get_openai_api_key(), base_url=get_openai_base_url()` |

#### `get_openai_api_key` pattern

```python
def get_openai_api_key() -> str:
    try:
        from open_webui.main import app
        keys = app.state.config.OPENAI_API_KEYS
        if keys and keys[0]:
            return keys[0]
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY", "")
```

The deferred import (`from open_webui.main import app` inside the function body) avoids
circular-import issues and ensures `app.state` is populated before the key is read.

#### Known limitation

If the deployment uses Ollama instead of OpenAI, `OPENAI_API_KEYS` is empty and the helpers
return an empty string, which is still rejected by `ChatOpenAI`. A `get_llm()` factory that
auto-detects Ollama vs OpenAI is identified as a follow-up improvement.

---

### Fix 11 — `engagement` score always 0 for summaries

**Problem:** `calculate_engagement_score()` only handled `"memory"` (episodic) and
`"pedagogical"` source types. The `"summary"` type had no code path that could produce a
score > 0. As a result, summaries were structurally penalized by 30% in every composite score
(engagement weight = 0.3), meaning a perfectly relevant, fresh summary scored lower than a
mediocre document with a few interactions.

**Before (composite for a relevance=1.0, recency=1.0, alignment=0.5 summary):**
```
0.4×1.0 + 0.3×0.0 + 0.2×1.0 + 0.1×0.5 = 0.65
```

**After:**
```
0.4×1.0 + 0.3×0.2 + 0.2×1.0 + 0.1×0.5 = 0.71
```

#### Files changed

| File | Change |
|---|---|
| `backend/open_tutorai/routers/context_retrieval.py` | Added `if item_type == "summary": score += 0.2` before the `"pedagogical"` block in `calculate_engagement_score` |

---

### Fix 12 — `user_alignment` always 0.5 / `topic` never sent in HTTP body

**Problem (three related issues):**

1. **`user_alignment` is a constant** — `calculate_user_alignment()` returns 0.5 as default
   when `user_profile["interests"]` and `user_profile["learning_objectives"]` are both empty.
   The frontend never passed `learning_objectives`, so the 10% weight was wasted on a constant.

2. **`topic` never reached the backend** — `topic` was defined in the `ContextRetrievalRequest`
   TypeScript interface but was absent from the request body construction in `retrieveContext()`.
   The topic isolation added in Fix 10 was therefore silently bypassed for every frontend call.

3. **`pendingSupportData` lacked course metadata** — the localStorage object stored by
   `SupportDetails.svelte` and `SupportCreation.svelte` only contained `id`, `timestamp`,
   `attempts`. The `title` and `learning_objective` fields were never stored, so
   `Chat.svelte` always read empty strings for both.

**Fix:**

#### Files changed

| File | Change |
|---|---|
| `src/lib/apis/context/index.ts` | Added `if (request.topic !== undefined) { body.topic = request.topic; }` to the body construction in `retrieveContext()` |
| `src/lib/components/student/pages/SupportDetails.svelte` | `pendingSupportData` now stores `title: support.title` and `learning_objective: support.learning_objective` |
| `src/lib/components/student/elements/SupportCreation.svelte` | `pendingSupportData` now stores `title: supportResponse.title ?? supportTitle` and `learning_objective: supportResponse.learning_objective ?? learningObjective` |
| `src/lib/components/student/tutor/Chat.svelte` | Reads `_sd.learning_objective` from `pendingSupportData`; passes `learning_objectives: [_sd.learning_objective]` to `retrieveContext` |

#### Updated call site in `Chat.svelte`

```typescript
let _ctxTopic = '';
let _ctxObjectives: string[] = [];
try {
    const _sd = JSON.parse(localStorage.getItem('pendingSupportData') ?? '{}');
    _ctxTopic = _sd?.title ?? '';
    if (_sd?.learning_objective) _ctxObjectives = [_sd.learning_objective];
} catch { /* ignore */ }
const _ctx = await retrieveContext(localStorage.token, {
    query: _userMsgContent.slice(0, 300),
    max_results: 5,
    topic: _ctxTopic,
    learning_objectives: _ctxObjectives.length ? _ctxObjectives : undefined
});
```

#### Effect

- `topic` now correctly reaches `retrieve_internal_memory` and `retrieve_generated_summaries`,
  activating course-based memory isolation end-to-end.
- `user_alignment` now returns 0.8–0.9 when the learner's objective matches the document
  content, rather than a constant 0.5.

---

### Fix 13 — Learner name injected into system prompt

**Problem:** The tutor had no knowledge of the learner's name. Each session began anonymously
— the LLM could not address the learner personally, making interactions feel generic and
impersonal.

**Solution:** At the start of `_learnerContextSection` construction (which runs before every
LLM call), prepend a line with the learner's name from `$user.name` (the authenticated
session store). The name line is injected unconditionally — even when no memories are
retrieved, the tutor always knows who it is speaking to.

#### File changed

| File | Change |
|---|---|
| `src/lib/components/student/tutor/Chat.svelte` | Refactored `_learnerContextSection` block: accumulates parts in `_ctxParts[]`; always prepends learner name line; memory items appended after |

#### Injected section format (example)

```
## Learner Context
Learner name: Alice — address the learner by this name naturally throughout the conversation.
- [memory] Concept appris : discriminant — Delta = b²-4ac détermine la nature des racines
- [pedagogical] Les équations quadratiques sont de la forme ax² + bx + c = 0...
```

#### Design decisions

- **Unconditional** — the name is always present, even if `retrieveContext` returns empty or
  fails. The `try/catch` wrapper still protects the full block.
- **Natural usage instruction** — the instruction "address the learner by this name naturally"
  avoids rigid repetition; the tutor decides when and how to use the name.
- **Single injection point** — works for both support sessions (`combinedSystemPrompt`) and
  general sessions (`baseSystemContent`), since `_learnerContextSection` is appended to
  whichever is active: `content: (combinedSystemPrompt || baseSystemContent) + _learnerContextSection`.
