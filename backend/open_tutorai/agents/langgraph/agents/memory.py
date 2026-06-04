"""MemoryAgent — chargement mémoire + tri LLM de pertinence.

Agentisation : après le chargement DB, le LLM filtre et priorise les souvenirs
selon leur pertinence pour la session courante.
Fallback : retourne les souvenirs bruts si le LLM est indisponible.
"""
from __future__ import annotations

import json

from open_tutorai.agents.langgraph.state import TutorGraphState
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG


def memory_node(state: TutorGraphState) -> dict:
    user_id = state["user_id"]
    topic   = state["topic"]
    query   = state.get("user_message") or topic
    types   = CONTEXT_RETRIEVAL_CONFIG["memory"]["memory_types"]

    # ── Chargement DB ─────────────────────────────────────────────────────────
    try:
        from open_webui.internal.db import get_db
        from open_tutorai.services.context_retrieval import retrieve_internal_memory_sync
        from open_tutorai.services.context_manager import ContextManager

        with get_db() as db:
            raw = retrieve_internal_memory_sync(
                user_id, query, memory_types=types, limit=15, db=db
            )
            memories = ContextManager.filter_memories(raw, topic)
    except Exception as exc:
        return {
            "memory_context": [],
            "agent_trace": state.get("agent_trace", []) + [f"[MemoryAgent] error: {exc}"],
            "next_agent": "knowledge",
        }

    # ── Tri LLM de pertinence ─────────────────────────────────────────────────
    filtered, used_llm = _llm_filter(memories, state)

    trace = state.get("agent_trace", []) + [
        f"[MemoryAgent] {len(memories)} loaded → {len(filtered)} kept"
        + (" [LLM]" if used_llm else " [fallback]")
    ]
    return {"memory_context": filtered, "agent_trace": trace, "next_agent": "knowledge"}


# ── Filtrage LLM ──────────────────────────────────────────────────────────────

def _llm_filter(
    memories: list[dict], state: TutorGraphState
) -> tuple[list[dict], bool]:
    """
    Le LLM sélectionne les souvenirs les plus pertinents pour la session.
    Retourne (filtered_memories, used_llm).
    """
    if not memories:
        return memories, False

    # Pas besoin de filtrer si peu de souvenirs
    if len(memories) <= 4:
        return memories, False

    try:
        from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG, get_openai_api_key, get_openai_base_url
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        lc_cfg = CONTEXT_RETRIEVAL_CONFIG["langchain"]
        llm = ChatOpenAI(
            model=lc_cfg.get("llm_model", "gpt-4o-mini"),
            temperature=0.0,
            api_key=get_openai_api_key(),
            base_url=get_openai_base_url() or None,
        )

        indexed = [
            {"idx": i, "type": m.get("memory_type", ""), "content": m.get("content", "")[:120]}
            for i, m in enumerate(memories)
        ]

        prompt = (
            "You are MemoryAgent. Select the most relevant past memories for the current session.\n\n"
            f"Current topic: {state['topic']}\n"
            f"Learner level: {state.get('current_level', 'unknown')}\n"
            f"Learning objectives: {state.get('learning_objectives', [])[:3]}\n"
            f"User message: {state.get('user_message', '')[:100]}\n\n"
            f"Available memories:\n{json.dumps(indexed, ensure_ascii=False)}\n\n"
            "Select the indices of the 4-6 most relevant memories. "
            "Prioritise: recent struggles, unmet objectives, behavioral patterns related to this topic.\n\n"
            "Respond ONLY with valid JSON (no markdown):\n"
            '{"selected": [<idx>, ...], "reasoning": "<one sentence>"}'
        )

        resp = llm.invoke([HumanMessage(content=prompt)])
        data = json.loads(resp.content.strip())

        selected_idxs = [int(i) for i in data.get("selected", [])
                         if isinstance(i, (int, float)) and 0 <= int(i) < len(memories)]

        if not selected_idxs:
            raise ValueError("no valid indices")

        filtered = [memories[i] for i in selected_idxs]
        return filtered, True

    except Exception:
        # Fallback : garder les 6 premiers
        return memories[:6], False
