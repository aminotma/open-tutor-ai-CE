"""FeedbackAgent — résumé LLM + persistance mémoire sélective + interrupt P3.

Agentisation : les templates d'écriture mémoire hardcodés remplacés par un LLM
qui décide quoi mémoriser et comment formuler chaque souvenir.
Fallback déterministe conservé si le LLM est indisponible.
"""
from __future__ import annotations

import json

from datetime import datetime, timezone

from open_tutorai.agents.langgraph.state import TutorGraphState


def feedback_node(state: TutorGraphState) -> dict:
    user_id      = state["user_id"]
    topic        = state["topic"]
    weak         = state.get("weak_concepts", [])
    difficulties = state.get("difficulties", [])
    level        = state.get("adjusted_level") or state["current_level"]
    strategy     = state.get("strategy", [])
    verification = state.get("verification", {})
    objectives   = state.get("learning_objectives", [])

    trace = state.get("agent_trace", [])

    # Auto-critique
    agent_reasoning = state.get("agent_reasoning") or {}
    critique = _self_critique(level, weak, strategy, state)
    if critique:
        agent_reasoning = {**agent_reasoning, "feedback": critique}
        trace = trace + [f"[FeedbackAgent] self-critique: {critique[:80]}"]

    # ── LLM décide quoi mémoriser ─────────────────────────────────────────────
    memory_entries, llm_reasoning = _llm_summarize(state, level, weak, strategy, verification)
    if llm_reasoning:
        agent_reasoning = {**agent_reasoning, "feedback_llm": llm_reasoning}
        trace = trace + [f"[FeedbackAgent] LLM memory plan: {llm_reasoning[:80]}"]
    else:
        trace = trace + ["[FeedbackAgent] memory plan [fallback]"]

    bilan = (
        f"Session sur '{topic}' : niveau {level}, "
        f"{len(weak)} concepts faibles, "
        f"vérification : {verification.get('verdict', 'unknown')}."
    )

    # Étape 13 — P3 interrupt
    human_feedback = state.get("human_feedback", "")
    try:
        from langgraph.types import interrupt
        human_response = interrupt({
            "checkpoint": "P3",
            "question": (
                f"Résumé de session : {bilan} "
                "Valider l'enregistrement en mémoire persistante ? (oui/non)"
            ),
            "context": {
                "level":                level,
                "weak_concepts":        weak[:3],
                "strategy_count":       len(strategy),
                "verification_verdict": verification.get("verdict"),
                "memories_planned":     len(memory_entries),
            },
        })
        human_feedback = str(human_response)
        trace = trace + [f"[FeedbackAgent] P3 human_feedback={human_feedback[:40]}"]

        if human_feedback.lower().strip() in ("non", "no", "n"):
            return {
                "weak_concepts":   weak,
                "agent_trace":     trace + ["[FeedbackAgent] user declined memory persistence"],
                "agent_reasoning": agent_reasoning,
                "human_feedback":  human_feedback,
                "next_agent":      "END",
                "iteration":       state.get("iteration", 0) + 1,
            }
    except Exception:
        pass

    # ── Persistance DB ────────────────────────────────────────────────────────
    try:
        from open_webui.internal.db import get_db
        from open_tutorai.services.knowledge_graph import KnowledgeGraphService
        from open_tutorai.models.database import Memory
        from uuid import uuid4

        with get_db() as db:
            for concept in weak:
                KnowledgeGraphService.update_mastery(db, user_id, concept, topic, delta=0.05)

            for entry in memory_entries:
                db.add(Memory(
                    id=uuid4().hex,
                    user_id=user_id,
                    memory_type=entry["type"],
                    content=entry["content"],
                    memory_metadata=entry["metadata"],
                ))

            from open_tutorai.services.summarization import SummarizationService
            SummarizationService.invalidate_cache(user_id, topic, db)
            db.commit()

        with get_db() as db:
            new_weak = KnowledgeGraphService.get_weak_concepts(user_id, topic, db)

    except Exception as exc:
        new_weak = weak
        return {
            "weak_concepts":   new_weak,
            "agent_trace":     trace + [f"[FeedbackAgent] error: {exc}"],
            "agent_reasoning": agent_reasoning,
            "human_feedback":  human_feedback,
            "next_agent":      "END",
            "iteration":       state.get("iteration", 0) + 1,
        }

    trace = trace + [
        f"[FeedbackAgent] {len(memory_entries)} memories persisted, "
        f"{len(new_weak)} concepts still weak"
    ]
    next_ag = "orchestrator" if new_weak and state.get("iteration", 0) == 0 else "END"
    return {
        "weak_concepts":   new_weak,
        "agent_trace":     trace,
        "agent_reasoning": agent_reasoning,
        "human_feedback":  human_feedback,
        "next_agent":      next_ag,
        "iteration":       state.get("iteration", 0) + 1,
    }


# ── Résumé LLM ────────────────────────────────────────────────────────────────

