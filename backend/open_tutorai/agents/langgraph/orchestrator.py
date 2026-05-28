"""OrchestratorAgent — deterministic routing with optional LLM fallback."""
from __future__ import annotations

from open_tutorai.agents.langgraph.state import TutorGraphState
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG

MAX_ITERATIONS = 10


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
    return {"next_agent": next_ag, "agent_trace": trace, "iteration": iteration + 1}


# ── Deterministic fast-path ───────────────────────────────────────────────────

def _ran(trace: list, tag: str) -> bool:
    return any(tag in t for t in trace)


def _count(trace: list, tag: str) -> int:
    return sum(1 for t in trace if tag in t)


MAX_PLAN_RETRIES = 2  # max needs_review retries


def _route(state: TutorGraphState) -> str:
    trace = state.get("agent_trace", [])

    # Phase 1 — load context (each agent runs exactly once)
    if not _ran(trace, "[MemoryAgent]"):
        return "memory"
    if not _ran(trace, "[KnowledgeAgent]"):
        return "knowledge"
    if not _ran(trace, "[DiagnosticsAgent]"):
        return "diagnostics"

    # Phase 2 — plan → exercise → verify cycle (may retry on needs_review)
    n_plan     = _count(trace, "[PlannerAgent]")
    n_exercise = _count(trace, "[ExerciseAgent]")
    n_verifier = _count(trace, "[VerifierAgent]")

    if n_plan == 0:
        return "planner"
    if n_exercise < n_plan:
        return "exercise"
    if n_verifier < n_exercise:
        return "verifier"

    # Retry only if verifier said needs_review and we haven't hit the retry cap
    if state.get("verification", {}).get("verdict") == "needs_review":
        if n_plan <= MAX_PLAN_RETRIES:
            return "planner"

    # Phase 3 — feedback (once, only when weak concepts remain)
    if state.get("weak_concepts") and not _ran(trace, "[FeedbackAgent]"):
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
