from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import networkx as nx
from sqlalchemy.orm import Session

from open_tutorai.models.database import KGConcept, KGRelation, KGUserMastery

MASTERY_THRESHOLD = 0.4


class KnowledgeGraphService:

    # ── Read ──────────────────────────────────────────────────────────────────

    @staticmethod
    def build_graph(user_id: str, topic: str, db: Session) -> nx.DiGraph:
        """Load concepts + edges for a topic and build a NetworkX DiGraph."""
        concepts = db.query(KGConcept).filter(KGConcept.topic == topic).all()
        concept_ids = {c.id for c in concepts}
        relations = (
            db.query(KGRelation)
            .filter(
                KGRelation.source_id.in_(concept_ids),
                KGRelation.target_id.in_(concept_ids),
            )
            .all()
        )
        masteries = (
            db.query(KGUserMastery)
            .filter(
                KGUserMastery.user_id == user_id,
                KGUserMastery.concept_id.in_(concept_ids),
            )
            .all()
        )
        mastery_map = {m.concept_id: m.mastery for m in masteries}

        G = nx.DiGraph()
        for c in concepts:
            G.add_node(c.name, id=c.id, difficulty=c.difficulty,
                       mastery=mastery_map.get(c.id, 0.0))
        for r in relations:
            src = next((c.name for c in concepts if c.id == r.source_id), None)
            tgt = next((c.name for c in concepts if c.id == r.target_id), None)
            if src and tgt:
                G.add_edge(src, tgt, relation=r.relation)
        return G

    @staticmethod
    def get_weak_concepts(user_id: str, topic: str, db: Session,
                          threshold: float = MASTERY_THRESHOLD) -> list[str]:
        """Return concept names whose mastery is below threshold."""
        concepts = db.query(KGConcept).filter(KGConcept.topic == topic).all()
        concept_ids = {c.id: c.name for c in concepts}
        masteries = (
            db.query(KGUserMastery)
            .filter(
                KGUserMastery.user_id == user_id,
                KGUserMastery.concept_id.in_(concept_ids.keys()),
            )
            .all()
        )
        mastered = {m.concept_id for m in masteries if m.mastery >= threshold}
        return [name for cid, name in concept_ids.items() if cid not in mastered]

    @staticmethod
    def find_prerequisites(concept_name: str, topic: str, db: Session) -> list[str]:
        """Return direct prerequisites (incoming 'requires' edges)."""
        concept = (
            db.query(KGConcept)
            .filter(KGConcept.name == concept_name, KGConcept.topic == topic)
            .first()
        )
        if not concept:
            return []
        prereq_rels = (
            db.query(KGRelation)
            .filter(KGRelation.target_id == concept.id, KGRelation.relation == "requires")
            .all()
        )
        prereq_ids = [r.source_id for r in prereq_rels]
        return [c.name for c in db.query(KGConcept).filter(KGConcept.id.in_(prereq_ids)).all()]

    # ── Write ─────────────────────────────────────────────────────────────────

    @staticmethod
    def upsert_concept(db: Session, name: str, topic: str,
                       difficulty: str = "intermediate") -> KGConcept:
        """Create or return existing concept."""
        concept = (
            db.query(KGConcept)
            .filter(KGConcept.name == name, KGConcept.topic == topic)
            .first()
        )
        if not concept:
            concept = KGConcept(
                id=uuid4().hex, name=name, topic=topic, difficulty=difficulty,
                last_seen=datetime.now(timezone.utc),
            )
            db.add(concept)
            db.flush()
        return concept

    @staticmethod
    def add_relation(db: Session, source_name: str, target_name: str,
                     relation: str, topic: str) -> KGRelation:
        """Add an edge if it does not already exist."""
        src = KnowledgeGraphService.upsert_concept(db, source_name, topic)
        tgt = KnowledgeGraphService.upsert_concept(db, target_name, topic)
        existing = (
            db.query(KGRelation)
            .filter(
                KGRelation.source_id == src.id,
                KGRelation.target_id == tgt.id,
                KGRelation.relation == relation,
            )
            .first()
        )
        if existing:
            return existing
        rel = KGRelation(id=uuid4().hex, source_id=src.id,
                         target_id=tgt.id, relation=relation)
        db.add(rel)
        db.flush()
        return rel

    @staticmethod
    def update_mastery(db: Session, user_id: str, concept_name: str,
                       topic: str, delta: float = 0.1,
                       last_error: str | None = None) -> KGUserMastery:
        """Increment (or create) a user's mastery for a concept."""
        concept = KnowledgeGraphService.upsert_concept(db, concept_name, topic)
        row = (
            db.query(KGUserMastery)
            .filter(KGUserMastery.user_id == user_id,
                    KGUserMastery.concept_id == concept.id)
            .first()
        )
        if not row:
            row = KGUserMastery(
                id=uuid4().hex, user_id=user_id,
                concept_id=concept.id, mastery=0.0, attempts=0,
            )
            db.add(row)

        row.mastery   = round(min(1.0, max(0.0, row.mastery + delta)), 3)
        row.attempts += 1
        row.last_seen = datetime.now(timezone.utc)
        if last_error:
            row.last_error = last_error
        db.flush()
        return row
