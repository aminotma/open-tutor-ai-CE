# Summarization Layer

## Objectif

Implémenter une couche de résumé pour réduire la taille du contexte tout en conservant l'information essentielle. Cette couche applique plusieurs techniques de réduction de contenu pour optimiser l'utilisation du contexte par le modèle de langage.

## Techniques utilisées

### 1. Résumé des interactions (`summarize_interactions`)
- **Objectif** : Réduire les contenus longs tout en gardant les points clés
- **Méthode** : Extraction des phrases clés (début, milieu, fin) avec comptage de tokens via `tiktoken`
- **Limite** : Nombre maximal de tokens configurable (défaut : 500 tokens) pour éviter les dépassements de limites de modèles externes

### 2. Fenêtre glissante (`sliding_window_filter`)
- **Objectif** : Garder seulement les éléments les plus pertinents et récents
- **Méthode** : Tri par score composite puis limitation à N éléments
- **Paramètres** : Taille de fenêtre et seuil de score

### 3. Oubli des informations non pertinentes (`forget_irrelevant`)
- **Objectif** : Retirer les contenus et phrases peu liés à la requête avant le résumé
- **Méthode** :
  - suppression des phrases contenant peu ou pas de termes de la requête
  - élimination des éléments de contexte à faible score composite et faible pertinence
- **Avantage** : Réduit le bruit et améliore la qualité du résumé

### 4. Extraction des éléments clés (`extract_key_elements`)
- **Objectif** : Identifier et extraire les phrases les plus pertinentes par rapport à la requête
- **Méthode** : Scoring des phrases basé sur les termes de la requête
- **Limite** : Maximum 3 phrases clés par contenu

## Modifications réalisées

### Backend
- `backend/open_tutorai/routers/context_retrieval.py`
  - Ajout des fonctions de résumé dans la section "SUMMARIZATION LAYER"
  - Intégration de `apply_summarization_layer()` dans le pipeline principal
  - Étape 6 ajoutée après le ranking

### Configuration
- `backend/open_tutorai/config.py`
  - Ajout de la section `summarization` avec paramètres configurables

## Pipeline mis à jour

```
┌─────────────────────────────────────────┐
│ STEP 1: RETRIEVE MULTI-SOURCES          │
│ • retrieve_pedagogical_documents()      │
│ • retrieve_internal_memory()            │
│ • retrieve_generated_summaries()        │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│ STEP 2: NORMALIZE                       │
│ • normalize_context()                   │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│ STEP 3: ENRICH PEDAGOGICALLY            │
│ • enrich_context()                      │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│ STEP 4: FILTER PEDAGOGICALLY            │
│ • filter_context_pedagogical()          │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│ STEP 5: RANK & SORT                     │
│ • rank_context()                        │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│ STEP 6: SUMMARIZATION LAYER             │
│ • apply_summarization_layer()           │
│   ├── summarize_interactions()          │
│   ├── sliding_window_filter()           │
│   └── extract_key_elements()            │
└────────────┬────────────────────────────┘
             ↓
        RESULTS (JSON)
```

## Configuration

```python
CONTEXT_RETRIEVAL_CONFIG = {
    "summarization": {
        "enabled": True,
        "max_content_length": 1000,        # Longueur max par contenu
        "sliding_window_size": 10,         # Nombre max d'éléments
        "score_threshold": 0.3,            # Seuil de score minimum
        "summarize_interactions": True,    # Activer résumé interactions
        "extract_key_elements": True,      # Activer extraction clés
        "forget_irrelevant": {
            "enabled": True,
            "context_threshold": 0.15,
            "min_relevance": 0.1,
            "sentence_match_ratio": 0.15
        }
    }
}
```

## Métriques ajoutées

Chaque élément résumé inclut maintenant :
- `original_length` : Longueur du contenu original
- `summarized_length` : Longueur du contenu résumé
- `content` : Contenu résumé

## Exemple d'utilisation

```python
# Avant résumé
{
    "content": "Longue explication détaillée sur les fractions...",
    "composite_score": 0.85
}

# Après résumé
{
    "content": "Les fractions représentent des parties d'un tout. Additionner nécessite un dénominateur commun.",
    "original_length": 2500,
    "summarized_length": 120,
    "composite_score": 0.85
}
```

## Avantages

- **Réduction de taille** : Contexte plus compact pour le modèle
- **Préservation d'information** : Points clés conservés
- **Performance améliorée** : Moins de tokens utilisés
- **Pertinence accrue** : Focus sur les éléments les plus importants

## Fichiers concernés

- `backend/open_tutorai/routers/context_retrieval.py`
- `backend/open_tutorai/config.py`