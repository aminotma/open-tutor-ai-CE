# Exercise Tools — Documentation

> Package : `open_tutorai.tools`
> Utilisés par : `ExerciseAgent` ([exercise.py](../backend/open_tutorai/agents/langgraph/agents/exercise.py))
> Générés par : `generate_typed_exercises()` ([helpers.py](../backend/open_tutorai/agents/helpers.py))

---

## Vue d'ensemble

Les outils sont **actifs automatiquement** dès qu'un sujet est résolu. Le flux complet est :

```
TutorGraphState
    └── subject / detected_subject
            │
            ▼
    ExerciseAgent — cascade de résolution du sujet
            │
            ├─ generate_typed_exercises()   ← sujet résolu → exercices avec champs déclencheurs
            │       └── _run_tool_for_exercise()  → appel outil selon (type, subject)
            │
            └─ generate_exercises()         ← fallback générique (aucun outil)
```

---

## Résolution du sujet — cascade à 3 sources

L'`ExerciseAgent` résout le sujet actif dans cet ordre (première valeur non vide gagne) :

| Priorité | Source | Champ | Qui le remplit |
|---|---|---|---|
| 1 | Déclaré par l'utilisateur | `state['subject']` | Frontend / Gateway API |
| 2 | Inféré par DiagnosticsAgent | `state['detected_subject']` | `detect_subject(topic, weak_concepts)` |
| 3 | Heuristique locale | résultat de `detect_subject()` | ExerciseAgent lui-même |
| — | Fallback | `None` | → `generate_exercises()` générique |

### `detect_subject(topic, weak_concepts)` — [helpers.py](../backend/open_tutorai/agents/helpers.py)

Détecte le sujet par correspondance de mots-clés multilingues (fr, en, ar, es).
Exige **≥ 2 hits** pour éviter les faux positifs sur les topics courts.

| Sujet retourné | Exemples de mots-clés déclencheurs |
|---|---|
| `cs` | algorithm, code, python, recursion, boucle, fonction, sorting |
| `math` | intégrale, dérivée, équation, matrix, vector, probability, limit |
| `science` | physique, chimie, énergie, atom, reaction, electricity |
| `language` | grammaire, conjugaison, dictée, spelling, translation, vocabulary |
| `history` | révolution, guerre, siècle, timeline, geography, civilization |
| `None` | topic trop court ou ambigu → fallback générique |

---

## Routing des outils — tableau complet

| `type` exercice | `subject` | Outil appelé | Champ déclencheur |
|---|---|---|---|
| `coding` | `cs` / tout | `live_code_evaluation` | `starter_code` présent |
| `math` | `math` / `science` | `math_evaluator` | `expression` ou `answer` présent |
| `chart` | tout | `generate_chart` | `chart_type` + `chart_payload` présents |
| `dictation`, `writing` | `language` | `grammar_checker` | `sample_text` ou `answer` présent |
| `mcq`, `explain` | tout | `search_web` | `search_query` présent |
| `mcq`, `explain` | tout | *(aucun)* | pas de `search_query` → LLM seul |

---

## Génération typée par matière — `generate_typed_exercises()`

Appelée automatiquement par l'ExerciseAgent quand un sujet est résolu.
Produit des exercices avec tous les **champs déclencheurs d'outils** selon `(subject, level)`.

| `subject` | `level` | `type` généré | Outil activé |
|---|---|---|---|
| `cs` | beginner / intermediate / advanced | `coding` | `live_code_evaluation` |
| `math` | tous | `math` | `math_evaluator` |
| `science` | beginner / intermediate | `math` | `math_evaluator` |
| `science` | advanced | `chart` (function) | `generate_chart` |
| `language` | tous | `dictation` | `grammar_checker` |
| `history` | tous (alterné) | `chart` (timeline) ou `mcq` | `generate_chart` / `search_web` |

---

## Champs produits par `generate_typed_exercises()`

