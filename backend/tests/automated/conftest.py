"""Fixtures partagées — DB in-memory + ChromaDB éphémère."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="module")
def db():
    from open_tutorai.models.database import Memory, KGConcept, KGRelation, KGUserMastery
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    for table in [Memory.__table__, KGConcept.__table__,
                  KGRelation.__table__, KGUserMastery.__table__]:
        table.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture(scope="module")
def chroma():
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    client = chromadb.EphemeralClient()
    ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    return client.get_or_create_collection("test_scenarios", embedding_function=ef)
