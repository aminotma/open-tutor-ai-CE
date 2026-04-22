# Intégration de LangChain dans Open TutorAI

## Vue d'ensemble

Ce document décrit l'intégration de LangChain dans le système Open TutorAI, en se basant sur l'agent de tutorat adaptatif existant. LangChain est déjà présent dans les dépendances (`langchain==0.3.7`), mais n'était pas utilisé. L'intégration vise à améliorer la modularité, la réutilisabilité et les capacités d'orchestration des agents.

## Contexte du système actuel

Le système Open TutorAI utilise un agent multi-agent personnalisé (`AdaptiveTutorAgent`) avec :
- Routage dynamique entre agents spécialisés (Perception, Diagnosis, Planning, etc.)
- Outils personnalisés (recherche web via DuckDuckGo, exécution de code sécurisée)
- Vérification RAG avec des documents pédagogiques
- Mémoire adaptative et feedback utilisateur

L'architecture repose sur FastAPI et Open WebUI pour les interactions LLM.

## Pourquoi intégrer LangChain ?

- **Modularité** : LangChain fournit des abstractions pour les chaînes, agents et outils, facilitant l'extension.
- **Écosystème** : Accès à des outils pré-construits (recherche web, calculs, etc.) et intégrations LLM.
- **Orchestration** : `AgentExecutor` pour gérer les boucles agentiques de manière standardisée.
- **Maintenance** : Réduction du code personnalisé en faveur de composants éprouvés.

## Étapes d'intégration

### 1. Préparation de l'environnement
- Vérifier que `langchain` et `langchain-community` sont installés (déjà présents dans `requirements.txt`).
- Importer les modules nécessaires dans les fichiers agents.

### 2. Création d'outils LangChain
- Convertir les fonctions d'outils personnalisées en `Tool` LangChain.
- Exemple : Remplacer la recherche web personnalisée par `DuckDuckGoSearchRun`.

### 3. Refactorisation des agents
- Utiliser `AgentExecutor` pour l'orchestration principale.
- Créer des chaînes pour les workflows complexes (diagnostic, planification).

### 4. Intégration avec le système existant
- Maintenir la compatibilité avec l'API actuelle.
- Ajouter des options pour activer/désactiver LangChain.

### 5. Tests et validation
- Tester les nouveaux outils.
- Valider que les pipelines fonctionnent correctement.

## Modifications apportées

### Fichier : `backend/open_tutorai/agents/adaptive_tutor_agent.py`

#### Ajouts d'imports
```python
from langchain.tools import Tool
from langchain_community.tools import DuckDuckGoSearchRun
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI  # Si OpenAI est utilisé
```

#### Modification de ToolAgent
- Remplacement de la méthode `web_search` personnalisée par un outil LangChain :
```python
class ToolAgent(BaseAgent):
    def __init__(self, state: AdaptiveTutorState):
        super().__init__(state)
        self.search_tool = DuckDuckGoSearchRun()

    def web_search(self, query: str, max_results: int = 5) -> str:
        self.state.agent_trace.append(f"ToolAgent (LangChain): recherche web pour '{query}'.")
        try:
            result = self.search_tool.run(query)
            self.state.tool_results["web_search"] = {"query": query, "summary": result}
            return result
        except Exception as exc:
            error_msg = f"Recherche web échouée : {exc}"
            self.state.agent_trace.append(f"ToolAgent: {error_msg}")
            return error_msg
```

#### Création d'un agent LangChain pour l'orchestration
- Ajout d'une classe `LangChainOrchestrator` qui utilise `AgentExecutor` pour gérer les agents :
```python
class LangChainOrchestrator:
    def __init__(self, state: AdaptiveTutorState, tools: List[Tool]):
        self.state = state
        self.llm = ChatOpenAI(temperature=0)  # Adapter selon la config
        self.tools = tools
        self.prompt = ChatPromptTemplate.from_template(
            "Tu es un orchestrateur pour un système de tutorat adaptatif. "
            "Utilise les outils disponibles pour aider l'apprenant. "
            "État actuel : {state}"
        )
        self.agent = create_openai_functions_agent(self.llm, self.tools, self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)

    async def run_orchestration(self, task: str) -> str:
        result = await self.executor.arun(task)
        return result
```

#### Intégration dans AdaptiveTutorAgent
- Ajouter une option pour utiliser LangChain :
```python
class AdaptiveTutorAgent:
    def __init__(self, user_id: str, request_data: Dict[str, Any], db, use_langchain: bool = False):
        # ... code existant ...
        self.use_langchain = use_langchain
        if self.use_langchain:
            tools = [
                Tool.from_function(
                    func=self.tool_agent.web_search,
                    name="web_search",
                    description="Recherche d'informations sur le web"
                ),
                # Ajouter d'autres outils
            ]
            self.orchestrator = LangChainOrchestrator(self.state, tools)
```

- Modifier la méthode `run` pour utiliser LangChain si activé :
```python
async def run(self) -> AdaptiveTutorState:
    if self.use_langchain:
        # Utiliser LangChain pour l'orchestration
        task = f"Orchestrer le tutorat pour le sujet {self.state.topic} au niveau {self.state.current_level}"
        result = await self.orchestrator.run_orchestration(task)
        # Parser le résultat et mettre à jour l'état
        # ... logique pour intégrer le résultat dans l'état ...
    else:
        # Code existant
        # ... boucle de routage personnalisée ...
    return self.state
```

### Fichier : `backend/open_tutorai/routers/adaptive_tutor.py` (supposé)
- Ajouter un paramètre pour activer LangChain :
```python
@router.post("/tutor")
async def adaptive_tutor(request: AdaptiveTutorRequest, use_langchain: bool = False):
    agent = AdaptiveTutorAgent(request.user_id, request.dict(), db, use_langchain=use_langchain)
    result = await agent.run()
    return result
```

## Pipeline intégré

### Pipeline avec LangChain activé
1. **Initialisation** : Créer l'agent avec `use_langchain=True`.
2. **Orchestration LangChain** : `AgentExecutor` analyse la tâche et appelle les outils appropriés.
3. **Outils** : Utilisation d'outils LangChain (recherche web, etc.) pour enrichir le contexte.
4. **Mise à jour de l'état** : Intégrer les résultats dans `AdaptiveTutorState`.
5. **Retour** : Générer la réponse finale via les agents spécialisés si nécessaire.

### Pipeline par défaut (sans LangChain)
- Utilise la boucle de routage personnalisée existante.

## Tests et validation

### Tests unitaires
- Tester les nouveaux outils LangChain.
- Valider que l'orchestration fonctionne.

### Tests d'intégration
- Comparer les sorties avec et sans LangChain.
- Mesurer les performances (temps de réponse, qualité des résultats).

### Exemple de test
```python
# Test de l'outil web_search
agent = AdaptiveTutorAgent("user1", {"topic": "math"}, db, use_langchain=True)
result = agent.tool_agent.web_search("algèbre linéaire")
assert "algèbre" in result.lower()
```

## Conclusion

L'intégration de LangChain améliore la flexibilité du système sans casser la logique existante. Elle permet d'exploiter des outils standardisés et de faciliter les futures extensions. Pour une adoption complète, envisager de migrer entièrement vers LangChain pour l'orchestration agentique.