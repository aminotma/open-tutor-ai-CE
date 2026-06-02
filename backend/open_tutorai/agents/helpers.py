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


# ── Subject detection ─────────────────────────────────────────────────────────

# Keywords per subject — order matters: more specific first
_SUBJECT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("cs", [
        "algorithm", "code", "coding", "python", "javascript", "java", "sql",
        "recursion", "function", "class", "loop", "array", "sorting", "debug",
        "algorithme", "récursion", "boucle", "tableau", "trier", "fonction",
        "программирование", "código",
    ]),
    ("math", [
        "intégrale", "dérivée", "équation", "matrice", "vecteur", "probabilité",
        "limite", "suite", "polynôme", "géométrie", "trigonométrie", "logarithme",
        "integral", "derivative", "equation", "matrix", "vector", "probability",
        "limit", "polynomial", "geometry", "trigonometry", "logarithm",
    ]),
    ("science", [
        "physique", "chimie", "biologie", "énergie", "force", "vitesse",
        "atome", "molécule", "réaction", "gravité", "électricité", "thermodynamique",
        "physics", "chemistry", "biology", "energy", "force", "velocity",
        "atom", "molecule", "reaction", "gravity", "electricity",
    ]),
    ("language", [
        "grammaire", "conjugaison", "orthographe", "rédaction", "lecture",
        "dictée", "traduction", "vocabulaire", "syntaxe", "phrase",
        "grammar", "conjugation", "spelling", "writing", "reading",
        "dictation", "translation", "vocabulary", "syntax", "sentence",
        "النحو", "الإملاء", "gramática",
    ]),
    ("history", [
        "histoire", "révolution", "guerre", "siècle", "empire", "civilisation",
        "chronologie", "événement", "géographie", "carte", "pays", "continent",
        "history", "revolution", "war", "century", "empire", "civilization",
        "timeline", "event", "geography", "map", "country", "continent",
    ]),
]


def detect_subject(topic: str, weak_concepts: list[str] | None = None) -> str | None:
    """
    Infer the academic subject from the topic and weak concepts using keyword matching.

    Returns one of: 'cs', 'math', 'science', 'language', 'history', or None.
    None means the subject is ambiguous — caller should fall back to generic exercises.
    """
    text = " ".join(filter(None, [topic] + (weak_concepts or []))).lower()
    scores: dict[str, int] = {}
    for subject, keywords in _SUBJECT_KEYWORDS:
        hit = sum(1 for kw in keywords if kw in text)
        if hit:
            scores[subject] = hit

    if not scores:
        return None
    best = max(scores, key=lambda s: scores[s])
    # Require at least 2 keyword hits to avoid false positives on short topics
    return best if scores[best] >= 2 else list(scores.keys())[0] if len(scores) == 1 else None


# ── Typed exercise generation (subject-aware) ─────────────────────────────────

# Starter code stubs for CS coding exercises — parameterised by level
_CS_STUBS: dict[str, str] = {
    "beginner": (
        "def exercice(valeur):\n"
        "    # {obj}\n"
        "    return valeur\n\n"
        "print(exercice(5))"
    ),
    "intermediate": (
        "def resoudre(donnees):\n"
        "    \"\"\"{obj}\"\"\"\n"
        "    resultat = []\n"
        "    for item in donnees:\n"
        "        resultat.append(item)\n"
        "    return resultat\n\n"
        "print(resoudre([1, 2, 3]))"
    ),
    "advanced": (
        "def optimiser(donnees, contrainte=None):\n"
        "    \"\"\"{obj}\"\"\"\n"
        "    pass\n\n"
        "print(optimiser([10, 5, 3, 8], contrainte=2))"
    ),
}

# Math expressions by level — used when no keyword hint matches
_MATH_EXPR_BY_LEVEL: dict[str, str] = {
    "beginner":     "2**8",
    "intermediate": "solve(x**2 - 5*x + 6, x)",
    "advanced":     "integrate(x**3 - 2*x, x)",
}

