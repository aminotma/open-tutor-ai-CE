# Refactoring : Pipeline → Agent ReAct Agentique

## Problèmes résolus

| Problème (ancien) | Solution (nouveau) |
|---|---|
| `_state` global dans chaque module d'outil | `StateRegistry` thread-safe indexé par `run_id` |
| `bind_state()` couplant les outils à une instance | `RunnableConfig["configurable"]["run_id"]` injecté par LangChain |
| Séquence prescrite dans le prompt | Prompt ouvert avec heuristiques, LLM décide librement |
| `use_langchain` flag mort | Paramètre supprimé, l'agent est toujours actif |
| `asyncio.new_event_loop()` fragile | `nest_asyncio` + gestion propre de la boucle |
| Fonctions helper dupliquées (router + agent) | Module `helpers.py` pur, sans état, importé partout |
| Outils non ré-entrants | Outils stateless, safe sous requêtes concurrentes |

---

## Architecture

```
open_tutorai/agents/
├── __init__.py                  # Exports publics
├── state.py                     # AdaptiveTutorState (dataclass immuable)
├── state_registry.py            # Registry thread-safe run_id → state
├── helpers.py                   # Fonctions pures sans état
├── prompts.py                   # Prompt ReAct ouvert (pas de séquence forcée)
├── adaptive_tutor_agent.py      # AgentExecutor + cycle de vie run_id
└── tools/
    └── __init__.py              # Tous les outils (state via config, pas globals)
```

---

## Flux d'exécution

```
POST /api/v1/adaptive/plan
        │
        ▼
AdaptiveTutorAgent.__init__()
  • génère run_id unique
  • construit AdaptiveTutorState initial

        │
        ▼
agent.run()
  • registry.register(run_id, state, user_id, db)
  • construit le prompt ouvert
  • crée AgentExecutor avec lc_config = {"configurable": {"run_id": run_id}}

        │
        ▼
LangChain ReAct loop (LLM décide librement)
  Thought → Action → tool_X(config=lc_config) → Observation → ...

        │ chaque tool :
        │   state = registry.get_state(run_id)
        │   ... logique ...
        │   new_state = state.with_updates(...)
        │   registry.update_state(run_id, new_state)
        │
        ▼
tool_final_answer() → is_complete = True

        │
        ▼
agent.run() retourne registry.get_state(run_id)
registry.deregister(run_id)   ← nettoyage garanti (finally)
```

---

## Ce qui rend le système vraiment agentique

### 1. Le LLM choisit librement la séquence

**Ancien prompt** :
```
Séquence minimale OBLIGATOIRE :
retrieve_memory → retrieve_rag → diagnose → plan → generate_exercises → verify → ...
```

**Nouveau prompt** :
```
Heuristiques de raisonnement :
1. Il est utile de récupérer le contexte avant de diagnostiquer, mais ce n'est pas obligatoire...
2. Si verify retourne needs_review, tu PEUX appeler tool_plan(focus_on_unsupported=True)...
```

### 2. État immutable et thread-safe

```python
# Ancien (dangereux)
_state = None                    # global partagé entre toutes les requêtes
def bind_state(state): ...       # mutation globale

# Nouveau (safe)
def tool_diagnose(config: RunnableConfig) -> str:
    run_id = config["configurable"]["run_id"]
    state = registry.get_state(run_id)        # isolé par run_id
    new_state = state.with_updates(...)        # immutable copy
    registry.update_state(run_id, new_state)  # atomique
```

### 3. Outils purs et ré-entrants

Les outils n'ont plus d'état propre. Deux requêtes simultanées ne peuvent
pas s'interférer car chacune a son propre `run_id`.

---
