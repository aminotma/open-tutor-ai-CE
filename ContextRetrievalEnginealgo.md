# Context Retrieval Engine - Algorithme Détaillé

## Objectif Global
Créer un moteur intelligent de récupération de contexte qui combine plusieurs sources d'information (documents pédagogiques, mémoire interne, résumés générés) pour fournir un contexte pertinent et classé selon sa valeur pédagogique.

---

## Architecture Générale

Le moteur fonctionne selon un pipeline en 5 étapes principales :
1. **Récupération multi-sources** : Collecter les informations de 3 sources
2. **Extraction et normalisation** : Standardiser les formats
3. **Enrichissement du contexte** : Ajouter des métadonnées
4. **Filtrage pédagogique** : Appliquer des critères de pertinence
5. **Classement et ranking** : Classer par score de pertinence

---

## Étape 1 : Récupération Multi-Sources

### 1.1 Source A : Documents Pédagogiques (RAG)

**Objectif** : Récupérer les documents pédagogiques pertinents par recherche vectorielle.

**Fichiers impliqués** :
- **Stockage** : `backend/data/uploads/` - Répertoire contenant les documents pédagogiques uploadés
- **API Backend** : `backend/open_tutorai/routers/supports.py` - Routeur pour accéder aux ressources pédagogiques
- **Configuration RAG** : `backend/open_tutorai/config.py` - Configuration du moteur de recherche vectoriel

**Pseudo-code** :
```
FONCTION RecupererDocumentsPedagogiques(requete_utilisateur, user_id):
    1. Encoder la requête en vecteur via embeddings
    2. Interroger la base vectorielle avec le vecteur
    3. Filtrer par user_id pour respecter les permissions
    4. Récupérer les top-K documents (K=5 par défaut)
    5. Extraire :
       - Document ID
       - Titre
       - Contenu (avec chunks)
       - Score de similarité vectorielle
       - Métadonnées (cours, sujet, etc.)
    6. RETOURNER : Liste de documents avec scores
FIN FONCTION
```

**Interfaçage** :
```python
# Dans backend/open_tutorai/routers/context_retrieval.py (fichier à créer)
from backend.open_tutorai.config import RAG_CONFIG
from open_webui.models.documents import Documents

async def retrieve_pedagogical_documents(
    user_id: str,
    query: str,
    top_k: int = 5
) -> List[Dict]:
    """Récupère les documents pédagogiques pertinents via RAG"""
    # Appel à l'API de recherche vectorielle
    # Retour : [{"id": "", "title": "", "content": "", "vector_score": 0.95}]
```

---

### 1.2 Source B : Mémoire Interne

**Objectif** : Récupérer les mémoires stockées de l'utilisateur pertinentes pour la requête.

**Fichiers impliqués** :
- **Modèle BDD** : `backend/open_tutorai/models/database.py` - Table `opentutorai_memory`
- **Routeur API** : `backend/open_tutorai/routers/memories.py` - Endpoints CRUD sur les mémoires
- **Types** : `src/lib/types/memory.ts` - Définition des types TypeScript

**Pseudo-code** :
```
FONCTION RecupererMemoireInterne(requete_utilisateur, user_id):
    1. Exécuter une requête textuelle sur la table opentutorai_memory
    2. Filtrer par user_id
    3. Appliquer une recherche ILIKE sur le champ content
       - Modifier requête : remplacer espaces par '%' (wildcard)
    4. Pour chaque type de mémoire, classer par updated_at DESC puis created_at DESC
    5. Limiter à top-N résultats (N=10 par défaut)
    6. Extraire :
       - Memory ID
       - Memory Type (episodic, semantic, procedural, behavioral)
       - Content
       - Metadata
       - Dates (created_at, updated_at)
       - Score de pertinence textuelle (basé sur position du match)
    7. RETOURNER : Liste de mémoires avec scores
FIN FONCTION
```

