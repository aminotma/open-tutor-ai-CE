"""VerifierAgent — checks RAG consistency of generated content."""
from __future__ import annotations

from open_tutorai.agents.langgraph.state import TutorGraphState
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG


def verifier_node(state: TutorGraphState) -> dict:
    rag_cfg   = CONTEXT_RETRIEVAL_CONFIG["rag"]
    threshold = rag_cfg.get("verification_threshold", 0.65)

    if not rag_cfg.get("verification_enabled", True):
        trace = state.get("agent_trace", []) + ["[VerifierAgent] disabled"]
        return {"verification": {"verdict": "disabled"}, "agent_trace": trace, "next_agent": "feedback"}

    rag_docs  = state.get("rag_docs", [])
    exercises = state.get("exercises", [])
    strategy  = state.get("strategy", [])

    if not rag_docs:
        trace = state.get("agent_trace", []) + ["[VerifierAgent] no RAG docs"]
        return {"verification": {"verdict": "no_sources"}, "agent_trace": trace, "next_agent": "feedback"}

    from open_tutorai.agents.helpers import is_text_supported
    corpus = " ".join(d.get("content", "") for d in rag_docs)

    candidates = (
        [state["topic"]]
        + [ex.get("question", "") for ex in exercises]
        + strategy
    )
    candidates = [c for c in candidates if c.strip()]

    supported   = [c for c in candidates if is_text_supported(c, corpus)]
    unsupported = [c for c in candidates if not is_text_supported(c, corpus)]
    score       = len(supported) / max(1, len(candidates))
    verdict     = "supported" if score >= threshold else "needs_review"

    verification = {
        "verified":          score >= threshold,
        "support_score":     round(score, 3),
        "supported_items":   supported,
        "unsupported_items": unsupported,
        "verdict":           verdict,
    }
    next_ag = "feedback" if score >= threshold else "orchestrator"
    trace = state.get("agent_trace", []) + [
        f"[VerifierAgent] verdict={verdict}, score={score:.2f} → {next_ag}"
    ]
    return {"verification": verification, "agent_trace": trace, "next_agent": next_ag}
