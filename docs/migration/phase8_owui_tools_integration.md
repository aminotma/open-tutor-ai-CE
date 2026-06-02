# Phase 8 — Open WebUI Tools Integration (Chat Function Calling)

## Objectif

Rendre les outils pédagogiques d'OpenTutorAI (`generate_chart`, `math_evaluator`,
`live_code_evaluation`, `search_web`) accessibles depuis le **chat classique** via
le mécanisme de function calling d'Open WebUI — pas seulement depuis le pipeline
LangGraph (ExerciseAgent).

## Problème résolu

Avant cette phase, demander `"représente y = x² - 8"` dans le chat produisait
une réponse texte (table de valeurs + conseil d'utiliser GeoGebra) car le LLM
n'avait pas accès aux outils. Le graphique n'était généré que via le pipeline
`/adaptive/plan`.

---

## Architecture

```
AVANT (Phase 7)
───────────────
Chat classique  →  LLM répond en texte  →  ❌ aucun outil
Pipeline adaptatif  →  ExerciseAgent  →  generate_chart  →  ✅ graphe

APRÈS (Phase 8)
───────────────
Chat classique  →  LLM + function calling  →  otai_generate_chart  →  ✅ graphe
                                           →  otai_math_evaluator  →  ✅ calcul
                                           →  otai_live_code       →  ✅ exécution
                                           →  otai_search_web      →  ✅ recherche
Pipeline adaptatif  →  ExerciseAgent  →  outils LangChain (inchangé)  →  ✅
```

---

## Nouveaux fichiers

### `backend/open_tutorai/tools/owui_tools.py`

Définit le **code source** des 4 tools au format Open WebUI (classe `Tools` avec
méthodes documentées). Ce code est stocké en base de données et exécuté
dynamiquement par Open WebUI lors d'un appel du LLM.

| Constante | Tool ID | Nom affiché | Méthodes LLM |
|-----------|---------|-------------|--------------|
| `GENERATE_CHART_CODE` | `otai_generate_chart` | OpenTutorAI — Graphique | `plot_function()`, `plot_timeline()` |
| `MATH_EVALUATOR_CODE` | `otai_math_evaluator` | OpenTutorAI — Calcul symbolique | `evaluate_expression()` |
| `LIVE_CODE_CODE` | `otai_live_code` | OpenTutorAI — Exécution de code | `run_python()` |
| `SEARCH_WEB_CODE` | `otai_search_web` | OpenTutorAI — Recherche web | `search()` |

Chaque méthode :
- a une docstring claire pour le LLM (conditions d'utilisation, paramètres)
- wrape l'outil LangChain existant (`open_tutorai.tools.*`)
- retourne un résultat markdown (image base64 pour les graphiques)

### `backend/open_tutorai/tools/tools_registrar.py`

Enregistre ou met à jour les tools OTAI dans la base Open WebUI au démarrage.

**Fonctions :**

| Fonction | Rôle |
|----------|------|
| `register_otai_tools()` | Point d'entrée — configure `DATABASE_URL` si absent, orchestre l'upsert de chaque tool |
| `_get_admin(Users)` | Trouve dynamiquement un admin : 1) premier user créé, 2) scan des 20 premiers users, 3) n'importe quel user |
| `_upsert_tool(...)` | Crée le tool s'il n'existe pas, le met à jour s'il existe déjà |
| `_extract_specs(...)` | Exécute le code du tool et extrait le schéma OpenAI function calling via `get_tools_specs()` |

**Robustesse :**
- `DATABASE_URL` configuré automatiquement depuis `DATA_DIR` si absent (évite la DB vide hors serveur)
- Toutes les erreurs sont silencieuses — un échec n'empêche pas le démarrage
- Upsert idempotent : relancer ne crée pas de doublons

---

## Fichiers modifiés

### `backend/open_tutorai/main.py`

Ajout dans `startup_db_client()` :

```python
# Transmet DATA_DIR au registrar, puis enregistre les tools
if not os.getenv("DATA_DIR"):
    os.environ["DATA_DIR"] = os.path.abspath(".../data")
from open_tutorai.tools.tools_registrar import register_otai_tools
register_otai_tools()
```

### `backend/open_tutorai/agents/helpers.py`

Correction de `generate_typed_exercises()` pour les maths :
- **Avant** : `type="math"` → `math_evaluator` pour tous les exercices maths
- **Après** : détecte les mots de visualisation (`parabole`, `courbe`, `graphe`, `tracer`…) → `type="chart"` → `generate_chart`

### `backend/open_tutorai/agents/langgraph/prompt_builder.py`

Schéma JSON de l'agent ExerciseAgent enrichi avec les **règles de sélection du type** :
```
type="chart"   → tracer/visualiser une courbe, parabole, fonction, timeline
type="math"    → calculer/résoudre sans graphe
type="coding"  → exercice de programmation
type="dictation" → grammaire/langue
type="mcq"     → vérification factuelle web
```

---

## Flux d'activation (une fois)

Après démarrage du serveur, dans Open WebUI :

1. **Workspace → Tools** → les 4 tools OTAI apparaissent automatiquement
2. Dans les **paramètres du modèle** → activer les tools souhaités (ou globalement)
3. Ou dans le chat : cliquer sur `+` dans la barre de message → sélectionner le tool

---

## Perspectives — Vers un vrai Full Agentic

1. **Orchestrateur 100% LLM** — supprimer `_route()`, le LLM décide seul
2. **Spawning de sous-agents dynamiques** — un agent délègue à un sous-agent spécialisé
3. **Boucle réflexive autonome** — les agents se relancent sans passer par l'orchestrateur
4. **Memory auto-update en cours de session** — écriture DB pendant le pipeline
5. **Planning multi-étapes (ReAct / Tree-of-Thought)** — raisonnement multi-sessions
6. **Évaluation autonome de la maîtrise** — sans delta fixe codé en dur