**Interfaçage** :
```python
# Dans backend/open_tutorai/routers/context_retrieval.py
from backend.open_tutorai.routers.memories import MemoryResponse
from sqlalchemy import and_, or_

async def retrieve_internal_memory(
    user_id: str,
    query: str,
    memory_types: Optional[List[str]] = None,
    limit: int = 10
) -> List[Dict]:
    """Récupère les mémoires pertinentes pour la requête"""
    # Requête SQL avec ILIKE wildcard
    # Retour : [{"id": "", "type": "semantic", "content": "", "textual_score": 0.8}]
```

**Requête SQL détaillée** :
```sql
SELECT id, user_id, memory_type, content, memory_metadata, 
       created_at, updated_at
FROM opentutorai_memory
WHERE user_id = :user_id 
  AND content ILIKE :search_pattern
  AND (memory_type = ANY(:types) OR :types IS NULL)
ORDER BY updated_at DESC NULLS LAST, created_at DESC
LIMIT :limit;
```

---

### 1.3 Source C : Résumés Générés

**Objectif** : Récupérer les résumés existants ou générer de nouveaux résumés des interactions précédentes.

**Fichiers impliqués** :
- **Stockage résumés** : `backend/data/cache/summaries/` - Cache des résumés générés
- **Modèle résumé** : `backend/open_tutorai/models/database.py` - Ajouter table `opentutorai_summary` (si nécessaire)
- **Configuration IA** : `backend/open_tutorai/config.py` - Configuration du modèle de génération

**Pseudo-code** :
```
FONCTION RecupererResumesGeneres(requete_utilisateur, user_id):
    1. Vérifier le cache local : backend/data/cache/summaries/
    2. SI résumé en cache ET (now - cache_timestamp) < TTL :
       a. Charger depuis le cache
    SINON :
       a. Récupérer les N derniers messages de la conversation
          - Source : `backend/data/` ou API chat historique
       b. Générer résumé via LLM (modèle configuré)
       c. Persister en cache avec horodatage
    3. Effectuer recherche textuelle sur les résumés
    4. Classer par pertinence et date
    5. Limiter à top-M résumés (M=5 par défaut)
    6. Extraire :
       - Summary ID
       - Generated text
       - Source conversation ID
       - Timestamp de génération
       - Score de pertinence textuelle
    7. RETOURNER : Liste de résumés avec scores
FIN FONCTION
```

**Interfaçage** :
```python
# Dans backend/open_tutorai/routers/context_retrieval.py
import json
from pathlib import Path
from datetime import datetime, timedelta

async def retrieve_generated_summaries(
    user_id: str,
    query: str,
    cache_ttl_hours: int = 24,
    limit: int = 5
) -> List[Dict]:
    """Récupère les résumés pertinents (avec cache)"""
    cache_dir = Path("backend/data/cache/summaries")
    # Charger depuis cache ou générer
    # Retour : [{"id": "", "text": "", "source_conversation": "", "summary_score": 0.75}]
```

---

## Étape 2 : Extraction et Normalisation

**Objectif** : Standardiser les formats de toutes les sources pour traitement unifié.

**Pseudo-code** :
```
FONCTION NormaliserContext(sources: {documents, memories, summaries}):
    1. Créer structure uniforme pour chaque source :
       {
           "source_type": "pedagogical" | "memory" | "summary",
           "id": string,
           "content": string,
           "metadata": {
               "type": string,           // document, episodic, semantic, etc.
               "created_at": timestamp,
               "last_updated": timestamp,
               "source_id": string
           },
           "raw_score": float            // Score brut de la source
       }
    2. POUR CHAQUE source :
       a. Extraire le content principal
       b. Tronquer si > 5000 caractères (avec ellipsis)
       c. Nettoyer : supprimer whitespace excessif, normaliser encodage
       d. Extraire les métadonnées standardisées
    3. RETOURNER : Liste d'objets normalisés
FIN FONCTION
```