```python
{
    # Champs communs (tous les types)
    "id":           str,   # UUID court généré automatiquement
    "type":         str,   # 'coding' | 'math' | 'chart' | 'dictation' | 'mcq'
    "subject":      str,   # 'cs' | 'math' | 'science' | 'language' | 'history'
    "difficulty":   str,   # 'beginner' | 'intermediate' | 'advanced'
    "question":     str,   # localisé selon state['language']
    "hint":         str,   # localisé selon state['language']
    "answer":       str,   # localisé ou valeur sympy / texte corrigé
    "skill_target": str,   # objectif pédagogique ciblé

    # Champs spécifiques — présents seulement quand le type le requiert
    "starter_code":   str,   # coding — stub Python valide et exécutable
    "code_language":  str,   # coding — 'python' (défaut)
    "expected_output": str,  # coding — sortie attendue (optionnel)

    "expression":  str,      # math — expression sympy (ex: "solve(x**2-4, x)")
    "expected":    str,      # math — résultat attendu (optionnel)

    "chart_type":    str,    # chart — 'function' | 'timeline'
    "chart_payload": str,    # chart — JSON sérialisé (voir schémas generate_chart)

    "sample_text": str,      # dictation — phrase à faire corriger par grammar_checker
    "lang_code":   str,      # dictation — code BCP-47 ('fr','en','ar','es')

    "search_query": str,     # mcq — requête envoyée à search_web
}
```

---

## Outil 1 — `live_code_evaluation`

**Fichier :** [live_code_evaluation.py](../backend/open_tutorai/tools/live_code_evaluation.py)

**Usage :** Informatique, algorithmique, sciences numériques (numpy/scipy).

**Déclenché quand :** `type == "coding"` ET `starter_code` présent.
→ Produit automatiquement par `generate_typed_exercises(subject="cs")`.

**Dépendances :** stdlib Python (`subprocess`, `sys`) — aucune installation requise.

### Paramètres