# Math expression hints derived from the objective/topic text
_MATH_EXPR_HINTS: list[tuple[list[str], str]] = [
    (["dérivée", "derivative", "diff"],      "diff(x**3 - 2*x**2 + x, x)"),
    (["intégrale", "integral", "integrat"],  "integrate(x**2 + 1, x)"),
    (["équation", "equation", "solve"],      "solve(x**2 - 4*x + 3, x)"),
    (["limite", "limit", "lim"],             "limit(sin(x)/x, x, 0)"),
    (["matrice", "matrix"],                  "Matrix([[1,2],[3,4]]).det()"),
    (["probabilité", "probability"],         "Rational(3, 4) * Rational(1, 2)"),
    (["factorielle", "factorial"],           "factorial(6)"),
    (["suite", "sequence"],                  "sum(1/n**2 for n in range(1, 101))"),
]

# Sample sentences for language dictation by level
_LANG_SAMPLES: dict[str, str] = {
    "beginner":     "Le chat mange du poisson.",
    "intermediate": "Les élèves ont bien travaillé pendant toute la semaine.",
    "advanced":     "Bien que la situation fût complexe, ils parvinrent à trouver une solution élégante.",
}

# Keywords that indicate the user wants a visual (chart) rather than a pure computation
_VIZ_KEYWORDS: frozenset[str] = frozenset({
    "parabole", "courbe", "graphe", "graphique", "tracer", "trace",
    "visualis", "représent", "repres", "dessiner", "afficher",
    "plot", "draw", "graph", "curve", "f(x)", "fonction",
})


def _wants_chart(text: str) -> bool:
    """Return True if *text* contains at least one visualisation keyword."""
    tl = text.lower()
    return any(kw in tl for kw in _VIZ_KEYWORDS)


# Chart payloads for history timelines and math functions
_CHART_MATH_FUNCTION: dict[str, dict] = {
    "beginner":     {"expr": "x**2",          "x_min": -4, "x_max": 4},
    "intermediate": {"expr": "x**3 - 3*x",    "x_min": -3, "x_max": 3},
    "advanced":     {"expr": "sin(x)*exp(-x/5)", "x_min": 0, "x_max": 20},
}


def _pick_math_expression(text: str, level: str) -> str:
    """Return the most relevant sympy expression for a math exercise."""
    text_lower = text.lower()
    for keywords, expr in _MATH_EXPR_HINTS:
        if any(kw in text_lower for kw in keywords):
            return expr
    return _MATH_EXPR_BY_LEVEL.get(level, _MATH_EXPR_BY_LEVEL["intermediate"])


