"""
S7  — Routage déterministe (fallback _route)
    Métriques : Task Completion Rate, séquence d'agents, latence

S11 — Routage LLM-first (_llm_route)
    Métriques : LLM Routing Accuracy, agent_reasoning, confidence, fallback déclenché
"""
import json
import time
import pytest
from unittest.mock import patch, MagicMock

from open_tutorai.agents.langgraph.orchestrator import (
    _route,
    orchestrator_node,
    MAX_ITERATIONS_SAFETY,
)


# ── Helper métrique ───────────────────────────────────────────────────────────

def _metric(name: str, value: str, threshold: str, passed: bool) -> None:
    icon = "✅" if passed else "❌"
    print(f"OTAI_METRIC | {name:<32} | {value:<16} | seuil {threshold:<12} | {icon}")


# ── État de base complet (tous les champs TutorGraphState) ────────────────────

def _base_state(**overrides) -> dict:
    state = {
        # Input
        "user_id": "test_routing_user", "user_name": "TestUser",
        "topic": "Python boucles", "current_level": "débutant",
        "language": "fr", "user_message": "Donne-moi un exercice sur les listes Python.",
        "recent_interactions": [], "feedback_comments": [],
        "learning_objectives": [], "preferred_exercise_types": [],
        "subject": "cs",
        # Pre-loaded context
        "rag_docs": [], "session_summary": "",
        # Loaded inside graph
        "memory_context": [], "knowledge_graph": {}, "weak_concepts": [],
        "detected_subject": "",
        # Intermediate outputs
        "adjusted_level": "", "difficulties": [],
        "priority_focus": [], "strategy": [], "strategy_decisions": [],
        "exercises": [], "tool_results": [], "verification": {},
        # Agentic signals (new)
        "agent_reasoning": {}, "tool_selection_log": [],
        "verification_feedback": [], "human_feedback": "",
        # LLM provider (new)
        "llm_model": "gpt-4o-mini",
        # Control
        "next_agent": "", "iteration": 0, "agent_trace": [],
    }
    state.update(overrides)
    return state


# ── Mock LLM helper ───────────────────────────────────────────────────────────

def _make_llm_mock(next_agent: str, reasoning: str = "test", confidence: float = 0.90):
    mock = MagicMock()
    resp = MagicMock()
    resp.content = json.dumps({
        "next_agent": next_agent,
        "reasoning": reasoning,
        "confidence": confidence,
    })
    mock.invoke.return_value = resp
    return mock


# ═══════════════════════════════════════════════════════════════════════════════
# S7 — Routage déterministe (_route fallback)
# ═══════════════════════════════════════════════════════════════════════════════

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


def test_needs_review_retry():
    result = _route(_base_state(
        verification={"verdict": "needs_review"},
        agent_trace=["[MemoryAgent]", "[KnowledgeAgent]", "[DiagnosticsAgent]",
                     "[PlannerAgent]", "[ExerciseAgent]", "[VerifierAgent]"],
    ))
    _metric("Retry sur needs_review", result, "= planner", result == "planner")
    assert result == "planner"


def test_max_iterations_guard():
    result = orchestrator_node(_base_state(iteration=MAX_ITERATIONS_SAFETY))
    ok = result["next_agent"] == "END"
    _metric("Garde MAX_ITERATIONS", result["next_agent"], "= END", ok)
    assert ok


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
    reached_end  = True
    phase1_ok    = actual_sequence[:3] == ["memory", "knowledge", "diagnostics"]

    _metric("Task Completion Rate",   "100%",                  "= 100%",          reached_end)
    _metric("Séquence Phase 1",       str(actual_sequence[:3]), "[mem,know,diag]", phase1_ok)
    _metric("Séquence complète",      str(actual_sequence),    "-",               True)
    _metric("Latence routage",        f"{latency}s",           "< 3.0s",          latency < 3.0)

    assert phase1_ok, f"Phase 1 incorrecte : {actual_sequence[:3]}"
    assert "planner"  in actual_sequence
    assert "exercise" in actual_sequence
    assert "verifier" in actual_sequence
    assert latency < 3.0


# ═══════════════════════════════════════════════════════════════════════════════
# S11 — Routage LLM-first (_llm_route)
# ═══════════════════════════════════════════════════════════════════════════════

_PATCH_GET_LLM = "open_tutorai.agents.langgraph.llm_factory.get_llm"


