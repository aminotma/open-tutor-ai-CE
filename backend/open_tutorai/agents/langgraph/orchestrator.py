"""OrchestratorAgent — LLM as the primary decision-maker, _route() as fallback.

Agentisation: the LLM is now called FIRST and makes the routing decision.
_route() is only called if the LLM fails or returns an invalid value.
"""
from __future__ import annotations

import json

from open_tutorai.agents.langgraph.state import TutorGraphState
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG

MAX_ITERATIONS_SAFETY = 15


def orchestrator_node(state: TutorGraphState) -> dict:
    iteration = state.get("iteration", 0)
    trace     = state.get("agent_trace", [])

    if iteration >= MAX_ITERATIONS_SAFETY:
        trace = trace + [f"[Orchestrator] safety ceiling {MAX_ITERATIONS_SAFETY} → END"]
        return {"next_agent": "END", "agent_trace": trace}

    # ── LLM as primary decision-maker, _route() as fallback ──────────────────
    next_ag, reasoning, confidence, used_llm = _llm_route(state)

    conf_tag = f" [conf={confidence:.2f}]" if confidence is not None else ""
    src_tag  = " [LLM]" if used_llm else " [fallback]"
    trace = trace + [f"[Orchestrator] → {next_ag} (iter={iteration}){conf_tag}{src_tag}"]

    agent_reasoning = state.get("agent_reasoning") or {}
    if reasoning:
        agent_reasoning = {**agent_reasoning, f"orchestrator_iter_{iteration}": reasoning}

    return {
        "next_agent":      next_ag,
        "agent_trace":     trace,
        "iteration":       iteration + 1,
        "agent_reasoning": agent_reasoning,
    }


# ── LLM — primary decision-maker ─────────────────────────────────────────────

def _llm_route(
    state: TutorGraphState,
) -> tuple[str, str | None, float | None, bool]:
    """
    Asks the LLM to choose the next agent.
    Returns (next_agent, reasoning, confidence, used_llm).
    If the LLM fails, calls _route() as a deterministic fallback.
    """
    try:
        from langchain_core.messages import HumanMessage
        from open_tutorai.agents.langgraph.llm_factory import get_llm

        llm = get_llm(state.get("llm_model"), temperature=0.0)

        trace        = state.get("agent_trace", [])
        verification = state.get("verification", {})
        n_retries    = {
            ag: _count(trace, f"[{ag}Agent]")
            for ag in ("Memory", "Knowledge", "Diagnostics", "Planner",
                       "Exercise", "Verifier", "Feedback")
        }
        mem_summary = [
            m.get("content", "")[:80]
            for m in (state.get("memory_context") or [])[:3]
        ]

        prompt = (
            "You are the orchestrator of an adaptive tutoring system. "
            "Your role is to decide which agent to run next based on the current state.\n\n"
            f"topic:            {state['topic']}\n"
            f"level:            {state.get('adjusted_level', '?')}\n"
            f"weak_concepts:    {state.get('weak_concepts', [])[:5]}\n"
            f"iteration:        {state.get('iteration', 0)}\n"
            f"agent_trace (last 8): {trace[-8:]}\n"
            f"n_retries:        {n_retries}\n"
            f"verification:     verdict={verification.get('verdict')}, "
            f"score={verification.get('support_score')}, "
            f"unsupported={verification.get('unsupported_items', [])[:3]}\n"
            f"memory_summary:   {mem_summary}\n"
            f"human_feedback:   {state.get('human_feedback', '')[:100]}\n\n"
            "Valid agents: memory, knowledge, diagnostics, planner, exercise, verifier, feedback, END\n\n"
            "Rules:\n"
            "- Run memory → knowledge → diagnostics first if not yet done\n"
            "- Then planner → exercise → verifier in order\n"
            "- If verification needs_review AND retries < 2: retry planner\n"
            "- Run feedback if weak_concepts remain and feedback not yet done\n"
            "- Return END when: verification score >= 0.65 AND objectives covered "
            "OR no further improvement is possible\n\n"
            "Respond ONLY with valid JSON — no markdown:\n"
            '{"next_agent": "<name>", "reasoning": "<one sentence why>", "confidence": <0.0-1.0>}'
        )

        resp = llm.invoke([HumanMessage(content=prompt)])
        data = json.loads(resp.content.strip())

        valid = {"memory", "knowledge", "diagnostics", "planner",
                 "exercise", "verifier", "feedback", "END"}
        agent = data.get("next_agent", "")
        if agent not in valid:
            raise ValueError(f"invalid agent: {agent}")

        return agent, data.get("reasoning"), float(data.get("confidence", 0.5)), True

    except Exception:
        # Deterministic fallback
        return _route(state), None, None, False


# ── Deterministic fallback ────────────────────────────────────────────────────

def _ran(trace: list, tag: str) -> bool:
    return any(tag in t for t in trace)


def _count(trace: list, tag: str) -> int:
    return sum(1 for t in trace if tag in t)


MAX_PLAN_RETRIES = 2


def _route(state: TutorGraphState) -> str:
    trace = state.get("agent_trace", [])

    if not _ran(trace, "[MemoryAgent]"):
        return "memory"
    if not _ran(trace, "[KnowledgeAgent]"):
        return "knowledge"
    if not _ran(trace, "[DiagnosticsAgent]"):
        return "diagnostics"

    n_plan     = _count(trace, "[PlannerAgent]")
    n_exercise = _count(trace, "[ExerciseAgent]")
    n_verifier = _count(trace, "[VerifierAgent]")

    if n_plan == 0:
        return "planner"
    if n_exercise < n_plan:
        return "exercise"
    if n_verifier < n_exercise:
        return "verifier"

    if state.get("verification", {}).get("verdict") == "needs_review":
        if n_plan <= MAX_PLAN_RETRIES:
            return "planner"

    if state.get("weak_concepts") and not _ran(trace, "[FeedbackAgent]"):
        return "feedback"

    return "END"
