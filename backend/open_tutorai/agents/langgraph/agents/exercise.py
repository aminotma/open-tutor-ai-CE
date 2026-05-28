"""ExerciseAgent — generates exercises targeting weak KG concepts."""
from __future__ import annotations

from open_tutorai.agents.langgraph.state import TutorGraphState


def exercise_node(state: TutorGraphState) -> dict:
    from open_tutorai.agents.helpers import generate_exercises

    level      = state.get("adjusted_level") or state["current_level"]
    language   = state.get("language") or "en"
    weak       = state.get("weak_concepts", [])
    objectives = state.get("learning_objectives", [])

    _master_prefix = {"fr": "Maîtriser", "ar": "إتقان", "es": "Dominar"}.get(language, "Master")
    targeted = [f"{_master_prefix}: {c}" for c in weak[:2]] + objectives

    exercises = generate_exercises(
        state["topic"], level, targeted, count=3, language=language
    )

    trace = state.get("agent_trace", []) + [
        f"[ExerciseAgent] {len(exercises)} exercises (level={level})"
    ]
    return {
        "exercises":   exercises,
        "agent_trace": trace,
        "next_agent":  "verifier",
    }
