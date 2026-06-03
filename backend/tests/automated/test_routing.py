"""
S7 — Routage agentique
Métriques : Task Completion Rate, séquence d'agents, latence
"""
import time
import pytest
from open_tutorai.agents.langgraph.orchestrator import _route


# ── Helper métrique ───────────────────────────────────────────────────────────

def _metric(name: str, value: str, threshold: str, passed: bool) -> None:
    icon = "✅" if passed else "❌"
    print(f"OTAI_METRIC | {name:<28} | {value:<14} | seuil {threshold:<10} | {icon}")


# ── État de base minimal ──────────────────────────────────────────────────────

def _base_state(**overrides) -> dict:
    state = {
        "user_id": "test_routing_user", "user_name": "TestUser",
        "topic": "Python boucles", "current_level": "débutant",
        "language": "fr", "user_message": "Donne-moi un exercice sur les listes Python.",
        "recent_interactions": [], "feedback_comments": [],
        "learning_objectives": [], "preferred_exercise_types": [],
        "subject": "cs", "rag_docs": [], "session_summary": "",
        "memory_context": [], "knowledge_graph": {}, "weak_concepts": [],
        "detected_subject": "", "adjusted_level": "", "difficulties": [],
        "priority_focus": [], "strategy": [], "strategy_decisions": [],
        "exercises": [], "tool_results": [], "verification": {},
        "next_agent": "", "iteration": 0, "agent_trace": [],
    }
    state.update(overrides)
    return state


# ── Tests de routage déterministe ─────────────────────────────────────────────

def test_first_agent_is_memory():
    result = _route(_base_state())
    _metric("1er agent (sans trace)", result, "= memory", result == "memory")
    assert result == "memory"


def test_second_agent_is_knowledge():
    result = _route(_base_state(agent_trace=["[MemoryAgent] done"]))
    _metric("2e agent (après memory)", result, "= knowledge", result == "knowledge")
    assert result == "knowledge"


def test_third_agent_is_diagnostics():
    result = _route(_base_state(agent_trace=["[MemoryAgent]", "[KnowledgeAgent]"]))
    _metric("3e agent (après knowledge)", result, "= diagnostics", result == "diagnostics")
    assert result == "diagnostics"


def test_phase2_starts_with_planner():
    result = _route(_base_state(agent_trace=["[MemoryAgent]", "[KnowledgeAgent]", "[DiagnosticsAgent]"]))
    _metric("Phase 2 démarre avec", result, "= planner", result == "planner")
    assert result == "planner"


def test_exercise_follows_planner():
    result = _route(_base_state(agent_trace=["[MemoryAgent]", "[KnowledgeAgent]", "[DiagnosticsAgent]", "[PlannerAgent]"]))
    _metric("Après planner", result, "= exercise", result == "exercise")
    assert result == "exercise"


def test_verifier_follows_exercise():
    result = _route(_base_state(agent_trace=["[MemoryAgent]", "[KnowledgeAgent]", "[DiagnosticsAgent]", "[PlannerAgent]", "[ExerciseAgent]"]))
    _metric("Après exercise", result, "= verifier", result == "verifier")
    assert result == "verifier"


def test_feedback_when_weak_concepts():
    result = _route(_base_state(
        weak_concepts=["boucles for"],
        verification={"verdict": "approved"},
        agent_trace=["[MemoryAgent]", "[KnowledgeAgent]", "[DiagnosticsAgent]",
                     "[PlannerAgent]", "[ExerciseAgent]", "[VerifierAgent]"],
    ))
    _metric("Avec weak_concepts", result, "= feedback", result == "feedback")
    assert result == "feedback"


def test_ends_without_weak_concepts():
    result = _route(_base_state(
        weak_concepts=[],
        verification={"verdict": "approved"},
        agent_trace=["[MemoryAgent]", "[KnowledgeAgent]", "[DiagnosticsAgent]",
                     "[PlannerAgent]", "[ExerciseAgent]", "[VerifierAgent]"],
    ))
    _metric("Sans weak_concepts", result, "= END", result == "END")
    assert result == "END"


def test_max_iterations_guard():
    from open_tutorai.agents.langgraph.orchestrator import orchestrator_node
    result = orchestrator_node(_base_state(iteration=10))
    ok = result["next_agent"] == "END"
    _metric("Garde MAX_ITERATIONS", result["next_agent"], "= END", ok)
    assert ok


# ── Task Completion Rate ──────────────────────────────────────────────────────

def test_task_completion_rate():
    state = _base_state()
    actual_sequence = []
    MAX_STEPS = 20

    t0 = time.time()
    for _ in range(MAX_STEPS):
        next_agent = _route(state)
        if next_agent == "END":
            break
        actual_sequence.append(next_agent)
        state["agent_trace"] = state["agent_trace"] + [f"[{next_agent.capitalize()}Agent] done"]
        if next_agent == "verifier":
            state["verification"] = {"verdict": "approved"}
            state["weak_concepts"] = []
    else:
        pytest.fail("La séquence n'a pas atteint END dans le nombre maximum d'étapes")

    latency = round(time.time() - t0, 4)
    reached_end = True
    phase1_ok   = actual_sequence[:3] == ["memory", "knowledge", "diagnostics"]

    _metric("Task Completion Rate", "100%", "= 100%", reached_end)
    _metric("Séquence Phase 1", str(actual_sequence[:3]), "[memory,know,diag]", phase1_ok)
    _metric("Séquence complète", str(actual_sequence), "-", True)
    _metric("Latence routage", f"{latency}s", "< 3.0s", latency < 3.0)

    assert phase1_ok, f"Phase 1 incorrecte : {actual_sequence[:3]}"
    assert "planner"  in actual_sequence
    assert "exercise" in actual_sequence
    assert "verifier" in actual_sequence
    assert latency < 3.0


def test_needs_review_retry():
    result = _route(_base_state(
        verification={"verdict": "needs_review"},
        agent_trace=["[MemoryAgent]", "[KnowledgeAgent]", "[DiagnosticsAgent]",
                     "[PlannerAgent]", "[ExerciseAgent]", "[VerifierAgent]"],
    ))
    _metric("Retry sur needs_review", result, "= planner", result == "planner")
    assert result == "planner"
