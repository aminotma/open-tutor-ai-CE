# Adaptive Tutor Engine

## Objectif

Mettre en place un moteur adaptatif qui assure :
- l'ajustement du niveau pédagogique
- la génération d'exercices adaptés
- la détection des difficultés
- la planification de l'apprentissage en fonction du feedback de l'apprenant

Le module doit être agentique et orienter la stratégie pédagogique plutôt que proposer des options vagues.

## Architecture

Le module fonctionne en quatre étapes principales :

1. **Analyse des performances**
   - Prend en entrée le niveau actuel, l'historique des interactions et les retours de l'apprenant
   - Estime si le niveau doit monter, descendre ou rester stable

2. **Détection des difficultés**
   - Identifie les zones de blocage via :
     - scores faibles
     - résultats incorrects
     - commentaires négatifs (confusion, difficulté, incompréhension)

3. **Génération d'exercices**
   - Produit des exercices adaptés au niveau ajusté
   - Oriente chaque exercice vers un objectif d'apprentissage clair
   - Utilise des modèles de prompt simples pour générer des questions, indices et réponses

4. **Planification stratégique**
   - Propose une stratégie claire et directive
   - Priorise les difficultés détectées
   - Explique le prochain pas pédagogique sans offrir une liste d'options

## Fichiers implémentés

- `backend/open_tutorai/routers/adaptive_tutor.py`
- `backend/open_tutorai/main.py` (ajout du router)

## Endpoint

### POST /api/v1/adaptive/plan

Reçoit :
- `topic`
- `current_level`
- `recent_interactions`
- `feedback_comments`
- `learning_objectives`
- `preferred_exercise_types`

Retourne :
- `adjusted_level`
- `detected_difficulties`
- `suggested_exercises`
- `strategy`
- `priority_focus`

## Exemple d'utilisation

```json
{
  "topic": "équations quadratiques",
  "current_level": "intermediate",
  "recent_interactions": [
    {
      "content": "Tentative de résolution d'une équation quadratique",
      "outcome": "incorrect",
      "score": 0.45
    }
  ],
  "feedback_comments": [
    "Je suis un peu confus sur l'utilisation du discriminant"
  ],
  "learning_objectives": [
    "maîtriser la formule quadratique",
    "appliquer le discriminant"
  ]
}
```

## Comportement attendu

- Le niveau est ajusté en fonction des performances récentes
- Les difficultés sont détectées et explicitement listées
- Les exercices proposés sont ciblés et adaptés
- La stratégie est directive : elle oriente l’apprenant sur la suite à suivre

## Notes

Le module reste simple mais extensible :
- on peut enrichir la génération d'exercices via un moteur de générative
- on peut intégrer des données de feedbacks existantes depuis la base de données
- on peut ajouter une méthode de planification à long terme sur plusieurs sessions

## Vérification RAG des résultats du tutor

Une couche de vérification a été ajoutée pour contrôler la justesse des résultats avant affichage :
- `backend/open_tutorai/routers/adaptive_tutor.py` vérifie les exercices et la stratégie générés
- elle utilise `retrieve_pedagogical_documents()` via une couche RAG documentaire locale
- le résultat inclut un `verification` dans la réponse de `/api/v1/adaptive/plan`
- un endpoint dédié `/api/v1/adaptive/verify` permet de vérifier manuellement des sorties générées

Cette vérification renvoie :
- un score de support
- des éléments soutenus / non soutenus
- les sources RAG consultées
- un verdict `supported` ou `needs_review`