def generate_typed_exercises(
    topic: str,
    subject: str,
    level: str,
    objectives: list[str],
    count: int = 3,
    language: str = "en",
) -> list[dict]:
    """
    Generate exercises enriched with tool-trigger fields based on the academic subject.

    Each exercise includes `type` and `subject` so that `_run_tool_for_exercise()`
    in ExerciseAgent can route to the correct tool automatically.

    Subject → tool mapping:
        cs       → coding  → live_code_evaluation  (starter_code)
        math     → math    → math_evaluator        (expression)
        science  → chart   → generate_chart        (chart_payload) at advanced
                  math    → math_evaluator        at beginner/intermediate
        language → dictation → grammar_checker    (sample_text)
        history  → chart   → generate_chart        (timeline) or mcq + search_web
    """
    import json as _json  # noqa: PLC0415

    count = min(max(1, count), 5)
    level = level or "intermediate"
    base_objs = objectives if objectives else [topic]
    objs = [base_objs[i % len(base_objs)] for i in range(count)]
    obj_text = " ".join(objs)

    exercises: list[dict] = []

    for i, obj in enumerate(objs):
        ex_id = uuid4().hex[:8]
        base = {
            "id":          ex_id,
            "subject":     subject,
            "difficulty":  level,
            "skill_target": obj,
        }

        # ── CS: coding exercise ───────────────────────────────────────────
        if subject == "cs":
            stub = _CS_STUBS.get(level, _CS_STUBS["intermediate"]).format(obj=obj[:60])
            base.update({
                "type":         "coding",
                "question":     _localise("cs_question", language, obj=obj, topic=topic),
                "hint":         _localise("cs_hint",     language, obj=obj, topic=topic),
                "answer":       _localise("cs_answer",   language, obj=obj, topic=topic),
                "starter_code": stub,
                "code_language": "python",
            })

        # ── Math: chart if visualisation keywords, otherwise symbolic eval ──
        elif subject == "math":
            if _wants_chart(obj + " " + topic):
                chart_data = _CHART_MATH_FUNCTION.get(level, _CHART_MATH_FUNCTION["intermediate"])
                payload = _json.dumps({
                    **chart_data,
                    "title": f"{topic} — {obj[:40]}",
                    "xlabel": "x", "ylabel": "f(x)",
                })
                base.update({
                    "type":          "chart",
                    "question":      _localise("chart_question", language, obj=obj, topic=topic),
                    "hint":          _localise("chart_hint",     language, obj=obj, topic=topic),
                    "answer":        _localise("chart_answer",   language, obj=obj, topic=topic),
                    "chart_type":    "function",
                    "chart_payload": payload,
                })
            else:
                expr = _pick_math_expression(obj + " " + topic, level)
                base.update({
                    "type":       "math",
                    "question":   _localise("math_question", language, obj=obj, topic=topic),
                    "hint":       _localise("math_hint",     language, obj=obj, topic=topic),
                    "answer":     expr,
                    "expression": expr,
                })

        # ── Science: formula at beginner/intermediate, chart at advanced ──
        elif subject == "science":
            if level == "advanced":
                payload = _json.dumps({
                    **_CHART_MATH_FUNCTION[level],
                    "title": f"{topic} — {obj[:40]}",
                    "xlabel": "x", "ylabel": "f(x)",
                })
                base.update({
                    "type":          "chart",
                    "question":      _localise("chart_question", language, obj=obj, topic=topic),
                    "hint":          _localise("chart_hint",     language, obj=obj, topic=topic),
                    "answer":        _localise("chart_answer",   language, obj=obj, topic=topic),
                    "chart_type":    "function",
                    "chart_payload": payload,
                })
            else:
                expr = _pick_math_expression(obj + " " + topic, level)
                base.update({
                    "type":       "math",
                    "question":   _localise("science_question", language, obj=obj, topic=topic),
                    "hint":       _localise("science_hint",     language, obj=obj, topic=topic),
                    "answer":     expr,
                    "expression": expr,
                })

        # ── Language: dictation / grammar check ───────────────────────────
        elif subject == "language":
            sample = _LANG_SAMPLES.get(level, _LANG_SAMPLES["intermediate"])
            lang_code = {"fr": "fr", "ar": "ar", "es": "es"}.get(language, "fr")
            base.update({
                "type":        "dictation",
                "question":    _localise("lang_question", language, obj=obj, topic=topic),
                "hint":        _localise("lang_hint",     language, obj=obj, topic=topic),
                "answer":      sample,
                "sample_text": sample,
                "lang_code":   lang_code,
            })

        # ── History: timeline chart or MCQ with web search ────────────────
        elif subject == "history":
            if i % 2 == 0:
                payload = _json.dumps({
                    "events": [
                        {"year": 1789, "label": "Révolution française"},
                        {"year": 1815, "label": "Waterloo"},
                        {"year": 1848, "label": "Printemps des peuples"},
                    ],
                    "title": f"Chronologie — {topic}",
                })
                base.update({
                    "type":          "chart",
                    "question":      _localise("history_chart_q", language, obj=obj, topic=topic),
                    "hint":          _localise("history_chart_h", language, obj=obj, topic=topic),
                    "answer":        _localise("history_chart_a", language, obj=obj, topic=topic),
                    "chart_type":    "timeline",
                    "chart_payload": payload,
                })
            else:
                base.update({
                    "type":         "mcq",
                    "question":     _localise("history_mcq_q", language, obj=obj, topic=topic),
                    "hint":         _localise("history_mcq_h", language, obj=obj, topic=topic),
                    "answer":       _localise("history_mcq_a", language, obj=obj, topic=topic),
                    "search_query": f"{obj} {topic}",
                })

        # ── Fallback (unknown subject) ────────────────────────────────────
        else:
            base.update({
                "type":     "explain",
                "question": f"Explain {obj} in the context of {topic}.",
                "hint":     f"Think about the key properties of {obj}.",
                "answer":   f"A clear explanation of {obj} linked to {topic}.",
            })

        exercises.append(base)

    return exercises


