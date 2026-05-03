# backend/open_tutorai/routers/adaptive_tutor.py
"""
Adaptive Tutor router.

The `use_langchain` flag has been removed — the ReAct agent is always used.
Helper functions (assess_current_level, detect_difficulties, verify_adaptive_tutor_output)
are kept here for backward compatibility with other call sites, but they now
delegate to the pure helpers module.
"""

from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from open_webui.internal.db import get_db
from open_webui.utils.auth import get_verified_user
from open_tutorai.agents.adaptive_tutor_agent import AdaptiveTutorAgent
from open_tutorai.agents.helpers import (
    assess_current_level as _assess_level,
    detect_difficulties as _detect_difficulties,
)
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG
from open_tutorai.routers.context_retrieval import retrieve_pedagogical_documents

router = APIRouter(tags=["adaptive"])


# ─── Pydantic models ──────────────────────────────────────────────────────────

class InteractionHistoryItem(BaseModel):
    content: str
    outcome: Optional[str] = None
    score: Optional[float] = None
    timestamp: Optional[float] = None


class AdaptiveTutorRequest(BaseModel):
    topic: str = Field(..., description="Learning topic or concept")
    current_level: Optional[str] = Field("intermediate")
    recent_interactions: Optional[List[InteractionHistoryItem]] = None
    feedback_comments: Optional[List[str]] = None
    learning_objectives: Optional[List[str]] = None
    preferred_exercise_types: Optional[List[str]] = None
    # NOTE: use_langchain removed — agent is always active


class ExerciseSuggestion(BaseModel):
    id: str
    difficulty: str
    question: str
    hint: str
    answer: str
    skill_target: str


class VerificationSource(BaseModel):
    source_id: str
    title: Optional[str] = None
    preview: str
    relevance_score: float
    path: Optional[str] = None


class StrategyDecision(BaseModel):
    id: str
    action: str
    rationale: str
    priority: int
    dependencies: Optional[List[str]] = None


class VerificationReport(BaseModel):
    verified: bool
    support_score: float
    supported_items: List[str]
    unsupported_items: List[str]
    sources: List[VerificationSource]
    verdict: str
    note: Optional[str] = None


class AdaptiveTutorResponse(BaseModel):
    adjusted_level: str
    detected_difficulties: List[str]
    suggested_exercises: List[ExerciseSuggestion]
    strategy: List[str]
    strategy_decisions: Optional[List[StrategyDecision]] = None
    priority_focus: List[str]
    verification: Optional[VerificationReport] = None
    agent_trace: Optional[List[str]] = None
    notes: Optional[str] = None


# ─── Backward-compatible helpers ─────────────────────────────────────────────

def assess_current_level(
    current_level: str,
    interactions: Optional[List[InteractionHistoryItem]],
    feedback_comments: Optional[List[str]],
) -> str:
    """Thin wrapper so existing call sites (e.g. tools/diagnose) still work."""
    raw = [i.dict() for i in interactions] if interactions else []
    return _assess_level(current_level, raw, feedback_comments)


def detect_difficulties(
    topic: str,
    interactions: Optional[List[InteractionHistoryItem]],
    feedback_comments: Optional[List[str]],
    learning_objectives: Optional[List[str]],
) -> List[str]:
    raw = [i.dict() for i in interactions] if interactions else []
    return _detect_difficulties(topic, raw, feedback_comments, learning_objectives)


async def verify_adaptive_tutor_output(
    user_id: str,
    request,  # duck-typed: needs .topic and .learning_objectives
    exercises: List[Dict[str, Any]],
    strategy: List[str],
) -> VerificationReport:
    """RAG verification — kept for backward compatibility with tool_verify."""
    from open_tutorai.agents.helpers import is_text_supported

    rag_cfg = CONTEXT_RETRIEVAL_CONFIG.get("rag", {})
    if not rag_cfg.get("verification_enabled", False):
        return VerificationReport(
            verified=False,
            support_score=0.0,
            supported_items=[],
            unsupported_items=[],
            sources=[],
            verdict="verification_disabled",
            note="La vérification RAG est désactivée.",
        )

    query = request.topic
    if getattr(request, "learning_objectives", None):
        query += " " + " ".join(request.learning_objectives)

    sources = await retrieve_pedagogical_documents(
        user_id, query, top_k=rag_cfg.get("top_k_documents", 5)
    )

    if not sources:
        return VerificationReport(
            verified=False,
            support_score=0.0,
            supported_items=[],
            unsupported_items=[],
            sources=[],
            verdict="no_sources_found",
            note="Aucune source trouvée.",
        )

    corpus = " ".join(s.get("content", "") for s in sources)

    candidates = [request.topic]
    if getattr(request, "learning_objectives", None):
        candidates.extend(request.learning_objectives)
    for ex in exercises:
        candidates += [ex.get("question", ""), ex.get("answer", "")]
    candidates.extend(strategy)
    candidates = [c for c in candidates if c and c.strip()]

    supported, unsupported = [], []
    for c in candidates:
        (supported if is_text_supported(c, corpus) else unsupported).append(c)

    score = len(supported) / max(1, len(candidates))
    threshold = rag_cfg.get("verification_threshold", 0.65)
    verdict = "supported" if score >= threshold else "needs_review"

    return VerificationReport(
        verified=score >= threshold,
        support_score=round(score, 3),
        supported_items=supported,
        unsupported_items=unsupported,
        sources=[
            VerificationSource(
                source_id=s.get("id", ""),
                title=s.get("metadata", {}).get("title"),
                preview=s.get("content", "")[:280],
                relevance_score=round(s.get("relevance_score", 0.0), 3),
                path=s.get("metadata", {}).get("path"),
            )
            for s in sources
        ],
        verdict=verdict,
        note=(
            "Vérification terminée via sources RAG locales."
            if score >= threshold
            else "Certains éléments non appuyés par les sources."
        ),
    )


