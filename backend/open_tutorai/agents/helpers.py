"""
Pure helper functions used by the LangGraph agents.
No side effects, no DB calls, no LLM calls — pure computation.
"""
from __future__ import annotations

import difflib
import re
from uuid import uuid4


# ── Level assessment ──────────────────────────────────────────────────────────

def assess_current_level(
    current_level: str,
    recent_interactions: list[dict],
    feedback_comments: list[str],
) -> str:
    """
    Adjust the learner's level based on interaction scores and feedback.
    Returns one of: beginner / intermediate / advanced.
    """
    level = (current_level or "intermediate").lower()
    if level not in ("beginner", "intermediate", "advanced"):
        level = "intermediate"

    scores = [
        float(i.get("score", 0.5))
        for i in recent_interactions
        if i.get("score") is not None
    ]
    negative_keywords = {"struggle", "difficult", "hard", "confused", "don't understand",
                         "ne comprend", "difficile", "bloqué", "problème"}
    positive_keywords = {"understand", "easy", "clear", "got it",
                         "compris", "facile", "ok", "parfait"}

    neg = sum(1 for c in feedback_comments
              if any(k in c.lower() for k in negative_keywords))
    pos = sum(1 for c in feedback_comments
              if any(k in c.lower() for k in positive_keywords))

    avg_score = sum(scores) / len(scores) if scores else 0.5

    if avg_score < 0.4 or neg > pos + 1:
        if level == "advanced":
            return "intermediate"
        if level == "intermediate":
            return "beginner"
    elif avg_score > 0.75 and pos >= neg:
        if level == "beginner":
            return "intermediate"
        if level == "intermediate":
            return "advanced"

    return level


# ── Difficulty detection ──────────────────────────────────────────────────────

def detect_difficulties(
    topic: str,
    recent_interactions: list[dict],
    feedback_comments: list[str],
    learning_objectives: list[str],
) -> list[str]:
    """Extract difficulty signals from interactions and feedback."""
    difficulties = []

    # Low-score interactions
    for inter in recent_interactions:
        score   = inter.get("score")
        content = inter.get("content", "")
        if score is not None and float(score) < 0.5 and content:
            difficulties.append(f"Low score on: {content[:80]}")

    # Negative feedback
    neg_kw = {"struggle", "difficult", "hard", "confused", "stuck",
               "ne comprend", "difficile", "bloqué", "problème", "help"}
    for comment in feedback_comments:
        if any(k in comment.lower() for k in neg_kw):
            difficulties.append(f"Feedback: {comment[:80]}")

    # Unmet objectives
    met_kw = {"understand", "master", "completed", "done", "compris", "maîtrisé"}
    for obj in learning_objectives:
        if not any(k in obj.lower() for k in met_kw):
            difficulties.append(f"Unmet objective: {obj[:80]}")

    return list(dict.fromkeys(difficulties))[:5]


# ── Memory signal extraction ──────────────────────────────────────────────────

def extract_memory_signals(topic: str, memory_context: list[dict]) -> list[str]:
    """Extract difficulty hints from past memories."""
    signals = []
    topic_lower = topic.lower()
    neg_kw = {"struggle", "difficult", "error", "gap", "weak",
               "difficile", "erreur", "lacune"}

    for mem in memory_context:
        content = mem.get("content", "").lower()
        if topic_lower in content:
            for kw in neg_kw:
                if kw in content:
                    signals.append(f"Past difficulty: {mem.get('content', '')[:80]}")
                    break

    return signals[:3]


# ── Exercise generation ───────────────────────────────────────────────────────

def generate_exercises(
    topic: str,
    level: str,
    objectives: list[str],
    count: int = 3,
) -> list[dict]:
    """
    Generate structured exercises adapted to the learner's level and objectives.
    Returns a list of exercise dicts with: id, difficulty, question, hint, answer, skill_target.
    """
    count = min(max(1, count), 5)
    level = level or "intermediate"
    exercises = []

    templates = {
        "beginner": [
            ("Define the concept of {obj} in your own words.",
             "Think about what {obj} means in the context of {topic}.",
             "A clear, simple explanation of {obj} as it relates to {topic}."),
            ("Give one real-world example of {obj}.",
             "Consider everyday situations where {obj} appears.",
             "Any valid real-world example demonstrating {obj}."),
        ],
        "intermediate": [
            ("Explain how {obj} works in {topic} and give an example.",
             "Break down the mechanism step by step.",
             "A step-by-step explanation with a concrete example."),
            ("What are the main differences between {obj} and a related concept?",
             "Compare key properties and use cases.",
             "A comparison highlighting at least 2 key differences."),
        ],
        "advanced": [
            ("Analyse the trade-offs of using {obj} in {topic}. When would you avoid it?",
             "Think about complexity, scalability, and edge cases.",
             "A nuanced analysis covering pros, cons, and specific scenarios."),
            ("Design a solution using {obj} for the following problem: {topic} optimisation.",
             "Consider constraints and justify your design choices.",
             "A complete design with justification of choices."),
        ],
    }

    tpls = templates.get(level, templates["intermediate"])
    base = objectives if objectives else [topic]
    objs = [base[i % len(base)] for i in range(count)]

    for i, obj in enumerate(objs[:count]):
        tpl = tpls[i % len(tpls)]
        exercises.append({
            "id":           uuid4().hex[:8],
            "difficulty":   level,
            "question":     tpl[0].format(obj=obj, topic=topic),
            "hint":         tpl[1].format(obj=obj, topic=topic),
            "answer":       tpl[2].format(obj=obj, topic=topic),
            "skill_target": obj,
        })

    return exercises


# ── Strategy planning ─────────────────────────────────────────────────────────

def plan_learning_strategy(
    topic: str,
    level: str,
    difficulties: list[str],
    feedback_comments: list[str],
    memory_context: list[dict],
) -> list[dict]:
    """
    Build a prioritised list of strategy decisions.
    Returns list of {id, action, rationale, priority, dependencies}.
    """
    decisions = []
    priority  = 1

    if difficulties:
        decisions.append({
            "id":           f"D{priority}",
            "action":       f"Address identified gaps in {topic}: {', '.join(difficulties[:2])}",
            "rationale":    "Targeted remediation of detected weaknesses.",
            "priority":     priority,
            "dependencies": [],
        })
        priority += 1

    level_actions = {
        "beginner":     "Focus on foundational concepts and simple examples",
        "intermediate": "Reinforce with applied exercises and real-world cases",
        "advanced":     "Challenge with analysis, design, and trade-off discussions",
    }
    decisions.append({
        "id":           f"D{priority}",
        "action":       level_actions.get(level, level_actions["intermediate"]),
        "rationale":    f"Adapted to current level: {level}.",
        "priority":     priority,
        "dependencies": [f"D{priority-1}"] if priority > 1 else [],
    })
    priority += 1

    if memory_context:
        decisions.append({
            "id":           f"D{priority}",
            "action":       f"Build on previous sessions: reinforce {topic} continuity",
            "rationale":    "Continuity ensures knowledge consolidation.",
            "priority":     priority,
            "dependencies": [f"D{priority-1}"],
        })

    return decisions


# ── RAG support check ─────────────────────────────────────────────────────────

def is_text_supported(text: str, corpus: str, threshold: float = 0.3) -> bool:
    """Return True if key terms from text appear in the corpus."""
    if not text.strip() or not corpus.strip():
        return False

    words = set(re.findall(r"\w{4,}", text.lower()))
    if not words:
        return True

    corpus_lower = corpus.lower()
    matches = sum(1 for w in words if w in corpus_lower)
    return (matches / len(words)) >= threshold
