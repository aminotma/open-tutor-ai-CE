# Pipeline du Context Retrieval Engine - Résumé Complet

## Vue d'ensemble

Le système Open TutorAI utilise un **pipeline en 6 étapes** pour récupérer et traiter le contexte pédagogique destiné aux apprenants. Ce pipeline combine trois sources d'information (documents pédagogiques, mémoire interne, résumés générés) et les classe selon leur pertinence pédagogique.

## Architecture du Pipeline

```mermaid
flowchart TD
    A[STEP 1: RETRIEVE MULTI-SOURCES<br/>• Documents pédagogiques<br/>• Mémoire interne<br/>• Résumés générés] --> B[STEP 2: NORMALIZE<br/>• normalize_context()]
    
    B --> C[STEP 3: ENRICH PEDAGOGICALLY<br/>• enrich_context()]
    
    C --> D[STEP 4: FILTER PEDAGOGICALLY<br/>• filter_context_pedagogical()]
    
    D --> E[STEP 5: RANK & SORT<br/>• rank_context()]
    
    E --> F[STEP 6: SUMMARIZATION LAYER<br/>• apply_summarization_layer()<br/>├── summarize_interactions()<br/>├── sliding_window_filter()<br/>└── extract_key_elements()]
    
    F --> G[RESULTS JSON]
```

## Détail des Étapes

### Étape 1: Récupération Multi-Sources
- **Documents pédagogiques** : Recherche dans les fichiers locaux (`docs/`, `backend/`)
- **Mémoire interne** : Récupération depuis la base de données (types: épisodique, sémantique, procédural, comportemental)
- **Résumés générés** : Cache des résumés précédemment créés

### Étape 2: Normalisation
- Standardisation du format de tous les éléments récupérés
- Limitation de la taille du contenu (5000 caractères max)
- Création d'objets `NormalizedContextItem` uniformes

### Étape 3: Enrichissement Pédagogique
Calcul de quatre scores principaux pour chaque élément :

#### 1. relevance_score (Pertinence textuelle)
```python
def calculate_relevance(content: str, query: str) -> float:
    # Comptage des termes de requête présents
    matches = sum(1 for term in query_terms if term in content)
    exact_score = min(matches / len(query_terms), 1.0)
    
    # Similarité textuelle
    similarity_score = _calculate_text_similarity(query, content)
    
    return max(exact_score, similarity_score)
```
**Résultat** : 0.0 à 1.0

#### 2. recency_score (Récence)
```python
def calculate_recency_score(created_at: float) -> float:
    age_days = (current_time - created_at) / (24 * 3600)
    recency = exp(-age_days / 30)  # Demi-vie: 30 jours
    return min(max(recency, 0.0), 1.0)
```
**Résultat** : 1.0 (très récent) à 0.0 (très ancien)

#### 3. engagement_score (Engagement)
```python
def calculate_engagement_score(item_type: str, metadata: Dict) -> float:
    score = 0.0
    if item_type == "memory" and metadata.get("type") == "episodic":
        score += 0.3  # Bonus mémoires épisodiques
    if metadata.get("last_updated"):
        score += 0.2  # Bonus éléments mis à jour
    return min(score, 1.0)
```
**Résultat** : 0.0 à 1.0

#### 4. user_preference_alignment (Alignement utilisateur)
```python
def calculate_user_alignment(subject_domain: str, user_profile: Dict, content: str) -> float:
    if subject_domain in user_interests:
        return 1.0  # Alignement parfait
    if any(obj in subject_domain for obj in learning_objectives):
        return 0.9  # Objectif dans domaine
    if any(obj in content for obj in learning_objectives):
        return 0.8  # Objectif dans contenu
    return 0.5  # Défaut
```
**Résultat** : 0.5 à 1.0

### Étape 4: Filtrage Pédagogique
- **Filtre par pertinence** : `relevance_score >= 0.3`
- **Filtre par récence** : `recency_score >= 0.1`
- **Filtre par niveau pédagogique** : écart maximum de 1 niveau
- **Suppression des doublons** : similarité cosinus > 0.95

### Étape 5: Classement et Tri
Calcul du **composite_score** comme moyenne pondérée :
```python
composite_score = (
    0.4 * relevance_score +      # 40% pertinence
    0.3 * engagement_score +     # 30% engagement
    0.2 * recency_score +        # 20% récence
    0.1 * user_preference_alignment  # 10% alignement
)
```

Tri par `composite_score` décroissant, puis application de la stratégie de diversité.

### Étape 6: Couche de Résumé (Summarization Layer)
Réduction de la taille du contexte tout en préservant l'information essentielle :

#### Techniques utilisées :
1. **Résumé des interactions** : Extraction des phrases clés (début, milieu, fin) avec limite de tokens
2. **Fenêtre glissante** : Garde les N éléments les plus pertinents avec `score_threshold >= 0.3`
3. **Extraction d'éléments clés** : Phrases les plus pertinentes par rapport à la requête

## Configuration

```python
CONTEXT_RETRIEVAL_CONFIG = {
    "summarization": {
        "enabled": True,
        "max_content_length": 1000,
        "sliding_window_size": 10,
        "score_threshold": 0.3,        # Seuil pour filtrage
        "summarize_interactions": True,
        "extract_key_elements": True
    },
    "filtering": {
        "relevance_threshold": 0.3,
        "recency_threshold": 0.1,
        "max_age_days": 365,
        "allow_level_gap": 1
    },
    "scoring": {
        "relevance_weight": 0.4,
        "engagement_weight": 0.3,
        "recency_weight": 0.2,
        "user_alignment_weight": 0.1
    }
}
```

## Avantages du Système

- **Multi-sources** : Combinaison de documents, mémoire et résumés
- **Personnalisation** : Adaptation aux intérêts et objectifs de l'apprenant
- **Optimisation** : Réduction de la taille du contexte sans perte d'information
- **Pertinence pédagogique** : Filtrage et classement selon critères éducatifs
- **Performance** : Utilisation efficace des tokens des modèles de langage

## Métriques de Sortie

Chaque élément final inclut :
- `rank` : Position dans le classement
- `source` : Type de source (pedagogical/memory/summary)
- `content_preview` : Aperçu du contenu (300 caractères)
- `scores` : Tous les scores calculés (relevance, engagement, recency, composite, etc.)
- `metadata` : Informations sur la source et la création

Ce système assure que l'apprenant reçoit le contexte le plus **pertinent**, **engageant**, **récent** et **pédagogiquement adapté** à ses besoins d'apprentissage.