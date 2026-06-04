"""ExerciseAgent — ReAct pour sélection autonome des outils + auto-critique.

Cascade de résolution du sujet (première valeur non vide) :
  1. state['subject']          — déclaré par l'utilisateur
  2. state['detected_subject'] — inféré par DiagnosticsAgent
  3. detect_subject(topic, weak_concepts) — heuristique de dernier recours

Étape 6 : create_react_agent décide quels outils appeler et dans quel ordre.
Étape 11 : auto-critique LLM avant de retourner les exercices.
"""
from __future__ import annotations

import json

from open_tutorai.agents.langgraph.state import TutorGraphState


def exercise_node(state: TutorGraphState) -> dict:
    from open_tutorai.agents.helpers import (
        generate_exercises,
        generate_typed_exercises,
        detect_subject,
    )

    level      = state.get("adjusted_level") or state["current_level"]
    language   = state.get("language") or "en"
    weak       = state.get("weak_concepts", [])
    objectives = state.get("learning_objectives", [])

    _pfx = {"fr": "Maîtriser", "ar": "إتقان", "es": "Dominar"}.get(language, "Master")
    targeted = [f"{_pfx}: {c}" for c in weak[:2]] + objectives

    # ── Cascade sujet ─────────────────────────────────────────────────────
    subject = state.get("subject", "").strip()
    if not subject:
        subject = state.get("detected_subject", "").strip()
    if not subject:
        subject = detect_subject(state["topic"], weak) or ""

    # ── Génération des exercices ──────────────────────────────────────────
    if subject:
        exercises = generate_typed_exercises(
            state["topic"], subject, level, targeted, count=3, language=language
        )
    else:
        exercises = generate_exercises(
            state["topic"], level, targeted, count=3, language=language
        )

    # ── Étape 6 — agent ReAct pour sélection autonome des outils ─────────
    tool_results, tool_selection_log = _react_tool_selection(exercises, state)

    trace = state.get("agent_trace", []) + [
        f"[ExerciseAgent] {len(exercises)} exercises"
        f" (level={level}, subject={subject or 'generic'})"
    ]
    if tool_results:
        tools_used = ", ".join(r["tool"] for r in tool_results)
        trace.append(f"[ExerciseAgent] tools: {tools_used}")

    # Étape 11 — auto-critique
    agent_reasoning = state.get("agent_reasoning") or {}
    critique = _self_critique(exercises, state)
    if critique:
        agent_reasoning = {**agent_reasoning, "exercise": critique}
        trace = trace + [f"[ExerciseAgent] self-critique: {critique[:80]}"]

    existing_log = state.get("tool_selection_log") or []

    return {
        "exercises":          exercises,
        "tool_results":       (state.get("tool_results") or []) + tool_results,
        "tool_selection_log": existing_log + tool_selection_log,
        "agent_reasoning":    agent_reasoning,
        "agent_trace":        trace,
        "next_agent":         "verifier",
    }


# ── Étape 6 — sélection ReAct ─────────────────────────────────────────────────

def _react_tool_selection(
    exercises: list, state: TutorGraphState
) -> tuple[list[dict], list[dict]]:
    """
    Utilise create_react_agent pour décider quels outils appeler sur chaque exercice.
    Fallback vers le routage déterministe en cas d'erreur.
    """
    try:
        from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG, get_openai_api_key, get_openai_base_url
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
        from langgraph.prebuilt import create_react_agent

        from open_tutorai.tools.live_code_evaluation import live_code_evaluation
        from open_tutorai.tools.math_evaluator       import math_evaluator
        from open_tutorai.tools.generate_chart       import generate_chart
        from open_tutorai.tools.grammar_checker      import grammar_checker
        from open_tutorai.tools.search_web           import search_web
        from open_tutorai.tools.sql_evaluator        import sql_evaluator

        lc_cfg = CONTEXT_RETRIEVAL_CONFIG["langchain"]
        llm = ChatOpenAI(
            model=lc_cfg.get("llm_model", "gpt-4o-mini"),
            temperature=0.0,
            api_key=get_openai_api_key(),
            base_url=get_openai_base_url() or None,
        )

        tools = [live_code_evaluation, sql_evaluator, math_evaluator, generate_chart, grammar_checker, search_web]
        agent = create_react_agent(llm, tools)

        ex_summary = json.dumps(
            [
                {
                    "id":            e.get("id"),
                    "type":          e.get("type"),
                    "subject":       e.get("subject"),
                    "question":      e.get("question", "")[:100],
                    "starter_code":  e.get("starter_code"),
                    "expression":    e.get("expression"),
                    "chart_type":    e.get("chart_type"),
                    "chart_payload": e.get("chart_payload"),
                    "sample_text":   e.get("sample_text"),
                    "search_query":  e.get("search_query"),
                }
                for e in exercises
            ],
            ensure_ascii=False,
        )

        prompt = (
            f"You are a tool orchestrator for an adaptive tutoring system.\n"
            f"Topic: {state['topic']}, "
            f"Level: {state.get('adjusted_level', state.get('current_level'))}\n"
            f"Weak concepts: {state.get('weak_concepts', [])[:3]}\n\n"
            f"Exercises to process:\n{ex_summary}\n\n"
            "For each exercise requiring tool execution, call the appropriate tool:\n"
            "- live_code_evaluation : Python coding exercises → run starter_code\n"
            "- sql_evaluator        : SQL exercises          → run sql_query\n"
            "- math_evaluator       : math/science           → evaluate expression\n"
            "- generate_chart       : chart/timeline         → use chart_type + chart_payload\n"
            "- grammar_checker      : language               → check sample_text\n"
            "- search_web           : MCQ/explain            → use search_query\n\n"
            "Think step by step about which tool fits each exercise. "
            "Only call a tool when the exercise provides the required field."
        )

        result   = agent.invoke({"messages": [HumanMessage(content=prompt)]})
        messages = result.get("messages", [])

        tool_results      = []
        tool_selection_log = []

        for i, msg in enumerate(messages):
            if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                continue
            for tc in msg.tool_calls:
                # Retrouver la ToolMessage correspondante
                tool_output = None
                for subsequent in messages[i + 1:]:
                    if (hasattr(subsequent, "tool_call_id")
                            and subsequent.tool_call_id == tc["id"]):
                        tool_output = subsequent.content
                        break

                rationale = (msg.content if isinstance(msg.content, str)
                             and msg.content else "autonomous")
                tool_results.append({
                    "tool":        tc["name"],
                    "exercise_id": "react",
                    **({"output": str(tool_output)[:500]} if tool_output else {}),
                })
                tool_selection_log.append({
                    "agent":     "exercise",
                    "tool":      tc["name"],
                    "rationale": rationale[:200],
                    "result":    str(tool_output)[:200] if tool_output else None,
                })

        return tool_results, tool_selection_log

    except Exception:
        # Fallback déterministe si le LLM ou create_react_agent n'est pas disponible
        return _deterministic_tool_selection(exercises)


