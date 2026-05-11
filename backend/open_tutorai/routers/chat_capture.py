from __future__ import annotations

import asyncio
import json as _json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from open_webui.internal.db import get_db
from open_webui.utils.auth import get_verified_user
from open_tutorai.agents.tools import (
    _create_episodic_memory,
    _create_semantic_memory,
    _create_procedural_memory,
    _create_behavioral_memory,
)
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG, get_openai_api_key, get_openai_base_url
from open_tutorai.models.database import Memory

router = APIRouter(tags=["chat-capture"])

# ── LLM response schema ───────────────────────────────────────────────────────

_RESPONSE_TRUNCATION = 600   # chars sent to the LLM — keeps token cost low
_CLASSIFY_TEMPERATURE = 0.0  # deterministic classification

_CLASSIFICATION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a pedagogical memory classifier. "
        "Given a tutor-learner exchange, decide which memory types to create and extract the key content.\n\n"
        "Memory type rules:\n"
        "- semantic   : the tutor's response defines a concept, notion, or explains what something IS\n"
        "- procedural : the tutor's response describes HOW to do something — steps, method, algorithm, strategy\n"
        "Both can be true simultaneously. Both can also be false (e.g. motivational or administrative exchanges).\n\n"
        "Return a JSON object matching the schema exactly. "
        "Leave concept/method/steps as null when the corresponding type is not selected."
    ),
    (
        "human",
        "TOPIC: {topic}\n\n"
        "LEARNER: {user_message}\n\n"
        "TUTOR: {assistant_response}"
    ),
])


class MemoryClassification(BaseModel):
    """Structured output produced by the LLM classifier."""
    memory_types: List[Literal["semantic", "procedural"]] = Field(
        description="Which memory types apply to this exchange (subset, may be empty)"
    )
    concept: Optional[str] = Field(
        None,
        description="Short name of the main concept explained (required when semantic is selected)"
    )
    method: Optional[str] = Field(
        None,
        description="Short name of the method or procedure described (required when procedural is selected)"
    )
    steps: Optional[List[str]] = Field(
        None,
        description="Ordered list of steps (required when procedural is selected)"
    )


async def _classify_exchange(
    user_message: str,
    assistant_response: str,
    topic: str,
) -> MemoryClassification:
    """
    Call a lightweight LLM to classify a chat exchange and extract key content.
    Returns an empty classification on any error — episodic + behavioral are
    always created regardless, so a failure here is non-critical.
    """
    lc_cfg = CONTEXT_RETRIEVAL_CONFIG.get("langchain", {})
    llm = ChatOpenAI(
        model=lc_cfg.get("llm_model", "gpt-4o-mini"),
        temperature=_CLASSIFY_TEMPERATURE,
        api_key=get_openai_api_key(),
        base_url=get_openai_base_url(),
    )
    chain = _CLASSIFICATION_PROMPT | llm.with_structured_output(MemoryClassification)

    try:
        result = await chain.ainvoke({
            "topic": topic or "not specified",
            "user_message": user_message[:300],
            "assistant_response": assistant_response[:_RESPONSE_TRUNCATION],
        })
        return result
    except Exception:
        return MemoryClassification(memory_types=[])


# ── Session summary (auto-generated every N exchanges) ────────────────────────

_SESSION_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a pedagogical session summarizer. "
        "Given a sequence of learner-tutor exchanges, produce a concise paragraph that covers: "
        "which topics were addressed, what the learner understood well, and any difficulties that emerged. "
        "This summary will be injected as context into future tutoring sessions. "
        "Return only the summary paragraph — no preamble, no headings."
    ),
    (
        "human",
        "TOPIC: {topic}\n\nEXCHANGES (most recent last):\n{transcript}"
    ),
])

_CACHE_DIR = Path("backend/data/cache/summaries")


