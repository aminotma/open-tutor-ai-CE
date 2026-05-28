"""KnowledgeAgent — loads and updates the Knowledge Graph."""
from __future__ import annotations

from open_tutorai.agents.langgraph.state import TutorGraphState


def knowledge_node(state: TutorGraphState) -> dict:
    user_id = state["user_id"]
    topic   = state["topic"]

    try:
        from open_webui.internal.db import get_db
        from open_tutorai.services.knowledge_graph import KnowledgeGraphService

        with get_db() as db:
            weak  = KnowledgeGraphService.get_weak_concepts(user_id, topic, db)
            graph = KnowledgeGraphService.build_graph(user_id, topic, db)

        kg_summary = {
            "weak_concepts": weak,
            "node_count":    graph.number_of_nodes(),
            "edge_count":    graph.number_of_edges(),
            "nodes":         [
                {"name": n, **d}
                for n, d in graph.nodes(data=True)
            ],
        }
    except Exception as exc:
        weak       = []
        kg_summary = {"weak_concepts": [], "node_count": 0, "edge_count": 0, "nodes": []}
        return {
            "knowledge_graph": kg_summary,
            "weak_concepts":   weak,
            "agent_trace": state.get("agent_trace", []) + [f"[KnowledgeAgent] error: {exc}"],
            "next_agent": "diagnostics",
        }

    trace = state.get("agent_trace", []) + [
        f"[KnowledgeAgent] {graph.number_of_nodes()} nodes, {len(weak)} weak"
    ]
    return {
        "knowledge_graph": kg_summary,
        "weak_concepts":   weak,
        "agent_trace":     trace,
        "next_agent":      "diagnostics",
    }
