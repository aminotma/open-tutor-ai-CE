"""
Phase 5 unit tests — Adaptive Tutor Engine.
Agents are tested with minimal mock state (no DB, no LLM, no ChromaDB).
"""
import pytest
from unittest.mock import patch, MagicMock


# ── helpers.py ────────────────────────────────────────────────────────────────

def test_assess_level_low_scores_downgrades():
    from open_tutorai.agents.helpers import assess_current_level
    interactions = [{"score": 0.2}, {"score": 0.3}]
    result = assess_current_level("intermediate", interactions, [])
    assert result == "beginner"


def test_assess_level_high_scores_upgrades():
    from open_tutorai.agents.helpers import assess_current_level
    interactions = [{"score": 0.9}, {"score": 0.85}]
    result = assess_current_level("beginner", interactions, [])
    assert result == "intermediate"


def test_assess_level_stable_when_mixed():
    from open_tutorai.agents.helpers import assess_current_level
    interactions = [{"score": 0.5}, {"score": 0.6}]
    result = assess_current_level("intermediate", interactions, [])
    assert result == "intermediate"


def test_assess_level_negative_feedback_downgrades():
    from open_tutorai.agents.helpers import assess_current_level
    result = assess_current_level("advanced", [], ["I'm confused", "This is difficult", "stuck"])
    assert result == "intermediate"


def test_detect_difficulties_low_score():
    from open_tutorai.agents.helpers import detect_difficulties
    interactions = [{"score": 0.3, "content": "recursion exercise"}]
    diffs = detect_difficulties("algorithms", interactions, [], [])
    assert any("recursion" in d for d in diffs)


def test_detect_difficulties_negative_feedback():
    from open_tutorai.agents.helpers import detect_difficulties
    diffs = detect_difficulties("algorithms", [], ["I'm stuck on sorting"], [])
    assert any("stuck" in d.lower() or "sorting" in d.lower() for d in diffs)


def test_detect_difficulties_empty_inputs():
    from open_tutorai.agents.helpers import detect_difficulties
    diffs = detect_difficulties("algorithms", [], [], [])
    assert isinstance(diffs, list)


def test_extract_memory_signals():
    from open_tutorai.agents.helpers import extract_memory_signals
    memories = [
        {"content": "algorithms: had difficulty with recursion"},
        {"content": "biology: easy session"},
    ]
    signals = extract_memory_signals("algorithms", memories)
    assert any("difficulty" in s.lower() or "algorithms" in s.lower() for s in signals)


def test_generate_exercises_count():
    from open_tutorai.agents.helpers import generate_exercises
    exs = generate_exercises("recursion", "beginner", ["understand recursion"], count=3)
    assert len(exs) == 3


def test_generate_exercises_fields():
    from open_tutorai.agents.helpers import generate_exercises
    exs = generate_exercises("sorting", "intermediate", ["bubble sort"], count=1)
    assert all(k in exs[0] for k in ["id", "difficulty", "question", "hint", "answer", "skill_target"])


def test_generate_exercises_max_5():
    from open_tutorai.agents.helpers import generate_exercises
    exs = generate_exercises("topic", "beginner", ["obj"] * 10, count=10)
    assert len(exs) <= 5


def test_plan_strategy_returns_decisions():
    from open_tutorai.agents.helpers import plan_learning_strategy
    decisions = plan_learning_strategy("algorithms", "intermediate",
                                       ["gap in recursion"], [], [])
    assert len(decisions) >= 1
    assert all("action" in d and "priority" in d for d in decisions)


def test_is_text_supported_match():
    from open_tutorai.agents.helpers import is_text_supported
    assert is_text_supported("bubble sort algorithm", "bubble sort is a simple sorting algorithm") is True


def test_is_text_supported_no_match():
    from open_tutorai.agents.helpers import is_text_supported
    assert is_text_supported("quantum entanglement physics", "bubble sort algorithm recursion") is False


