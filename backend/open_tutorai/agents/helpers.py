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

_TEMPLATES: dict[str, dict[str, list[tuple]]] = {
    "en": {
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
    },
    "fr": {
        "beginner": [
            ("Définissez le concept de {obj} avec vos propres mots.",
             "Pensez à ce que signifie {obj} dans le contexte de {topic}.",
             "Une explication claire et simple de {obj} en lien avec {topic}."),
            ("Donnez un exemple concret de {obj} dans la vie quotidienne.",
             "Pensez à des situations du quotidien où {obj} apparaît.",
             "Tout exemple réel valide illustrant {obj}."),
        ],
        "intermediate": [
            ("Expliquez le fonctionnement de {obj} dans {topic} et donnez un exemple.",
             "Décomposez le mécanisme étape par étape.",
             "Une explication pas à pas avec un exemple concret."),
            ("Quelles sont les principales différences entre {obj} et un concept voisin ?",
             "Comparez les propriétés clés et les cas d'usage.",
             "Une comparaison mettant en évidence au moins 2 différences importantes."),
        ],
        "advanced": [
            ("Analysez les compromis liés à {obj} dans {topic}. Dans quel cas l'éviteriez-vous ?",
             "Pensez à la complexité, la scalabilité et les cas limites.",
             "Une analyse nuancée couvrant avantages, inconvénients et scénarios spécifiques."),
            ("Concevez une solution utilisant {obj} pour le problème suivant : optimisation de {topic}.",
             "Tenez compte des contraintes et justifiez vos choix de conception.",
             "Une conception complète avec justification des choix."),
        ],
    },
    "ar": {
        "beginner": [
            ("عرِّف مفهوم {obj} بكلماتك الخاصة.",
             "فكّر في معنى {obj} في سياق {topic}.",
             "شرح واضح وبسيط لـ {obj} في إطار {topic}."),
            ("أعطِ مثالاً حقيقياً على {obj} من الحياة اليومية.",
             "فكّر في مواقف يومية تظهر فيها {obj}.",
             "أي مثال حقيقي صحيح يوضّح {obj}."),
        ],
        "intermediate": [
            ("اشرح كيف يعمل {obj} في {topic} مع تقديم مثال.",
             "حلّل الآلية خطوة بخطوة.",
             "شرح تدريجي مع مثال ملموس."),
            ("ما الفروق الرئيسية بين {obj} ومفهوم مشابه؟",
             "قارن الخصائص الأساسية وحالات الاستخدام.",
             "مقارنة تبرز فارقَين أساسيَّين على الأقل."),
        ],
        "advanced": [
            ("حلّل المقايضات المرتبطة بـ {obj} في {topic}. متى ستتجنّبها؟",
             "فكّر في التعقيد وقابلية التوسع والحالات الحدّية.",
             "تحليل دقيق يغطي الإيجابيات والسلبيات والسيناريوهات المحددة."),
            ("صمّم حلاً باستخدام {obj} للمشكلة التالية: تحسين {topic}.",
             "ضع في اعتبارك القيود وبرّر خياراتك.",
             "تصميم كامل مع تبرير الخيارات."),
        ],
    },
    "es": {
        "beginner": [
            ("Define el concepto de {obj} con tus propias palabras.",
             "Piensa en lo que significa {obj} en el contexto de {topic}.",
             "Una explicación clara y sencilla de {obj} relacionada con {topic}."),
            ("Da un ejemplo real de {obj} en la vida cotidiana.",
             "Piensa en situaciones cotidianas donde aparece {obj}.",
             "Cualquier ejemplo real válido que ilustre {obj}."),
        ],
        "intermediate": [
            ("Explica cómo funciona {obj} en {topic} y da un ejemplo.",
             "Desglosa el mecanismo paso a paso.",
             "Una explicación paso a paso con un ejemplo concreto."),
            ("¿Cuáles son las principales diferencias entre {obj} y un concepto relacionado?",
             "Compara las propiedades clave y los casos de uso.",
             "Una comparación que destaque al menos 2 diferencias clave."),
        ],
        "advanced": [
            ("Analiza las ventajas y desventajas de usar {obj} en {topic}. ¿Cuándo lo evitarías?",
             "Piensa en complejidad, escalabilidad y casos límite.",
             "Un análisis detallado que cubra pros, contras y escenarios específicos."),
            ("Diseña una solución usando {obj} para el siguiente problema: optimización de {topic}.",
             "Considera las restricciones y justifica tus decisiones de diseño.",
             "Un diseño completo con justificación de las elecciones."),
        ],
    },
}

# Fallback si la langue n'est pas supportée
_DEFAULT_LANG = "en"


def generate_exercises(
    topic: str,
    level: str,
    objectives: list[str],
    count: int = 3,
    language: str = "en",
) -> list[dict]:
    """
    Generate structured exercises in the learner's language, adapted to level and objectives.
    Returns a list of exercise dicts with: id, difficulty, question, hint, answer, skill_target.
    Supported languages: en, fr, ar, es (falls back to en for others).
    """
    count = min(max(1, count), 5)
    level = level or "intermediate"

    lang_templates = _TEMPLATES.get(language, _TEMPLATES[_DEFAULT_LANG])
    tpls = lang_templates.get(level, lang_templates["intermediate"])

    base = objectives if objectives else [topic]
    objs = [base[i % len(base)] for i in range(count)]

    exercises = []
    for i, obj in enumerate(objs):
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
