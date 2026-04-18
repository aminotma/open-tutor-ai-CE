# Dynamic Context Manager

## Objectif

Implémenter un gestionnaire de contexte dynamique qui construit le contexte utilisé par le modèle de langage à partir de sources multiples :
- profil apprenant
- historique utilisateur
- résultats de récupération
- objectifs pédagogiques

Le système doit sélectionner et classer les informations pertinentes pour limiter le bruit informationnel.

## Modifications réalisées

### Backend
- `backend/open_tutorai/routers/context_retrieval.py`
  - Ajout du champ `learning_objectives` dans le modèle de requête `ContextRetrievalRequest`
  - Enrichissement du profil utilisateur avec `learning_objectives`
  - Ajout de la fonction `calculate_user_alignment(...)` pour calculer l'alignement entre :
    - les intérêts utilisateur
    - les objectifs pédagogiques
    - le domaine du contenu et le texte du contexte
  - Mise à jour de la logique `enrich_context(...)` pour utiliser ce nouvel alignement

### Frontend / Typescript
- `src/lib/apis/context/index.ts`
  - Ajout du champ `learning_objectives` dans `ContextRetrievalRequest`
  - Transmission de `learning_objectives` dans le body de la requête POST vers `/api/v1/context/retrieve`
- `src/lib/types/context.ts`
  - Ajout du champ `learning_objectives` dans `ContextRetrievalOptions`

## Fonctionnement du pipeline

1. **Récupération multi-sources**
   - Documents pédagogiques
   - Mémoires internes
   - Résumés générés

2. **Normalisation**
   - Uniformisation du format de chaque source

3. **Enrichissement**
   - Pertinence textuelle
   - Récence
   - Engagement
   - Alignement profil/utilisateur + objectifs pédagogiques

4. **Filtrage pédagogique**
   - Seuils de pertinence et de récence
   - Compatibilité du niveau pédagogique
   - Suppression des doublons similaires

5. **Classement**
   - Score composite pondéré
   - Stratégie de diversité
   - Limitation du nombre de résultats

## Utilisation

Envoyer une requête POST vers `/api/v1/context/retrieve` avec :

```json
{
  "query": "Comprendre les fractions",
  "max_results": 10,
  "pedagogical_level": "intermediate",
  "learning_objectives": [
    "maîtriser la simplification",
    "comprendre l'addition de fractions"
  ]
}
```

## Fichiers concernés

- `backend/open_tutorai/routers/context_retrieval.py`
- `src/lib/apis/context/index.ts`
- `src/lib/types/context.ts`

## Résultat attendu

Le contexte renvoyé est désormais mieux aligné sur les objectifs pédagogiques et les intérêts de l'apprenant, tout en préservant la pertinence, la récence et la diversité des sources.
