# Context Retrieval Engine - Implémentation Guide

## Vue d'ensemble

L'algorithme du **Context Retrieval Engine** a été implémenté dans le projet Open TutorAI. Ce guide explique la structure de fichiers créée et comment utiliser le système.

---

## Architecture Implémentée

### 1. Backend (Python/FastAPI)

#### Fichier Principal : `backend/open_tutorai/routers/context_retrieval.py`

Ce fichier contient toute la logique du Context Retrieval Engine :

**Les 5 étapes du pipeline:**

1. **Récupération Multi-Sources** (Lines 152-230)
   - `retrieve_pedagogical_documents()` - Documents pédagogiques (RAG)
   - `retrieve_internal_memory()` - Mémoires internes (Table SQL)
   - `retrieve_generated_summaries()` - Résumés en cache

2. **Normalisation** (Lines 237-280)
   - `normalize_context()` - Standardise tous les résultats

3. **Enrichissement Pédagogique** (Lines 287-376)
   - `calculate_relevance()` - Score textuel
   - `calculate_recency_score()` - Score d'ancienneté
   - `calculate_engagement_score()` - Score d'engagement
   - `enrich_context()` - Agrégation des scores

4. **Filtrage Pédagogique** (Lines 383-441)
   - `filter_context_pedagogical()` - Filtrage par critères
   - `remove_duplicates()` - Élimination des doublons

5. **Classement & Ranking** (Lines 448-520)
   - `rank_context()` - Tri par score composite
   - `apply_diversity_strategy()` - Diversité des sources

**Endpoints API:**
- `POST /api/v1/context/retrieve` - Récupère le contexte pertinent
- `GET /api/v1/context/stats` - Statistiques sur les sources disponibles

#### Fichiers Modifiés

1. **`backend/open_tutorai/main.py`**
   - Ajout de l'import : `from open_tutorai.routers import ... context_retrieval`
   - Ajout du routeur : `app.include_router(context_retrieval.router, prefix="/api/v1", tags=["context"])`

2. **`backend/open_tutorai/config.py`**
   - Ajout de `CONTEXT_RETRIEVAL_CONFIG` avec configuration complète :
     - RAG settings
     - Memory settings
     - Summaries settings
     - Filtering thresholds
     - Scoring weights
     - Output configuration

### 2. Frontend (TypeScript/Svelte)

#### Client API : `src/lib/apis/context/index.ts`

Fournit l'interface pour interagir avec le backend :

**Fonctions principales:**

```typescript
// Récupérer le contexte
retrieveContext(token, request) → ContextRetrievalResponse[]

// Obtenir les statistiques
getContextStats(token) → ContextStatsResponse

// Fonctions de commodité
retrieveContextByMemoryType(token, query, types, maxResults)
retrieveContextFromSources(token, query, sources, maxResults)

// Utilitaires de formatage
formatContextScores(scores) → Record<string, string>
filterContextByScore(results, minScore) → ContextRetrievalResponse[]
groupContextBySource(results) → Record<string, ContextRetrievalResponse[]>
getSourceIcon(source) → string
getSourceLabel(source) → string
```

#### Fichier de Types : `src/lib/types/context.ts`

Définit tous les types TypeScript :
- `ContextScores` - Scores d'un item
- `ContextMetadata` - Métadonnées
- `ContextItem` - Item complet
- `ContextRetrievalOptions` - Options de requête
- `ContextStats` - Statistiques
- `ContextGroupedBySource` - Groupage par source
- `ContextGroupedByMemoryType` - Groupage par type de mémoire

---

## Utilisation

### Backend

#### 1. Appeler l'API de récupération de contexte

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/context/retrieve \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How to solve quadratic equations?",
    "max_results": 10,
    "pedagogical_level": "intermediate",
    "memory_types": ["episodic", "semantic"]
  }'
