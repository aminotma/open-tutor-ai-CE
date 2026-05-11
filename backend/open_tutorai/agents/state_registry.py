# backend/open_tutorai/agents/state_registry.py
"""
Thread-safe registry that maps a run_id → (AdaptiveTutorState, user_id).

Tools receive the run_id via LangChain RunnableConfig['configurable']['run_id']
and look up their state here instead of using module-level globals.
This makes tools re-entrant and safe under concurrent requests.

DB sessions are NOT stored here — each tool that needs a DB connection opens
a fresh context-managed session via open_webui.internal.db.get_db() directly.
Storing a session here caused stale-connection failures on long ReAct loops.
"""

from __future__ import annotations

import threading
from typing import Any, Dict

from open_tutorai.agents.state import AdaptiveTutorState

_lock = threading.Lock()
_registry: Dict[str, Dict[str, Any]] = {}


def register(run_id: str, state: AdaptiveTutorState, user_id: str) -> None:
    with _lock:
        _registry[run_id] = {"state": state, "user_id": user_id}


def get_state(run_id: str) -> AdaptiveTutorState:
    with _lock:
        return _registry[run_id]["state"]


def get_user_id(run_id: str) -> str:
    with _lock:
        return _registry[run_id]["user_id"]


def update_state(run_id: str, state: AdaptiveTutorState) -> None:
    """Replace the state for a run — called after each tool mutates it."""
    with _lock:
        _registry[run_id]["state"] = state


def deregister(run_id: str) -> None:
    with _lock:
        _registry.pop(run_id, None)