async def _generate_session_summary(user_id: str, chat_id: str, topic: str) -> None:
    """
    Build a transcript from all behavioral memories for this chat, call the LLM,
    and write the result as a JSON file to the summaries cache directory.
    Runs fire-and-forget; any exception is silently swallowed.
    """
    try:
        with get_db() as db:
            all_behavioral = (
                db.query(Memory)
                .filter(Memory.user_id == user_id, Memory.memory_type == "behavioral")
                .order_by(Memory.created_at)
                .all()
            )

        chat_memories = [
            m for m in all_behavioral
            if m.memory_metadata and m.memory_metadata.get("chat_id") == chat_id
        ]
        if not chat_memories:
            return

        # Build transcript from the last 20 exchanges to limit token cost
        transcript = "\n".join(
            f"{i + 1}. {m.content}" for i, m in enumerate(chat_memories[-20:])
        )

        lc_cfg = CONTEXT_RETRIEVAL_CONFIG.get("langchain", {})
        llm = ChatOpenAI(
            model=lc_cfg.get("llm_model", "gpt-4o-mini"),
            temperature=0.2,
            api_key=get_openai_api_key(),
            base_url=get_openai_base_url(),
        )
        result = await (_SESSION_SUMMARY_PROMPT | llm).ainvoke({
            "topic": topic or "general",
            "transcript": transcript,
        })
        summary_text = result.content.strip()

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(datetime.now(timezone.utc).timestamp())
        (_CACHE_DIR / f"{user_id}_{chat_id}_{ts}.json").write_text(
            _json.dumps({
                "id": uuid4().hex,
                "user_id": user_id,
                "chat_id": chat_id,
                "text": summary_text,
                "source_conversation": chat_id,
                "topic": topic or "",
                "created_at": ts,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass  # Non-critical; the main exchange flow is unaffected


# ── Request / Response models ─────────────────────────────────────────────────

class ChatCaptureForm(BaseModel):
    user_message: str = Field(..., min_length=1)
    assistant_response: str = Field(..., min_length=1)
    chat_id: str = Field(..., min_length=1)
    topic: Optional[str] = None
    metadata: Optional[dict] = None


class ChatCaptureResponse(BaseModel):
    created: List[str]
    chat_id: str
    classification: Optional[dict] = None


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/chat/capture", response_model=ChatCaptureResponse)
async def capture_chat_exchange(
    form: ChatCaptureForm,
    user=Depends(get_verified_user),
):
    """
    Classify a question/answer pair with an LLM and persist the appropriate memories:
    - episodic   : always (learner message)
    - semantic   : when LLM detects a concept explanation
    - procedural : when LLM detects a method or step-by-step description
    - behavioral : always (full exchange summary)
    """
    user_id = user.id
    created: List[str] = []
    meta_base = {
        "chat_id": form.chat_id,
        "topic": form.topic or "",
        **(form.metadata or {}),
    }

    # LLM classification runs before opening the DB session (async, no DB needed)
    classification = await _classify_exchange(
        user_message=form.user_message,
        assistant_response=form.assistant_response,
        topic=form.topic or "",
    )

    trigger_summary = False
    with get_db() as db:
        # Episodic — learner message (always)
        episodic = _create_episodic_memory(
            db, user_id,
            f"Learner: {form.user_message[:200]}{'...' if len(form.user_message) > 200 else ''}",
            {**meta_base, "interaction_type": "learner_message", "message_length": len(form.user_message)},
        )
        if episodic:
            created.append("episodic")

        # Semantic — concept explanation
        if "semantic" in classification.memory_types and classification.concept:
            sem = _create_semantic_memory(
                db, user_id,
                classification.concept,
                f"Concept explained by tutor: {classification.concept}",
                {**meta_base, "source": "tutor_explanation", "classifier": "llm"},
            )
            if sem:
                created.append("semantic")

        # Procedural — method / steps
        if "procedural" in classification.memory_types and classification.method:
            steps = classification.steps or [form.assistant_response[:200]]
            proc = _create_procedural_memory(
                db, user_id,
                classification.method,
                steps,
                {**meta_base, "source": "tutor_instruction", "classifier": "llm"},
            )
            if proc:
                created.append("procedural")

        # Behavioral — full exchange (deduplicated)
        behavioral_content = (
            f"Q: {form.user_message[:150]} | "
            f"A: {form.assistant_response[:150]}"
        )
        behavioral = _create_behavioral_memory(
            db, user_id,
            behavioral_content,
            {
                **meta_base,
                "interaction_type": "chat_exchange",
                "llm_types": classification.memory_types,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if behavioral:
            created.append("behavioral")

        db.commit()

        # Check trigger for session summary (while session is still open)
        summaries_cfg = CONTEXT_RETRIEVAL_CONFIG.get("summaries", {})
        trigger = summaries_cfg.get("exchanges_per_summary", 5)
        if trigger > 0:
            chat_count = sum(
                1 for m in db.query(Memory).filter(
                    Memory.user_id == user_id,
                    Memory.memory_type == "behavioral",
                ).all()
                if m.memory_metadata and m.memory_metadata.get("chat_id") == form.chat_id
            )
            trigger_summary = (chat_count > 0 and chat_count % trigger == 0)

    # Fire-and-forget outside the DB session (opens its own fresh session)
    if trigger_summary:
        asyncio.create_task(
            _generate_session_summary(user_id, form.chat_id, form.topic or "")
        )

    return ChatCaptureResponse(
        created=created,
        chat_id=form.chat_id,
        classification=classification.model_dump(),
    )
