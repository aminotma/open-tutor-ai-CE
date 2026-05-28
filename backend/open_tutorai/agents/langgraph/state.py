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

    # ── Pre-loaded context (from ContextManager, before graph starts) ──────
    rag_docs:         list        # ChromaDB results
    session_summary:  str         # SummarizationService cache

    # ── Loaded inside the graph (mutable during session) ──────────────────
    memory_context:   list        # MemoryAgent — episodic/behavioral/procedural
    knowledge_graph:  dict        # KnowledgeAgent — {nodes, edges, weak_concepts}
    weak_concepts:    list        # KnowledgeAgent — mastery < 0.4

    # ── Intermediate outputs ───────────────────────────────────────────────
    adjusted_level:     str
    difficulties:       list
    priority_focus:     list
    strategy:           list
    strategy_decisions: list
    exercises:          list
    verification:       dict      # {verdict, support_score, supported_items, ...}

    # ── Control ────────────────────────────────────────────────────────────
    next_agent:  str
    iteration:   int
    agent_trace: list