def test_is_text_supported_empty():
    from open_tutorai.agents.helpers import is_text_supported
    assert is_text_supported("", "some corpus") is False


# ── TutorGraphState ───────────────────────────────────────────────────────────

def test_tutor_graph_state_importable():
    from open_tutorai.agents.langgraph.state import TutorGraphState
    assert TutorGraphState is not None


# ── Orchestrator routing ──────────────────────────────────────────────────────

def test_orchestrator_routes_to_memory_when_empty():
    from open_tutorai.agents.langgraph.orchestrator import _route
    state = {"agent_trace": [], "memory_context": [], "knowledge_graph": {},
             "difficulties": [], "strategy": [], "exercises": [], "verification": {},
             "weak_concepts": [], "iteration": 0, "topic": "t", "current_level": "intermediate"}
    assert _route(state) == "memory"


def test_orchestrator_routes_to_knowledge_after_memory():
    from open_tutorai.agents.langgraph.orchestrator import _route
    state = {"agent_trace": ["[MemoryAgent] loaded 0 memories"],
             "memory_context": [], "knowledge_graph": {},
             "difficulties": [], "strategy": [], "exercises": [], "verification": {},
             "weak_concepts": [], "iteration": 1, "topic": "t", "current_level": "intermediate"}
    assert _route(state) == "knowledge"


def test_orchestrator_routes_to_diagnostics():
    from open_tutorai.agents.langgraph.orchestrator import _route
    state = {"agent_trace": ["[MemoryAgent] loaded 0 memories", "[KnowledgeAgent] loaded"],
             "memory_context": [], "knowledge_graph": {"nodes": []},
             "difficulties": [], "strategy": [], "exercises": [], "verification": {},
             "weak_concepts": [], "iteration": 2, "topic": "t", "current_level": "intermediate"}
    assert _route(state) == "diagnostics"


def test_orchestrator_routes_to_planner_on_needs_review():
    from open_tutorai.agents.langgraph.orchestrator import _route
    state = {"agent_trace": [
                 "[MemoryAgent] loaded 0 memories", "[KnowledgeAgent] loaded",
                 "[DiagnosticsAgent] done", "[PlannerAgent] 1 decisions",
                 "[ExerciseAgent] 1 exercises", "[VerifierAgent] needs_review",
             ],
             "memory_context": [], "knowledge_graph": {"nodes": []},
             "difficulties": ["gap"], "strategy": ["s1"], "exercises": [{"id": "e1"}],
             "verification": {"verdict": "needs_review"}, "weak_concepts": [],
             "iteration": 1, "topic": "t", "current_level": "intermediate"}
    assert _route(state) == "planner"


def test_orchestrator_routes_to_end():
    from open_tutorai.agents.langgraph.orchestrator import _route
    state = {"agent_trace": [
                 "[MemoryAgent] loaded 0 memories", "[KnowledgeAgent] loaded",
                 "[DiagnosticsAgent] done", "[PlannerAgent] 1 decisions",
                 "[ExerciseAgent] 1 exercises", "[VerifierAgent] supported",
             ],
             "memory_context": [], "knowledge_graph": {"nodes": []},
             "difficulties": ["gap"], "strategy": ["s1"], "exercises": [{"id": "e1"}],
             "verification": {"verdict": "supported"}, "weak_concepts": [],
             "iteration": 6, "topic": "t", "current_level": "intermediate"}
    assert _route(state) == "END"


def test_orchestrator_max_iterations_guard():
    from open_tutorai.agents.langgraph.orchestrator import orchestrator_node, MAX_ITERATIONS_SAFETY
    state = {"iteration": MAX_ITERATIONS_SAFETY, "agent_trace": [], "memory_context": [],
             "knowledge_graph": {}, "difficulties": [], "strategy": [],
             "exercises": [], "verification": {}, "weak_concepts": [],
             "topic": "t", "current_level": "intermediate",
             "user_id": "u1", "user_name": "", "language": "en",
             "user_message": "", "recent_interactions": [], "feedback_comments": [],
             "learning_objectives": [], "preferred_exercise_types": [],
             "rag_docs": [], "session_summary": "", "adjusted_level": "",
             "priority_focus": [], "strategy_decisions": [], "next_agent": ""}
    result = orchestrator_node(state)
    assert result["next_agent"] == "END"