**Implémentation** :
```python
# Dans backend/open_tutorai/routers/context_retrieval.py

from dataclasses import dataclass
from typing import Literal
from datetime import datetime

@dataclass
class NormalizedContextItem:
    source_type: Literal["pedagogical", "memory", "summary"]
    id: str
    content: str
    metadata: Dict[str, Any]
    raw_score: float

def normalize_context(
    documents: List[Dict],
    memories: List[Dict],
    summaries: List[Dict]
) -> List[NormalizedContextItem]:
    """Normalise tous les résultats au même format"""
    normalized = []
    
    # Normaliser documents
    for doc in documents:
        normalized.append(NormalizedContextItem(
            source_type="pedagogical",
            id=doc["id"],
            content=doc["content"][:5000] if len(doc["content"]) > 5000 else doc["content"],
            metadata={
                "type": "document",
                "title": doc.get("title", ""),
                "created_at": doc.get("created_at"),
                "source_id": doc["id"]
            },
            raw_score=doc.get("vector_score", 0.0)
        ))
    
    # Normaliser mémoires
    for memory in memories:
        normalized.append(NormalizedContextItem(
            source_type="memory",
            id=memory["id"],
            content=memory["content"][:5000],
            metadata={
                "type": memory.get("type", "semantic"),
                "created_at": memory.get("created_at"),
                "last_updated": memory.get("updated_at"),
                "source_id": memory["id"]
            },
            raw_score=memory.get("textual_score", 0.0)
        ))
    
    # Normaliser résumés
    for summary in summaries:
        normalized.append(NormalizedContextItem(
            source_type="summary",
            id=summary["id"],
            content=summary["text"][:5000],
            metadata={
                "type": "summary",
                "source_conversation": summary.get("source_conversation"),
                "created_at": summary.get("created_at"),
                "source_id": summary["id"]
            },
            raw_score=summary.get("summary_score", 0.0)
        ))
    
    return normalized
```

---

## Étape 3 : Enrichissement du Contexte

**Objectif** : Ajouter des métadonnées pédagogiques pour le classement ultérieur.

**Fichiers impliqués** :
- **Modèle utilisateur** : `backend/open_tutorai/models/database.py` - Profil utilisateur
- **Configuration pédagogique** : `backend/open_tutorai/config.py` - Niveaux, domaines, etc.

**Pseudo-code** :
```
FONCTION EnrichirContext(contexte_normalise, user_id, query):
    1. Récupérer le profil utilisateur :
       - Niveau pédagogique (beginner, intermediate, advanced)
       - Domaines d'intérêt
       - Préférences d'apprentissage
    2. POUR CHAQUE item du contexte :
       a. Calculer relevance_score :
          - Pertinence textuelle (query matching)
          - Pertinence sémantique (si disponible)
       b. Déduire pedagogical_level à partir du contenu
       c. Associer subject_domain en fonction des métadonnées
       d. Calculer recency_score = exp(-days_since_update / 30)
       e. Calculer engagement_score :
          - Si episodic memory : +0.3
          - Si frequently_accessed : +0.2
       f. Ajouter au contexte :
          - relevance_score
          - pedagogical_level
          - subject_domain
          - recency_score
          - engagement_score
    3. RETOURNER : Contexte enrichi avec scores pédagogiques
FIN FONCTION
```

**Implémentation** :
```python
# Dans backend/open_tutorai/routers/context_retrieval.py

from math import exp
from datetime import datetime, timezone

async def enrich_context(
    context_items: List[NormalizedContextItem],
    user_id: str,
    query: str,
    user_profile: Dict
) -> List[Dict]:
    """Enrichit le contexte avec des scores pédagogiques"""
    
    enriched = []
    current_time = datetime.now(timezone.utc)
    
    for item in context_items:
        # Scores individuels
        relevance_score = calculate_relevance(item.content, query)
        
        # Recency score (exponentiel décroissant)
        created_at = item.metadata.get("created_at", current_time)
        days_ago = (current_time - created_at).days
        recency_score = exp(-days_ago / 30)
        
        # Engagement score
        engagement_score = 0.0
        if item.source_type == "memory" and item.metadata.get("type") == "episodic":
            engagement_score += 0.3
        if item.metadata.get("last_updated"):
            engagement_score += 0.2
        
        enriched.append({
            **item.__dict__,
            "relevance_score": relevance_score,
            "recency_score": recency_score,
            "engagement_score": engagement_score,
            "pedagogical_level": deduce_pedagogical_level(item.content),
            "subject_domain": extract_subject_domain(item.metadata),
            "user_preference_alignment": calculate_user_alignment(
                item.metadata.get("subject_domain"),
                user_profile.get("interests", [])
            )
        })
    
    return enriched

def calculate_relevance(content: str, query: str) -> float:
    """Calcule le score de pertinence textuelle"""
    terms = query.lower().split()
    content_lower = content.lower()
    matches = sum(1 for term in terms if term in content_lower)
    return min(matches / len(terms) if terms else 0, 1.0)

def deduce_pedagogical_level(content: str) -> str:
    """Déduit le niveau pédagogique du contenu"""
    # Heuristique simple basée sur la longueur et la complexité
    if len(content) < 100:
        return "beginner"
    elif len(content) < 500:
        return "intermediate"
    else:
        return "advanced"

def extract_subject_domain(metadata: Dict) -> str:
    """Extrait le domaine de sujet"""
    return metadata.get("subject_domain", "general")

def calculate_user_alignment(subject: str, interests: List[str]) -> float:
    """Calcule l'alignement avec les préférences utilisateur"""
    if subject in interests:
        return 1.0
    return 0.5
```

