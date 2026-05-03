# backend/open_tutorai/agents/tools/reflect.py

from langchain_core.tools import tool
from typing import Optional

_state = None

def bind_state(state):
    global _state
    _state = state


@tool
def tool_reflect(note: Optional[str] = None) -> str:
    """
    Analyse les résultats actuels, ajuste la stratégie si la vérification a échoué,
    et prépare un résumé de session pour la persistance mémoire.
    
    Args:
        note: Note optionnelle à ajouter aux réflexions
    
    Retourne : un résumé structuré prêt pour tool_persist_memory.
    
    Appeler après tool_verify, ou quand le LLM détecte une incohérence.
    """
    global _state
    if not _state:
        return "Erreur: état non initialisé"
    
    verification = _state.verification or {}
    verdict = verification.get("verdict", "unknown")
    score = verification.get("support_score", 0)
    
    adjustments = []
    
    if verdict == "needs_review":
        adjustment = (
            "Réviser la stratégie : certains éléments ne sont pas soutenus par les sources RAG. "
            f"Score actuel : {score:.0%}."
        )
        _state.strategy.append(adjustment)
        _state.difficulties.append("Contenu partiellement non validé par RAG")
        adjustments.append(adjustment)
    
    if note:
        _state.reflection_notes.append(note)
        adjustments.append(f"Note ajoutée : {note}")
    
    _state.tools_called.append("tool_reflect")
    _state.agent_trace.append(f"[tool_reflect] verdict={verdict}, ajustements={len(adjustments)}")
    
    # Préparer le résumé pour tool_persist_memory
    memory_summary = (
        f"Session ReAct : topic={_state.topic}, niveau={_state.adjusted_level}, "
        f"difficultés={', '.join(_state.difficulties[:3])}, "
        f"vérification={verdict} ({score:.0%}), "
        f"outils utilisés={', '.join(set(_state.tools_called))}."
    )
    
    return (
        f"Réflexion terminée.\n"
        f"Ajustements effectués : {len(adjustments)}\n"
        f"Résumé pour mémoire : {memory_summary}\n"
        f"→ Appeler tool_persist_memory avec ce résumé si la session est terminée."
    )