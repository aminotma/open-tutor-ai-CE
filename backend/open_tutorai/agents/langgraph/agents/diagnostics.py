"""DiagnosticsAgent — LLM level assessment + LLM gap detection + P1 interrupt.

Agentisation: assess_current_level() and detect_difficulties() (rule-based) replaced by
a structured LLM call that reasons over the learner's full profile.
Deterministic fallback preserved if the LLM is unavailable.
"""
from __future__ import annotations

import json

from open_tutorai.agents.langgraph.state import TutorGraphState


def diagnostics_node(state: TutorGraphState) -> dict:
    from open_tutorai.agents.helpers import detect_subject

    # ── LLM diagnostic (agentic) with deterministic fallback ─────────────────
    adjusted, difficulties, reasoning = _llm_diagnose(state)

    # Enrich with memory signals and KG weak concepts
    from open_tutorai.agents.helpers import extract_memory_signals
    memory_signals = extract_memory_signals(state["topic"], state.get("memory_context", []))
    difficulties   = list(dict.fromkeys(difficulties + memory_signals))[:5]

    for concept in state.get("weak_concepts", [])[:3]:
        hint = f"KG weak concept: {concept}"
        if hint not in difficulties:
            difficulties.append(hint)

    if not difficulties:
        difficulties = [f"No critical gap detected for {state['topic']}."]

    detected = detect_subject(state["topic"], state.get("weak_concepts", []))

    trace = state.get("agent_trace", []) + [
        f"[DiagnosticsAgent] level={adjusted}, {len(difficulties)} difficulties"
        + (f", subject={detected}" if detected else "")
        + (f" [LLM]" if reasoning else " [fallback]")
    ]

    agent_reasoning = state.get("agent_reasoning") or {}
    if reasoning:
        agent_reasoning = {**agent_reasoning, "diagnostics_llm": reasoning}

    # Self-critique
    critique = _self_critique(adjusted, difficulties, state)
    if critique:
        agent_reasoning = {**agent_reasoning, "diagnostics": critique}
        trace = trace + [f"[DiagnosticsAgent] self-critique: {critique[:80]}"]

    # Step 13 — P1 interrupt
    human_feedback = state.get("human_feedback", "")
    try:
        from langgraph.types import interrupt
        weak_summary = ", ".join(state.get("weak_concepts", [])[:3]) or "aucun identifié"
        human_response = interrupt({
            "checkpoint": "P1",
            "question": (
                f"Votre niveau a été évalué à '{adjusted}'. "
                f"Concepts faibles : {weak_summary}. "
                "Continuer ? (oui/non)"
            ),
            "context": {
                "adjusted_level":   adjusted,
                "difficulties":     difficulties[:3],
                "detected_subject": detected,
            },
        })
        human_feedback = str(human_response)
        trace = trace + [f"[DiagnosticsAgent] P1 human_feedback={human_feedback[:40]}"]
    except Exception:
        pass

    return {
        "adjusted_level":   adjusted,
        "difficulties":     difficulties,
        "priority_focus":   difficulties[:3],
        "detected_subject": detected or "",
        "agent_trace":      trace,
        "agent_reasoning":  agent_reasoning,
        "human_feedback":   human_feedback,
        "next_agent":       "planner",
    }


# ── LLM diagnostic ────────────────────────────────────────────────────────────

def _llm_diagnose(state: TutorGraphState) -> tuple[str, list[str], str | None]:
    """
    Assesses the level and knowledge gaps via LLM with structured reasoning.
    Returns (adjusted_level, difficulties, reasoning).
    Falls back to deterministic helpers if the LLM fails.
    """
    try:
        from langchain_core.messages import HumanMessage
        from open_tutorai.agents.langgraph.llm_factory import get_llm

        llm = get_llm(state.get("llm_model"), temperature=0.0)

        interactions_summary = json.dumps(
            [{"score": i.get("score"), "content": i.get("content", "")[:80]}
             for i in state.get("recent_interactions", [])[:5]],
            ensure_ascii=False,
        )
        memory_summary = "\n".join(
            m.get("content", "")[:100]
            for m in state.get("memory_context", [])[:4]
        ) or "aucune mémoire disponible"

        prompt = (
            "You are DiagnosticsAgent, an expert pedagogical assessor.\n\n"
            f"Topic: {state['topic']}\n"
            f"Declared level: {state['current_level']}\n"
            f"Known weak concepts (KG): {state.get('weak_concepts', [])[:5]}\n"
            f"Learning objectives: {state.get('learning_objectives', [])[:3]}\n"
            f"Recent interactions (score + content): {interactions_summary}\n"
            f"Feedback comments: {state.get('feedback_comments', [])[:3]}\n"
            f"Past memories:\n{memory_summary}\n\n"
            "Based on ALL this information, reason about:\n"
            "1. The learner's actual level (beginner / intermediate / advanced)\n"
            "2. The specific knowledge gaps and difficulties to address\n\n"
            "Respond ONLY with valid JSON (no markdown):\n"
            '{"adjusted_level": "beginner|intermediate|advanced", '
            '"difficulties": ["<gap1>", "<gap2>", ...], '
            '"reasoning": "<one sentence explaining your assessment>"}'
        )

        resp = llm.invoke([HumanMessage(content=prompt)])
        data = json.loads(resp.content.strip())

        level = data.get("adjusted_level", state["current_level"]).lower()
        if level not in ("beginner", "intermediate", "advanced"):
            level = state["current_level"]

        difficulties = [str(d)[:120] for d in data.get("difficulties", [])[:5]]
        reasoning    = data.get("reasoning", "")
        return level, difficulties, reasoning

    except Exception:
        # Deterministic fallback
        from open_tutorai.agents.helpers import assess_current_level, detect_difficulties
        level = assess_current_level(
            state["current_level"],
            state.get("recent_interactions", []),
            state.get("feedback_comments", []),
        )
        difficulties = detect_difficulties(
            state["topic"],
            state.get("recent_interactions", []),
            state.get("feedback_comments", []),
            state.get("learning_objectives", []),
        )
        return level, difficulties, None


# ── Self-critique ─────────────────────────────────────────────────────────────

def _self_critique(
    adjusted_level: str, difficulties: list, state: TutorGraphState
) -> str | None:
    try:
        from langchain_core.messages import HumanMessage
        from open_tutorai.agents.langgraph.llm_factory import get_llm

        llm = get_llm(state.get("llm_model"), temperature=0.0)
        prompt = (
            "You are DiagnosticsAgent performing a self-critique.\n"
            f"Topic: {state['topic']}, "
            f"Original level: {state['current_level']}, "
            f"Assessed level: {adjusted_level}\n"
            f"Difficulties identified: {difficulties[:3]}\n\n"
            "Is this assessment coherent with the learner's profile? "
            "If not, describe the issue in one sentence. If yes, reply 'OK'."
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        result = resp.content.strip()
        return None if result.upper() == "OK" else result
    except Exception:
        return None