---

## Étape 4 : Filtrage Pédagogique

**Objectif** : Appliquer des critères pédagogiques pour éliminer le contexte non pertinent.

**Pseudo-code** :
```
FONCTION FiltrerContext(contexte_enrichi, user_profile, seuils):
    1. Définir seuils de filtrage :
       - relevance_min = 0.3
       - recency_max_days = 365
       - pedagogical_level_match = user_profile.level ± 1
    2. POUR CHAQUE item :
       a. FILTRER SI :
          - relevance_score < relevance_min
          - recency_score < 0.1 (très ancien)
          - pedagogical_level incompatible avec le profil utilisateur
          - contenu dupliqué (vérifier similarité > 0.95)
       b. AJOUTER À keep_list SI tous les critères passent
    3. Éliminer les doublons :
       - Comparer les contenus avec cosine similarity
       - Conserver celui avec le meilleur score composite
    4. RETOURNER : Contexte filtré
FIN FONCTION
```

**Implémentation** :
```python
# Dans backend/open_tutorai/routers/context_retrieval.py

def filter_context_pedagogical(
    enriched_items: List[Dict],
    user_profile: Dict,
    config: Dict
) -> List[Dict]:
    """Filtre le contexte selon des critères pédagogiques"""
    
    relevance_min = config.get("relevance_threshold", 0.3)
    recency_min = config.get("recency_threshold", 0.1)
    
    filtered = []
    
    for item in enriched_items:
        # Critères de filtrage
        if item["relevance_score"] < relevance_min:
            continue
        
        if item["recency_score"] < recency_min:
            continue
        
        # Vérifier compatibilité pédagogique
        user_level = user_profile.get("pedagogical_level", "intermediate")
        item_level = item.get("pedagogical_level", "intermediate")
        
        level_map = {"beginner": 0, "intermediate": 1, "advanced": 2}
        level_diff = abs(level_map.get(item_level, 1) - level_map.get(user_level, 1))
        
        if level_diff > 1:  # Écart maximal de 1 niveau
            continue
        
        filtered.append(item)
    
    # Éliminer les doublons
    filtered = remove_duplicates(filtered, similarity_threshold=0.95)
    
    return filtered

def remove_duplicates(
    items: List[Dict],
    similarity_threshold: float = 0.95
) -> List[Dict]:
    """Élimine les éléments trop similaires"""
    unique = []
    
    for i, item1 in enumerate(items):
        is_duplicate = False
        
        for item2 in unique:
            similarity = calculate_cosine_similarity(
                item1["content"],
                item2["content"]
            )
            
            if similarity > similarity_threshold:
                is_duplicate = True
                # Conserver celui avec meilleur score composite
                score1 = compute_composite_score(item1)
                score2 = compute_composite_score(item2)
                
                if score1 > score2:
                    unique.remove(item2)
                    unique.append(item1)
                
                break
        
        if not is_duplicate:
            unique.append(item1)
    
    return unique

def compute_composite_score(item: Dict) -> float:
    """Calcule un score composite pour le classement"""
    return (
        0.4 * item.get("relevance_score", 0) +
        0.3 * item.get("engagement_score", 0) +
        0.2 * item.get("recency_score", 0) +
        0.1 * item.get("user_preference_alignment", 0)
    )
```

