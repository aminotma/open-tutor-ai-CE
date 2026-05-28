"""
Database module for OpenTutorAI

This module defines the database tables specific to OpenTutorAI while using
the same database connection as OpenWebUI to maintain compatibility.
"""

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    func,
    ARRAY,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from open_webui.internal.db import Base, get_db, JSONField

PREFIX = "opentutorai_"


class Support(Base):
    """
    Table for storing student support requests.
    Each support request is linked to a chat in the Open WebUI chat table.
    """

    __tablename__ = f"{PREFIX}support"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    short_description = Column(String, nullable=True)
    subject = Column(String, nullable=False)
    custom_subject = Column(String, nullable=True)
    course_id = Column(String, nullable=True)
    learning_objective = Column(Text, nullable=True)
    learning_type = Column(String, nullable=True)
    level = Column(String, nullable=False)
    content_language = Column(String, nullable=True, default="English")
    estimated_duration = Column(String, nullable=True)
    access_type = Column(String, nullable=True, default="Private")
    keywords = Column(String, nullable=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    avatar_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="open")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())
    meta_data = Column(JSONField, nullable=True)

    chat_id = Column(
        String, ForeignKey("chat.id", ondelete="CASCADE"), index=True, nullable=True
    )

    def __repr__(self):
        return f"<Support(id={self.id}, user_id={self.user_id}, title={self.title})>"


class SupportFile(Base):
    """
    Table for storing files attached to support requests.
    """

    __tablename__ = f"{PREFIX}support_file"

    id = Column(String, primary_key=True, index=True)
    support_id = Column(
        String, ForeignKey(f"{PREFIX}support.id", ondelete="CASCADE"), nullable=False
    )
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    support = relationship("Support", backref="files")

    def __repr__(self):
        return f"<SupportFile(id={self.id}, support_id={self.support_id}, filename={self.filename})>"


class Memory(Base):
    """User memories — episodic, behavioral, procedural, session_summary."""

    __tablename__ = f"{PREFIX}memory"

    id              = Column(String, primary_key=True, index=True)
    user_id         = Column(String, nullable=False, index=True)
    memory_type     = Column(String, nullable=False)
    content         = Column(Text, nullable=False)
    memory_metadata = Column(JSONField, nullable=True)
    created_at      = Column(DateTime, nullable=False, server_default=func.now())
    updated_at      = Column(DateTime, nullable=True, onupdate=func.now())

    def __repr__(self):
        return f"<Memory(id={self.id}, user_id={self.user_id}, type={self.memory_type})>"


class KGConcept(Base):
    """Knowledge Graph node — one concept for a given topic."""

    __tablename__ = f"{PREFIX}kg_concept"

    id         = Column(String, primary_key=True, index=True)
    name       = Column(String, nullable=False, index=True)
    topic      = Column(String, nullable=False, index=True)
    difficulty = Column(String, nullable=True)
    last_seen  = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    relations_from = relationship(
        "KGRelation", foreign_keys="KGRelation.source_id",
        back_populates="source", cascade="all, delete-orphan",
    )
    relations_to = relationship(
        "KGRelation", foreign_keys="KGRelation.target_id",
        back_populates="target", cascade="all, delete-orphan",
    )
    masteries = relationship(
        "KGUserMastery", back_populates="concept", cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<KGConcept(name={self.name}, topic={self.topic})>"


class KGRelation(Base):
    """Knowledge Graph edge — relation between two concepts."""

    __tablename__ = f"{PREFIX}kg_relation"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "relation",
                         name="uq_kg_relation_source_target_rel"),
    )

    id        = Column(String, primary_key=True, index=True)
    source_id = Column(String, ForeignKey(f"{PREFIX}kg_concept.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    target_id = Column(String, ForeignKey(f"{PREFIX}kg_concept.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    relation  = Column(String, nullable=False)

    source = relationship("KGConcept", foreign_keys=[source_id], back_populates="relations_from")
    target = relationship("KGConcept", foreign_keys=[target_id], back_populates="relations_to")

    def __repr__(self):
        return f"<KGRelation({self.source_id} -{self.relation}-> {self.target_id})>"


class KGUserMastery(Base):
    """User mastery overlay — mastery level per concept per user."""

    __tablename__ = f"{PREFIX}kg_user_mastery"
    __table_args__ = (
        UniqueConstraint("user_id", "concept_id", name="uq_kg_mastery_user_concept"),
    )

    id         = Column(String, primary_key=True, index=True)
    user_id    = Column(String, nullable=False, index=True)
    concept_id = Column(String, ForeignKey(f"{PREFIX}kg_concept.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    mastery    = Column(Float, nullable=False, default=0.0)
    attempts   = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    last_seen  = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    concept = relationship("KGConcept", back_populates="masteries")

    def __repr__(self):
        return f"<KGUserMastery(user={self.user_id}, concept={self.concept_id}, mastery={self.mastery})>"


def init_database():
    """
    Initialize the database tables for OpenTutorAI.
    Call this function when your app starts to ensure all tables exist.

    This is safe to call even if tables already exist, as SQLAlchemy's
    create_all() only creates tables that don't exist yet.
    """
    from open_webui.internal.db import engine

    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("OpenTutorAI database tables initialized successfully")

    return engine