def _deterministic_tool_selection(
    exercises: list,
) -> tuple[list[dict], list[dict]]:
    """Fallback : routage déterministe basé sur les métadonnées de l'exercice."""
    tool_results      = []
    tool_selection_log = []
    for ex in exercises:
        result = _run_tool_for_exercise(ex)
        if result:
            tool_results.append(result)
            tool_selection_log.append({
                "agent":     "exercise",
                "tool":      result["tool"],
                "rationale": "deterministic fallback",
                "result":    None,
            })
    return tool_results, tool_selection_log


def _run_tool_for_exercise(ex: dict) -> dict | None:
    """Routage déterministe d'origine — conservé comme fallback."""
    ex_type    = ex.get("type", "")
    ex_subject = ex.get("subject", "")
    ex_id      = ex.get("id", "")

    if ex_type == "sql" and ex.get("sql_query"):
        from open_tutorai.tools.sql_evaluator import sql_evaluator
        result = sql_evaluator.invoke({
            "query":              ex["sql_query"],
            "expected_row_count": ex.get("expected_row_count", -1),
        })
        return {"tool": "sql_evaluator", "exercise_id": ex_id, **result}

    if ex_type == "coding" and ex.get("starter_code"):
        from open_tutorai.tools.live_code_evaluation import live_code_evaluation
        result = live_code_evaluation.invoke({
            "code":     ex["starter_code"],
            "language": ex.get("code_language", "python"),
        })
        return {"tool": "live_code_evaluation", "exercise_id": ex_id, **result}

    if ex_type == "math" or ex_subject in ("math", "science"):
        expr = ex.get("expression") or ex.get("answer", "")
        if expr:
            from open_tutorai.tools.math_evaluator import math_evaluator
            result = math_evaluator.invoke({
                "expression": expr,
                "expected":   ex.get("expected", ""),
            })
            return {"tool": "math_evaluator", "exercise_id": ex_id, **result}

    if ex_type == "chart" and ex.get("chart_type") and ex.get("chart_payload"):
        from open_tutorai.tools.generate_chart import generate_chart
        payload = ex["chart_payload"]
        result = generate_chart.invoke({
            "chart_type": ex["chart_type"],
            "payload":    payload if isinstance(payload, str) else json.dumps(payload),
        })
        return {"tool": "generate_chart", "exercise_id": ex_id, **result}

    if ex_type == "dictation" or (
        ex_type in ("writing", "fill_in_blank") and ex_subject == "language"
    ):
        sample = ex.get("sample_text") or ex.get("answer", "")
        if sample:
            from open_tutorai.tools.grammar_checker import grammar_checker
            result = grammar_checker.invoke({
                "text":     sample,
                "language": ex.get("lang_code", "fr"),
            })
            return {"tool": "grammar_checker", "exercise_id": ex_id, **result}

    if ex_type in ("mcq", "explain") and ex.get("search_query"):
        from open_tutorai.tools.search_web import search_web
        result = search_web.invoke({
            "query":       ex["search_query"],
            "max_results": 3,
        })
        return {"tool": "search_web", "exercise_id": ex_id, **result}

    return None


# ── Étape 11 — auto-critique ──────────────────────────────────────────────────

def _self_critique(exercises: list, state: TutorGraphState) -> str | None:
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
        questions = [e.get("question", "") for e in exercises]
        prompt = (
            "You are ExerciseAgent performing a self-critique.\n"
            f"Topic: {state['topic']}, "
            f"Level: {state.get('adjusted_level', state.get('current_level'))}\n"
            f"Weak concepts: {state.get('weak_concepts', [])[:3]}\n"
            f"Exercises generated: {questions}\n\n"
            "Are these exercises coherent with the pedagogical objective and learner level? "
            "If not, describe the issue in one sentence. If yes, reply 'OK'."
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        result = resp.content.strip()
        return None if result.upper() == "OK" else result
    except Exception:
        return None
