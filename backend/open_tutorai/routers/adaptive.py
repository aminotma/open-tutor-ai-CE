"""
Adaptive Tutor router — full agentic phase.

POST /api/v1/adaptive/plan    → launch the LangGraph pipeline (returns interrupted if P1/P2/P3)
POST /api/v1/adaptive/resume  → resume after a human interrupt()
GET  /api/v1/adaptive/session/{session_id} → replay a checkpointed state
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
    topic:                    str
    current_level:            str   = "intermediate"
    language:                 str   = "en"
    subject:                  str   = ""   # 'cs'|'math'|'science'|'language'|'history'
    user_message:             str   = ""
    model:                    str   = ""   # LLM model chosen in the frontend (e.g.: "gpt-4o-mini", "llama3:8b")
    recent_interactions:      list  = Field(default_factory=list)
    feedback_comments:        list  = Field(default_factory=list)
    learning_objectives:      list  = Field(default_factory=list)
    preferred_exercise_types: list  = Field(default_factory=list)
    session_id:               Optional[str] = None


class AdaptivePlanResponse(BaseModel):
    session_id:            str
    topic:                 str
    adjusted_level:        str
    exercises:             list
    strategy:              list
    verification:          dict
    agent_trace:           list
    # New agentic fields
    agent_reasoning:       dict = Field(default_factory=dict)
    tool_selection_log:    list = Field(default_factory=list)
    verification_feedback: list = Field(default_factory=list)
    # Steps 12-14 — Human-in-the-Loop
    interrupted:           bool = False
    interrupt_checkpoint:  Optional[str]  = None   # "P1" | "P2" | "P3"
    interrupt_question:    Optional[str]  = None   # question asked to the human
    interrupt_context:     Optional[dict] = None   # context for the UI


class ResumeRequest(BaseModel):
    """Body of the POST /adaptive/resume request."""
    session_id:     str
    human_feedback: str   # user's response ("oui" / "non" / free text)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/adaptive/plan", response_model=AdaptivePlanResponse)
async def adaptive_plan(
    body: AdaptivePlanRequest,
    user=Depends(get_verified_user),
):
    """
    Launch the full adaptive pipeline.
    May return interrupted=True if a Human-in-the-Loop checkpoint is triggered.
    """
    session_id = body.session_id or uuid4().hex

    # 1. Pre-load context
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
    except Exception:
        rag_docs        = []
        session_summary = ""

    # 2. Initial graph state
    initial_state = {
        "user_id":                  user.id,
        "user_name":                getattr(user, "name", ""),
        "topic":                    body.topic,
        "current_level":            body.current_level,
        "language":                 body.language,
        "subject":                  body.subject,
        "user_message":             body.user_message,
        "llm_model":                body.model,
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
        "tool_results":             [],
        "verification":             {},
        # Agentic fields (Phase B/C/D)
        "agent_reasoning":          {},
        "tool_selection_log":       [],
        "verification_feedback":    [],
        "human_feedback":           "",
        # Control
        "next_agent":               "",
        "iteration":                0,
        "agent_trace":              [],
    }

    # 3. Graph invocation
    return await _invoke_graph(initial_state, session_id)


@router.post("/adaptive/resume", response_model=AdaptivePlanResponse)
async def adaptive_resume(
    body: ResumeRequest,
    user=Depends(get_verified_user),
):
    """
    Step 14 — resume the graph after a Human-in-the-Loop checkpoint.
    Injects human_feedback via Command(resume=...).
    """
    try:
        from open_tutorai.agents.langgraph.graph import tutor_graph as _tutor_graph
        from langgraph.types import Command

        config = {"configurable": {"thread_id": body.session_id}}

        # Verify that the session belongs to the current user
        snapshot = _tutor_graph.get_state(config)
        if not snapshot or not snapshot.values:
            raise HTTPException(status_code=404, detail="Session not found")
        if snapshot.values.get("user_id") != user.id:
            raise HTTPException(status_code=403, detail="Session does not belong to this user")

        final_state = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _tutor_graph.invoke(
                Command(resume=body.human_feedback),
                config=config,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Resume error: {exc}")

    return _build_response(body.session_id, final_state)


@router.get("/adaptive/session/{session_id}", response_model=AdaptivePlanResponse)
async def get_session(
    session_id: str,
    user=Depends(get_verified_user),
):
    """Replay / retrieve the last checkpointed state of a session."""
    try:
        from open_tutorai.agents.langgraph.graph import tutor_graph as _tutor_graph
        config   = {"configurable": {"thread_id": session_id}}
        snapshot = _tutor_graph.get_state(config)
        state    = snapshot.values if snapshot else None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Checkpoint read error: {exc}")

    if not state or state.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    return _build_response(session_id, state)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _invoke_graph(initial_state: dict, session_id: str) -> AdaptivePlanResponse:
    """Invoke the graph and handle Human-in-the-Loop interruptions."""
    try:
        from open_tutorai.agents.langgraph.graph import tutor_graph as _tutor_graph
        config = {"configurable": {"thread_id": session_id}}

        final_state = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _tutor_graph.invoke(initial_state, config=config)
        )
        return _build_response(session_id, final_state)

    except Exception as exc:
        # Step 12 — detect a Human-in-the-Loop interrupt()
        interrupt_info = _extract_interrupt(exc)
        if interrupt_info:
            # Read the partial state saved by the checkpointer
            try:
                from open_tutorai.agents.langgraph.graph import tutor_graph as _tutor_graph
                config   = {"configurable": {"thread_id": session_id}}
                snapshot = _tutor_graph.get_state(config)
                partial  = snapshot.values if snapshot else {}
            except Exception:
                partial = {}

            return AdaptivePlanResponse(
                session_id=session_id,
                topic=partial.get("topic", initial_state.get("topic", "")),
                adjusted_level=partial.get("adjusted_level") or initial_state.get("current_level", ""),
                exercises=partial.get("exercises", []),
                strategy=partial.get("strategy", []),
                verification=partial.get("verification", {}),
                agent_trace=partial.get("agent_trace", []),
                agent_reasoning=partial.get("agent_reasoning", {}),
                tool_selection_log=partial.get("tool_selection_log", []),
                verification_feedback=partial.get("verification_feedback", []),
                interrupted=True,
                interrupt_checkpoint=interrupt_info.get("checkpoint"),
                interrupt_question=interrupt_info.get("question"),
                interrupt_context=interrupt_info.get("context"),
            )

        # Fallback: agentic pipeline unavailable → direct helpers without LLM
        try:
            return _fallback_response(initial_state, session_id, str(exc))
        except Exception as fallback_exc:
            raise HTTPException(
                status_code=500,
                detail=f"Graph error: {exc} | Fallback error: {fallback_exc}",
            )


def _fallback_response(initial_state: dict, session_id: str, reason: str) -> AdaptivePlanResponse:
    """Degraded mode: bypasses LangGraph and calls helpers directly."""
    from open_tutorai.agents.helpers import (
        assess_current_level,
        detect_difficulties,
        plan_learning_strategy,
        generate_exercises,
    )

    topic    = initial_state.get("topic", "")
    level    = initial_state.get("current_level", "intermediate")
    language = initial_state.get("language", "en")

    adjusted    = assess_current_level(
        level,
        initial_state.get("recent_interactions", []),
        initial_state.get("feedback_comments", []),
    )
    difficulties = detect_difficulties(
        topic,
        initial_state.get("recent_interactions", []),
        initial_state.get("feedback_comments", []),
        initial_state.get("learning_objectives", []),
    )
    decisions  = plan_learning_strategy(
        topic, adjusted, difficulties,
        initial_state.get("feedback_comments", []),
        initial_state.get("memory_context", []),
    )
    exercises  = generate_exercises(
        topic, adjusted,
        initial_state.get("learning_objectives", []),
        count=3,
        language=language,
    )

    return AdaptivePlanResponse(
        session_id=session_id,
        topic=topic,
        adjusted_level=adjusted,
        exercises=exercises,
        strategy=[d["action"] for d in decisions],
        verification={"verdict": "skipped", "reason": "fallback mode"},
        agent_trace=[f"[FALLBACK] LangGraph unavailable: {reason[:120]}"],
    )


def _extract_interrupt(exc: Exception) -> dict | None:
    """Extract interrupt info from a GraphInterrupt if that is what it is."""
    try:
        # LangGraph raises GraphInterrupt(interrupts=[Interrupt(value=...)])
        cls_name = type(exc).__name__
        if "Interrupt" not in cls_name:
            return None
        interrupts = getattr(exc, "interrupts", None)
        if not interrupts:
            # Try to extract from args
            if exc.args:
                payload = exc.args[0]
                if isinstance(payload, list) and payload:
                    value = getattr(payload[0], "value", payload[0])
                    return value if isinstance(value, dict) else {"question": str(value)}
            return {}
        first = interrupts[0]
        value = getattr(first, "value", first)
        return value if isinstance(value, dict) else {"question": str(value)}
    except Exception:
        return None


def _build_response(session_id: str, state: dict) -> AdaptivePlanResponse:
    return AdaptivePlanResponse(
        session_id=session_id,
        topic=state.get("topic", ""),
        adjusted_level=state.get("adjusted_level") or state.get("current_level", ""),
        exercises=state.get("exercises", []),
        strategy=state.get("strategy", []),
        verification=state.get("verification", {}),
        agent_trace=state.get("agent_trace", []),
        agent_reasoning=state.get("agent_reasoning", {}),
        tool_selection_log=state.get("tool_selection_log", []),
        verification_feedback=state.get("verification_feedback", []),
        interrupted=False,
    )
