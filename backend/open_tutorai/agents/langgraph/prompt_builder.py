"""Exercise type selection rules for the ExerciseAgent.

Provides the JSON schema and prompt fragment that guides the LLM (or heuristic)
when choosing the `type` field of each generated exercise.

Type → tool mapping:
    chart      → generate_chart  (plot_function / plot_timeline)
    math       → math_evaluator  (evaluate_expression)
    coding     → live_code_evaluation (run_python)
    dictation  → grammar_checker
    mcq        → search_web (search)
"""
from __future__ import annotations


# ── Schema ────────────────────────────────────────────────────────────────────

TYPE_SELECTION_RULES: list[dict] = [
    {
        "type": "chart",
        "tool": "generate_chart",
        "triggers": [
            "tracer", "trace", "visualiser", "représenter", "dessiner", "afficher",
            "parabole", "courbe", "graphe", "graphique", "fonction", "f(x)",
            "plot", "draw", "graph", "curve", "function", "timeline", "chronologie",
        ],
        "description": (
            "Use when the request involves visualising a mathematical function "
            "(y = f(x), polynomial, trigonometric, exponential…) or a historical timeline. "
            "Keywords: tracer, courbe, parabole, graphe, représente, visualise, timeline."
        ),
        "fields": ["chart_type", "chart_payload"],
    },
    {
        "type": "math",
        "tool": "math_evaluator",
        "triggers": [
            "calculer", "résoudre", "dériver", "intégrer", "limite", "factorielle",
            "calculate", "solve", "derivative", "integral", "limit", "factorial",
            "équation", "equation", "matrice", "matrix",
        ],
        "description": (
            "Use when the request is a pure symbolic computation WITHOUT a graph: "
            "solving an equation, computing a derivative/integral, evaluating an expression. "
            "Keywords: calculer, résoudre, dériver, intégrer, solve, diff, integrate."
        ),
        "fields": ["expression"],
    },
    {
        "type": "coding",
        "tool": "live_code_evaluation",
        "triggers": [
            "code", "coder", "programmer", "python", "script", "fonction", "algorithme",
            "algorithm", "function", "implement", "debug", "exécuter",
        ],
        "description": (
            "Use for programming exercises: write, complete, or debug Python code. "
            "Keywords: code, python, algorithme, programmer, implémenter."
        ),
        "fields": ["starter_code", "code_language"],
    },
    {
        "type": "dictation",
        "tool": "grammar_checker",
        "triggers": [
            "dictée", "grammaire", "orthographe", "conjugaison", "rédaction",
            "dictation", "grammar", "spelling", "conjugation",
        ],
        "description": (
            "Use for language / grammar exercises: dictation, spelling correction, "
            "grammar rules. Keywords: dictée, grammaire, orthographe."
        ),
        "fields": ["sample_text", "lang_code"],
    },
    {
        "type": "mcq",
        "tool": "search_web",
        "triggers": [
            "qcm", "mcq", "vrai ou faux", "true or false", "factuel", "factual",
            "historique", "historical", "vérifier", "verify", "rechercher", "search",
        ],
        "description": (
            "Use for factual verification questions (multiple-choice, true/false, "
            "historical facts) that benefit from a web search. "
            "Keywords: qcm, factuel, historique, vérifier, rechercher."
        ),
        "fields": ["search_query"],
    },
]


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_exercise_type_rules() -> list[dict]:
    """Return the full type selection rule set."""
    return TYPE_SELECTION_RULES


def build_type_selection_prompt() -> str:
    """Return a prompt fragment (system message section) describing type selection rules.

    Intended for inclusion in the ExerciseAgent system prompt when LLM-based
    type selection is used instead of the keyword heuristic.
    """
    lines = [
        "## Règles de sélection du type d'exercice\n",
        "Choisissez le champ `type` selon les critères suivants :\n",
    ]
    for rule in TYPE_SELECTION_RULES:
        lines.append(
            f"- **type=\"{rule['type']}\"** (tool: `{rule['tool']}`)"
            f" — {rule['description']}"
        )
        lines.append(
            f"  Champs requis : {', '.join('`' + f + '`' for f in rule['fields'])}"
        )
        lines.append("")
    lines.append(
        "Priorité : si des mots-clés de visualisation sont présents (courbe, graphe, "
        "parabole, tracer, représenter), choisissez `chart` même si le sujet est `math`."
    )
    return "\n".join(lines)


def detect_exercise_type(text: str) -> str | None:
    """Return the exercise type whose triggers best match *text*, or None.

    Lighter alternative to the full heuristic in helpers.py — useful when a
    single short question string needs to be classified.
    """
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for rule in TYPE_SELECTION_RULES:
        hits = sum(1 for kw in rule["triggers"] if kw in text_lower)
        if hits:
            scores[rule["type"]] = hits

    if not scores:
        return None

    # chart wins on ties when math is also a candidate (visualization priority)
    best = max(scores, key=lambda t: (scores[t], t == "chart"))
    return best if scores[best] >= 1 else None