def test_llm_routing_uses_llm_decision():
    """L'orchestrateur choisit l'agent via LLM (chemin primaire)."""
    with patch(_PATCH_GET_LLM, return_value=_make_llm_mock("memory")):
        result = orchestrator_node(_base_state())
    ok = result["next_agent"] == "memory" and "[LLM]" in str(result["agent_trace"])
    _metric("LLM routing — agent choisi", result["next_agent"], "= memory [LLM]", ok)
    assert ok


def test_llm_routing_agent_reasoning_populated():
    """agent_reasoning contient le raisonnement de l'orchestrateur après appel LLM."""
    with patch(_PATCH_GET_LLM, return_value=_make_llm_mock("memory", reasoning="besoin mémoire d'abord")):
        result = orchestrator_node(_base_state())
    reasoning = result.get("agent_reasoning") or {}
    ok = bool(reasoning) and any("besoin mémoire" in str(v) for v in reasoning.values())
    _metric("agent_reasoning peuplé", str(bool(ok)), "= True", ok)
    assert ok, f"agent_reasoning vide ou raisonnement manquant : {reasoning}"


def test_llm_routing_confidence_in_trace():
    """La confiance (conf=X.XX) apparaît dans agent_trace quand le LLM répond."""
    with patch(_PATCH_GET_LLM, return_value=_make_llm_mock("knowledge", confidence=0.85)):
        result = orchestrator_node(_base_state(agent_trace=["[MemoryAgent] done"]))
    trace_str = str(result["agent_trace"])
    ok = "conf=0.85" in trace_str
    _metric("confidence dans trace", trace_str[-80:], "conf=0.85", ok)
    assert ok, f"conf=0.85 absent de la trace : {trace_str}"


def test_llm_routing_fallback_on_llm_exception():
    """Fallback déterministe (_route) quand le LLM lève une exception."""
    mock = MagicMock()
    mock.invoke.side_effect = Exception("LLM unavailable")
    with patch(_PATCH_GET_LLM, return_value=mock):
        result = orchestrator_node(_base_state())
    ok = result["next_agent"] == "memory" and "[fallback]" in str(result["agent_trace"])
    _metric("Fallback sur exception LLM", result["next_agent"], "= memory [fallback]", ok)
    assert ok


def test_llm_routing_fallback_on_invalid_json():
    """Fallback déterministe quand le LLM retourne du JSON invalide."""
    mock = MagicMock()
    resp = MagicMock()
    resp.content = "not valid json {{ }"
    mock.invoke.return_value = resp
    with patch(_PATCH_GET_LLM, return_value=mock):
        result = orchestrator_node(_base_state())
    ok = result["next_agent"] == "memory" and "[fallback]" in str(result["agent_trace"])
    _metric("Fallback sur JSON invalide", result["next_agent"], "= memory [fallback]", ok)
    assert ok


def test_llm_routing_rejects_unknown_agent():
    """Fallback déclenché quand le LLM retourne un nom d'agent inconnu."""
    with patch(_PATCH_GET_LLM, return_value=_make_llm_mock("agent_inconnu")):
        result = orchestrator_node(_base_state())
    valid = {"memory", "knowledge", "diagnostics", "planner", "exercise", "verifier", "feedback", "END"}
    ok = result["next_agent"] in valid
    _metric("Agent inconnu rejeté", result["next_agent"], "agent valide", ok)
    assert ok, f"Agent invalide accepté : {result['next_agent']}"


def test_llm_routing_accuracy():
    """LLM Routing Accuracy ≥ 80% : ratio d'appels LLM valides sans fallback."""
    valid_responses = [
        _make_llm_mock("memory"),
        _make_llm_mock("knowledge"),
        _make_llm_mock("diagnostics"),
        _make_llm_mock("planner"),
        _make_llm_mock("verifier"),
    ]
    invalid_responses = [
        *(MagicMock(**{"invoke.side_effect": Exception("err")}) for _ in range(1)),
    ]
    all_mocks = valid_responses + invalid_responses

    llm_used_count = 0
    for mock in all_mocks:
        with patch(_PATCH_GET_LLM, return_value=mock):
            result = orchestrator_node(_base_state())
        if "[LLM]" in str(result["agent_trace"]):
            llm_used_count += 1

    accuracy = llm_used_count / len(all_mocks)
    ok = accuracy >= 0.80
    _metric("LLM Routing Accuracy", f"{accuracy:.0%}", "≥ 80%", ok)
    assert ok, f"LLM Routing Accuracy={accuracy:.0%} < seuil 80%"
