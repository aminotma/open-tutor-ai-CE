# Agentique — Réflexion et autocorrection

Ce document décrit la couche de réflexion agentique ajoutée au moteur adaptatif.

## Objectif

Permettre au système de :
- analyser ses propres suggestions,
- vérifier la cohérence des décisions,
- corriger automatiquement les plans lorsque la vérification échoue,
- enrichir la mémoire interne avec des observations structurées.

## Implémentation

Le code se trouve dans :
- `backend/open_tutorai/agents/adaptive_tutor_agent.py`

### Composants clés

- `ReflectionAgent` : auto-corrige la stratégie en fonction des résultats de vérification.
- `VerificationAgent` : vérifie les exercices et la stratégie via RAG.
- `AdaptiveTutorAgent` : orchestre la boucle perception → diagnostic → planification → exécution → vérification → réflexion.

### Fonctionnement

1. L’agent génère un plan pédagogique et des exercices.
2. Il vérifie ce plan par rapport aux sources pédagogiques récupérées.
3. Si la vérification échoue, le système ajuste la stratégie et marque les points à relire.
4. Une mémoire comportementale est enregistrée pour conserver l’historique de la réflexion.

### Améliorations récentes (Mémoire et consolidation)

- **Persistance automatique** : `ReflectionAgent` enregistre désormais des détails structurés dans la mémoire :
  - Niveau ajusté de l'apprenant.
  - Difficultés clés identifiées.
  - Verdict de vérification RAG (e.g., "supported" ou "needs_review").
  - IDs des décisions de stratégie prises.
- **Consolidation mémoire** : Pour éviter l'accumulation indéfinie, le système conserve les 40 éléments de mémoire les plus récents et supprime les anciens. Cela simule un oubli actif basé sur la récence.

## Bénéfices

- amélioration continue des réponses,
- réduction des erreurs non détectées,
- traçabilité des choix de l’agent,
- gestion proactive de la mémoire pour maintenir la pertinence. 
