"""
Phase 6 unit tests — Global Pipeline Integration.
All tests run without DB, LLM, or ChromaDB.
FastAPI endpoints are tested via TestClient with mocked dependencies.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_user(user_id="u1", name="Alice"):
    user = MagicMock()
    user.id   = user_id
    user.name = name
    return user


def _make_app_with_adaptive():
    """Return a minimal FastAPI app with the adaptive router mounted."""
    from open_tutorai.routers.adaptive import router
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _make_app_with_kg():
    """Return a minimal FastAPI app with the knowledge-graph router mounted."""
    from open_tutorai.routers.knowledge_graph import router
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


# ── adaptive.py — Pydantic models ─────────────────────────────────────────────

def test_adaptive_plan_request_defaults():
    from open_tutorai.routers.adaptive import AdaptivePlanRequest
    req = AdaptivePlanRequest(topic="recursion")
    assert req.current_level == "intermediate"
    assert req.language == "en"
    assert req.recent_interactions == []


def test_adaptive_plan_response_fields():
    from open_tutorai.routers.adaptive import AdaptivePlanResponse
    resp = AdaptivePlanResponse(
        session_id="sid1", topic="recursion", adjusted_level="intermediate",
        exercises=[{"id": "e1"}], strategy=["s1"], verification={"verdict": "supported"},
        agent_trace=["[Orchestrator] → END"],
    )
    assert resp.session_id == "sid1"
    assert len(resp.exercises) == 1


# ── adaptive.py — POST /adaptive/plan ─────────────────────────────────────────

def _mock_tutor_graph_invoke(initial_state, config=None):
    """Fake tutor_graph.invoke that returns a plausible final state."""
    return {
        **initial_state,
        "adjusted_level": "intermediate",
        "difficulties": ["gap in recursion"],
        "strategy": [{"id": "D1", "action": "Focus on recursion base cases", "priority": 1}],
        "exercises": [{"id": "ex1", "question": "Explain recursion", "difficulty": "intermediate"}],
        "verification": {"verdict": "supported", "support_score": 0.8},
        "agent_trace": ["[Orchestrator] → memory", "[Orchestrator] → END"],
        "iteration": 1,
    }


def test_adaptive_plan_returns_200():
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_adaptive()
    app.dependency_overrides[get_verified_user] = lambda: _make_user()

    with patch("open_tutorai.routers.adaptive.SummarizationService") as mock_sum, \
         patch("open_tutorai.routers.adaptive.ContextManager") as mock_cm, \
         patch("open_tutorai.routers.adaptive.get_db"):

        mock_sum.get_cached_summary.return_value = "Previous session on recursion."
        ctx = MagicMock()
        ctx.rag_docs = [{"id": "d1", "content": "recursion is a function calling itself", "metadata": {}, "vector_score": 0.9}]
        mock_cm.build_agent_context = AsyncMock(return_value=ctx)

        with patch("open_tutorai.agents.langgraph.graph.tutor_graph") as mock_graph:
            mock_graph.invoke.side_effect = _mock_tutor_graph_invoke

            with TestClient(app) as client:
                resp = client.post("/api/v1/adaptive/plan", json={
                    "topic": "recursion",
                    "current_level": "intermediate",
                })

    assert resp.status_code == 200
    data = resp.json()
    assert data["topic"] == "recursion"
    assert "session_id" in data
    assert isinstance(data["exercises"], list)
    assert isinstance(data["strategy"], list)


def test_adaptive_plan_uses_provided_session_id():
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_adaptive()
    app.dependency_overrides[get_verified_user] = lambda: _make_user()

    with patch("open_tutorai.routers.adaptive.SummarizationService") as mock_sum, \
         patch("open_tutorai.routers.adaptive.ContextManager") as mock_cm, \
         patch("open_tutorai.routers.adaptive.get_db"):

        mock_sum.get_cached_summary.return_value = None
        ctx = MagicMock(); ctx.rag_docs = []
        mock_cm.build_agent_context = AsyncMock(return_value=ctx)

        with patch("open_tutorai.agents.langgraph.graph.tutor_graph") as mock_graph:
            mock_graph.invoke.side_effect = _mock_tutor_graph_invoke

            with TestClient(app) as client:
                resp = client.post("/api/v1/adaptive/plan", json={
                    "topic": "sorting",
                    "session_id": "my-fixed-session",
                })

    assert resp.status_code == 200
    assert resp.json()["session_id"] == "my-fixed-session"


def test_adaptive_plan_graph_error_returns_500():
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_adaptive()
    app.dependency_overrides[get_verified_user] = lambda: _make_user()

    with patch("open_tutorai.routers.adaptive.SummarizationService") as mock_sum, \
         patch("open_tutorai.routers.adaptive.ContextManager") as mock_cm, \
         patch("open_tutorai.routers.adaptive.get_db"):

        mock_sum.get_cached_summary.return_value = None
        ctx = MagicMock(); ctx.rag_docs = []
        mock_cm.build_agent_context = AsyncMock(return_value=ctx)

        with patch("open_tutorai.agents.langgraph.graph.tutor_graph") as mock_graph:
            mock_graph.invoke.side_effect = RuntimeError("graph crashed")

            with TestClient(app) as client:
                resp = client.post("/api/v1/adaptive/plan", json={"topic": "algorithms"})

    assert resp.status_code == 500
    assert "graph crashed" in resp.json()["detail"]


def test_adaptive_plan_context_error_still_runs_graph():
    """If ContextManager fails, plan should still invoke the graph with empty rag_docs."""
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_adaptive()
    app.dependency_overrides[get_verified_user] = lambda: _make_user()

    with patch("open_tutorai.routers.adaptive.SummarizationService", side_effect=Exception("db down")), \
         patch("open_tutorai.routers.adaptive.get_db"):

        with patch("open_tutorai.agents.langgraph.graph.tutor_graph") as mock_graph:
            mock_graph.invoke.side_effect = _mock_tutor_graph_invoke

            with TestClient(app) as client:
                resp = client.post("/api/v1/adaptive/plan", json={"topic": "graphs"})

    assert resp.status_code == 200


# ── adaptive.py — GET /adaptive/session/{id} ─────────────────────────────────

def test_get_session_returns_state():
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_adaptive()
    app.dependency_overrides[get_verified_user] = lambda: _make_user(user_id="u1")

    with patch("open_tutorai.agents.langgraph.graph.tutor_graph") as mock_graph:
        snapshot        = MagicMock()
        snapshot.values = {
            "user_id": "u1", "topic": "graphs", "current_level": "beginner",
            "adjusted_level": "beginner", "exercises": [], "strategy": [],
            "verification": {}, "agent_trace": [],
        }
        mock_graph.get_state.return_value = snapshot

        with TestClient(app) as client:
            resp = client.get("/api/v1/adaptive/session/sess-abc")

    assert resp.status_code == 200
    assert resp.json()["topic"] == "graphs"


def test_get_session_unknown_returns_404():
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_adaptive()
    app.dependency_overrides[get_verified_user] = lambda: _make_user(user_id="u1")

    with patch("open_tutorai.agents.langgraph.graph.tutor_graph") as mock_graph:
        mock_graph.get_state.return_value = None

        with TestClient(app) as client:
            resp = client.get("/api/v1/adaptive/session/does-not-exist")

    assert resp.status_code == 404


def test_get_session_wrong_user_returns_404():
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_adaptive()
    app.dependency_overrides[get_verified_user] = lambda: _make_user(user_id="u2")

    with patch("open_tutorai.agents.langgraph.graph.tutor_graph") as mock_graph:
        snapshot        = MagicMock()
        snapshot.values = {"user_id": "u1", "topic": "t", "exercises": [], "strategy": [],
                           "verification": {}, "agent_trace": [], "adjusted_level": ""}
        mock_graph.get_state.return_value = snapshot

        with TestClient(app) as client:
            resp = client.get("/api/v1/adaptive/session/sess-xyz")

    assert resp.status_code == 404


# ── knowledge_graph.py — Pydantic models ─────────────────────────────────────

def test_kg_response_model():
    from open_tutorai.routers.knowledge_graph import KGResponse, ConceptNode, GraphEdge
    kg = KGResponse(
        topic="algorithms",
        nodes=[ConceptNode(name="recursion", difficulty="intermediate", mastery=0.6)],
        edges=[GraphEdge(source="recursion", target="sorting", relation="requires")],
        weak_concepts=["sorting"],
    )
    assert len(kg.nodes) == 1
    assert kg.weak_concepts == ["sorting"]


# ── knowledge_graph.py — GET /knowledge-graph/{topic} ────────────────────────

def _make_nx_graph():
    import networkx as nx
    G = nx.DiGraph()
    G.add_node("recursion", difficulty="intermediate", mastery=0.3)
    G.add_node("sorting",   difficulty="beginner",     mastery=0.8)
    G.add_edge("recursion", "sorting", relation="requires")
    return G


def test_get_knowledge_graph_returns_200():
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_kg()
    app.dependency_overrides[get_verified_user] = lambda: _make_user()

    with patch("open_tutorai.routers.knowledge_graph.get_db") as mock_db, \
         patch("open_tutorai.routers.knowledge_graph.KnowledgeGraphService") as mock_svc, \
         patch("open_tutorai.routers.knowledge_graph.MASTERY_THRESHOLD", 0.4):

        mock_db.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_db.return_value.__exit__  = MagicMock(return_value=False)
        mock_svc.build_graph.return_value = _make_nx_graph()
        mock_svc.get_weak_concepts.return_value = ["recursion"]

        with TestClient(app) as client:
            resp = client.get("/api/v1/knowledge-graph/algorithms")

    assert resp.status_code == 200
    data = resp.json()
    assert data["topic"] == "algorithms"
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert "recursion" in data["weak_concepts"]


# ── knowledge_graph.py — POST /knowledge-graph/{topic}/concepts ───────────────

def test_add_concept_returns_201():
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_kg()
    app.dependency_overrides[get_verified_user] = lambda: _make_user()

    concept_mock       = MagicMock()
    concept_mock.name  = "memoization"
    concept_mock.difficulty = "intermediate"

    with patch("open_tutorai.routers.knowledge_graph.get_db") as mock_db, \
         patch("open_tutorai.routers.knowledge_graph.KnowledgeGraphService") as mock_svc, \
         patch("open_tutorai.routers.knowledge_graph.MASTERY_THRESHOLD", 0.4):

        ctx = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__  = MagicMock(return_value=False)
        mock_svc.upsert_concept.return_value = concept_mock

        with TestClient(app) as client:
            resp = client.post("/api/v1/knowledge-graph/algorithms/concepts", json={
                "name": "memoization",
                "difficulty": "intermediate",
            })

    assert resp.status_code == 201
    assert resp.json()["name"] == "memoization"


def test_add_concept_with_relation_calls_add_relation():
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_kg()
    app.dependency_overrides[get_verified_user] = lambda: _make_user()

    concept_mock       = MagicMock()
    concept_mock.name  = "dp"
    concept_mock.difficulty = "advanced"

    with patch("open_tutorai.routers.knowledge_graph.get_db") as mock_db, \
         patch("open_tutorai.routers.knowledge_graph.KnowledgeGraphService") as mock_svc, \
         patch("open_tutorai.routers.knowledge_graph.MASTERY_THRESHOLD", 0.4):

        ctx = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__  = MagicMock(return_value=False)
        mock_svc.upsert_concept.return_value = concept_mock

        with TestClient(app) as client:
            resp = client.post("/api/v1/knowledge-graph/algorithms/concepts", json={
                "name": "dp",
                "difficulty": "advanced",
                "relation_to": "recursion",
                "relation_type": "requires",
            })

    assert resp.status_code == 201
    mock_svc.add_relation.assert_called_once()


# ── knowledge_graph.py — PUT /knowledge-graph/{topic}/mastery ────────────────

def test_update_mastery_returns_dict():
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_kg()
    app.dependency_overrides[get_verified_user] = lambda: _make_user()

    mastery_mock          = MagicMock()
    mastery_mock.mastery  = 0.5
    mastery_mock.attempts = 3

    with patch("open_tutorai.routers.knowledge_graph.get_db") as mock_db, \
         patch("open_tutorai.routers.knowledge_graph.KnowledgeGraphService") as mock_svc, \
         patch("open_tutorai.routers.knowledge_graph.MASTERY_THRESHOLD", 0.4):

        ctx = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__  = MagicMock(return_value=False)
        mock_svc.update_mastery.return_value = mastery_mock

        with TestClient(app) as client:
            resp = client.put("/api/v1/knowledge-graph/algorithms/mastery", json={
                "concept_name": "recursion",
                "delta": 0.1,
            })

    assert resp.status_code == 200
    data = resp.json()
    assert data["mastery"] == 0.5
    assert data["attempts"] == 3


# ── knowledge_graph.py — DELETE /knowledge-graph/{topic}/mastery ─────────────

def test_reset_mastery_returns_204():
    from open_webui.utils.auth import get_verified_user
    app = _make_app_with_kg()
    app.dependency_overrides[get_verified_user] = lambda: _make_user()

    with patch("open_tutorai.routers.knowledge_graph.get_db") as mock_db, \
         patch("open_tutorai.routers.knowledge_graph.KGConcept"), \
         patch("open_tutorai.routers.knowledge_graph.KGUserMastery"), \
         patch("open_tutorai.routers.knowledge_graph.MASTERY_THRESHOLD", 0.4):

        ctx = MagicMock()
        ctx.query.return_value.filter.return_value.all.return_value = []
        ctx.query.return_value.filter.return_value.delete.return_value = 0
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__  = MagicMock(return_value=False)

        with TestClient(app) as client:
            resp = client.delete("/api/v1/knowledge-graph/algorithms/mastery")

    assert resp.status_code == 204


# ── main.py router registration ───────────────────────────────────────────────

def test_main_imports_adaptive_router():
    import open_tutorai.routers.adaptive as mod
    assert hasattr(mod, "router")


def test_main_imports_kg_router():
    import open_tutorai.routers.knowledge_graph as mod
    assert hasattr(mod, "router")
