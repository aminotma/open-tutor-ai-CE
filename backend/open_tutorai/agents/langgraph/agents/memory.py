"""MemoryAgent — loads episodic/behavioral/procedural memories from SQL."""
from __future__ import annotations

from open_tutorai.agents.langgraph.state import TutorGraphState
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG


def memory_node(state: TutorGraphState) -> dict:
    user_id = state["user_id"]
    topic   = state["topic"]
    query   = state.get("user_message") or topic
    types   = CONTEXT_RETRIEVAL_CONFIG["memory"]["memory_types"]

    try:
        import asyncio
        from open_webui.internal.db import get_db
        from open_tutorai.services.context_retrieval import retrieve_internal_memory
        from open_tutorai.services.context_manager import ContextManager

        with get_db() as db:
            raw = asyncio.run(
                retrieve_internal_memory(user_id, query, memory_types=types, limit=10, db=db)
            )
            memories = ContextManager.filter_memories(raw, topic)
    except Exception as exc:
        memories = []
        return {
            "memory_context": [],
            "agent_trace": state.get("agent_trace", []) + [f"[MemoryAgent] error: {exc}"],
            "next_agent": "knowledge",
        }

    trace = state.get("agent_trace", []) + [
        f"[MemoryAgent] {len(memories)} memories loaded"
    ]
    return {"memory_context": memories, "agent_trace": trace, "next_agent": "knowledge"}
