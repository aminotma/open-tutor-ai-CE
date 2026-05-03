# backend/open_tutorai/agents/helpers.py
"""
Pure, stateless helper functions.

No imports from state, no globals.  Every function receives what it
needs as arguments and returns a value.  This makes them trivially
testable and reusable by any tool without coupling.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional


# ── Level helpers ─────────────────────────────────────────────────────────────

LEVEL_ORDER = ["beginner", "intermediate", "advanced"]
NEGATIVE_FEEDBACK_KEYWORDS = [
    "confused", "hard", "difficult", "struggle", "mistake",
    "wrong", "lost", "unclear", "challenge", "stuck",
]


def normalize_level(level: Optional[str]) -> str:
    if not level:
        return "intermediate"
    lower = level.lower()
    return lower if lower in LEVEL_ORDER else "intermediate"


def parse_feedback_difficulties(feedback_comments: List[str]) -> List[str]:
    difficulties = []
    for comment in feedback_comments:
        text = comment.lower()
        if any(kw in text for kw in NEGATIVE_FEEDBACK_KEYWORDS):
            cleaned = text.replace("\n", " ").strip()
            if cleaned:
                difficulties.append(cleaned)
    return difficulties


def assess_current_level(
    current_level: str,
    interactions: Optional[List[Dict[str, Any]]],
    feedback_comments: Optional[List[str]],
) -> str:
    level = normalize_level(current_level)
    if not interactions and not feedback_comments:
        return level

    total_score = 0.0
    scored_items = 0
    difficulty_flags = 0

    if interactions:
        for item in interactions:
            score = item.get("score")
            if score is not None:
                score = max(0.0, min(float(score), 1.0))
                total_score += score
                scored_items += 1
                if score < 0.6:
                    difficulty_flags += 1
            outcome = (item.get("outcome") or "").lower()
            if outcome in {"incorrect", "wrong", "failed"}:
                difficulty_flags += 1

    if feedback_comments:
        difficulty_flags += len(parse_feedback_difficulties(feedback_comments))

    avg = total_score / scored_items if scored_items else 0.7

    if avg >= 0.85 and difficulty_flags == 0:
        if level == "beginner":
            return "intermediate"
        if level == "intermediate":
            return "advanced"
    if avg <= 0.55 or difficulty_flags >= 2:
        if level == "advanced":
            return "intermediate"
        if level == "intermediate":
            return "beginner"

    return level


def detect_difficulties(
    topic: str,
    interactions: Optional[List[Dict[str, Any]]],
    feedback_comments: Optional[List[str]],
    learning_objectives: Optional[List[str]],
) -> List[str]:
    difficulties = []
    if feedback_comments:
        difficulties.extend(parse_feedback_difficulties(feedback_comments))

    if interactions:
        for item in interactions:
            score = item.get("score")
            if score is not None and float(score) < 0.6:
                label = item.get("outcome") or "low performance"
                difficulties.append(f"Difficulté avec l'interaction : {label}")
            content = item.get("content", "")
            if content and topic.lower() in content.lower():
                if score is not None and float(score) < 0.6:
                    difficulties.append(f"Compréhension de {topic} insuffisante")

    if learning_objectives:
        for obj in learning_objectives:
            if any(kw in obj.lower() for kw in ["understand", "comprehend", "maîtriser"]):
                difficulties.append(f"Objectif à clarifier: {obj}")

    unique: List[str] = []
    for d in difficulties:
        if d not in unique:
            unique.append(d)
    return unique[:5]


def extract_memory_signals(topic: str, memory_context: List[Dict[str, Any]]) -> List[str]:
    signals = []
    for m in memory_context:
        content = str(m.get("content", "")).lower()
        if topic.lower() in content:
            preview = str(m.get("content", ""))[:150].replace("\n", " ")
            signals.append(f"Mémoire pertinente : {preview}")
    return signals[:2]


# ── Exercise generation ───────────────────────────────────────────────────────

def build_exercise(topic: str, level: str, objective: Optional[str], index: int) -> Dict[str, str]:
    descriptor = {"beginner": "simple", "intermediate": "standard", "advanced": "challenging"}[level]
    if objective:
        question = f"Exercice {index}: Propose un exercice {descriptor} sur {topic.capitalize()} axé sur {objective}."
    else:
        question = f"Exercice {index}: Propose un exercice {descriptor} sur {topic.capitalize()} avec correction pas à pas."
    return {
        "id": f"exercise_{index}",
        "difficulty": level,
        "question": question,
        "hint": f"Réfléchis aux éléments fondamentaux de {topic}.",
        "answer": f"Réponse attendue pour l'exercice {index} sur {topic}.",
        "skill_target": objective or f"Maîtrise de {topic}",
    }


def generate_exercises(
    topic: str,
    level: str,
    learning_objectives: Optional[List[str]],
    count: int = 3,
) -> List[Dict[str, Any]]:
    objectives = learning_objectives or []
    count = min(count, 5)
    return [
        build_exercise(topic, level, objectives[i - 1] if i - 1 < len(objectives) else None, i)
        for i in range(1, count + 1)
    ]


# ── Strategy planning ─────────────────────────────────────────────────────────

def plan_learning_strategy(
    topic: str,
    adjusted_level: str,
    difficulties: List[str],
    feedback_comments: Optional[List[str]],
    memory_context: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    decisions: List[Dict[str, Any]] = []
    priority = 1

    if difficulties:
        primary = difficulties[0]
        decisions += [
            {
                "id": "focus_primary_difficulty",
                "action": f"Se concentrer sur la difficulté principale : {primary}.",
                "rationale": f"Difficulté prioritaire détectée : {primary}.",
                "priority": priority,
                "dependencies": [],
            },
            {
                "id": "review_concept",
                "action": f"Revoir le concept de base lié à {topic} avant de proposer de nouveaux exercices.",
                "rationale": "Un rappel conceptuel renforce la compréhension.",
                "priority": priority + 1,
                "dependencies": ["focus_primary_difficulty"],
            },
            {
                "id": "generate_guided_exercises",
                "action": f"Proposer des exercices guidés adaptés au niveau {adjusted_level}.",
                "rationale": "La pratique guidée aide à corriger les erreurs.",
                "priority": priority + 2,
                "dependencies": ["review_concept"],
            },
        ]
        priority += 3
    else:
        decisions += [
            {
                "id": "maintain_progress",
                "action": f"Niveau stable ({adjusted_level}). Continuer avec des exercices progressifs sur {topic}.",
                "rationale": "La progression régulière consolide les acquis.",
                "priority": priority,
                "dependencies": [],
            },
            {
                "id": "reinforce_acquis",
                "action": "Renforcer les acquis avec une pratique ciblée et un auto-test.",
                "rationale": "La consolidation détecte les faiblesses émergentes.",
                "priority": priority + 1,
                "dependencies": ["maintain_progress"],
            },
        ]
        priority += 2

    if feedback_comments:
        combined = " ".join(feedback_comments[:2])
        decisions.append({
            "id": "consider_feedback",
            "action": f"Prendre en compte : {combined}.",
            "rationale": "Le feedback fournit un contexte précieux.",
            "priority": priority,
            "dependencies": [],
        })
        priority += 1

    if memory_context:
        decisions.append({
            "id": "leverage_memory",
            "action": "Exploiter les mémoires antérieures pour adapter le plan.",
            "rationale": "Les mémoires révèlent les difficultés récurrentes.",
            "priority": priority,
            "dependencies": [],
        })

    return decisions


# ── RAG verification ──────────────────────────────────────────────────────────

def tokenize(text: str) -> List[str]:
    return re.findall(r"\w{4,}", text.lower())


def is_text_supported(candidate: str, source_corpus: str, threshold: float = 0.15) -> bool:
    tokens = tokenize(candidate)
    if not tokens or not source_corpus:
        return False
    source_tokens = set(tokenize(source_corpus))
    matches = sum(1 for t in tokens if t in source_tokens)
    return (matches / len(tokens)) >= threshold
