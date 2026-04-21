# Interactions des Agents Adaptatifs avec la Mémoire et le Contexte

## Vue d'ensemble

L'agent `AdaptiveTutorAgent` est un système multi-agent qui orchestre plusieurs agents spécialisés pour fournir un tutorat adaptatif. Les interactions avec la mémoire et le contexte sont centrales pour permettre l'adaptation personnalisée et la continuité des apprentissages. Ce document décrit comment les agents interagissent avec ces deux éléments clés.

## Architecture des Agents

L'agent principal orchestre les agents suivants dans une boucle de routage dynamique :

1. **PerceptionAgent** : Collecte la mémoire et le contexte pédagogique
2. **DiagnosisAgent** : Évalue le niveau et détecte les difficultés
3. **PlanningAgent** : Construit la stratégie pédagogique
4. **ExerciseAgent** : Génère des exercices adaptés
5. **VerificationAgent** : Vérifie la cohérence avec les sources RAG
6. **ReflectionAgent** : Persiste les réflexions et consolide la mémoire
7. **CollaborationAgent** : Évalue le consensus et déclenche des corrections

## Mémoire par Agent

- **PerceptionAgent** : récupère les mémoires internes de l'utilisateur en utilisant tous les types activés dans la configuration :
  - `episodic` (rappels de sessions précédentes)
  - `semantic` (connaissances et concepts appris)
  - `procedural` (stratégies et étapes de résolution)
  - `behavioral` (comportements, retours et habitudes)

- **DiagnosisAgent** : exploite principalement les mémoires `episodic` et `behavioral` pour détecter les difficultés récurrentes et les tendances pédagogiques, tout en pouvant s'appuyer sur les mémoires `semantic` lorsque le contenu du topic correspond à des connaissances stockées.

- **PlanningAgent** : utilise la mémoire consolidée dans `state.memory_context` pour ajuster le plan d'apprentissage, en tirant profit des signaux comportementaux et des références épisodiques contenues dans les mémoires.

- **ExerciseAgent** : ne récupère pas directement de nouveaux types de mémoire, mais génère des exercices en s'appuyant sur le diagnostic et la stratégie définis à partir des mémoires déjà extraites.

- **VerificationAgent** : ne stocke pas de mémoire spécifique ; il vérifie la cohérence des sorties contre des sources RAG et transmet le résultat au pipeline.

- **ReflectionAgent** : persiste explicitement des mémoires de type `behavioral` pour capturer les décisions pédagogiques, les difficultés détectées et le verdict de vérification.

- **CollaborationAgent** : n'ajoute pas de nouvelle mémoire, mais utilise l'état courant et les résultats de vérification pour décider d'un consensus ou d'un cycle correctif.

## Interactions avec la Mémoire

### Récupération de la Mémoire

- **Agent responsable** : `PerceptionAgent`
- **Méthode utilisée** : `retrieve_internal_memory()`
- **Paramètres** :
  - `user_id` : Identifiant de l'utilisateur
  - `query` : Requête basée sur le topic et les objectifs d'apprentissage
  - `memory_types` : Types de mémoire (épisodique, sémantique, procédural, comportemental)
  - `limit` : Nombre maximum de mémoires à récupérer (configuré à 10)
- **Résultat** : Liste d'items mémoire stockés dans `state.memory_context`

### Utilisation de la Mémoire dans le Diagnostic

- **Agent responsable** : `DiagnosisAgent`
- **Fonction** : `_extract_memory_signals()`
- **Logique** :
  - Recherche des signaux de difficulté dans les mémoires liées au topic
  - Ajoute des difficultés détectées à partir des patterns mémorisés
  - Exemple : Si une mémoire contient "difficulté avec X", cela influence le diagnostic

### Persistance de la Mémoire

- **Agent responsable** : `ReflectionAgent`
- **Méthode** : `_persist_reflection_memory()`
- **Contenu persisté** :
  - Résumé de la session (niveau, difficultés, verdict de vérification)
  - Métadonnées (topic, étape agent, décisions stratégiques)
  - Type de mémoire : "behavioral"
- **Modèle de données** : `Memory` (table `opentutorai_memory`)

### Consolidation de la Mémoire

- **Agent responsable** : `ReflectionAgent`
- **Méthode** : `_consolidate_memory()`
- **Logique** :
  - Limite à 50 mémoires par utilisateur
  - Supprime les mémoires les plus anciennes au-delà de 40
  - Préserve l'historique récent pour l'adaptation continue

## Interactions avec le Contexte

### Récupération du Contexte Pédagogique

- **Agent responsable** : `PerceptionAgent`
- **Méthode utilisée** : `retrieve_pedagogical_documents()`
- **Paramètres** :
  - `user_id` : Identifiant de l'utilisateur
  - `query` : Requête basée sur le topic et les objectifs
  - `top_k` : Nombre maximum de documents (configuré à 5)
- **Résultat** : Liste de documents pédagogiques stockés dans `state.pedagogical_context`

### Utilisation du Contexte dans la Planification

- **Agent responsable** : `PlanningAgent`
- **Logique de routage dynamique** :
  - Si aucun document RAG disponible : Route vers "web_enrichment" pour recherche web
  - Intègre le contexte dans les décisions stratégiques
  - Utilise les sources pour enrichir la stratégie pédagogique

### Vérification RAG

- **Agent responsable** : `VerificationAgent`
- **Méthode** : `verify_agent_output()`
- **Fonctionnement** :
  - Compare les exercices et stratégies générés avec le corpus des sources RAG
  - Calcule un score de support basé sur la similarité textuelle
  - Seuil de consensus : 0.65
  - Résultat : Verdict "supported" ou "needs_review"

### Enrichissement par Recherche Web

- **Agent responsable** : `ToolAgent` (via routage "web_enrichment")
- **Méthode** : `web_search()`
- **API utilisée** : DuckDuckGo Instant Answer API
- **Intégration** : Résultats injectés dans le contexte pédagogique quand RAG est insuffisant

## Flux d'Interaction Complet

1. **Perception** : Récupération mémoire + contexte RAG
2. **Diagnostic** : Analyse niveau + difficultés (utilise mémoire)
3. **Planification** : Stratégie basée sur contexte (route vers web si nécessaire)
4. **Exercice** : Génération adaptée au contexte
5. **Vérification** : Validation contre sources RAG
6. **Réflexion** : Persistance mémoire + consolidation
7. **Collaboration** : Consensus ou cycle correctif

## Configuration

Les interactions sont configurées dans `CONTEXT_RETRIEVAL_CONFIG` :

```python
CONTEXT_RETRIEVAL_CONFIG = {
    "memory": {
        "enabled": True,
        "top_k_memories": 10,
        "memory_types": ["episodic", "semantic", "procedural", "behavioral"]
    },
    "rag": {
        "enabled": True,
        "top_k_documents": 5,
        "verification_enabled": True,
        "verification_threshold": 0.65
    }
}
```

## Avantages de cette Architecture

- **Adaptation continue** : La mémoire permet de personnaliser l'enseignement
- **Cohérence pédagogique** : Le contexte RAG assure la fiabilité du contenu
- **Robustesse** : Recherche web comme fallback quand RAG est insuffisant
- **Évolutivité** : Consolidation mémoire pour performance optimale
- **Transparence** : Trace agentique pour débogage et amélioration

Cette architecture permet un tutorat véritablement adaptatif qui apprend de chaque interaction pour améliorer les futures sessions.