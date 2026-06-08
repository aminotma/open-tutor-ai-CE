"""Compile the LangGraph StateGraph and expose tutor_graph singleton."""
from __future__ import annotations

import os
from pathlib import Path

from langgraph.graph import StateGraph, END

from open_tutorai.agents.langgraph.state import TutorGraphState
from open_tutorai.agents.langgraph.orchestrator import orchestrator_node
from open_tutorai.agents.langgraph.agents.memory      import memory_node
from open_tutorai.agents.langgraph.agents.knowledge   import knowledge_node
from open_tutorai.agents.langgraph.agents.diagnostics import diagnostics_node
from open_tutorai.agents.langgraph.agents.planner     import planner_node
from open_tutorai.agents.langgraph.agents.exercise    import exercise_node
from open_tutorai.agents.langgraph.agents.verifier    import verifier_node
from open_tutorai.agents.langgraph.agents.feedback    import feedback_node

CHECKPOINT_DB = os.getenv("LANGGRAPH_CHECKPOINT_DB", "data/langgraph_checkpoints.sqlite")


def build_graph(use_checkpointer: bool = True):
    workflow = StateGraph(TutorGraphState)

    # ── Nodes ────────────────────────────────────────────────────────────────
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("memory",       memory_node)
    workflow.add_node("knowledge",    knowledge_node)
    workflow.add_node("diagnostics",  diagnostics_node)
    workflow.add_node("planner",      planner_node)
    workflow.add_node("exercise",     exercise_node)
    workflow.add_node("verifier",     verifier_node)
    workflow.add_node("feedback",     feedback_node)

    # ── Entry point ───────────────────────────────────────────────────────────
    workflow.set_entry_point("orchestrator")

    # ── Conditional routing from orchestrator ─────────────────────────────────
    workflow.add_conditional_edges(
        "orchestrator",
        lambda s: s["next_agent"],
        {
            "memory":      "memory",
            "knowledge":   "knowledge",
            "diagnostics": "diagnostics",
            "planner":     "planner",
            "exercise":    "exercise",
            "verifier":    "verifier",
            "feedback":    "feedback",
            "END":         END,
        },
    )

    # ── All agents return to orchestrator ─────────────────────────────────────
    for node in ["memory","knowledge","diagnostics","planner","exercise","verifier","feedback"]:
        workflow.add_edge(node, "orchestrator")

    # ── Checkpointer ──────────────────────────────────────────────────────────
    if use_checkpointer:
        try:
            import sqlite3
            Path(CHECKPOINT_DB).parent.mkdir(parents=True, exist_ok=True)
            from langgraph.checkpoint.sqlite import SqliteSaver
            conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
            checkpointer = SqliteSaver(conn)
        except (ImportError, ModuleNotFoundError):
            # langgraph >= 1.x : SqliteSaver moved to langgraph-checkpoint-sqlite package
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()
        return workflow.compile(checkpointer=checkpointer)

    return workflow.compile()


# Singleton — imported by the router in Phase 6
tutor_graph = build_graph()
