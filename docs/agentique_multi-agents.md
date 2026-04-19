# Agentique — Collaboration multi-agents

Ce document décrit la structure multi-agents ajoutée au moteur adaptatif.

## Objectif

Construire un système où plusieurs agents spécialisés coopèrent pour produire une solution pédagogique robuste.

## Implémentation

Le code se trouve dans :
- `backend/open_tutorai/agents/adaptive_tutor_agent.py`

### Composants clés

- `PerceptionAgent` : collecte la mémoire et le contexte documentaire.
- `DiagnosisAgent` : évalue le niveau et identifie les difficultés.
- `PlanningAgent` : construit le plan et les sous-tâches.
- `ExerciseAgent` : génère des exercices et des recommandations.
- `VerificationAgent` : vérifie la cohérence par RAG.
- `ReflectionAgent` : corrige et enrichit la mémoire.
- `CollaborationAgent` : synthétise la décision collective.

### Fonctionnement

1. Chaque agent exécute un rôle dédié.
2. L’orchestrateur `AdaptiveTutorAgent` organise la séquence d’actions.
3. La `CollaborationAgent` valide la cohérence entre les rôles.
4. La trace des actions (`agent_trace`) documente la coopération.

### Exemple de code

Voici un extrait illustrant la boucle agentique dans `AdaptiveTutorAgent.run()` :

```python
async def run(self) -> AdaptiveTutorState:
    self.state.agent_trace.append("AdaptiveTutorAgent: démarrage de la boucle agentique.")
    await self.perception_agent.act()  # Collecte mémoire et contexte
    await self.diagnosis_agent.act()   # Évalue niveau et difficultés
    await self.planning_agent.act()    # Construit le plan
    await self.exercise_agent.act()    # Génère exercices
    await self.verification_agent.act() # Vérifie via RAG
    await self.reflection_agent.act()  # Corrige et persiste mémoire
    await self.collaboration_agent.act() # Synthétise
    self.state.agent_trace.append("AdaptiveTutorAgent: boucle terminée.")
    return self.state
```

Cet exemple montre comment les agents sont orchestrés séquentiellement, chacun contribuant à l'état partagé.

### Améliorations récentes (Intégration mémoire dans la boucle agentique)

- **PerceptionAgent** : Récupère la mémoire interne et le contexte pédagogique avec une recherche sémantique améliorée.
- **DiagnosisAgent** : Intègre `memory_context` pour enrichir l'identification des difficultés, en extrayant des signaux de mémoire pertinents (e.g., difficultés récurrentes liées au sujet).
- **PlanningAgent** : Utilise `memory_context` pour ajouter des décisions basées sur l'historique, comme exploiter les souvenirs pédagogiques pour une adaptation personnalisée.
- **ReflectionAgent** : Persiste automatiquement la mémoire comportementale avec des détails structurés et applique une consolidation pour éviter l'accumulation (oubli actif des éléments anciens).

## Bénéfices

- séparation des responsabilités,
- meilleure évolutivité,
- facilitation de l’ajout de nouveaux agents spécialisés,
- intégration profonde de la mémoire pour une boucle perceive-decide-act véritablement agentique.

## Problématiques et limitations

### Limite de tokens dans les modèles externes

L'architecture multi-agents peut générer des requêtes volumineuses en raison de la collecte de contexte mémoire et pédagogique, ainsi que de la trace des actions des agents. Cela peut entraîner des erreurs de limite de tokens, par exemple :

```
413: Request too large for model `openai/gpt-oss-20b` in organization `org_01kp46t0ejfb1b5hc0fykrswn4` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Requested 8036, please reduce your message size and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing
```

**Solutions possibles :**
- Réduire la taille du contexte récupéré (e.g., limiter à 5-10 éléments mémoire).
- Compresser ou résumer le contexte avant envoi.
- Utiliser des modèles avec des limites plus élevées ou des services payants.
- Implémenter une gestion de tokens côté client pour tronquer automatiquement.

**Correction appliquée :** La fonction `summarize_interactions` a été améliorée pour utiliser `tiktoken` et tronquer à un nombre fixe de tokens (500 par défaut), réduisant ainsi la taille des résumés et évitant les dépassements.
