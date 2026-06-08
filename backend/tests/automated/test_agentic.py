"""
S12 — Boucle Verifier→Planner (verification_feedback)
    Métriques : feedback propagé, retry planner sur needs_review, MAX_PLAN_RETRIES respecté

S13 (partie agent) — Agent Reasoning
    Métriques : agent_reasoning peuplé, accumulation itérative
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from open_tutorai.agents.langgraph.orchestrator import _route, MAX_PLAN_RETRIES


# ── Helper métrique ───────────────────────────────────────────────────────────

def _metric(name: str, value: str, threshold: str, passed: bool) -> None:
    icon = "✅" if passed else "❌"
    print(f"OTAI_METRIC | {name:<34} | {value:<16} | seuil {threshold:<14} | {icon}")


# ── État de base complet ──────────────────────────────────────────────────────

def _base_state(**overrides) -> dict:
    state = {
        "user_id": "test_agentic_user", "user_name": "TestUser",
        "topic": "Python boucles", "current_level": "débutant",
        "language": "fr", "user_message": "Donne-moi un exercice.",
        "recent_interactions": [], "feedback_comments": [],
        "learning_objectives": [], "preferred_exercise_types": [],
        "subject": "cs",
        "rag_docs": [], "session_summary": "",
        "memory_context": [], "knowledge_graph": {}, "weak_concepts": [],
        "detected_subject": "", "adjusted_level": "", "difficulties": [],
        "priority_focus": [], "strategy": [], "strategy_decisions": [],
        "exercises": [], "tool_results": [], "verification": {},
        "agent_reasoning": {}, "tool_selection_log": [],
        "verification_feedback": [], "human_feedback": "",
        "llm_model": "gpt-4o-mini",
        "next_agent": "", "iteration": 0, "agent_trace": [],
    }
    state.update(overrides)
    return state


_PHASE1_TRACE = ["[MemoryAgent]", "[KnowledgeAgent]", "[DiagnosticsAgent]"]
_FULL_TRACE   = _PHASE1_TRACE + ["[PlannerAgent]", "[ExerciseAgent]", "[VerifierAgent]"]

_PATCH_GET_LLM = "open_tutorai.agents.langgraph.llm_factory.get_llm"


# ═══════════════════════════════════════════════════════════════════════════════
# S12 — Boucle Verifier→Planner
# ═══════════════════════════════════════════════════════════════════════════════

def test_verifier_no_rag_verdict_no_sources():
    """VerifierAgent retourne verdict=no_sources quand rag_docs est vide."""
    from open_tutorai.agents.langgraph.agents.verifier import verifier_node
    result = verifier_node(_base_state(rag_docs=[]))
    verdict = result["verification"]["verdict"]
    ok = verdict == "no_sources"
    _metric("Verdict sans RAG", verdict, "= no_sources", ok)
    assert ok


def test_verifier_no_rag_feedback_empty():
    """verification_feedback est [] quand aucun RAG doc disponible."""
    from open_tutorai.agents.langgraph.agents.verifier import verifier_node
    result = verifier_node(_base_state(rag_docs=[]))
    fb = result.get("verification_feedback", "ABSENT")
    ok = fb == []
    _metric("verification_feedback sans RAG", str(fb), "= []", ok)
    assert ok, f"Attendu [], reçu : {fb}"


def test_needs_review_retries_planner():
    """_route() retourne 'planner' sur needs_review si < MAX_PLAN_RETRIES tentatives."""
    result = _route(_base_state(
        verification={"verdict": "needs_review"},
        agent_trace=_FULL_TRACE,
    ))
    ok = result == "planner"
    _metric("Retry planner (1 tentative)", result, "= planner", ok)
    assert ok


def test_max_plan_retries_respected():
    """Après MAX_PLAN_RETRIES+1 planners, _route() ne retourne plus 'planner'."""
    extra_planners = ["[PlannerAgent]"] * (MAX_PLAN_RETRIES + 1)
    state = _base_state(
        verification={"verdict": "needs_review"},
        agent_trace=_PHASE1_TRACE + extra_planners + ["[ExerciseAgent]", "[VerifierAgent]"],
    )
    result = _route(state)
    ok = result != "planner"
    _metric(f"MAX_PLAN_RETRIES={MAX_PLAN_RETRIES} respecté", result, "≠ planner", ok)
    assert ok, f"Planner accepté après {MAX_PLAN_RETRIES+1} tentatives — boucle infinie possible"


def test_verification_feedback_propagated_by_llm():
    """VerifierAgent propage specific_feedback depuis la réponse LLM vers le state."""
    from open_tutorai.agents.langgraph.agents.verifier import verifier_node

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.content = json.dumps({
        "verdict": "needs_review",
        "score": 0.40,
        "specific_feedback": ["exercice hors sujet", "manque de progressivité"],
        "unsupported_items": ["item A"],
    })
    mock_llm.invoke.return_value = resp

    rag = [{"content": "Les boucles for permettent d'itérer sur une liste Python.", "metadata": {}}]
    exercises = [{"question": "Qu'est-ce que JavaScript ?"}]

    with patch(_PATCH_GET_LLM, return_value=mock_llm):
        result = verifier_node(_base_state(rag_docs=rag, exercises=exercises))

    fb = result.get("verification_feedback", [])
    ok = isinstance(fb, list) and len(fb) >= 1
    _metric("verification_feedback non vide", str(len(fb)), "≥ 1", ok)
    assert ok, f"Aucun feedback spécifique retourné : {fb}"


def test_verifier_verdict_needs_review_on_low_score():
    """verdict=needs_review quand le score LLM < seuil (0.65)."""
    from open_tutorai.agents.langgraph.agents.verifier import verifier_node

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.content = json.dumps({
        "verdict": "needs_review",
        "score": 0.30,
        "specific_feedback": ["contenu non aligné"],
        "unsupported_items": [],
    })
    mock_llm.invoke.return_value = resp

    rag = [{"content": "Algèbre linéaire.", "metadata": {}}]

    with patch(_PATCH_GET_LLM, return_value=mock_llm):
        result = verifier_node(_base_state(rag_docs=rag))

    verdict = result["verification"]["verdict"]
    ok = verdict == "needs_review"
    _metric("needs_review sur score 0.30", verdict, "= needs_review", ok)
    assert ok


def test_verifier_verdict_supported_on_high_score():
    """verdict=supported et next_agent=feedback quand le score LLM ≥ 0.65."""
    from open_tutorai.agents.langgraph.agents.verifier import verifier_node

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.content = json.dumps({
        "verdict": "supported",
        "score": 0.90,
        "specific_feedback": [],
        "unsupported_items": [],
    })
    mock_llm.invoke.return_value = resp

    rag = [{"content": "Les boucles for permettent d'itérer sur une séquence.", "metadata": {}}]
    exercises = [{"question": "Écris une boucle for qui affiche 1 à 5."}]

    with patch(_PATCH_GET_LLM, return_value=mock_llm):
        result = verifier_node(_base_state(rag_docs=rag, exercises=exercises))

    verdict = result["verification"]["verdict"]
    next_ag  = result.get("next_agent", "")
    ok = verdict == "supported" and next_ag == "feedback"
    _metric("supported → next=feedback", f"{verdict}/{next_ag}", "supported/feedback", ok)
    assert ok


def test_retry_loop_ends_at_feedback():
    """Après MAX retries, la boucle ne bloque pas — routing sort vers END ou feedback."""
    extra_planners = ["[PlannerAgent]", "[ExerciseAgent]", "[VerifierAgent]"] * (MAX_PLAN_RETRIES + 1)
    state = _base_state(
        verification={"verdict": "needs_review"},
        weak_concepts=[],
        agent_trace=_PHASE1_TRACE + extra_planners,
    )
    result = _route(state)
    ok = result in {"END", "feedback"}
    _metric("Sortie boucle MAX retries", result, "END ou feedback", ok)
    assert ok, f"Routage bloqué : {result}"


# ═══════════════════════════════════════════════════════════════════════════════
# S13 (partie agent) — Agent Reasoning
# ═══════════════════════════════════════════════════════════════════════════════

def _make_llm_mock(next_agent: str, reasoning: str = "test reasoning", confidence: float = 0.9):
    mock = MagicMock()
    resp = MagicMock()
    resp.content = json.dumps({"next_agent": next_agent, "reasoning": reasoning, "confidence": confidence})
    mock.invoke.return_value = resp
    return mock


def test_agent_reasoning_populated_after_llm_route():
    """orchestrator_node peuple agent_reasoning avec le texte reasoning du LLM."""
    from open_tutorai.agents.langgraph.orchestrator import orchestrator_node

    with patch(_PATCH_GET_LLM, return_value=_make_llm_mock("memory", reasoning="mémoire non chargée")):
        result = orchestrator_node(_base_state())

    reasoning = result.get("agent_reasoning") or {}
    ok = bool(reasoning) and any("mémoire non chargée" in str(v) for v in reasoning.values())
    _metric("agent_reasoning peuplé", str(bool(ok)), "= True", ok)
    assert ok, f"agent_reasoning vide ou raisonnement manquant : {reasoning}"


def test_agent_reasoning_accumulates_across_iterations():
    """agent_reasoning conserve les entrées des itérations précédentes."""
    from open_tutorai.agents.langgraph.orchestrator import orchestrator_node

    prior_reasoning = {"orchestrator_iter_0": "iter 0 reasoning"}
    state = _base_state(agent_reasoning=prior_reasoning, iteration=1)

    with patch(_PATCH_GET_LLM, return_value=_make_llm_mock("knowledge", reasoning="knowledge next")):
        result = orchestrator_node(state)

    reasoning = result.get("agent_reasoning") or {}
    ok = len(reasoning) >= 2
    _metric("agent_reasoning cumule iter.", str(len(reasoning)), "≥ 2", ok)
    assert ok, f"Nb entrées reasoning: {len(reasoning)}, attendu ≥ 2"


def test_agent_reasoning_absent_on_fallback():
    """Aucun reasoning ajouté quand le LLM échoue et que le fallback est utilisé."""
    from open_tutorai.agents.langgraph.orchestrator import orchestrator_node

    mock = MagicMock()
    mock.invoke.side_effect = Exception("LLM unavailable")

    with patch(_PATCH_GET_LLM, return_value=mock):
        result = orchestrator_node(_base_state())

    reasoning = result.get("agent_reasoning") or {}
    ok = len(reasoning) == 0
    _metric("Pas de reasoning sur fallback", str(len(reasoning)), "= 0", ok)
    assert ok, f"reasoning inattendu en mode fallback : {reasoning}"


def test_agent_reasoning_key_format():
    """La clé agent_reasoning suit le format 'orchestrator_iter_N'."""
    from open_tutorai.agents.langgraph.orchestrator import orchestrator_node

    with patch(_PATCH_GET_LLM, return_value=_make_llm_mock("memory")):
        result = orchestrator_node(_base_state(iteration=3))

    reasoning = result.get("agent_reasoning") or {}
    expected_key = "orchestrator_iter_3"
    ok = expected_key in reasoning
    _metric("Format clé reasoning", str(list(reasoning.keys())), f"contient {expected_key}", ok)
    assert ok, f"Clé '{expected_key}' absente. Clés présentes : {list(reasoning.keys())}"