---

## Étape 5 : Classement et Ranking

**Objectif** : Classer le contexte selon un score composite optimisé pour la pertinence pédagogique.

**Pseudo-code** :
```
FONCTION ClasserContext(contexte_filtre):
    1. Calculer score composite pour chaque item :
       score = (0.4 × relevance) + (0.3 × engagement) + 
               (0.2 × recency) + (0.1 × user_alignment)
    2. Trier par score composite DESC
    3. Appliquer stratégie de diversité (optionnel) :
       - SI trop d'items du même type : limiter à 30%
       - SI même sujet dominé : répartir
    4. Limiter à top-N résultats (N dépend du contexte)
    5. Ajouter ranking position et score normalisé [0,1]
    6. RETOURNER : Contexte classé avec metadata de ranking
FIN FONCTION
```

**Implémentation** :
```python
# Dans backend/open_tutorai/routers/context_retrieval.py

def rank_context(
    filtered_items: List[Dict],
    weights: Dict[str, float] = None,
    diversity_strategy: bool = True,
    max_results: int = 20
) -> List[Dict]:
    """Classe le contexte selon un score composite"""
    
    # Poids par défaut
    if weights is None:
        weights = {
            "relevance": 0.4,
            "engagement": 0.3,
            "recency": 0.2,
            "user_alignment": 0.1
        }
    
    # Calculer scores composites
    for item in filtered_items:
        composite_score = (
            weights["relevance"] * item.get("relevance_score", 0) +
            weights["engagement"] * item.get("engagement_score", 0) +
            weights["recency"] * item.get("recency_score", 0) +
            weights["user_alignment"] * item.get("user_preference_alignment", 0)
        )
        item["composite_score"] = composite_score
    
    # Trier par score décroissant
    ranked = sorted(filtered_items, key=lambda x: x["composite_score"], reverse=True)
    
    # Appliquer diversité si demandé
    if diversity_strategy:
        ranked = apply_diversity_strategy(ranked)
    
    # Limiter et ajouter metadata de ranking
    ranked = ranked[:max_results]
    
    # Normaliser les scores et ajouter le ranking
    max_score = max([item["composite_score"] for item in ranked]) if ranked else 1.0
    
    for rank, item in enumerate(ranked, 1):
        item["ranking_position"] = rank
        item["normalized_score"] = item["composite_score"] / max_score if max_score > 0 else 0
    
    return ranked

def apply_diversity_strategy(items: List[Dict]) -> List[Dict]:
    """Applique une stratégie de diversité pour éviter la concentration"""
    
    # Compter les types de sources
    source_counts = {}
    for item in items:
        source_type = item.get("source_type", "unknown")
        source_counts[source_type] = source_counts.get(source_type, 0) + 1
    
    total = len(items)
    max_per_type = max(3, total // len(source_counts)) if source_counts else total
    
    # Rééquilibrer
    diversified = []
    type_counts = {}
    
    for item in items:
        source_type = item.get("source_type", "unknown")
        type_counts[source_type] = type_counts.get(source_type, 0) + 1
        
        if type_counts[source_type] <= max_per_type:
            diversified.append(item)
    
    return diversified

def format_ranked_output(ranked_items: List[Dict]) -> List[Dict]:
    """Formate le résultat final pour le retour API"""
    output = []
    
    for item in ranked_items:
        output.append({
            "rank": item.get("ranking_position"),
            "source": item.get("source_type"),
            "source_id": item.get("id"),
            "content_preview": item.get("content")[:300] + "..." if len(item.get("content", "")) > 300 else item.get("content"),
            "full_content": item.get("content"),
            "metadata": item.get("metadata", {}),
            "scores": {
                "relevance": round(item.get("relevance_score", 0), 3),
                "engagement": round(item.get("engagement_score", 0), 3),
                "recency": round(item.get("recency_score", 0), 3),
                "user_alignment": round(item.get("user_preference_alignment", 0), 3),
                "composite": round(item.get("composite_score", 0), 3),
                "normalized": round(item.get("normalized_score", 0), 3)
            }
        })
    
    return output
```

