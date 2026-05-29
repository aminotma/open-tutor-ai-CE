"""ExerciseAgent — generates exercises targeting weak KG concepts.

Subject resolution cascade (first non-empty value wins):
  1. state['subject']          — declared by the user via the frontend/API
  2. state['detected_subject'] — inferred by DiagnosticsAgent from topic + weak_concepts
  3. detect_subject(topic, weak_concepts) — last-resort heuristic inside this node

When a subject is resolved → generate_typed_exercises() is called, which produces
exercises with tool-trigger fields (starter_code, expression, chart_payload, …).
When no subject can be resolved → generate_exercises() fallback (text-only).

Tool routing is handled by _run_tool_for_exercise() which reads those fields and
calls the appropriate tool from open_tutorai.tools.
"""
from __future__ import annotations

import json

from open_tutorai.agents.langgraph.state import TutorGraphState


# ── Tool router ───────────────────────────────────────────────────────────────

def _run_tool_for_exercise(ex: dict) -> dict | None:
    """Return a tool result dict for ex, or None when no tool applies."""
    ex_type    = ex.get("type", "")
    ex_subject = ex.get("subject", "")
    ex_id      = ex.get("id", "")

    # 1. Coding → live_code_evaluation
    if ex_type == "coding" and ex.get("starter_code"):
        from open_tutorai.tools.live_code_evaluation import live_code_evaluation  # noqa: PLC0415
        result = live_code_evaluation.invoke({
            "code":     ex["starter_code"],
            "language": ex.get("code_language", "python"),
        })
        return {"tool": "live_code_evaluation", "exercise_id": ex_id, **result}

    # 2. Math expression → math_evaluator
    if ex_type == "math" or ex_subject in ("math", "science"):
        expr = ex.get("expression") or ex.get("answer", "")
        if expr:
            from open_tutorai.tools.math_evaluator import math_evaluator  # noqa: PLC0415
            result = math_evaluator.invoke({
                "expression": expr,
                "expected":   ex.get("expected", ""),
            })
            return {"tool": "math_evaluator", "exercise_id": ex_id, **result}

    # 3. Chart / timeline / function plot → generate_chart
    if ex_type == "chart" and ex.get("chart_type") and ex.get("chart_payload"):
        from open_tutorai.tools.generate_chart import generate_chart  # noqa: PLC0415
        payload = ex["chart_payload"]
        result = generate_chart.invoke({
            "chart_type": ex["chart_type"],
            "payload":    payload if isinstance(payload, str) else json.dumps(payload),
        })
        return {"tool": "generate_chart", "exercise_id": ex_id, **result}

    # 4. Dictation / writing → grammar_checker
    if ex_type == "dictation" or (ex_type in ("writing", "fill_in_blank") and ex_subject == "language"):
        sample = ex.get("sample_text") or ex.get("answer", "")
        if sample:
            from open_tutorai.tools.grammar_checker import grammar_checker  # noqa: PLC0415
            result = grammar_checker.invoke({
                "text":     sample,
                "language": ex.get("lang_code", "fr"),
            })
            return {"tool": "grammar_checker", "exercise_id": ex_id, **result}

    # 5. MCQ / explain with search query → search_web
    if ex_type in ("mcq", "explain") and ex.get("search_query"):
        from open_tutorai.tools.search_web import search_web  # noqa: PLC0415
        result = search_web.invoke({
            "query":       ex["search_query"],
            "max_results": 3,
        })
        return {"tool": "search_web", "exercise_id": ex_id, **result}

    return None


# ── Node ─────────────────────────────────────────────────────────────────────

def exercise_node(state: TutorGraphState) -> dict:
    from open_tutorai.agents.helpers import (  # noqa: PLC0415
        generate_exercises,
        generate_typed_exercises,
        detect_subject,
    )

    level      = state.get("adjusted_level") or state["current_level"]
    language   = state.get("language") or "en"
    weak       = state.get("weak_concepts", [])
    objectives = state.get("learning_objectives", [])

    _master_prefix = {"fr": "Maîtriser", "ar": "إتقان", "es": "Dominar"}.get(language, "Master")
    targeted = [f"{_master_prefix}: {c}" for c in weak[:2]] + objectives

    # ── Subject cascade ───────────────────────────────────────────────────
    # Source 1 — declared by user via Gateway API
    subject = state.get("subject", "").strip()

    # Source 2 — inferred by DiagnosticsAgent
    if not subject:
        subject = state.get("detected_subject", "").strip()

    # Source 3 — last-resort heuristic inside this node
    if not subject:
        subject = detect_subject(state["topic"], weak) or ""

    # ── Exercise generation ───────────────────────────────────────────────
    if subject:
        exercises = generate_typed_exercises(
            state["topic"], subject, level, targeted, count=3, language=language
        )
    else:
        exercises = generate_exercises(
            state["topic"], level, targeted, count=3, language=language
        )

    # ── Tool calls ────────────────────────────────────────────────────────
    tool_results: list[dict] = []
    for ex in exercises:
        result = _run_tool_for_exercise(ex)
        if result:
            tool_results.append(result)

    # ── Trace ─────────────────────────────────────────────────────────────
    trace = state.get("agent_trace", []) + [
        f"[ExerciseAgent] {len(exercises)} exercises"
        f" (level={level}, subject={subject or 'generic'})"
    ]
    if tool_results:
        tools_used = ", ".join(r["tool"] for r in tool_results)
        trace.append(f"[ExerciseAgent] tools: {tools_used}")

    return {
        "exercises":    exercises,
        "tool_results": (state.get("tool_results") or []) + tool_results,
        "agent_trace":  trace,
        "next_agent":   "verifier",
    }
