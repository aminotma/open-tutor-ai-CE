"""OrchestratorAgent — deterministic routing with optional LLM fallback."""
from __future__ import annotations

from open_tutorai.agents.langgraph.state import TutorGraphState
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG

MAX_ITERATIONS = 3


def orchestrator_node(state: TutorGraphState) -> dict:
    iteration = state.get("iteration", 0)
    trace     = state.get("agent_trace", [])

    # Guard against infinite loops
    if iteration >= MAX_ITERATIONS:
        trace = trace + [f"[Orchestrator] MAX_ITERATIONS={MAX_ITERATIONS} reached → END"]
        return {"next_agent": "END", "agent_trace": trace}

    next_ag = _route(state)

    # Optional LLM override for ambiguous cases
    if CONTEXT_RETRIEVAL_CONFIG["langchain"].get("orchestrator_use_llm", False):
        next_ag = _llm_route(state, next_ag)

    trace = trace + [f"[Orchestrator] → {next_ag} (iter={iteration})"]
    return {"next_agent": next_ag, "agent_trace": trace}


# ── Deterministic fast-path ───────────────────────────────────────────────────

def _route(state: TutorGraphState) -> str:
    if not state.get("memory_context"):
        return "memory"
    if not state.get("knowledge_graph"):
        return "knowledge"
    if not state.get("difficulties"):
        return "diagnostics"
    if not state.get("strategy"):
        return "planner"
    if not state.get("exercises"):
        return "exercise"
    if not state.get("verification"):
        return "verifier"
    if state.get("verification", {}).get("verdict") == "needs_review":
        return "planner"
    if state.get("weak_concepts") and state.get("iteration", 0) == 0:
        return "feedback"
    return "END"


# ── Optional LLM override ─────────────────────────────────────────────────────

def _llm_route(state: TutorGraphState, default: str) -> str:
    try:
        from open_tutorai.config import get_openai_api_key, get_openai_base_url
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        lc_cfg = CONTEXT_RETRIEVAL_CONFIG["langchain"]
        llm = ChatOpenAI(
            model=lc_cfg.get("llm_model", "gpt-4o-mini"),
            temperature=0.0,
            api_key=get_openai_api_key(),
            base_url=get_openai_base_url(),
        )
        prompt = (
            f"You orchestrate an adaptive tutor. Current state:\n"
            f"- topic: {state['topic']}\n"
            f"- level: {state.get('adjusted_level', '?')}\n"
            f"- weak_concepts: {state.get('weak_concepts', [])[:5]}\n"
            f"- verification verdict: {state.get('verification', {}).get('verdict')}\n"
            f"- iteration: {state.get('iteration', 0)}\n\n"
            f"Choose the next agent from: "
            f"memory, knowledge, diagnostics, planner, exercise, verifier, feedback, END\n"
            f"Reply with ONLY the agent name."
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        decision = resp.content.strip().lower()
        valid = {"memory","knowledge","diagnostics","planner","exercise","verifier","feedback","END"}
        if decision in valid:
            return decision
    except Exception:
        pass
    return default
