"""DiagnosticsAgent — assesses learner level and detects gaps via the KG."""
from __future__ import annotations

from open_tutorai.agents.langgraph.state import TutorGraphState


def diagnostics_node(state: TutorGraphState) -> dict:
    from open_tutorai.agents.helpers import (
        assess_current_level,
        detect_difficulties,
        extract_memory_signals,
    )

    adjusted = assess_current_level(
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
    memory_signals = extract_memory_signals(state["topic"], state.get("memory_context", []))
    difficulties   = (difficulties + memory_signals)[:5]

    # Enrich with weak KG concepts
    for concept in state.get("weak_concepts", [])[:3]:
        hint = f"KG weak concept: {concept}"
        if hint not in difficulties:
            difficulties.append(hint)

    if not difficulties:
        difficulties = [f"No critical gap detected for {state['topic']}."]

    trace = state.get("agent_trace", []) + [
        f"[DiagnosticsAgent] level={adjusted}, {len(difficulties)} difficulties"
    ]
    return {
        "adjusted_level": adjusted,
        "difficulties":   difficulties,
        "priority_focus": difficulties[:3],
        "agent_trace":    trace,
        "next_agent":     "planner",
    }