# ─── Standalone verification endpoint ────────────────────────────────────────

class AdaptiveTutorVerificationRequest(BaseModel):
    topic: str
    generated_texts: List[str]
    learning_objectives: Optional[List[str]] = None


@router.post("/adaptive/verify", response_model=VerificationReport)
async def verify_adaptive_output(
    request: AdaptiveTutorVerificationRequest,
    user=Depends(get_verified_user),
):
    from open_tutorai.agents.helpers import is_text_supported

    rag_cfg = CONTEXT_RETRIEVAL_CONFIG.get("rag", {})
    if not rag_cfg.get("verification_enabled", False):
        return VerificationReport(
            verified=False, support_score=0.0, supported_items=[],
            unsupported_items=[], sources=[], verdict="verification_disabled",
        )

    query = request.topic
    if request.learning_objectives:
        query += " " + " ".join(request.learning_objectives)

    sources = await retrieve_pedagogical_documents(
        user.id, query, top_k=rag_cfg.get("top_k_documents", 5)
    )
    corpus = " ".join(s.get("content", "") for s in sources)

    supported, unsupported = [], []
    for text in request.generated_texts:
        (supported if is_text_supported(text, corpus) else unsupported).append(text)

    score = len(supported) / max(1, len(request.generated_texts))
    verdict = "supported" if score >= rag_cfg.get("verification_threshold", 0.65) else "needs_review"

    return VerificationReport(
        verified=score >= rag_cfg.get("verification_threshold", 0.65),
        support_score=round(score, 3),
        supported_items=supported,
        unsupported_items=unsupported,
        sources=[
            VerificationSource(
                source_id=s.get("id", ""),
                title=s.get("metadata", {}).get("title"),
                preview=s.get("content", "")[:280],
                relevance_score=round(s.get("relevance_score", 0.0), 3),
                path=s.get("metadata", {}).get("path"),
            )
            for s in sources
        ],
        verdict=verdict,
    )


# ─── Main adaptive plan endpoint ──────────────────────────────────────────────

@router.post("/adaptive/plan", response_model=AdaptiveTutorResponse)
async def create_adaptive_plan(
    request: AdaptiveTutorRequest,
    user=Depends(get_verified_user),
    db=Depends(get_db),
):
    try:
        agent = AdaptiveTutorAgent(
            user_id=user.id,
            request_data=request.dict(),
            db=db,
        )
        state = await agent.run()

        # Prefer the consolidated final_answer produced by tool_final_answer
        if state.final_answer:
            fa = state.final_answer
            return AdaptiveTutorResponse(
                adjusted_level=fa.get("adjusted_level", "intermediate"),
                detected_difficulties=fa.get("detected_difficulties", []),
                suggested_exercises=[
                    ExerciseSuggestion(**ex)
                    for ex in fa.get("suggested_exercises", [])
                    if all(k in ex for k in ["id", "difficulty", "question", "hint", "answer", "skill_target"])
                ],
                strategy=fa.get("strategy", []),
                strategy_decisions=fa.get("strategy_decisions"),
                priority_focus=fa.get("priority_focus", [f"Renforcer {request.topic}"]),
                verification=fa.get("verification"),
                agent_trace=fa.get("agent_trace", []),
                notes=(
                    f"ReAct: {fa.get('react_iterations', 0)} itérations, "
                    f"outils: {', '.join(fa.get('tools_used', []))}"
                ),
            )

        # Fallback: read from state directly if tool_final_answer was not called
        return AdaptiveTutorResponse(
            adjusted_level=state.adjusted_level,
            detected_difficulties=state.difficulties,
            suggested_exercises=[ExerciseSuggestion(**ex) for ex in state.suggested_exercises],
            strategy=state.strategy,
            strategy_decisions=state.strategy_decisions,
            priority_focus=state.priority_focus or [f"Renforcer {request.topic}"],
            verification=state.verification,
            agent_trace=state.agent_trace,
            notes="Fallback: tool_final_answer non appelé",
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ReAct agent failed: {exc}")