# ── Localised question strings for typed exercises ────────────────────────────

_TYPED_STRINGS: dict[str, dict[str, str]] = {
    "cs_question": {
        "fr": "Complète la fonction Python pour résoudre : {obj}.",
        "ar": "أكمل دالة Python لحلّ: {obj}.",
        "es": "Completa la función Python para resolver: {obj}.",
        "en": "Complete the Python function to solve: {obj}.",
    },
    "cs_hint": {
        "fr": "Commence par définir le cas de base, puis le cas récursif ou itératif.",
        "ar": "ابدأ بتعريف الحالة الأساسية ثم الحالة التكرارية.",
        "es": "Empieza por definir el caso base, luego el caso recursivo o iterativo.",
        "en": "Start by defining the base case, then the recursive or iterative case.",
    },
    "cs_answer": {
        "fr": "Une fonction correcte qui produit le résultat attendu sans erreur.",
        "ar": "دالة صحيحة تنتج النتيجة المتوقعة دون أخطاء.",
        "es": "Una función correcta que produce el resultado esperado sin errores.",
        "en": "A correct function that produces the expected result without errors.",
    },
    "math_question": {
        "fr": "Calcule ou résous : {obj} (sujet : {topic}).",
        "ar": "احسب أو حلّ: {obj} (الموضوع: {topic}).",
        "es": "Calcula o resuelve: {obj} (tema: {topic}).",
        "en": "Calculate or solve: {obj} (topic: {topic}).",
    },
    "math_hint": {
        "fr": "Utilise les propriétés algébriques de {obj}.",
        "ar": "استخدم الخصائص الجبرية لـ {obj}.",
        "es": "Usa las propiedades algebraicas de {obj}.",
        "en": "Use the algebraic properties of {obj}.",
    },
    "science_question": {
        "fr": "Applique la formule liée à {obj} dans le contexte de {topic}.",
        "ar": "طبّق الصيغة المرتبطة بـ {obj} في سياق {topic}.",
        "es": "Aplica la fórmula relacionada con {obj} en el contexto de {topic}.",
        "en": "Apply the formula related to {obj} in the context of {topic}.",
    },
    "science_hint": {
        "fr": "Identifie les variables et les unités avant de calculer.",
        "ar": "حدّد المتغيرات والوحدات قبل الحساب.",
        "es": "Identifica las variables y las unidades antes de calcular.",
        "en": "Identify the variables and units before calculating.",
    },
    "chart_question": {
        "fr": "Analyse la courbe représentant {obj} dans {topic}.",
        "ar": "حلّل المنحنى الممثِّل لـ {obj} في {topic}.",
        "es": "Analiza la curva que representa {obj} en {topic}.",
        "en": "Analyse the curve representing {obj} in {topic}.",
    },
    "chart_hint": {
        "fr": "Observe les extremums, les zéros et le comportement aux bornes.",
        "ar": "لاحظ النقاط القصوى والأصفار والسلوك عند الحدود.",
        "es": "Observa los extremos, los ceros y el comportamiento en los extremos.",
        "en": "Observe extrema, zeros, and boundary behaviour.",
    },
    "chart_answer": {
        "fr": "Une description précise des caractéristiques principales de la courbe.",
        "ar": "وصف دقيق للخصائص الرئيسية للمنحنى.",
        "es": "Una descripción precisa de las características principales de la curva.",
        "en": "A precise description of the main characteristics of the curve.",
    },
    "lang_question": {
        "fr": "Réécris la phrase suivante en corrigeant les erreurs de {obj}.",
        "ar": "أعِد كتابة الجملة التالية مع تصحيح أخطاء {obj}.",
        "es": "Reescribe la siguiente frase corrigiendo los errores de {obj}.",
        "en": "Rewrite the following sentence correcting {obj} errors.",
    },
    "lang_hint": {
        "fr": "Lis la phrase à voix haute et repère les incohérences grammaticales.",
        "ar": "اقرأ الجملة بصوت عالٍ وحدّد التناقضات النحوية.",
        "es": "Lee la frase en voz alta e identifica las incoherencias gramaticales.",
        "en": "Read the sentence aloud and spot grammatical inconsistencies.",
    },
    "history_chart_q": {
        "fr": "Replace les événements de {topic} dans l'ordre chronologique.",
        "ar": "رتّب أحداث {topic} بالترتيب الزمني.",
        "es": "Ordena los eventos de {topic} cronológicamente.",
        "en": "Place the events of {topic} in chronological order.",
    },
    "history_chart_h": {
        "fr": "Utilise la timeline pour repérer les dates clés.",
        "ar": "استخدم الجدول الزمني لتحديد التواريخ الرئيسية.",
        "es": "Usa la línea de tiempo para identificar las fechas clave.",
        "en": "Use the timeline to identify key dates.",
    },
    "history_chart_a": {
        "fr": "Les événements correctement ordonnés avec leurs dates.",
        "ar": "الأحداث مرتبة بشكل صحيح مع تواريخها.",
        "es": "Los eventos correctamente ordenados con sus fechas.",
        "en": "Events correctly ordered with their dates.",
    },
    "history_mcq_q": {
        "fr": "Quelle est la cause principale de {obj} dans l'histoire de {topic} ?",
        "ar": "ما السبب الرئيسي لـ {obj} في تاريخ {topic}؟",
        "es": "¿Cuál es la causa principal de {obj} en la historia de {topic}?",
        "en": "What is the main cause of {obj} in the history of {topic}?",
    },
    "history_mcq_h": {
        "fr": "Pense au contexte politique et économique de l'époque.",
        "ar": "فكّر في السياق السياسي والاقتصادي للحقبة.",
        "es": "Piensa en el contexto político y económico de la época.",
        "en": "Think about the political and economic context of the period.",
    },
    "history_mcq_a": {
        "fr": "Une réponse précise mentionnant les facteurs historiques clés.",
        "ar": "إجابة دقيقة تذكر العوامل التاريخية الرئيسية.",
        "es": "Una respuesta precisa mencionando los factores históricos clave.",
        "en": "A precise answer mentioning key historical factors.",
    },
    # shared math_answer / science_answer — use expression directly
}

_MATH_ANSWER_TPL = {
    "fr": "Le résultat de l'expression sympy évaluée.",
    "en": "The result of the evaluated sympy expression.",
    "ar": "نتيجة التعبير الرياضي المقيَّم.",
    "es": "El resultado de la expresión sympy evaluada.",
}


def _localise(key: str, language: str, **kwargs) -> str:
    """Return a localised string for typed exercise fields."""
    lang = language if language in ("fr", "ar", "es") else "en"
    tpl = _TYPED_STRINGS.get(key, {}).get(lang) or _TYPED_STRINGS.get(key, {}).get("en", "")
    try:
        return tpl.format(**kwargs)
    except KeyError:
        return tpl


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
