"""PlannerAgent — builds a targeted strategy on weak KG nodes."""
from __future__ import annotations

from open_tutorai.agents.langgraph.state import TutorGraphState


def planner_node(state: TutorGraphState) -> dict:
    from open_tutorai.agents.helpers import plan_learning_strategy

    difficulties = state.get("difficulties", [])
    verification = state.get("verification", {})

    # Re-focus on unsupported items if verifier sent us back
    if verification.get("verdict") == "needs_review":
        unsupported = verification.get("unsupported_items", [])
        if unsupported:
            difficulties = [item[:120] for item in unsupported[:3]]

    decisions = plan_learning_strategy(
        state["topic"],
        state.get("adjusted_level", state["current_level"]),
        difficulties,
        state.get("feedback_comments", []),
        state.get("memory_context", []),
    )

    trace = state.get("agent_trace", []) + [
        f"[PlannerAgent] {len(decisions)} decisions"
    ]
    return {
        "strategy_decisions": decisions,
        "strategy":           [d["action"] for d in decisions],
        "agent_trace":        trace,
        "next_agent":         "exercise",
    }
