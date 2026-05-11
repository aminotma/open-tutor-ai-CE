# 📘 Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),  
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — Memory & Context Engine enhancements

### Added
- **Learner name in system prompt** (`Chat.svelte`): the tutor now always knows the learner's name (`$user.name`) and is instructed to use it naturally in conversation; injected as the first line of `## Learner Context` before every LLM call.
- **LLM-based summarization** (`context_retrieval.py`): replaced mechanical 3-sentence extraction with an async `gpt-4o-mini` call that produces query-aware summaries; old logic kept as `_summarize_mechanical` fallback.
- **Automatic session summary cache** (`chat_capture.py`): after every N exchanges (default 5), a background task generates a coherent session summary and writes it to `backend/data/cache/summaries/`; cache directory is now actually populated, activating the previously dead summaries branch of the retrieval pipeline.
- **Memory deduplication** (`tools/__init__.py`): `_is_duplicate_memory()` guard prevents storing near-identical memories within a 24-hour window; behavioral memories use exact-match (1.0) threshold to avoid false positives on template-structured strings.
- **Course-based memory isolation** (`context_retrieval.py`, `tools/__init__.py`, `Chat.svelte`): memories and session summaries are filtered by `topic` (course title), giving each course a separate bucket; a `"general"` bucket handles interactions outside any active course.
- **`get_openai_api_key()` / `get_openai_base_url()` helpers** (`config.py`): read the API key configured in the OpenWebUI admin UI (`app.state.config.OPENAI_API_KEYS`) at call time, with env var fallback; all `ChatOpenAI` instantiations use these helpers.
- **Dedicated chat capture endpoint** (`chat_capture.py`): `POST /api/v1/chat/capture` classifies each Q&A pair with an LLM and creates the appropriate memory types (episodic, semantic, procedural, behavioral), replacing the fragile OpenWebUI monkey-patch.
- **Context injection in tutor chat** (`Chat.svelte`): top-5 context items retrieved before each LLM call and injected as a `## Learner Context` section in the system prompt.
- **`tool_persist_memory` mandatory enforcement** (`adaptive_tutor_agent.py`): ReAct loop post-execution check raises `ValueError` if the tool was never called during the session.
- **`ANONYMIZED_TELEMETRY=False`** (`start.sh`): eliminates noisy ChromaDB/PostHog telemetry errors in logs.

### Fixed
- `_GeneratorContextManager` runtime error: `get_db` must be used as `with get_db() as db:`, not via FastAPI `Depends()`.
- `api_key client option must be set` runtime error: `ChatOpenAI` now receives `api_key` + `base_url` from `get_openai_api_key()` / `get_openai_base_url()`.
- `engagement` score always 0 for summaries: added baseline score of 0.2 for `"summary"` type in `calculate_engagement_score()`.
- `topic` never reached the backend: was in the TypeScript interface but absent from the HTTP body construction in `retrieveContext()`.
- `pendingSupportData` lacked `title` and `learning_objective`: stored by `SupportDetails.svelte` and `SupportCreation.svelte`, now read and passed as `learning_objectives` to `retrieveContext`.
- `retrieve_generated_summaries` returned newest files regardless of relevance: now scores a wider candidate pool and sorts by `summary_score` before truncating to `limit`.
- Dead code removed: `openwebui_chat_patch.py`, `hooks/chat_memory.py`, and their import in `patches/__init__.py`.

### Changed
- `apply_summarization_layer` is now `async` (required by LLM-based summarization).
- `retrieve_internal_memory` now accepts a `topic` parameter for course isolation.
- `retrieve_generated_summaries` now accepts a `topic` parameter and sorts by relevance.
- `ContextRetrievalRequest` (backend + TypeScript) extended with `topic` and `learning_objectives` fields.

---

## [0.0.1] - 2025-05-12

### Added
- 👩‍🎓 **Student onboarding features**: profile creation, course joining, AI tutor setup, and learning start.
- 🏠 **Learner Space**: personal hub with progress tracking, AI help, and peer interaction.
- 📊 **Smart Dashboard**: deadlines, achievements, and learning overview at a glance.
- 📚 **Course Library**: manage and access all enrolled courses.
- 🧩 **Supports (Personalized Tutorials)**: custom learning paths powered by AI.
- 📝 **Assignment Central**: task management with feedback, deadlines, and points.
- 💬 **Connect & Learn**: messaging system with group and private chat.
- 🤖 **AI Chat Magic**: 24/7 interactive AI tutor with engagement tracking.
- 🌐 **3D Learning World**: immersive learning with avatars and visual lessons.
- ⚙️ **Settings Hub**: profile customization, themes, and privacy controls.
- 🚀 **Smart Tips & Quick Start Guide**: intuitive walkthrough for new learners.

### Fixed
- ✅ Project setup initialized.
- 🧭 Centralized App Launcher in `open_tutorai/main.py` (using `open_webui` as submodule).
- 📁 Corrected data directory structure — now handled in backend, not `openweb-ui`.

### Changed
- 🎨 Updated OpenTutor AI interface and features.