# ── diagnostics_node ──────────────────────────────────────────────────────────

def test_diagnostics_node_returns_level_and_difficulties():
    from open_tutorai.agents.langgraph.agents.diagnostics import diagnostics_node
    state = {
        "topic": "algorithms", "current_level": "intermediate",
        "recent_interactions": [{"score": 0.3, "content": "recursion"}],
        "feedback_comments": [], "learning_objectives": ["understand recursion"],
        "memory_context": [], "weak_concepts": [], "agent_trace": [],
    }
    result = diagnostics_node(state)
    assert "adjusted_level" in result
    assert "difficulties" in result
    assert result["next_agent"] == "planner"


# ── planner_node ──────────────────────────────────────────────────────────────

def test_planner_node_returns_strategy():
    from open_tutorai.agents.langgraph.agents.planner import planner_node
    state = {
        "topic": "algorithms", "current_level": "intermediate",
        "adjusted_level": "intermediate", "difficulties": ["gap in recursion"],
        "feedback_comments": [], "memory_context": [], "verification": {},
        "agent_trace": [],
    }
    result = planner_node(state)
    assert "strategy" in result
    assert len(result["strategy"]) >= 1
    assert result["next_agent"] == "exercise"


# ── exercise_node ─────────────────────────────────────────────────────────────

def test_exercise_node_returns_exercises():
    from open_tutorai.agents.langgraph.agents.exercise import exercise_node
    state = {
        "topic": "recursion", "current_level": "intermediate",
        "adjusted_level": "intermediate", "weak_concepts": ["base case"],
        "learning_objectives": ["understand recursion"], "agent_trace": [],
    }
    result = exercise_node(state)
    assert "exercises" in result
    assert len(result["exercises"]) >= 1
    assert result["next_agent"] == "verifier"


# ── verifier_node ─────────────────────────────────────────────────────────────

def test_verifier_node_no_rag_docs():
    from open_tutorai.agents.langgraph.agents.verifier import verifier_node
    state = {
        "topic": "recursion", "rag_docs": [], "exercises": [], "strategy": [],
        "agent_trace": [],
    }
    result = verifier_node(state)
    assert result["verification"]["verdict"] == "no_sources"
    assert result["next_agent"] == "feedback"


def test_verifier_node_supported():
    from open_tutorai.agents.langgraph.agents.verifier import verifier_node
    state = {
        "topic": "recursion",
        "rag_docs": [{"content": "recursion is a technique where a function calls itself repeatedly"}],
        "exercises": [{"question": "explain recursion function"}],
        "strategy": ["understand recursion"],
        "agent_trace": [],
    }
    result = verifier_node(state)
    assert "verification" in result
    assert result["verification"]["support_score"] >= 0


def test_verifier_node_disabled():
    from open_tutorai.agents.langgraph.agents.verifier import verifier_node
    with patch("open_tutorai.agents.langgraph.agents.verifier.CONTEXT_RETRIEVAL_CONFIG",
               {"rag": {"verification_enabled": False, "verification_threshold": 0.65}}):
        state = {"topic": "t", "rag_docs": [], "exercises": [], "strategy": [], "agent_trace": []}
        result = verifier_node(state)
    assert result["verification"]["verdict"] == "disabled"


# ── graph compilation ─────────────────────────────────────────────────────────

def test_graph_compiles():
    from open_tutorai.agents.langgraph.graph import build_graph
    graph = build_graph(use_checkpointer=False)
    assert graph is not None
