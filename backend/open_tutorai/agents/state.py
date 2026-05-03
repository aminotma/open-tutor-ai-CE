# backend/open_tutorai/agents/state.py
"""
Agentique state — passed explicitly, never stored globally.
Each tool receives state via LangChain RunnableConfig and returns
an updated copy, preserving immutability and re-entrancy.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional


@dataclass
class AgentStep:
    """One reasoning step in the ReAct loop."""
    thought: str
    action: str
    action_input: Dict[str, Any]
    observation: str
    iteration: int = 0


@dataclass
class AdaptiveTutorState:
    """
    Immutable-friendly state shared across the ReAct loop.

    Tools never hold a reference to this object — they receive it
    via config and return a mutated copy.  The AgentRunner merges
    updates after each tool call.
    """

    # ── Inputs ────────────────────────────────────────────────────
    user_id: str
    topic: str
    current_level: str
    recent_interactions: List[Dict[str, Any]] = field(default_factory=list)
    feedback_comments: List[str] = field(default_factory=list)
    learning_objectives: List[str] = field(default_factory=list)
    preferred_exercise_types: List[str] = field(default_factory=list)

    # ── Retrieved context ─────────────────────────────────────────
    memory_context: List[Dict[str, Any]] = field(default_factory=list)
    pedagogical_context: List[Dict[str, Any]] = field(default_factory=list)
    web_search_results: str = ""

    # ── Tool outputs ──────────────────────────────────────────────
    adjusted_level: str = "intermediate"
    difficulties: List[str] = field(default_factory=list)
    priority_focus: List[str] = field(default_factory=list)
    strategy: List[str] = field(default_factory=list)
    strategy_decisions: List[Dict[str, Any]] = field(default_factory=list)
    suggested_exercises: List[Dict[str, Any]] = field(default_factory=list)
    verification: Optional[Dict[str, Any]] = None
    reflection_notes: List[str] = field(default_factory=list)

    # ── ReAct bookkeeping ─────────────────────────────────────────
    react_steps: List[AgentStep] = field(default_factory=list)
    agent_trace: List[str] = field(default_factory=list)
    iteration_count: int = 0
    max_iterations: int = 10
    is_complete: bool = False
    final_answer: Optional[Dict[str, Any]] = None

    # ── Audit ─────────────────────────────────────────────────────
    tools_called: List[str] = field(default_factory=list)
    corrective_cycles: int = 0

    def with_updates(self, **kwargs) -> "AdaptiveTutorState":
        """Return a new state with the given fields replaced."""
        return replace(self, **kwargs)

    def append_trace(self, msg: str) -> "AdaptiveTutorState":
        return replace(self, agent_trace=[*self.agent_trace, msg])

    def mark_tool_called(self, name: str) -> "AdaptiveTutorState":
        return replace(self, tools_called=[*self.tools_called, name])