```

**Response:**
```json
[
  {
    "rank": 1,
    "source": "memory",
    "source_id": "abc123",
    "content_preview": "I learned that quadratic equations...",
    "full_content": "...",
    "metadata": {
      "type": "semantic",
      "created_at": 1713476400,
      "source_id": "abc123"
    },
    "scores": {
      "relevance": 0.95,
      "engagement": 0.3,
      "recency": 0.75,
      "user_alignment": 0.5,
      "composite": 0.68,
      "normalized": 1.0
    }
  }
]
```

### Frontend (TypeScript/Svelte)

#### 1. Récupérer le contexte

```typescript
import { retrieveContext } from '$lib/apis/context';

const results = await retrieveContext(token, {
  query: "How to solve quadratic equations?",
  max_results: 10,
  pedagogical_level: "intermediate"
});

console.log(`Found ${results.length} relevant items`);
results.forEach((item) => {
  console.log(`[${item.rank}] ${item.source}: ${item.content_preview}`);
});
```

#### 2. Utiliser les utilitaires

```typescript
import { 
  groupContextBySource, 
  formatContextScores, 
  getSourceLabel,
  filterContextByScore 
} from '$lib/apis/context';

// Grouper par source
const grouped = groupContextBySource(results);
console.log(`Memory sources: ${grouped.memory.length}`);

// Formater les scores pour affichage
const scores = formatContextScores(results[0].scores);
console.log(`Relevance: ${scores.relevance}`);

// Filtrer par score minimum
const highQuality = filterContextByScore(results, 0.7);

// Obtenir le label de la source
const label = getSourceLabel("memory"); // "Your Memory"
```

#### 3. Afficher dans une composante Svelte

```svelte
<script>
  import { retrieveContext } from '$lib/apis/context';

  let query = "";
  let results = [];
  let loading = false;

  async function search() {
    loading = true;
    try {
      results = await retrieveContext(token, { query, max_results: 15 });
    } catch (error) {
      console.error("Search failed:", error);
    } finally {
      loading = false;
    }
  }
</script>