---

## Pipeline Complet

**Pseudo-code du pipeline principal** :
```
FONCTION RetrieveContext(user_id, query, user_profile):
    1. PARALLÉLISER (si possible) :
       - documents = RecupererDocumentsPedagogiques(query, user_id)
       - memories = RecupererMemoireInterne(query, user_id)
       - summaries = RecupererResumesGeneres(query, user_id)
    
    2. contexte_normalise = NormaliserContext(documents, memories, summaries)
    
    3. contexte_enrichi = EnrichirContext(contexte_normalise, user_id, query)
    
    4. contexte_filtre = FiltrerContext(contexte_enrichi, user_profile)
    
    5. contexte_classe = ClasserContext(contexte_filtre)
    
    6. resultat_final = FormatOutput(contexte_classe)
    
    7. RETOURNER resultat_final
FIN FONCTION
```

**Implémentation du routeur** :
```python
# Dans backend/open_tutorai/routers/context_retrieval.py (fichier à créer)

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from open_webui.utils.auth import get_verified_user

router = APIRouter(tags=["context"])

class ContextRetrievalRequest(BaseModel):
    query: str
    max_results: int = 20
    include_source_types: Optional[List[str]] = None

class ContextRetrievalResponse(BaseModel):
    rank: int
    source: str
    source_id: str
    content_preview: str
    full_content: str
    metadata: Dict[str, Any]
    scores: Dict[str, float]

@router.post("/context/retrieve", response_model=List[ContextRetrievalResponse])
async def retrieve_context(
    request: ContextRetrievalRequest,
    user=Depends(get_verified_user),
    db=Depends(get_db),
):
    """
    Récupère le contexte pertinent en combinant:
    - Documents pédagogiques (RAG)
    - Mémoire interne (episodic, semantic, procedural, behavioral)
    - Résumés générés
    """
    try:
        # Récupérer le profil utilisateur
        user_profile = get_user_profile(user.id, db)
        
        # Étape 1: Récupération multi-sources
        documents = await retrieve_pedagogical_documents(
            user.id, request.query, top_k=5
        )
        memories = await retrieve_internal_memory(
            user.id, request.query, limit=10
        )
        summaries = await retrieve_generated_summaries(
            user.id, request.query, limit=5
        )
        
        # Étape 2: Normalisation
        normalized = normalize_context(documents, memories, summaries)
        
        # Étape 3: Enrichissement
        enriched = await enrich_context(
            normalized, user.id, request.query, user_profile
        )
        
        # Étape 4: Filtrage pédagogique
        filtered = filter_context_pedagogical(
            enriched, user_profile, config={}
        )
        
        # Étape 5: Classement et ranking
        ranked = rank_context(
            filtered,
            max_results=request.max_results
        )
        
        # Formatage du résultat
        result = format_ranked_output(ranked)
        
        return result
        
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
```

---

## Fichiers à Créer/Modifier

### Fichiers à Créer :

1. **`backend/open_tutorai/routers/context_retrieval.py`**
   - Routeur principal implémentant l'algorithme
   - Endpoints : `POST /context/retrieve`

2. **`backend/open_tutorai/models/context_schema.py`**
   - Classes Pydantic pour validation
   - Dataclasses pour structure interne

3. **`src/lib/apis/context/index.ts`**
   - Client TypeScript pour appeler l'API contexte
   - Fonction : `retrieveContext(query: string)`

### Fichiers à Modifier :

1. **`backend/open_tutorai/main.py`**
   - Ajouter import et inclusion du routeur context_retrieval

2. **`backend/open_tutorai/models/database.py`**
   - Ajouter table `opentutorai_summary` (optionnel selon implémentation)

3. **`backend/open_tutorai/config.py`**
   - Ajouter configuration RAG et LLM summarization
   - Définir poids des scores, seuils, etc.

---

## Flux de Données Visuel

