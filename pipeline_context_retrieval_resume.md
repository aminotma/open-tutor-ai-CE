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

#### Calcul du composite_score
Chaque élément reçoit une moyenne pondérée combinant les 4 scores :
```python
composite_score = (
    0.4 * relevance_score +              # 40% pertinence
    0.3 * engagement_score +             # 30% engagement
    0.2 * recency_score +                # 20% récence
    0.1 * user_preference_alignment      # 10% alignement
)
```
**Résultat** : 0.0 à 1.0

**Exemple** :
- relevance_score = 0.85 → 0.4 × 0.85 = 0.34
- engagement_score = 0.60 → 0.3 × 0.60 = 0.18
- recency_score = 0.95 → 0.2 × 0.95 = 0.19
- user_alignment = 0.80 → 0.1 × 0.80 = 0.08
- **composite_score = 0.79**

#### Calcul du normalized_score
Après tri par `composite_score` décroissant, chaque élément est normalisé relatif au meilleur :
```python
max_score = max(composite_score pour tous les éléments)
normalized_score = composite_score / max_score if max_score > 0 else 0
```
**Résultat** : 0.0 à 1.0, où 1.0 = meilleur élément du lot

**Exemple** :
- Si max_score = 0.90 et composite_score = 0.79
- normalized_score = 0.79 / 0.90 = **0.878** (soit 87.8% du meilleur)

#### Application de la stratégie de diversité
Limitation par source pour éviter la concentration :
- Maximum 3 éléments par source type (pedagogical, memory, summary)
- Répartition équilibrée entre les trois sources

### Étape 6: Couche de Résumé (Summarization Layer)
Réduction de la taille du contexte tout en préservant l'information essentielle :

#### 1. Oubli des informations non pertinentes (forget_irrelevant)

**Objectif** : Éliminer les éléments et phrases contribuant peu à la pertinence globale

**Étape A : Suppression des phrases non pertinentes**
```python
def forget_irrelevant_sentences(content: str, query: str, min_match_ratio: float = 0.15) -> str:
    # Pour chaque phrase, calculer le ratio de termes de requête présents
    for sentence in content.split('.'):
        matches = sum(1 for term in query_terms if term in sentence)
        match_ratio = matches / len(query_terms)
        
        # Garder la phrase seulement si min_match_ratio >= 0.15
        if match_ratio >= min_match_ratio:
            kept_sentences.append(sentence)
    
    return '. '.join(kept_sentences)
```

**Exemple** :
- Query: "machine learning model"
- Phrase 1: "The neural network uses gradient descent" → match_ratio = 1/3 = 0.33 ✓ gardée
- Phrase 2: "The weather today is sunny" → match_ratio = 0/3 = 0.0 ✗ supprimée

**Étape B : Suppression des éléments contextuels faibles**
```python
def forget_irrelevant_context_items(items: List[Dict], 
                                   threshold: float = 0.15,
                                   min_relevance: float = 0.1) -> List[Dict]:
    kept = []
    for item in items:
        # Critère 1 : normalized_score >= context_threshold
        if item.get("normalized_score", 0) >= threshold:
            kept.append(item)
        # Critère 2 : sinon, vérifier relevance_score >= min_relevance
        elif item.get("relevance_score", 0) >= min_relevance:
            kept.append(item)
    
    # Garantir au minimum 1 élément
    return kept if kept else items[:1]
```

**Logique d'oubli** :
- Si `normalized_score >= 0.15` → Élément conservé (suffisamment bon relatif aux autres)
- Sinon si `relevance_score >= 0.1` → Élément conservé (malgré tout, pertinent)
- Sinon → Élément oublié (oubli pédagogique)
- Minimum 1 élément garanti (fallback)

**Exemple avec 3 éléments** :
```
Élément A: normalized_score = 0.95, relevance_score = 0.85 → CONSERVÉ
Élément B: normalized_score = 0.20, relevance_score = 0.12 → CONSERVÉ (≥ 0.15 non, mais ≥ 0.1 oui)
Élément C: normalized_score = 0.08, relevance_score = 0.05 → OUBLIÉ
```

#### 2. Techniques de résumé appliquées après l'oubli

**Résumé des interactions** : Extraction des phrases clés (début, milieu, fin) avec limite de tokens

**Fenêtre glissante** : Garde les N éléments les plus pertinents avec `score_threshold >= 0.3`

**Extraction d'éléments clés** : Phrases les plus pertinentes par rapport à la requête

## Configuration

```python
CONTEXT_RETRIEVAL_CONFIG = {
    "summarization": {
        "enabled": True,
        "max_content_length": 1000,
        "sliding_window_size": 10,
        "score_threshold": 0.3,
        "summarize_interactions": True,
        "extract_key_elements": True,
        "forget_irrelevant": {
            "enabled": True,
            "context_threshold": 0.15,      # Min normalized_score pour conserver
            "min_relevance": 0.1,           # Min relevance_score fallback
            "sentence_match_ratio": 0.15    # Min ratio termes/requête par phrase
        }
    },
    "filtering": {
        "relevance_threshold": 0.3,
        "recency_threshold": 0.1,
        "max_age_days": 365,
        "allow_level_gap": 1
    },
    "scoring": {
        "relevance_weight": 0.4,            # 40% pertinence
        "engagement_weight": 0.3,           # 30% engagement
        "recency_weight": 0.2,              # 20% récence
        "user_alignment_weight": 0.1        # 10% alignement utilisateur
    }
}
```

### Paramètres d'oubli expliqués

| Paramètre | Valeur | Utilisation |
|-----------|--------|-------------|
| `context_threshold` | 0.15 | Seuil minimum du `normalized_score` pour conserver un élément. Un élément avec score normalisé < 0.15 (< 15% du meilleur) est considéré comme non pertinent. |
| `min_relevance` | 0.1 | Fallback : si un élément ne passe pas le seuil de contexte, il est quand même conservé s'il a une `relevance_score` ≥ 0.1. |
| `sentence_match_ratio` | 0.15 | Dans les contenus longs, une phrase est gardée seulement si au moins 15% de ses termes correspondent à la requête. |

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