{#if loading}
  <p>Searching...</p>
{:else if results.length > 0}
  {#each results as item (item.source_id)}
    <div class="context-item">
      <h3>{item.rank}. {item.metadata.title || item.source}</h3>
      <p>{item.content_preview}</p>
      <div class="scores">
        <span>Relevance: {Math.round(item.scores.composite * 100)}%</span>
      </div>
    </div>
  {/each}
{/if}
```

---

## Scoring Pédagogique

Le système utilise un score composite pondéré :

```
Composite Score = (0.4 × Relevance) + (0.3 × Engagement) + 
                  (0.2 × Recency) + (0.1 × User Alignment)
```

### Détail de chaque score :

| Score | Calcul | Plage | Description |
|-------|--------|-------|-------------|
| **Relevance** | Correspondance textuelle query | 0-1 | Pertinence au sujet demandé |
| **Engagement** | Type de mémoire + dernière utilisation | 0-1 | Interactions utilisateur |
| **Recency** | exp(-days_old / 30) | 0-1 | Fraîcheur de l'info (demi-vie 30j) |
| **User Alignment** | Alignement profil utilisateur | 0-1 | Match avec les intérêts |
| **Composite** | Moyenne pondérée | 0-1 | Score final |
| **Normalized** | Score / max_score | 0-1 | Relatif dans les résultats |

---

## Configuration

La configuration est définie dans `backend/open_tutorai/config.py` :

```python
CONTEXT_RETRIEVAL_CONFIG = {
    "rag": {
        "enabled": True,
        "top_k_documents": 5,
        "min_vector_similarity": 0.3
    },
    "memory": {
        "enabled": True,
        "top_k_memories": 10,
        "min_textual_relevance": 0.3,
        "memory_types": ["episodic", "semantic", "procedural", "behavioral"]
    },
    "summaries": {
        "enabled": True,
        "top_k_summaries": 5,
        "cache_ttl_hours": 24,
        "summarization_model": "gpt-3.5-turbo"
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
    },
    "output": {
        "max_results": 20,
        "diversity_strategy": True,
        "include_source_preview": True,
        "preview_length": 300
    }
}
```

---

## Sources de Données

### 1. Documents Pédagogiques (RAG)

**Source:** `backend/data/uploads/`  
**Type:** Documents uploadés par l'utilisateur  
**Recherche:** Vectorielle (embeddings)  
**Intégration:** À faire (nécessite un service RAG)

```python
async def retrieve_pedagogical_documents(user_id, query, top_k=5):
    # TODO: Intégrer avec le système RAG
    return []
```

### 2. Mémoire Interne

**Source:** Table `opentutorai_memory` (SQLAlchemy)  
**Types:** episodic, semantic, procedural, behavioral  
**Recherche:** ILIKE textuelle  
**Implémentation:** ✅ Complète

```python
async def retrieve_internal_memory(user_id, query, memory_types=None, limit=10, db=None):
    # Recherche textuelle dans opentutorai_memory
    # Filtrage par user_id et memory_types
    # Tri par date de mise à jour
```

### 3. Résumés Générés

**Source:** `backend/data/cache/summaries/` (JSON files)  
**Génération:** Via LLM (configurable)  
**Cache:** TTL de 24 heures  
**Implémentation:** ✅ Complète

```python
async def retrieve_generated_summaries(user_id, query, cache_ttl_hours=24, limit=5):
    # Charge depuis cache
    # Vérifie TTL
    # Recherche par pertinence
```

---

## Flux de Données

```
User Query
    ↓
┌─────────────────────────────────┐
│ STEP 1: Retrieve Multi-Sources  │
├─────────────────────────────────┤
│ • Pedagogical Documents (RAG)   │
│ • Internal Memory (SQL)         │
│ • Generated Summaries (Cache)   │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ STEP 2: Normalize               │
│ (Unified format)                │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ STEP 3: Enrich                  │
│ (Add pedagogical metadata)      │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ STEP 4: Filter                  │
│ (Remove non-relevant items)     │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ STEP 5: Rank                    │
│ (Sort by composite score)       │
└────────────┬────────────────────┘
             ↓
    Ranked Results (JSON)
```

---

## Prochaines Étapes

### 1. Intégration RAG
Implémenter la récupération des documents pédagogiques via un service vectoriel :
- Weaviate, Pinecone, Milvus, ou autre
- Intégrer dans `retrieve_pedagogical_documents()`

### 2. Génération de Résumés
Implémenter la génération automatique de résumés :
- Appeler l'LLM pour créer des résumés
- Persister en cache
- Mettre à jour TTL

### 3. Feedback Utilisateur
Ajouter un mécanisme de feedback :
- L'utilisateur évalue la pertinence
- Affiner les poids dynamiquement
- ML pour optimisation continue

### 4. Analytics
Tracker l'utilisation :
- Query patterns
- Context item access patterns
- User engagement metrics

### 5. UI Components
Créer des composantes Svelte pour afficher:
- Search avec context retrieval
- Result cards avec scores
- Filtering UI
- Context statistics dashboard

---

## Dépannage

### Les résultats sont vides ?

1. Vérifier que l'utilisateur a des mémoires stockées :
   ```bash
   curl http://localhost:8000/api/v1/context/stats \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

2. Vérifier les seuils de filtrage dans `config.py` :
   - `relevance_threshold` ne doit pas être trop haut
   - `recency_threshold` ne doit pas éliminer tout

### Les scores ne paraissent pas logiques ?

1. Vérifier le calcul dans `compute_composite_score()`
2. Ajuster les poids dans `config.py` → `scoring`
3. Vérifier les normalisations dans les fonctions individuelles

### Performance lente ?

1. Réduire `top_k_memories` dans la config
2. Ajouter des indexes sur la table `opentutorai_memory`
3. Implémenter du caching au niveau des queries

---

## Fichiers Créés/Modifiés

✅ **Fichiers Créés :**
- `backend/open_tutorai/routers/context_retrieval.py` - Routeur principal
- `src/lib/apis/context/index.ts` - Client TypeScript
- `src/lib/types/context.ts` - Definitions TypeScript

✅ **Fichiers Modifiés :**
- `backend/open_tutorai/main.py` - Ajout du routeur
- `backend/open_tutorai/config.py` - Configuration CRE

---

## Contact & Support

Pour des questions ou issues sur l'implémentation :
- Consultez le fichier `ContextRetrievalEnginealgo.md` pour l'algorithme détaillé
- Regardez les docstrings dans `context_retrieval.py`
- Vérifiez la configuration dans `config.py`

