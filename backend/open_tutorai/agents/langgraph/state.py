from __future__ import annotations
from typing import TypedDict, Optional


class TutorGraphState(TypedDict):
    # ── Input (from Gateway API) ───────────────────────────────────────────
    user_id:                  str
    user_name:                str
    topic:                    str
    current_level:            str
    language:                 str
    user_message:             str
    recent_interactions:      list
    feedback_comments:        list
    learning_objectives:      list
    preferred_exercise_types: list
    subject:                  str   # declared by user: 'cs'|'math'|'science'|'language'|'history'

    # ── Pre-loaded context (from ContextManager, before graph starts) ──────
    rag_docs:         list        # ChromaDB results
    session_summary:  str         # SummarizationService cache

    # ── Loaded inside the graph (mutable during session) ──────────────────
    memory_context:    list        # MemoryAgent — episodic/behavioral/procedural
    knowledge_graph:   dict        # KnowledgeAgent — {nodes, edges, weak_concepts}
    weak_concepts:     list        # KnowledgeAgent — mastery < 0.4
    detected_subject:  str         # DiagnosticsAgent — inferred from topic+weak_concepts

    # ── Intermediate outputs ───────────────────────────────────────────────
    adjusted_level:     str
    difficulties:       list
    priority_focus:     list
    strategy:           list
    strategy_decisions: list
    exercises:          list
    tool_results:       list      # ExerciseAgent tool outputs [{tool, exercise_id, ...}]
    verification:       dict      # {verdict, support_score, supported_items, ...}

    # ── Agentic signals (Phase B / C / D) ─────────────────────────────────
    agent_reasoning:       dict   # {agent_name: reasoning_text} — raisonnement interne par agent
    tool_selection_log:    list   # [{agent, tool, rationale, result}] — log des appels d'outils
    verification_feedback: list   # specific_feedback du VerifierAgent → PlannerAgent (retry)
    human_feedback:        str    # réponse humaine injectée aux checkpoints interrupt()

    # ── Control ────────────────────────────────────────────────────────────
    next_agent:  str
    iteration:   int
    agent_trace: list
