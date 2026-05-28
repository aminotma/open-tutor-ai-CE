"""FeedbackAgent — updates KG mastery and persists session memories."""
from __future__ import annotations

from datetime import datetime, timezone

from open_tutorai.agents.langgraph.state import TutorGraphState


def feedback_node(state: TutorGraphState) -> dict:
    user_id      = state["user_id"]
    topic        = state["topic"]
    weak         = state.get("weak_concepts", [])
    difficulties = state.get("difficulties", [])
    level        = state.get("adjusted_level") or state["current_level"]
    strategy     = state.get("strategy", [])
    verification = state.get("verification", {})
    objectives   = state.get("learning_objectives", [])

    try:
        from open_webui.internal.db import get_db
        from open_tutorai.services.knowledge_graph import KnowledgeGraphService
        from open_tutorai.models.database import Memory
        from uuid import uuid4

        with get_db() as db:
            # 1. Update mastery for weak concepts (slight positive delta — exercise done)
            for concept in weak:
                KnowledgeGraphService.update_mastery(db, user_id, concept, topic, delta=0.05)

            # 2. Persist session memories
            now_iso = datetime.now(timezone.utc).isoformat()
            meta_base = {"topic": topic, "created_at": now_iso}

            # Behavioral — session summary
            summary = (
                f"Session on '{topic}': level={level}, "
                f"difficulties={', '.join(difficulties[:3])}, "
                f"verification={verification.get('verdict', 'unknown')}."
            )
            db.add(Memory(
                id=uuid4().hex, user_id=user_id, memory_type="behavioral",
                content=summary,
                memory_metadata={**meta_base, "adjusted_level": level,
                                 "verification_verdict": verification.get("verdict")},
            ))

            # Episodic — session event
            db.add(Memory(
                id=uuid4().hex, user_id=user_id, memory_type="episodic",
                content=f"Adaptive session on '{topic}' — {len(weak)} weak concepts identified.",
                memory_metadata=meta_base,
            ))

            # Semantic — one entry per learning objective
            for obj in objectives[:3]:
                db.add(Memory(
                    id=uuid4().hex, user_id=user_id, memory_type="semantic",
                    content=f"Concept worked on: {obj} in context of {topic}.",
                    memory_metadata={**meta_base, "concept": obj, "mastery_level": level},
                ))

            # Procedural — strategy steps
            if strategy:
                steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(strategy[:4]))
                db.add(Memory(
                    id=uuid4().hex, user_id=user_id, memory_type="procedural",
                    content=f"Learning strategy for {topic}:\n{steps_text}",
                    memory_metadata={**meta_base, "steps_count": len(strategy)},
                ))

            # Invalidate summary cache so next session gets a fresh one
            from open_tutorai.services.summarization import SummarizationService
            SummarizationService.invalidate_cache(user_id, topic, db)

            db.commit()

        # Recalculate weak concepts after mastery updates
        with get_db() as db:
            new_weak = KnowledgeGraphService.get_weak_concepts(user_id, topic, db)

    except Exception as exc:
        new_weak = weak
        return {
            "weak_concepts": new_weak,
            "agent_trace": state.get("agent_trace", []) + [f"[FeedbackAgent] error: {exc}"],
            "next_agent":  "END",
            "iteration":   state.get("iteration", 0) + 1,
        }

    trace = state.get("agent_trace", []) + [
        f"[FeedbackAgent] memories persisted, {len(new_weak)} concepts still weak"
    ]
    # Re-diagnose if significant gaps remain after first pass
    next_ag = "orchestrator" if new_weak and state.get("iteration", 0) == 0 else "END"
    return {
        "weak_concepts": new_weak,
        "agent_trace":   trace,
        "next_agent":    next_ag,
        "iteration":     state.get("iteration", 0) + 1,
    }
