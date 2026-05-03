from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from open_tutorai.agents import state_registry as registry
from open_tutorai.agents.helpers import (
    assess_current_level,
    detect_difficulties,
    extract_memory_signals,
    generate_exercises,
    plan_learning_strategy,
    is_text_supported,
    tokenize,
)


# ─── Helper to resolve run_id from LangChain config ──────────────────────────

def _run_id(config: RunnableConfig) -> str:
    run_id = (config.get("configurable") or {}).get("run_id")
    if not run_id:
        raise ValueError("run_id missing from RunnableConfig — was AdaptiveTutorAgent.run() called?")
    return run_id


def _run_async(coro):
    """Execute an async coroutine safely from a sync tool."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply(loop)
            return loop.run_until_complete(coro)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ─── Tool: retrieve memory ────────────────────────────────────────────────────

@tool
def tool_retrieve_memory(
    query: Optional[str] = None,
    memory_types: Optional[List[str]] = None,
    limit: int = 10,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve the learner's internal memories from the database.

    Args:
        query: Search query (defaults to topic + learning objectives)
        memory_types: Filter by ['episodic','semantic','procedural','behavioral']
        limit: Max number of memories to retrieve (default 10)

    Call this FIRST to personalise the session with the learner's history.
    """
    run_id = _run_id(config)
    state = registry.get_state(run_id)
    user_id = registry.get_user_id(run_id)
    db = registry.get_db(run_id)

    from open_tutorai.routers.context_retrieval import retrieve_internal_memory
    from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG

    search_query = query or f"{state.topic} {' '.join(state.learning_objectives[:2])}"
    types = memory_types or CONTEXT_RETRIEVAL_CONFIG["memory"]["memory_types"]

    memories = _run_async(
        retrieve_internal_memory(user_id, search_query, memory_types=types, limit=limit, db=db)
    )

    new_state = (
        state
        .with_updates(memory_context=memories)
        .mark_tool_called("tool_retrieve_memory")
        .append_trace(f"[tool_retrieve_memory] {len(memories)} mémoires récupérées")
    )
    registry.update_state(run_id, new_state)

    if not memories:
        return "Aucune mémoire pertinente trouvée pour cet apprenant."

    summary = "\n".join(
        f"  [{m.get('type','?')}] {str(m.get('content',''))[:100]}..."
        for m in memories[:5]
    )
    return f"Mémoires récupérées ({len(memories)}) :\n{summary}"


# ─── Tool: retrieve RAG documents ────────────────────────────────────────────

