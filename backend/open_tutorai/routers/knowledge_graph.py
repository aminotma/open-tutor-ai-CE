"""
Knowledge Graph router — Phase 6.

GET    /api/v1/knowledge-graph/{topic}                → read full KG for user+topic
POST   /api/v1/knowledge-graph/{topic}/concepts       → add concept (+ optional relation)
PUT    /api/v1/knowledge-graph/{topic}/mastery        → update mastery for a concept
DELETE /api/v1/knowledge-graph/{topic}/mastery        → reset mastery for user+topic
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from open_webui.internal.db import get_db
from open_webui.utils.auth import get_verified_user
from open_tutorai.services.knowledge_graph import KnowledgeGraphService, MASTERY_THRESHOLD
from open_tutorai.models.database import KGConcept, KGUserMastery

router = APIRouter(tags=["knowledge-graph"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class ConceptNode(BaseModel):
    name: str
    difficulty: str
    mastery: float


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str


class KGResponse(BaseModel):
    topic: str
    nodes: list[ConceptNode]
    edges: list[GraphEdge]
    weak_concepts: list[str]


class ConceptAddRequest(BaseModel):
    name: str
    difficulty: str = "intermediate"
    relation_to: Optional[str] = None
    relation_type: str = "relates_to"


class MasteryUpdateRequest(BaseModel):
    concept_name: str
    delta: float = 0.1
    last_error: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/knowledge-graph/{topic}", response_model=KGResponse)
def get_knowledge_graph(
    topic: str,
    user=Depends(get_verified_user),
):
    """Return the full knowledge graph for the authenticated user and topic."""
    with get_db() as db:
        graph        = KnowledgeGraphService.build_graph(user.id, topic, db)
        weak_concepts = KnowledgeGraphService.get_weak_concepts(user.id, topic, db)

    nodes = [
        ConceptNode(
            name=n,
            difficulty=data.get("difficulty", "intermediate"),
            mastery=round(data.get("mastery", 0.0), 3),
        )
        for n, data in graph.nodes(data=True)
    ]
    edges = [
        GraphEdge(source=u, target=v, relation=data.get("relation", "relates_to"))
        for u, v, data in graph.edges(data=True)
    ]

    return KGResponse(topic=topic, nodes=nodes, edges=edges, weak_concepts=weak_concepts)


@router.post("/knowledge-graph/{topic}/concepts", response_model=ConceptNode, status_code=201)
def add_concept(
    topic: str,
    body: ConceptAddRequest,
    user=Depends(get_verified_user),
):
    """
    Add a concept to the knowledge graph.
    Optionally link it to an existing concept via `relation_to` + `relation_type`.
    """
    with get_db() as db:
        concept = KnowledgeGraphService.upsert_concept(
            db, name=body.name, topic=topic, difficulty=body.difficulty
        )
        if body.relation_to:
            KnowledgeGraphService.add_relation(
                db,
                source_name=body.name,
                target_name=body.relation_to,
                relation=body.relation_type,
                topic=topic,
            )
        db.commit()
        db.refresh(concept)

    return ConceptNode(name=concept.name, difficulty=concept.difficulty, mastery=0.0)


@router.put("/knowledge-graph/{topic}/mastery", response_model=dict)
def update_mastery(
    topic: str,
    body: MasteryUpdateRequest,
    user=Depends(get_verified_user),
):
    """Update (increment/decrement) mastery for one concept."""
    with get_db() as db:
        row = KnowledgeGraphService.update_mastery(
            db,
            user_id=user.id,
            concept_name=body.concept_name,
            topic=topic,
            delta=body.delta,
            last_error=body.last_error,
        )
        db.commit()

    return {"concept": body.concept_name, "mastery": row.mastery, "attempts": row.attempts}


@router.delete("/knowledge-graph/{topic}/mastery", status_code=204)
def reset_mastery(
    topic: str,
    user=Depends(get_verified_user),
):
    """Reset all mastery scores for the authenticated user on a topic."""
    with get_db() as db:
        concepts = db.query(KGConcept).filter(KGConcept.topic == topic).all()
        concept_ids = {c.id for c in concepts}
        deleted = (
            db.query(KGUserMastery)
            .filter(
                KGUserMastery.user_id == user.id,
                KGUserMastery.concept_id.in_(concept_ids),
            )
            .delete(synchronize_session=False)
        )
        db.commit()