def _llm_summarize(
    state: TutorGraphState,
    level: str,
    weak: list,
    strategy: list,
    verification: dict,
) -> tuple[list[dict], str | None]:
    """
    Le LLM décide quels souvenirs créer et comment les formuler.
    Retourne (memory_entries, reasoning).
    Fallback vers templates déterministes si le LLM échoue.
    """
    try:
        from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG, get_openai_api_key, get_openai_base_url
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        lc_cfg = CONTEXT_RETRIEVAL_CONFIG["langchain"]
        llm = ChatOpenAI(
            model=lc_cfg.get("llm_model", "gpt-4o-mini"),
            temperature=0.1,
            api_key=get_openai_api_key(),
            base_url=get_openai_base_url() or None,
        )

        prompt = (
            "You are FeedbackAgent. Based on this learning session, decide what is worth "
            "memorising for future sessions and write concise memory entries.\n\n"
            f"Topic: {state['topic']}\n"
            f"Learner level: {level}\n"
            f"Weak concepts: {weak[:5]}\n"
            f"Difficulties: {state.get('difficulties', [])[:4]}\n"
            f"Strategy applied: {strategy[:4]}\n"
            f"Learning objectives: {state.get('learning_objectives', [])[:3]}\n"
            f"Verification verdict: {verification.get('verdict', 'unknown')}\n"
            f"Exercises count: {len(state.get('exercises', []))}\n\n"
            "Create 2-4 memory entries. Each entry must specify:\n"
            "- type: 'behavioral' (learner habits/struggles), 'episodic' (session event), "
            "'procedural' (strategy/process), or 'semantic' (concept/knowledge)\n"
            "- content: a concise factual sentence (max 150 chars)\n"
            "- importance: 'high'|'medium'|'low' (only 'high' and 'medium' should be saved)\n\n"
            "Respond ONLY with valid JSON (no markdown):\n"
            '{"entries": [{"type": "...", "content": "...", "importance": "..."},...], '
            '"reasoning": "<one sentence on what matters most to remember>"}'
        )

        resp = llm.invoke([HumanMessage(content=prompt)])
        data = json.loads(resp.content.strip())

        now_iso = datetime.now(timezone.utc).isoformat()
        meta_base = {"topic": state["topic"], "created_at": now_iso}

        entries = []
        for e in data.get("entries", []):
            if e.get("importance", "medium") == "low":
                continue
            mem_type = e.get("type", "episodic")
            if mem_type not in ("behavioral", "episodic", "procedural", "semantic"):
                mem_type = "episodic"
            entries.append({
                "type":     mem_type,
                "content":  str(e.get("content", ""))[:300],
                "metadata": {**meta_base, "level": level,
                             "verification_verdict": verification.get("verdict"),
                             "importance": e.get("importance", "medium")},
            })

        if not entries:
            raise ValueError("no entries generated")

        return entries, data.get("reasoning", "")

    except Exception:
        # Fallback templates
        return _fallback_memories(state, level, weak, strategy, verification), None


def _fallback_memories(
    state: TutorGraphState,
    level: str,
    weak: list,
    strategy: list,
    verification: dict,
) -> list[dict]:
    now_iso   = datetime.now(timezone.utc).isoformat()
    meta_base = {"topic": state["topic"], "created_at": now_iso}
    topic     = state["topic"]
    entries = [
        {
            "type":    "behavioral",
            "content": (f"Session on '{topic}': level={level}, "
                        f"difficulties={', '.join(state.get('difficulties', [])[:3])}, "
                        f"verification={verification.get('verdict', 'unknown')}."),
            "metadata": {**meta_base, "adjusted_level": level,
                         "verification_verdict": verification.get("verdict")},
        },
        {
            "type":    "episodic",
            "content": f"Adaptive session on '{topic}' — {len(weak)} weak concepts identified.",
            "metadata": meta_base,
        },
    ]
    for obj in state.get("learning_objectives", [])[:3]:
        entries.append({
            "type":    "semantic",
            "content": f"Concept worked on: {obj} in context of {topic}.",
            "metadata": {**meta_base, "concept": obj, "mastery_level": level},
        })
    if strategy:
        steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(strategy[:4]))
        entries.append({
            "type":    "procedural",
            "content": f"Learning strategy for {topic}:\n{steps_text}",
            "metadata": {**meta_base, "steps_count": len(strategy)},
        })
    return entries


# ── Auto-critique ─────────────────────────────────────────────────────────────

def _self_critique(
    level: str, weak: list, strategy: list, state: TutorGraphState
) -> str | None:
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
        prompt = (
            "You are FeedbackAgent performing a self-critique before persisting memories.\n"
            f"Topic: {state['topic']}, Level: {level}\n"
            f"Weak concepts to update: {weak[:3]}\n"
            f"Strategy: {strategy[:2]}\n"
            f"Verification verdict: {state.get('verification', {}).get('verdict')}\n\n"
            "Is this feedback coherent with the session outcomes? "
            "If not, describe the issue in one sentence. If yes, reply 'OK'."
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        result = resp.content.strip()
        return None if result.upper() == "OK" else result
    except Exception:
        return None
