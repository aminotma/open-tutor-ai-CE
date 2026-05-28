"""
Adaptive Tutor router — Phase 6.

POST /api/v1/adaptive/plan   → run the full LangGraph tutor pipeline
GET  /api/v1/adaptive/session/{session_id} → replay a checkpointed session
"""
from __future__ import annotations

import asyncio
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from open_webui.internal.db import get_db
from open_webui.utils.auth import get_verified_user
from open_tutorai.services.context_manager import ContextManager
from open_tutorai.services.summarization import SummarizationService

router = APIRouter(tags=["adaptive"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class AdaptivePlanRequest(BaseModel):
    topic: str
    current_level: str = "intermediate"
    language: str = "en"
    user_message: str = ""
    recent_interactions: list = Field(default_factory=list)
    feedback_comments: list = Field(default_factory=list)
    learning_objectives: list = Field(default_factory=list)
    preferred_exercise_types: list = Field(default_factory=list)
    session_id: Optional[str] = None


class AdaptivePlanResponse(BaseModel):
    session_id: str
    topic: str
    adjusted_level: str
    exercises: list
    strategy: list
    verification: dict
    agent_trace: list


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/adaptive/plan", response_model=AdaptivePlanResponse)
async def adaptive_plan(
    body: AdaptivePlanRequest,
    user=Depends(get_verified_user),
):
    """
    Run the full adaptive tutor pipeline for the authenticated user.

    1. Pre-load RAG docs + session summary (ContextManager / SummarizationService).
    2. Build TutorGraphState.
    3. Invoke tutor_graph (LangGraph StateGraph).
    4. Return exercises, strategy, verification, adjusted_level, agent_trace.
    """
    session_id = body.session_id or uuid4().hex

    # 1. Pre-load context (synchronous DB call inside async via run_in_executor)
    try:
        with get_db() as db:
            session_summary = SummarizationService.get_cached_summary(
                user_id=user.id, topic=body.topic, db=db
            ) or ""

        agent_context = await ContextManager.build_agent_context(
            user_id=user.id,
            topic=body.topic,
            query=body.user_message or body.topic,
            db=None,
            user_name=getattr(user, "name", ""),
            language=body.language,
            learning_objectives=body.learning_objectives,
            session_summary=session_summary,
        )
        rag_docs = agent_context.rag_docs
    except Exception as exc:
        rag_docs = []
        session_summary = ""

    # 2. Build initial TutorGraphState
    initial_state = {
        "user_id":                  user.id,
        "user_name":                getattr(user, "name", ""),
        "topic":                    body.topic,
        "current_level":            body.current_level,
        "language":                 body.language,
        "user_message":             body.user_message,
        "recent_interactions":      body.recent_interactions,
        "feedback_comments":        body.feedback_comments,
        "learning_objectives":      body.learning_objectives,
        "preferred_exercise_types": body.preferred_exercise_types,
        # Pre-loaded
        "rag_docs":                 rag_docs,
        "session_summary":          session_summary,
        # Will be populated by agents
        "memory_context":           [],
        "knowledge_graph":          {},
        "weak_concepts":            [],
        "adjusted_level":           "",
        "difficulties":             [],
        "priority_focus":           [],
        "strategy":                 [],
        "strategy_decisions":       [],
        "exercises":                [],
        "verification":             {},
        # Control
        "next_agent":               "",
        "iteration":                0,
        "agent_trace":              [],
    }

    # 3. Invoke tutor_graph
    try:
        from open_tutorai.agents.langgraph.graph import tutor_graph as _tutor_graph
        config = {"configurable": {"thread_id": session_id}}
        final_state = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _tutor_graph.invoke(initial_state, config=config)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph execution error: {exc}")

    return AdaptivePlanResponse(
        session_id=session_id,
        topic=body.topic,
        adjusted_level=final_state.get("adjusted_level") or body.current_level,
        exercises=final_state.get("exercises", []),
        strategy=final_state.get("strategy", []),
        verification=final_state.get("verification", {}),
        agent_trace=final_state.get("agent_trace", []),
    )


@router.get("/adaptive/session/{session_id}", response_model=AdaptivePlanResponse)
async def get_session(
    session_id: str,
    user=Depends(get_verified_user),
):
    """
    Replay / retrieve the last saved state of a checkpointed session.
    Returns 404 if the session_id is unknown or belongs to another user.
    """
    try:
        from open_tutorai.agents.langgraph.graph import tutor_graph as _tutor_graph
        config = {"configurable": {"thread_id": session_id}}
        snapshot = _tutor_graph.get_state(config)
        state = snapshot.values if snapshot else None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Checkpoint read error: {exc}")

    if not state or state.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    return AdaptivePlanResponse(
        session_id=session_id,
        topic=state.get("topic", ""),
        adjusted_level=state.get("adjusted_level") or state.get("current_level", ""),
        exercises=state.get("exercises", []),
        strategy=state.get("strategy", []),
        verification=state.get("verification", {}),
        agent_trace=state.get("agent_trace", []),
    )
