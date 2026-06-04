"""VerifierAgent — jugement pédagogique LLM structuré + interrupt P2."""
from __future__ import annotations

import json

from open_tutorai.agents.langgraph.state import TutorGraphState
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG


def verifier_node(state: TutorGraphState) -> dict:
    rag_cfg   = CONTEXT_RETRIEVAL_CONFIG["rag"]
    threshold = rag_cfg.get("verification_threshold", 0.65)

    if not rag_cfg.get("verification_enabled", True):
        trace = state.get("agent_trace", []) + ["[VerifierAgent] disabled"]
        return {
            "verification":          {"verdict": "disabled"},
            "verification_feedback": [],
            "agent_trace":           trace,
            "next_agent":            "feedback",
        }

    rag_docs  = state.get("rag_docs", [])
    exercises = state.get("exercises", [])
    strategy  = state.get("strategy", [])

    if not rag_docs:
        trace = state.get("agent_trace", []) + ["[VerifierAgent] no RAG docs"]
        return {
            "verification":          {"verdict": "no_sources"},
            "verification_feedback": [],
            "agent_trace":           trace,
            "next_agent":            "feedback",
        }

    # Étape 9 — jugement LLM structuré (fallback texte si LLM indisponible)
    verification, specific_feedback = _llm_verify(exercises, strategy, rag_docs, state, threshold)

    verdict = verification["verdict"]
    next_ag = "feedback" if verdict in ("supported", "disabled", "no_sources") else "orchestrator"

    trace = state.get("agent_trace", []) + [
        f"[VerifierAgent] verdict={verdict}, "
        f"score={verification.get('support_score', 0):.2f} → {next_ag}"
    ]

    # Étape 13 — P2 interrupt : si needs_review, demander confirmation humaine
    human_feedback = state.get("human_feedback", "")
    if verdict == "needs_review":
        unsupported = verification.get("unsupported_items", [])
        try:
            from langgraph.types import interrupt
            human_response = interrupt({
                "checkpoint": "P2",
                "question": (
                    f"Ces éléments n'ont pas pu être vérifiés : {unsupported[:3]}. "
                    "Voulez-vous continuer quand même ? (oui/non)"
                ),
                "context": {
                    "verdict":    verdict,
                    "score":      verification.get("support_score"),
                    "unsupported": unsupported,
                    "feedback":   specific_feedback[:3],
                },
            })
            # Étape 14 — consommer human_feedback
            human_feedback = str(human_response)
            trace = trace + [f"[VerifierAgent] P2 human_feedback={human_feedback[:40]}"]
            if human_feedback.lower().strip() in ("oui", "yes", "y", "o"):
                next_ag = "feedback"
                trace = trace + ["[VerifierAgent] human approved → continue to feedback"]
        except Exception:
            # ImportError si langgraph.types n'a pas interrupt()
            # RuntimeError si appelé hors contexte LangGraph (tests unitaires)
            pass

    return {
        "verification":          verification,
        "verification_feedback": specific_feedback,
        "agent_trace":           trace,
        "human_feedback":        human_feedback,
        "next_agent":            next_ag,
    }


# ── Étape 9 — jugement LLM structuré ─────────────────────────────────────────

def _llm_verify(
    exercises: list,
    strategy:  list,
    rag_docs:  list,
    state:     TutorGraphState,
    threshold: float,
) -> tuple[dict, list]:
    """Étape 9 : LLM renvoie { verdict, score, specific_feedback, unsupported_items }."""
    try:
        from open_tutorai.config import get_openai_api_key, get_openai_base_url
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        lc_cfg = CONTEXT_RETRIEVAL_CONFIG["langchain"]
        llm = ChatOpenAI(
            model=lc_cfg.get("llm_model", "gpt-4o-mini"),
            temperature=0.0,
            api_key=get_openai_api_key(),
            base_url=get_openai_base_url() or None,
        )

        corpus_excerpt = " | ".join(d.get("content", "")[:150] for d in rag_docs[:3])
        ex_questions   = [ex.get("question", "")[:120] for ex in exercises[:3]]

        prompt = (
            "You are a pedagogical verifier.\n"
            f"Topic: {state['topic']}, "
            f"Level: {state.get('adjusted_level', state['current_level'])}\n"
            f"RAG sources (excerpt): {corpus_excerpt}\n\n"
            f"Exercises generated:\n{json.dumps(ex_questions, ensure_ascii=False)}\n\n"
            f"Strategy:\n{json.dumps(strategy[:4], ensure_ascii=False)}\n\n"
            "Are these exercises pedagogically correct and aligned with the RAG sources?\n"
            "Assign a score 0.0 (completely wrong) to 1.0 (perfectly aligned).\n"
            "If score < 0.65, list the specific issues and the unsupported items.\n\n"
            "Respond ONLY with valid JSON (no markdown):\n"
            '{"verdict": "supported"|"needs_review", "score": <float>, '
            '"specific_feedback": ["<issue1>", ...], "unsupported_items": ["<item1>", ...]}'
        )

        resp = llm.invoke([HumanMessage(content=prompt)])
        data = json.loads(resp.content.strip())

        score   = float(data.get("score", 0.5))
        verdict = data.get("verdict") or ("supported" if score >= threshold else "needs_review")

        verification = {
            "verified":          score >= threshold,
            "support_score":     round(score, 3),
            "supported_items":   [],
            "unsupported_items": data.get("unsupported_items", []),
            "verdict":           verdict,
        }
        return verification, data.get("specific_feedback", [])

    except Exception:
        # Fallback chevauchement textuel
        return _text_overlap_verify(exercises, strategy, rag_docs, state["topic"], threshold)


def _text_overlap_verify(
    exercises: list,
    strategy:  list,
    rag_docs:  list,
    topic:     str,
    threshold: float,
) -> tuple[dict, list]:
    from open_tutorai.agents.helpers import is_text_supported
    corpus     = " ".join(d.get("content", "") for d in rag_docs)
    candidates = [topic] + [ex.get("question", "") for ex in exercises] + strategy
    candidates = [c for c in candidates if c.strip()]
    supported   = [c for c in candidates if is_text_supported(c, corpus)]
    unsupported = [c for c in candidates if not is_text_supported(c, corpus)]
    score       = len(supported) / max(1, len(candidates))
    verdict     = "supported" if score >= threshold else "needs_review"
    return {
        "verified":          score >= threshold,
        "support_score":     round(score, 3),
        "supported_items":   supported,
        "unsupported_items": unsupported,
        "verdict":           verdict,
    }, []