| Paramètre | Type | Description |
|---|---|---|
| `code` | `str` | Code Python à exécuter |
| `language` | `str` | Langage (`"python"` uniquement pour l'instant) |

### Retour

```python
{
    "success":  bool,   # True si exit code == 0
    "stdout":   str,    # Sortie standard (max 2 000 chars)
    "stderr":   str,    # Sortie d'erreur (max 500 chars)
    "language": str,
}
```

### Exemple d'exercice (produit par `generate_typed_exercises`)

```python
{
    "type":         "coding",
    "subject":      "cs",
    "difficulty":   "intermediate",
    "question":     "Complète la fonction Python pour résoudre : Maîtriser: récursion.",
    "starter_code": "def resoudre(donnees):\n    \"\"\"Maîtriser: récursion\"\"\"\n    resultat = []\n    for item in donnees:\n        resultat.append(item)\n    return resultat\n\nprint(resoudre([1, 2, 3]))",
    "code_language": "python",
}
```

### Limites

- Timeout fixé à **5 secondes** — protège contre les boucles infinies.
- Seul Python est supporté pour l'instant.
- Le subprocess n'a **pas accès au réseau** ni aux fichiers du projet.

---

## Outil 2 — `math_evaluator`

**Fichier :** [math_evaluator.py](../backend/open_tutorai/tools/math_evaluator.py)

**Usage :** Mathématiques (calcul, équations, dérivées, intégrales, simplification), Sciences (formules).

**Déclenché quand :** `type == "math"` OU `subject in ("math", "science")`, avec `expression` ou `answer` présent.
→ Produit automatiquement par `generate_typed_exercises(subject="math")` et `generate_typed_exercises(subject="science", level="beginner"|"intermediate")`.

**Dépendances :** `sympy` (recommandé) — fallback `eval()` numérique si absent.

### Sélection automatique de l'expression sympy

`generate_typed_exercises` choisit l'expression selon les mots-clés de l'objectif :

| Mots-clés détectés | Expression générée |
|---|---|
| dérivée / derivative / diff | `diff(x**3 - 2*x**2 + x, x)` |
| intégrale / integral | `integrate(x**2 + 1, x)` |
| équation / equation / solve | `solve(x**2 - 4*x + 3, x)` |
| limite / limit | `limit(sin(x)/x, x, 0)` |
| matrice / matrix | `Matrix([[1,2],[3,4]]).det()` |
| probabilité / probability | `Rational(3, 4) * Rational(1, 2)` |
| factorielle / factorial | `factorial(6)` |
| *(aucun)* → beginner | `2**8` |
| *(aucun)* → intermediate | `solve(x**2 - 5*x + 6, x)` |
| *(aucun)* → advanced | `integrate(x**3 - 2*x, x)` |

### Paramètres

| Paramètre | Type | Description |
|---|---|---|
| `expression` | `str` | Expression sympy compatible |
| `expected` | `str` | Résultat attendu pour vérification (optionnel) |

### Retour

```python
{
    "success": bool,
    "result":  str,          # résultat sous forme de chaîne
    "matched": bool | None,  # True si résultat == expected (None si pas d'expected)
    "error":   str,
}
```

---

## Outil 3 — `generate_chart`

**Fichier :** [generate_chart.py](../backend/open_tutorai/tools/generate_chart.py)

**Usage :** Mathématiques (tracé de fonction), Sciences (courbes avancées), Histoire (timeline).

**Déclenché quand :** `type == "chart"` avec `chart_type` et `chart_payload` présents.
→ Produit automatiquement par `generate_typed_exercises(subject="science", level="advanced")` et `generate_typed_exercises(subject="history")` (exercices pairs).

**Dépendances :** `matplotlib` — renvoie une erreur claire si absent.

### Payloads générés automatiquement

| Subject + level | chart_type | Contenu du payload |
|---|---|---|
| `science` advanced | `function` | `{"expr": "sin(x)*exp(-x/5)", "x_min": 0, "x_max": 20}` |
| `history` (pair) | `timeline` | `{"events": [{year, label}, ...], "title": ...}` |

### Paramètres

| Paramètre | Type | Description |
|---|---|---|
| `chart_type` | `str` | `'line'` \| `'bar'` \| `'scatter'` \| `'function'` \| `'timeline'` |
| `payload` | `str` | JSON décrivant les données |

### Schémas payload par chart_type

```json
// line / scatter
{"x": [1,2,3], "y": [4,5,6], "xlabel": "t (s)", "ylabel": "v (m/s)", "title": "Vitesse"}

// bar
{"labels": ["A","B","C"], "values": [10,20,15], "xlabel": "Catégorie", "ylabel": "Fréquence", "title": "Résultats"}

// function
{"expr": "x**2 - 2*x + 1", "x_min": -5, "x_max": 5, "title": "f(x) = x²-2x+1"}

// timeline
{"events": [{"year": 1789, "label": "Révolution fr."}, {"year": 1815, "label": "Waterloo"}], "title": "Timeline"}
```

### Retour

```python
{
    "success":   bool,
    "image_b64": str,   # PNG encodé en base64 — à afficher côté frontend
    "mime_type": str,   # "image/png"
    "error":     str,
}
```

### Intégration frontend

```html
<img src="data:image/png;base64,{{ tool_result.image_b64 }}" />
```

---

## Outil 4 — `search_web`

**Fichier :** [search_web.py](../backend/open_tutorai/tools/search_web.py)

**Usage :** Toutes matières — vérification de faits, données récentes, enrichissement d'énoncé.

**Déclenché quand :** `type in ("mcq", "explain")` ET `search_query` présent.
→ Produit automatiquement par `generate_typed_exercises(subject="history")` (exercices impairs) avec `search_query = f"{obj} {topic}"`.

**Dépendances :** `duckduckgo-search` (déjà dans `requirements.txt`).

### Paramètres

| Paramètre | Type | Description |
|---|---|---|
| `query` | `str` | Requête de recherche en langage naturel |
| `max_results` | `int` | Nombre de résultats (1–10, défaut 5 ; ExerciseAgent utilise 3) |

### Retour

```python
{
    "success": bool,
    "results": [
        {"title": str, "body": str, "href": str},
        ...
    ],
    "error": str,
}
```

### Note pédagogique

Les snippets sont injectés dans le contexte de l'exercice pour enrichir la question ou valider la réponse. Ils ne sont **pas affichés bruts** à l'élève — c'est le rôle du FeedbackAgent de les interpréter.

---

## Outil 5 — `grammar_checker`

**Fichier :** [grammar_checker.py](../backend/open_tutorai/tools/grammar_checker.py)

**Usage :** Langues vivantes — dictée, rédaction, traduction, texte à trous.

**Déclenché quand :** `type == "dictation"` OU (`type in ("writing", "fill_in_blank")` ET `subject == "language"`).
→ Produit automatiquement par `generate_typed_exercises(subject="language")` avec `sample_text` pré-rempli selon le niveau.

**Dépendances :** `openai` SDK + variable `OPENAI_API_KEY`. Supporte Ollama via `OPENAI_BASE_URL`.

### Phrases de référence générées automatiquement par niveau

| Level | `sample_text` injecté |
|---|---|
| `beginner` | `"Le chat mange du poisson."` |
| `intermediate` | `"Les élèves ont bien travaillé pendant toute la semaine."` |
| `advanced` | `"Bien que la situation fût complexe, ils parvinrent à trouver une solution élégante."` |

### Paramètres

| Paramètre | Type | Description |
|---|---|---|
| `text` | `str` | Texte de l'élève à corriger |
| `language` | `str` | Code BCP-47 (`'fr'`, `'en'`, `'ar'`, `'es'`, …) |

### Retour

```python
{
    "success":        bool,
    "correct":        bool,        # True si aucune erreur
    "errors":         list[str],   # liste des erreurs décrites
    "corrected_text": str,         # version corrigée
    "explanation":    str,         # explication pédagogique dans la langue de l'élève
    "error":          str,         # erreur technique si success == False
}
```

### Variables d'environnement

| Variable | Rôle |
|---|---|
| `OPENAI_API_KEY` | Clé API OpenAI (obligatoire) |
| `OPENAI_BASE_URL` | Base URL alternative (Ollama, proxy) |
| `OPENAI_MODEL` | Modèle à utiliser (défaut : `gpt-4o-mini`) |

---

## Activer les outils — guide rapide

### Via le frontend (Source 1 — recommandé)

Passer `subject` dans le body de `POST /api/v1/adaptive/plan` :

```json
{
    "topic": "récursion",
    "subject": "cs",
    "current_level": "intermediate",
    ...
}
```

### Via le topic seul (Sources 2 & 3 — automatique)

Si `subject` est absent, le `DiagnosticsAgent` appelle `detect_subject(topic, weak_concepts)`.
Les outils s'activent automatiquement si ≥ 2 mots-clés du sujet sont présents dans le topic ou les `weak_concepts`.

```python
# Exemples de topics qui activent les outils automatiquement
"récursion et algorithmes de tri"  → subject="cs"  → live_code_evaluation
"dérivées et intégrales"           → subject="math" → math_evaluator
"grammaire et conjugaison"         → subject="language" → grammar_checker
"révolution et guerre mondiale"    → subject="history"  → generate_chart + search_web
```

### Vérifier dans l'agent_trace

```python
"[DiagnosticsAgent] level=intermediate, 3 difficulties, subject=cs"
"[ExerciseAgent] 3 exercises (level=intermediate, subject=cs)"
"[ExerciseAgent] tools: live_code_evaluation, live_code_evaluation, live_code_evaluation"
```

---

## Ajouter un nouvel outil

1. Créer `backend/open_tutorai/tools/mon_outil.py` avec le décorateur `@tool`.
2. L'exporter dans [__init__.py](../backend/open_tutorai/tools/__init__.py).
3. Ajouter une branche dans `_run_tool_for_exercise()` dans [exercise.py](../backend/open_tutorai/agents/langgraph/agents/exercise.py).
4. Optionnel : ajouter un cas dans `generate_typed_exercises()` dans [helpers.py](../backend/open_tutorai/agents/helpers.py) pour que le champ déclencheur soit produit automatiquement.
5. Documenter ici : usage, déclencheur, paramètres, retour, exemple d'exercice.
