"""
Phase 1 unit tests — Hybrid Memory System + Knowledge Graph.

Uses SQLite in-memory so no real DB is needed.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from open_webui.internal.db import Base

# ── Fixture: in-memory SQLite session ────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    from open_tutorai.models.database import Memory, KGConcept, KGRelation, KGUserMastery
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    # Only create the Phase 1 tables — avoids unresolvable FK to OpenWebUI's `chat` table
    for table in [Memory.__table__, KGConcept.__table__,
                  KGRelation.__table__, KGUserMastery.__table__]:
        table.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


# ── Model import tests ────────────────────────────────────────────────────────

def test_models_importable():
    from open_tutorai.models.database import Memory, KGConcept, KGRelation, KGUserMastery
    assert Memory.__tablename__ == "opentutorai_memory"
    assert KGConcept.__tablename__ == "opentutorai_kg_concept"
    assert KGRelation.__tablename__ == "opentutorai_kg_relation"
    assert KGUserMastery.__tablename__ == "opentutorai_kg_user_mastery"


# ── KnowledgeGraphService tests ───────────────────────────────────────────────

def test_upsert_concept_creates(db):
    from open_tutorai.services.knowledge_graph import KnowledgeGraphService
    c = KnowledgeGraphService.upsert_concept(db, "recursion", "algorithms")
    db.commit()
    assert c.name == "recursion"
    assert c.topic == "algorithms"


def test_upsert_concept_idempotent(db):
    from open_tutorai.services.knowledge_graph import KnowledgeGraphService
    c1 = KnowledgeGraphService.upsert_concept(db, "sorting", "algorithms")
    db.commit()
    c2 = KnowledgeGraphService.upsert_concept(db, "sorting", "algorithms")
    db.commit()
    assert c1.id == c2.id


def test_add_relation(db):
    from open_tutorai.services.knowledge_graph import KnowledgeGraphService
    rel = KnowledgeGraphService.add_relation(db, "quick_sort", "sorting", "extends", "algorithms")
    db.commit()
    assert rel.relation == "extends"


def test_add_relation_idempotent(db):
    from open_tutorai.services.knowledge_graph import KnowledgeGraphService
    r1 = KnowledgeGraphService.add_relation(db, "bubble_sort", "sorting", "extends", "algorithms")
    db.commit()
    r2 = KnowledgeGraphService.add_relation(db, "bubble_sort", "sorting", "extends", "algorithms")
    db.commit()
    assert r1.id == r2.id


def test_update_mastery_creates_row(db):
    from open_tutorai.services.knowledge_graph import KnowledgeGraphService
    row = KnowledgeGraphService.update_mastery(db, "user_1", "recursion", "algorithms", delta=0.2)
    db.commit()
    assert row.mastery == pytest.approx(0.2, abs=1e-3)
    assert row.attempts == 1


def test_update_mastery_increments(db):
    from open_tutorai.services.knowledge_graph import KnowledgeGraphService
    KnowledgeGraphService.update_mastery(db, "user_2", "recursion", "algorithms", delta=0.3)
    db.commit()
    row = KnowledgeGraphService.update_mastery(db, "user_2", "recursion", "algorithms", delta=0.3)
    db.commit()
    assert row.mastery == pytest.approx(0.6, abs=1e-3)
    assert row.attempts == 2


def test_mastery_capped_at_1(db):
    from open_tutorai.services.knowledge_graph import KnowledgeGraphService
    for _ in range(5):
        KnowledgeGraphService.update_mastery(db, "user_3", "sorting", "algorithms", delta=0.5)
    db.commit()
    from open_tutorai.models.database import KGUserMastery
    row = db.query(KGUserMastery).filter(KGUserMastery.user_id == "user_3").first()
    assert row.mastery <= 1.0


def test_get_weak_concepts(db):
    from open_tutorai.services.knowledge_graph import KnowledgeGraphService
    KnowledgeGraphService.upsert_concept(db, "binary_search", "algorithms")
    db.commit()
    weak = KnowledgeGraphService.get_weak_concepts("user_1", "algorithms", db, threshold=0.4)
    assert isinstance(weak, list)
    assert "binary_search" in weak


def test_build_graph_nodes(db):
    from open_tutorai.services.knowledge_graph import KnowledgeGraphService
    G = KnowledgeGraphService.build_graph("user_1", "algorithms", db)
    assert G.number_of_nodes() >= 1


def test_find_prerequisites(db):
    from open_tutorai.services.knowledge_graph import KnowledgeGraphService
    KnowledgeGraphService.add_relation(db, "comparison", "recursion", "requires", "algorithms")
    db.commit()
    prereqs = KnowledgeGraphService.find_prerequisites("recursion", "algorithms", db)
    assert "comparison" in prereqs


# ── Memory model tests ────────────────────────────────────────────────────────

def test_memory_create(db):
    from open_tutorai.models.database import Memory
    from uuid import uuid4
    mem = Memory(
        id=uuid4().hex,
        user_id="user_test",
        memory_type="episodic",
        content="Learned about recursion today.",
        memory_metadata={"topic": "algorithms"},
    )
    db.add(mem)
    db.commit()
    fetched = db.query(Memory).filter(Memory.user_id == "user_test").first()
    assert fetched.memory_type == "episodic"
    assert "recursion" in fetched.content