```
┌─────────────────────────────────────────────────────────┐
│          REQUÊTE UTILISATEUR (Query + User ID)          │
└───────────────┬─────────────────────────────────────────┘
                │
                ▼
    ┌─────────────────────────────────────────┐
    │   ÉTAPE 1: RÉCUPÉRATION MULTI-SOURCES   │
    ├─────────────────────────────────────────┤
    │ ┌──────────────────────────────────────┐│
    │ │ Source A: Documents Pédagogiques     ││
    │ │ (RAG - base vectorielle)             ││
    │ │ Fichier: backend/data/uploads/       ││
    │ └──────────────────────────────────────┘│
    │ ┌──────────────────────────────────────┐│
    │ │ Source B: Mémoire Interne            ││
    │ │ (opentutorai_memory table)           ││
    │ │ Fichier: models/database.py          ││
    │ └──────────────────────────────────────┘│
    │ ┌──────────────────────────────────────┐│
    │ │ Source C: Résumés Générés            ││
    │ │ (Cache + LLM generation)             ││
    │ │ Fichier: backend/data/cache/         ││
    │ └──────────────────────────────────────┘│
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │   ÉTAPE 2: NORMALISATION                │
    │   (Format unifié pour toutes sources)   │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │   ÉTAPE 3: ENRICHISSEMENT               │
    │   (Ajout scores pédagogiques)           │
    │ - relevance_score                       │
    │ - recency_score                         │
    │ - engagement_score                      │
    │ - pedagogical_level                     │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │   ÉTAPE 4: FILTRAGE PÉDAGOGIQUE        │
    │   (Élimination contexte non pertinent)  │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │   ÉTAPE 5: CLASSEMENT & RANKING         │
    │   Score composite + Tri décroissant     │
    │   Diversité si nécessaire               │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────────────┐
        │   RÉSULTAT FINAL (Top-N items)      │
        │   Avec scores et métadonnées        │
        │   JSON formaté pour client          │
        └─────────────────────────────────────┘
```

---

## Configurations Recommandées

À ajouter dans `backend/open_tutorai/config.py` :

```python
# Context Retrieval Engine Configuration
CONTEXT_RETRIEVAL_CONFIG = {
    # RAG Configuration
    "rag": {
        "enabled": True,
        "top_k_documents": 5,
        "min_vector_similarity": 0.3
    },
    
    # Mémoire Configuration
    "memory": {
        "enabled": True,
        "top_k_memories": 10,
        "min_textual_relevance": 0.3,
        "memory_types": ["episodic", "semantic", "procedural", "behavioral"]
    },
    
    # Résumés Configuration
    "summaries": {
        "enabled": True,
        "top_k_summaries": 5,
        "cache_ttl_hours": 24,
        "summarization_model": "gpt-3.5-turbo"
    },
    
    # Filtrage Pédagogique
    "filtering": {
        "relevance_threshold": 0.3,
        "recency_threshold": 0.1,
        "max_age_days": 365,
        "allow_level_gap": 1  # Niveaux
    },
    
    # Scoring Pédagogique
    "scoring": {
        "relevance_weight": 0.4,
        "engagement_weight": 0.3,
        "recency_weight": 0.2,
        "user_alignment_weight": 0.1
    },
    
    # Output Configuration
    "output": {
        "max_results": 20,
        "diversity_strategy": True,
        "include_source_preview": True,
        "preview_length": 300
    }
}
```

---

## Avantages de cette Architecture

✅ **Multi-source** : Combine 3 sources d'information complémentaires  
✅ **Pertinence pédagogique** : Scoring spécifiquement conçu pour l'éducation  
✅ **Scalabilité** : Peut être parallélisé pour les grandes requêtes  
✅ **Transparence** : Chaque score est tracé et expliquable  
✅ **Flexibilité** : Poids configurables, filtres ajustables  
✅ **Performance** : Utilise cache et normalisation pour vitesse  
✅ **Traçabilité** : Chaque résultat indique source et score  

---

## Optimisations Futures

- Implémentation du parallélisme async pour les 3 sources
- Caching au niveau des requêtes fréquentes
- Feedback utilisateur pour affiner les poids
- Machine Learning pour apprentissage des poids optimaux
- Support du multi-langue avec détection automatique
- Integration avec analytics pour tracking usage patterns

