# Agentique — Planification et décomposition en sous-tâches

Ce document décrit la planification agentique introduite dans le moteur adaptatif.

## Objectif

Transformer la génération de stratégie en un processus structuré :
- décomposer le travail en sous-tâches,
- prioriser les difficultés,
- planifier des actions claires et séquentielles.

## Implémentation

Le code se trouve dans :
- `backend/open_tutorai/agents/adaptive_tutor_agent.py`

### Composants clés

- `PlanningAgent` : décompose le plan en sous-tâches et formalise la stratégie.
- `AdaptiveTutorAgent` : orchestre les agents et conserve la liste des tâches.

### Processus

1. Analyse de l’état de l’apprenant (niveau, feedback, interactions).
2. Détection des difficultés prioritaires.
3. Génération d’une stratégie pédagogique claire.
4. Construction de sous-tâches telles que :
   - récupérer le contexte,
   - identifier les difficultés,
   - générer des exercices ciblés,
   - vérifier le contenu,
   - réviser si nécessaire.

### Améliorations récentes (Intégration mémoire)

- **Utilisation du contexte mémoire** : `PlanningAgent` intègre désormais `memory_context` pour enrichir la planification. Cela permet d'ajouter une décision explicite pour exploiter les souvenirs pédagogiques et les historiques antérieurs de l'apprenant.
- **Décision "leverage_memory"** : Une nouvelle décision est ajoutée au plan pour tirer parti des éléments mémorisés, fournissant des indices sur les difficultés récurrentes et les progrès passés.

## Bénéfices

- meilleure transparence des décisions,
- passage d’une simple sortie textuelle à un plan opérationnel,
- préparation naturelle à la collaboration multi-agent,
- adaptation basée sur l'historique mémorisé pour une personnalisation accrue.