@tool
def tool_retrieve_rag(
    query: Optional[str] = None,
    top_k: int = 5,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve pedagogical documents from the ChromaDB vector store.

    Args:
        query: Semantic search query (defaults to topic + objectives)
        top_k: Number of documents to retrieve (max 10)

    Use when pedagogical context is missing or insufficient, or before
    tool_verify to enrich the reference corpus.
    Use as fallback only if RAG returns 0 documents: call tool_search_web.
    """
    run_id = _run_id(config)
    state = registry.get_state(run_id)
    user_id = registry.get_user_id(run_id)

    from open_tutorai.routers.context_retrieval import retrieve_pedagogical_documents

    search_query = query or f"{state.topic} {' '.join(state.learning_objectives[:3])}"
    top_k = min(top_k, 10)

    docs = _run_async(retrieve_pedagogical_documents(user_id, search_query, top_k=top_k))

    new_state = (
        state
        .with_updates(pedagogical_context=docs)
        .mark_tool_called("tool_retrieve_rag")
        .append_trace(f"[tool_retrieve_rag] {len(docs)} documents récupérés")
    )
    registry.update_state(run_id, new_state)

    if not docs:
        return (
            "Aucun document pédagogique trouvé dans ChromaDB. "
            "→ Envisager tool_search_web comme fallback."
        )

    summary = "\n".join(
        f"  [{i+1}] {d.get('metadata', {}).get('title','?')} "
        f"(score={d.get('vector_score', 0):.2f}) : {str(d.get('content',''))[:80]}..."
        for i, d in enumerate(docs[:3])
    )
    return f"Documents RAG récupérés ({len(docs)}) :\n{summary}"


# ─── Tool: web search ─────────────────────────────────────────────────────────

@tool
def tool_search_web(
    query: str,
    config: RunnableConfig = None,
) -> str:
    """
    Search the web via DuckDuckGo to enrich the pedagogical context.

    Args:
        query: Precise, targeted search query

    Use ONLY when tool_retrieve_rag finds no documents or the subject is
    very specific or recent. Do NOT call systematically.
    """
    run_id = _run_id(config)
    state = registry.get_state(run_id)

    from langchain_community.tools import DuckDuckGoSearchRun

    search = DuckDuckGoSearchRun()
    try:
        result = search.run(query)
        new_state = (
            state
            .with_updates(web_search_results=result)
            .mark_tool_called("tool_search_web")
            .append_trace(f"[tool_search_web] query='{query[:50]}'")
        )
        registry.update_state(run_id, new_state)
        return f"Résultats web pour '{query}' :\n{result[:800]}"
    except Exception as exc:
        return f"Recherche web échouée : {exc}"


# ─── Tool: diagnose ───────────────────────────────────────────────────────────

@tool
def tool_diagnose(
    force_level: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Evaluate the learner's level and identify difficulties.

    Analyses recent interaction scores, negative feedback comments,
    memory signals, and unmet learning objectives.

    Args:
        force_level: Override the computed level (beginner/intermediate/advanced)

    Call after retrieving memory and RAG context, or when a major
    difficulty is detected mid-session.
    """
    run_id = _run_id(config)
    state = registry.get_state(run_id)

    adjusted = force_level or assess_current_level(
        state.current_level,
        state.recent_interactions,
        state.feedback_comments,
    )

    difficulties = detect_difficulties(
        state.topic,
        state.recent_interactions,
        state.feedback_comments,
        state.learning_objectives,
    )

    # Enrich from memory signals
    memory_signals = extract_memory_signals(state.topic, state.memory_context)
    difficulties = (difficulties + memory_signals)[:5]

    if not difficulties:
        difficulties = [f"Aucun point critique détecté pour {state.topic}."]

    new_state = (
        state
        .with_updates(
            adjusted_level=adjusted,
            difficulties=difficulties,
            priority_focus=difficulties[:3],
        )
        .mark_tool_called("tool_diagnose")
        .append_trace(f"[tool_diagnose] niveau={adjusted}, difficultés={len(difficulties)}")
    )
    registry.update_state(run_id, new_state)

    lines = "\n".join(f"  - {d}" for d in difficulties)
    return (
        f"Diagnostic terminé.\n"
        f"Niveau ajusté : {adjusted}\n"
        f"Difficultés détectées ({len(difficulties)}) :\n{lines}"
    )


# ─── Tool: plan ───────────────────────────────────────────────────────────────

@tool
def tool_plan(
    focus_on_unsupported: bool = False,
    config: RunnableConfig = None,
) -> str:
    """
    Build the pedagogical strategy based on the current diagnosis.

    Args:
        focus_on_unsupported: If True, re-focus on items not validated
                              by the previous RAG verification pass.

    Generates a prioritised list of concrete strategy decisions.
    Call after tool_diagnose, or after a failed verification pass.
    """
    run_id = _run_id(config)
    state = registry.get_state(run_id)

    difficulties = state.difficulties
    if focus_on_unsupported and state.verification:
        unsupported = state.verification.get("unsupported_items", [])
        if unsupported:
            difficulties = [item[:120] for item in unsupported[:3]]

    decisions = plan_learning_strategy(
        state.topic,
        state.adjusted_level,
        difficulties,
        state.feedback_comments,
        state.memory_context,
    )

    new_state = (
        state
        .with_updates(
            strategy_decisions=decisions,
            strategy=[d["action"] for d in decisions],
        )
        .mark_tool_called("tool_plan")
        .append_trace(f"[tool_plan] {len(decisions)} décisions générées")
    )
    registry.update_state(run_id, new_state)

    lines = "\n".join(
        f"  {d['priority']}. [{d['id']}] {d['action']}" for d in decisions
    )
    return f"Stratégie construite ({len(decisions)} étapes) :\n{lines}"


# ─── Tool: generate exercises ─────────────────────────────────────────────────

@tool
def tool_generate_exercises(
    count: int = 3,
    override_level: Optional[str] = None,
    target_objectives: Optional[List[str]] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Generate pedagogical exercises adapted to the learner's level and difficulties.

    Args:
        count: Number of exercises (default 3, max 5)
        override_level: Force a specific level (beginner/intermediate/advanced)
        target_objectives: Specific objectives to target (overrides state objectives)

    Each exercise includes: question, hint, answer, skill target.
    Call after tool_plan or to regenerate after a failed verification.
    """
    run_id = _run_id(config)
    state = registry.get_state(run_id)

    level = override_level or state.adjusted_level
    objectives = target_objectives or state.learning_objectives

    exercises = generate_exercises(state.topic, level, objectives, count=min(count, 5))

    new_state = (
        state
        .with_updates(suggested_exercises=exercises)
        .mark_tool_called("tool_generate_exercises")
        .append_trace(f"[tool_generate_exercises] {len(exercises)} exercices (niveau={level})")
    )
    registry.update_state(run_id, new_state)

    preview = "\n".join(
        f"  Ex{i+1}: {ex['question'][:80]}..." for i, ex in enumerate(exercises)
    )
    return f"Exercices générés ({len(exercises)}) :\n{preview}"


# ─── Tool: verify ─────────────────────────────────────────────────────────────

@tool
def tool_verify(config: RunnableConfig = None) -> str:
    """
    Verify that the generated exercises and strategy are supported by RAG sources.

    Computes a support score (0–1) based on concept presence in the
    pedagogical corpus.

    Returns: verdict (supported / needs_review), score, unsupported items.

    Call after tool_generate_exercises.
    If score < threshold, call tool_plan(focus_on_unsupported=True) and regenerate.
    """
    run_id = _run_id(config)
    state = registry.get_state(run_id)
    user_id = registry.get_user_id(run_id)

    from open_tutorai.routers.context_retrieval import retrieve_pedagogical_documents
    from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG

    rag_cfg = CONTEXT_RETRIEVAL_CONFIG.get("rag", {})

    if not rag_cfg.get("verification_enabled", False):
        result = {
            "verified": False,
            "support_score": 0.0,
            "supported_items": [],
            "unsupported_items": [],
            "sources": [],
            "verdict": "verification_disabled",
        }
        new_state = (
            state
            .with_updates(verification=result)
            .mark_tool_called("tool_verify")
            .append_trace("[tool_verify] vérification désactivée")
        )
        registry.update_state(run_id, new_state)
        return "Vérification RAG désactivée dans la configuration."

    query = state.topic
    if state.learning_objectives:
        query += " " + " ".join(state.learning_objectives)

    sources = _run_async(
        retrieve_pedagogical_documents(user_id, query, top_k=rag_cfg.get("top_k_documents", 5))
    )

    if not sources:
        result = {
            "verified": False,
            "support_score": 0.0,
            "supported_items": [],
            "unsupported_items": [],
            "sources": [],
            "verdict": "no_sources_found",
        }
        new_state = (
            state
            .with_updates(verification=result)
            .mark_tool_called("tool_verify")
            .append_trace("[tool_verify] aucune source trouvée")
        )
        registry.update_state(run_id, new_state)
        return "Aucune source trouvée. Vérification impossible."

    corpus = " ".join(s.get("content", "") for s in sources)

    candidates = [state.topic] + (state.learning_objectives or [])
    for ex in state.suggested_exercises:
        candidates += [ex.get("question", ""), ex.get("answer", "")]
    candidates += state.strategy
    candidates = [c for c in candidates if c and c.strip()]

    supported, unsupported = [], []
    for c in candidates:
        (supported if is_text_supported(c, corpus) else unsupported).append(c)

    score = len(supported) / max(1, len(candidates))
    threshold = rag_cfg.get("verification_threshold", 0.65)
    verdict = "supported" if score >= threshold else "needs_review"

    result = {
        "verified": score >= threshold,
        "support_score": round(score, 3),
        "supported_items": supported,
        "unsupported_items": unsupported,
        "sources": [
            {
                "source_id": s.get("id", ""),
                "title": s.get("metadata", {}).get("title"),
                "preview": s.get("content", "")[:280],
                "relevance_score": round(s.get("relevance_score", 0.0), 3),
            }
            for s in sources
        ],
        "verdict": verdict,
    }

    new_state = (
        state
        .with_updates(verification=result)
        .mark_tool_called("tool_verify")
        .append_trace(f"[tool_verify] verdict={verdict}, score={score:.2f}")
    )
    registry.update_state(run_id, new_state)

    msg = f"Vérification RAG : {verdict} (score={score:.2f})\n"
    if unsupported:
        msg += f"Éléments non validés ({len(unsupported)}) :\n"
        msg += "\n".join(f"  - {u[:80]}" for u in unsupported[:3])
    else:
        msg += "Tous les éléments sont soutenus par les sources RAG."
    return msg


# ─── Tool: reflect ────────────────────────────────────────────────────────────

@tool
def tool_reflect(
    note: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Analyse current results, adjust strategy if verification failed,
    and prepare a session summary for memory persistence.

    Args:
        note: Optional observation to add to reflection notes

    Call after tool_verify, or when the agent detects an inconsistency.
    The returned summary should be passed to tool_persist_memory.
    """
    run_id = _run_id(config)
    state = registry.get_state(run_id)

    verification = state.verification or {}
    verdict = verification.get("verdict", "unknown")
    score = verification.get("support_score", 0)

    adjustments = []
    new_strategy = list(state.strategy)
    new_difficulties = list(state.difficulties)

    if verdict == "needs_review":
        adj = (
            f"Réviser la stratégie : contenu partiellement non validé RAG "
            f"(score={score:.0%})."
        )
        new_strategy.append(adj)
        new_difficulties.append("Contenu partiellement non validé par RAG")
        adjustments.append(adj)

    new_notes = list(state.reflection_notes)
    if note:
        new_notes.append(note)
        adjustments.append(f"Note ajoutée : {note}")

    memory_summary = (
        f"Session ReAct : topic={state.topic}, niveau={state.adjusted_level}, "
        f"difficultés={', '.join(state.difficulties[:3])}, "
        f"vérification={verdict} ({score:.0%}), "
        f"outils={', '.join(set(state.tools_called))}."
    )

    new_state = (
        state
        .with_updates(
            strategy=new_strategy,
            difficulties=new_difficulties,
            reflection_notes=new_notes,
        )
        .mark_tool_called("tool_reflect")
        .append_trace(f"[tool_reflect] verdict={verdict}, ajustements={len(adjustments)}")
    )
    registry.update_state(run_id, new_state)

    return (
        f"Réflexion terminée.\n"
        f"Ajustements : {len(adjustments)}\n"
        f"Résumé pour mémoire : {memory_summary}\n"
        f"→ Passer ce résumé à tool_persist_memory."
    )


# ─── Tool: persist memory ─────────────────────────────────────────────────────

@tool
def tool_persist_memory(
    summary: str,
    config: RunnableConfig = None,
) -> str:
    """
    Persist an important observation into the learner's behavioural memory.

    Args:
        summary: Structured summary to record (level, difficulties, decisions)

    Call before tool_final_answer to ensure session continuity across sessions.
    """
    run_id = _run_id(config)
    state = registry.get_state(run_id)
    user_id = registry.get_user_id(run_id)
    db = registry.get_db(run_id)

    if not db:
        return "Erreur : DB non disponible, mémoire non persistée."

    from open_tutorai.models.database import Memory

    memory = Memory(
        id=uuid4().hex,
        user_id=user_id,
        memory_type="behavioral",
        content=summary,
        memory_metadata={
            "topic": state.topic,
            "agent_step": "react_persist",
            "verification_verdict": (state.verification or {}).get("verdict"),
            "adjusted_level": state.adjusted_level,
            "tools_called": state.tools_called[-5:],
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    try:
        db.add(memory)
        db.commit()
        db.refresh(memory)
        new_state = (
            state
            .mark_tool_called("tool_persist_memory")
            .append_trace("[tool_persist_memory] mémoire comportementale persistée")
        )
        registry.update_state(run_id, new_state)
        return f"Mémoire persistée (id={memory.id[:8]}...)"
    except Exception as exc:
        db.rollback()
        return f"Échec de persistance : {exc}"


# ─── Tool: final answer ───────────────────────────────────────────────────────

@tool
def tool_final_answer(config: RunnableConfig = None) -> str:
    """
    Mark the session as complete and consolidate the final answer.

    Call ONLY when:
    - Diagnosis is done
    - Exercises are generated and verified (or max corrective cycles reached)
    - Memory has been persisted

    This is the ONLY tool that stops the ReAct loop.
    Do NOT call prematurely.
    """
    run_id = _run_id(config)
    state = registry.get_state(run_id)

    final = {
        "adjusted_level": state.adjusted_level,
        "detected_difficulties": state.difficulties,
        "suggested_exercises": state.suggested_exercises,
        "strategy": state.strategy,
        "strategy_decisions": state.strategy_decisions,
        "priority_focus": state.priority_focus,
        "verification": state.verification,
        "agent_trace": state.agent_trace,
        "react_iterations": state.iteration_count,
        "tools_used": list(set(state.tools_called)),
    }

    new_state = (
        state
        .with_updates(is_complete=True, final_answer=final)
        .mark_tool_called("tool_final_answer")
        .append_trace(
            f"[tool_final_answer] session terminée après {state.iteration_count} itérations"
        )
    )
    registry.update_state(run_id, new_state)

    return (
        f"Session terminée.\n"
        f"Itérations : {state.iteration_count}\n"
        f"Outils : {', '.join(set(state.tools_called))}\n"
        f"Niveau final : {state.adjusted_level}\n"
        f"Exercices : {len(state.suggested_exercises)}\n"
        f"Vérification : {(state.verification or {}).get('verdict', 'N/A')}"
    )


# ─── Public registry ──────────────────────────────────────────────────────────

ALL_TOOLS = [
    tool_retrieve_memory,
    tool_retrieve_rag,
    tool_search_web,
    tool_diagnose,
    tool_plan,
    tool_generate_exercises,
    tool_verify,
    tool_reflect,
    tool_persist_memory,
    tool_final_answer,
]

__all__ = [
    "tool_retrieve_memory",
    "tool_retrieve_rag",
    "tool_search_web",
    "tool_diagnose",
    "tool_plan",
    "tool_generate_exercises",
    "tool_verify",
    "tool_reflect",
    "tool_persist_memory",
    "tool_final_answer",
    "ALL_TOOLS",
]