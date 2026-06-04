"""PlannerAgent — stratégie d'apprentissage LLM + enrichissement web + auto-critique.

Agentisation : plan_learning_strategy() (règles if/elif) remplacé par un LLM call
qui génère une stratégie raisonnée à partir du contexte complet.
Fallback déterministe conservé si le LLM est indisponible.
"""
from __future__ import annotations

import json

from open_tutorai.agents.langgraph.state import TutorGraphState


def planner_node(state: TutorGraphState) -> dict:
    difficulties          = state.get("difficulties", [])
    verification          = state.get("verification", {})
    verification_feedback = state.get("verification_feedback", [])
    human_feedback        = state.get("human_feedback", "")

    # Étape 10 — re-focus sur les éléments non vérifiés lors d'un retry
    if verification.get("verdict") == "needs_review":
        unsupported = verification.get("unsupported_items", [])
        if unsupported:
            difficulties = [item[:120] for item in unsupported[:3]]
        if verification_feedback:
            difficulties = difficulties + [fb[:120] for fb in verification_feedback[:2]]

    # Étape 14 — intégrer le feedback humain libre de P1
    if human_feedback and human_feedback.lower().strip() not in ("oui", "yes", "y", "o", ""):
        difficulties = difficulties + [f"Human feedback: {human_feedback[:100]}"]

    # ── Planification LLM (agentique) avec fallback déterministe ─────────────
    decisions, strategy, reasoning = _llm_plan(state, difficulties)

    # Étape 7 — enrichissement web si RAG insuffisant
    search_enriched = False
    if len(state.get("rag_docs", [])) < 2:
        strategy, search_enriched = _enrich_with_search(state["topic"], strategy)
        decisions = [{"id": f"D{i+1}", "action": s, "rationale": "web-enriched",
                      "priority": i + 1, "dependencies": []}
                     for i, s in enumerate(strategy)]

    trace = state.get("agent_trace", []) + [
        f"[PlannerAgent] {len(decisions)} decisions"
        + (" (search-enriched)" if search_enriched else "")
        + (" (retry with feedback)" if verification_feedback else "")
        + (" [LLM]" if reasoning else " [fallback]")
    ]

    agent_reasoning = state.get("agent_reasoning") or {}
    if reasoning:
        agent_reasoning = {**agent_reasoning, "planner_llm": reasoning}

    # Auto-critique
    critique = _self_critique(strategy, state)
    if critique:
        agent_reasoning = {**agent_reasoning, "planner": critique}
        trace = trace + [f"[PlannerAgent] self-critique: {critique[:80]}"]

    return {
        "strategy_decisions": decisions,
        "strategy":           strategy,
        "agent_trace":        trace,
        "agent_reasoning":    agent_reasoning,
        "next_agent":         "exercise",
    }


# ── Planification LLM ─────────────────────────────────────────────────────────

def _llm_plan(
    state: TutorGraphState, difficulties: list[str]
) -> tuple[list[dict], list[str], str | None]:
    """
    Génère une stratégie pédagogique via LLM.
    Retourne (decisions, strategy_actions, reasoning).
    Fallback vers plan_learning_strategy() si le LLM échoue.
    """
    try:
        from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG, get_openai_api_key, get_openai_base_url
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        lc_cfg = CONTEXT_RETRIEVAL_CONFIG["langchain"]
        llm = ChatOpenAI(
            model=lc_cfg.get("llm_model", "gpt-4o-mini"),
            temperature=0.2,
            api_key=get_openai_api_key(),
            base_url=get_openai_base_url() or None,
        )

        rag_excerpt = " | ".join(
            d.get("content", "")[:120] for d in state.get("rag_docs", [])[:3]
        ) or "aucun document RAG disponible"

        memory_excerpt = "\n".join(
            m.get("content", "")[:80] for m in state.get("memory_context", [])[:3]
        ) or "aucune mémoire"

        prompt = (
            "You are PlannerAgent, an expert pedagogical strategist.\n\n"
            f"Topic: {state['topic']}\n"
            f"Learner level: {state.get('adjusted_level', state['current_level'])}\n"
            f"Identified difficulties: {difficulties[:5]}\n"
            f"Weak concepts (KG): {state.get('weak_concepts', [])[:4]}\n"
            f"Learning objectives: {state.get('learning_objectives', [])[:3]}\n"
            f"RAG sources (excerpt): {rag_excerpt}\n"
            f"Past memories:\n{memory_excerpt}\n\n"
            "Design a prioritised learning strategy of 3-5 steps to address the difficulties "
            "and achieve the objectives. Each step must be concrete and actionable.\n\n"
            "Respond ONLY with valid JSON (no markdown):\n"
            '{"decisions": [{"id": "D1", "action": "<step>", "rationale": "<why>", '
            '"priority": 1, "dependencies": []}, ...], '
            '"reasoning": "<one sentence summarising your strategy>"}'
        )

        resp = llm.invoke([HumanMessage(content=prompt)])
        data = json.loads(resp.content.strip())

        decisions = data.get("decisions", [])
        if not decisions:
            raise ValueError("empty decisions")

        # Normalise
        normalized = []
        for i, d in enumerate(decisions[:5]):
            normalized.append({
                "id":           d.get("id", f"D{i+1}"),
                "action":       str(d.get("action", ""))[:200],
                "rationale":    str(d.get("rationale", ""))[:200],
                "priority":     int(d.get("priority", i + 1)),
                "dependencies": d.get("dependencies", []),
            })

        strategy  = [d["action"] for d in normalized]
        reasoning = data.get("reasoning", "")
        return normalized, strategy, reasoning

    except Exception:
        # Fallback déterministe
        from open_tutorai.agents.helpers import plan_learning_strategy
        decisions = plan_learning_strategy(
            state["topic"],
            state.get("adjusted_level", state["current_level"]),
            difficulties,
            state.get("feedback_comments", []),
            state.get("memory_context", []),
        )
        return decisions, [d["action"] for d in decisions], None


# ── Enrichissement web ────────────────────────────────────────────────────────

def _enrich_with_search(topic: str, strategy: list[str]) -> tuple[list[str], bool]:
    try:
        from open_tutorai.tools.search_web import search_web
        result = search_web.invoke({"query": topic, "max_results": 2})
        if result.get("success") and result.get("results"):
            titles = [r.get("title", "") for r in result["results"][:2] if r.get("title")]
            if titles:
                return strategy + [f"[web] {t}" for t in titles], True
    except Exception:
        pass
    return strategy, False


# ── Auto-critique ─────────────────────────────────────────────────────────────

def _self_critique(strategy: list[str], state: TutorGraphState) -> str | None:
    try:
        from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG, get_openai_api_key, get_openai_base_url
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        lc_cfg = CONTEXT_RETRIEVAL_CONFIG["langchain"]
        llm = ChatOpenAI(
            model=lc_cfg.get("llm_model", "gpt-4o-mini"),
            temperature=0.0,
            api_key=get_openai_api_key(),
            base_url=get_openai_base_url() or None,
        )
        prompt = (
            "You are PlannerAgent performing a self-critique.\n"
            f"Topic: {state['topic']}, Level: {state.get('adjusted_level', state['current_level'])}\n"
            f"Weak concepts: {state.get('weak_concepts', [])[:3]}\n"
            f"Strategy: {strategy[:4]}\n\n"
            "Is this strategy coherent with the pedagogical objective and learner level? "
            "If not, describe the issue in one sentence. If yes, reply 'OK'."
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        result = resp.content.strip()
        return None if result.upper() == "OK" else result
    except Exception:
        return None
