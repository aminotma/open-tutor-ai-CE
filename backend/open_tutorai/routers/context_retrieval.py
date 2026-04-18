"""
Context Retrieval Engine Router

This module implements the Context Retrieval Engine that combines:
- Pedagogical documents (RAG)
- Internal memory (episodic, semantic, procedural, behavioral)
- Generated summaries

Results are filtered and ranked according to pedagogical relevance.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import uuid4
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from math import exp
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from open_webui.internal.db import get_db
from open_webui.utils.auth import get_verified_user
from open_tutorai.models.database import Memory

router = APIRouter(tags=["context"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ContextRetrievalRequest(BaseModel):
    """Request model for context retrieval"""
    query: str = Field(..., min_length=1, description="Search query")
    max_results: int = Field(20, ge=1, le=50, description="Maximum results to return")
    include_source_types: Optional[List[str]] = Field(
        None, 
        description="Filter by source types: 'pedagogical', 'memory', 'summary'"
    )
    memory_types: Optional[List[str]] = Field(
        None,
        description="Filter memories by types: 'episodic', 'semantic', 'procedural', 'behavioral'"
    )
    pedagogical_level: Optional[str] = Field(
        "intermediate",
        description="User pedagogical level: 'beginner', 'intermediate', 'advanced'"
    )


class ScoresSchema(BaseModel):
    """Score breakdown for context item"""
    relevance: float = Field(..., description="Relevance score (0-1)")
    engagement: float = Field(..., description="Engagement score (0-1)")
    recency: float = Field(..., description="Recency score (0-1)")
    user_alignment: float = Field(..., description="User preference alignment (0-1)")
    composite: float = Field(..., description="Composite score (0-1)")
    normalized: float = Field(..., description="Normalized score within result set (0-1)")


class MetadataSchema(BaseModel):
    """Metadata for context item"""
    type: str = Field(..., description="Content type")
    created_at: Optional[float] = Field(None, description="Creation timestamp")
    last_updated: Optional[float] = Field(None, description="Last update timestamp")
    source_id: str = Field(..., description="Source identifier")
    title: Optional[str] = Field(None, description="Title if applicable")
    subject_domain: Optional[str] = Field(None, description="Subject domain")


class ContextRetrievalResponse(BaseModel):
    """Response model for a single context item"""
    rank: int = Field(..., description="Ranking position")
    source: str = Field(..., description="Source type: pedagogical, memory, summary")
    source_id: str = Field(..., description="Source identifier")
    content_preview: str = Field(..., description="Preview of content (first 300 chars)")
    full_content: str = Field(..., description="Full content")
    metadata: MetadataSchema = Field(..., description="Content metadata")
    scores: ScoresSchema = Field(..., description="Score breakdown")


# ============================================================================
# DATACLASSES FOR INTERNAL PROCESSING
# ============================================================================

@dataclass
class NormalizedContextItem:
    """Normalized context item from any source"""
    source_type: str  # 'pedagogical', 'memory', 'summary'
    id: str
    content: str
    metadata: Dict[str, Any]
    raw_score: float


# ============================================================================
# STEP 1: RETRIEVE FROM MULTIPLE SOURCES
# ============================================================================

async def retrieve_pedagogical_documents(
    user_id: str,
    query: str,
    top_k: int = 5
) -> List[Dict]:
    """
    Retrieve pedagogical documents using RAG (Retrieval-Augmented Generation)
    
    Sources: backend/data/uploads/, vectorial search
    """
    try:
        # This would typically use a vector database (e.g., Weaviate, Pinecone, etc.)
        # For now, returning placeholder structure
        # TODO: Integrate with actual RAG system when available
        
        # Placeholder: Return empty list for now (integration needed)
        return []
        
    except Exception as e:
        print(f"Error retrieving pedagogical documents: {str(e)}")
        return []


async def retrieve_internal_memory(
    user_id: str,
    query: str,
    memory_types: Optional[List[str]] = None,
    limit: int = 10,
    db = None
) -> List[Dict]:
    """
    Retrieve internal memories matching the query
    
    Source: opentutorai_memory table
    Uses: ILIKE for text search
    """
    if db is None:
        return []
    
    try:
        # Build the base query
        db_query = db.query(Memory).filter(Memory.user_id == user_id)
        
        # Filter by memory types if provided
        if memory_types and len(memory_types) > 0:
            db_query = db_query.filter(Memory.memory_type.in_(memory_types))
        
        # Search in content using ILIKE
        search_pattern = f"%{query}%"
        db_query = db_query.filter(Memory.content.ilike(search_pattern))
        
        # Order by recency
        memories = db_query.order_by(
            Memory.updated_at.desc().nullslast(),
            Memory.created_at.desc()
        ).limit(limit).all()
        
        # Convert to dict format
        results = []
        for memory in memories:
            # Calculate textual relevance score
            textual_score = calculate_relevance(memory.content, query)
            
            results.append({
                "id": memory.id,
                "type": memory.memory_type,
                "content": memory.content,
                "metadata": memory.memory_metadata or {},
                "created_at": memory.created_at.timestamp() if memory.created_at else None,
                "updated_at": memory.updated_at.timestamp() if memory.updated_at else None,
                "textual_score": textual_score
            })
        
        return results
        
    except Exception as e:
        print(f"Error retrieving internal memory: {str(e)}")
        return []


async def retrieve_generated_summaries(
    user_id: str,
    query: str,
    cache_ttl_hours: int = 24,
    limit: int = 5
) -> List[Dict]:
    """
    Retrieve generated summaries from cache
    
    Source: backend/data/cache/summaries/
    Uses cache with TTL
    """
    try:
        cache_dir = Path("backend/data/cache/summaries")
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        summaries = []
        current_time = datetime.now(timezone.utc)
        
        # Scan cache directory
        if cache_dir.exists():
            for cache_file in sorted(cache_dir.glob("*.json"))[:limit]:
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_summary = json.load(f)
                    
                    # Check TTL
                    created_timestamp = cached_summary.get("created_at", 0)
                    created_date = datetime.fromtimestamp(created_timestamp, tz=timezone.utc)
                    age = (current_time - created_date).total_seconds() / 3600  # hours
                    
                    if age <= cache_ttl_hours:
                        # Calculate relevance to query
                        relevance = calculate_relevance(cached_summary.get("text", ""), query)
                        
                        if relevance > 0.1:  # Only include if somewhat relevant
                            summaries.append({
                                "id": cached_summary.get("id", cache_file.stem),
                                "text": cached_summary.get("text", ""),
                                "source_conversation": cached_summary.get("source_conversation"),
                                "created_at": created_timestamp,
                                "summary_score": relevance
                            })
                
                except (json.JSONDecodeError, IOError):
                    continue
        
        return summaries
        
    except Exception as e:
        print(f"Error retrieving generated summaries: {str(e)}")
        return []


# ============================================================================
# STEP 2: NORMALIZE AND STANDARDIZE
# ============================================================================

def normalize_context(
    documents: List[Dict],
    memories: List[Dict],
    summaries: List[Dict]
) -> List[NormalizedContextItem]:
    """
    Normalize results from all sources to unified format
    """
    normalized = []
    
    # Normalize pedagogical documents
    for doc in documents:
        content = doc.get("content", "")
        if len(content) > 5000:
            content = content[:5000] + "..."
        
        normalized.append(NormalizedContextItem(
            source_type="pedagogical",
            id=doc.get("id", ""),
            content=content,
            metadata={
                "type": "document",
                "title": doc.get("title", ""),
                "created_at": doc.get("created_at"),
                "source_id": doc.get("id", "")
            },
            raw_score=doc.get("vector_score", 0.0)
        ))
    
    # Normalize memories
    for memory in memories:
        content = memory.get("content", "")
        if len(content) > 5000:
            content = content[:5000] + "..."
        
        normalized.append(NormalizedContextItem(
            source_type="memory",
            id=memory.get("id", ""),
            content=content,
            metadata={
                "type": memory.get("type", "semantic"),
                "created_at": memory.get("created_at"),
                "last_updated": memory.get("updated_at"),
                "source_id": memory.get("id", "")
            },
            raw_score=memory.get("textual_score", 0.0)
        ))
    
    # Normalize summaries
    for summary in summaries:
        content = summary.get("text", "")
        if len(content) > 5000:
            content = content[:5000] + "..."
        
        normalized.append(NormalizedContextItem(
            source_type="summary",
            id=summary.get("id", ""),
            content=content,
            metadata={
                "type": "summary",
                "source_conversation": summary.get("source_conversation"),
                "created_at": summary.get("created_at"),
                "source_id": summary.get("id", "")
            },
            raw_score=summary.get("summary_score", 0.0)
        ))
    
    return normalized


# ============================================================================
# STEP 3: ENRICH WITH PEDAGOGICAL METADATA
# ============================================================================

def calculate_relevance(content: str, query: str) -> float:
    """
    Calculate textual relevance score
    
    Returns: score between 0 and 1
    """
    if not query or not content:
        return 0.0
    
    query_lower = query.lower()
    content_lower = content.lower()
    
    # Count query terms found
    terms = [t.strip() for t in query_lower.split() if t.strip()]
    if not terms:
        return 0.0
    
    matches = sum(1 for term in terms if term in content_lower)
    score = min(matches / len(terms), 1.0)
    
    return score


def deduce_pedagogical_level(content: str) -> str:
    """
    Deduce pedagogical level from content characteristics
    
    Returns: 'beginner', 'intermediate', or 'advanced'
    """
    if not content:
        return "intermediate"
    
    content_length = len(content)
    
    # Heuristic based on content length and complexity
    if content_length < 100:
        return "beginner"
    elif content_length < 500:
        return "intermediate"
    else:
        return "advanced"


def calculate_recency_score(created_at: Optional[float]) -> float:
    """
    Calculate recency score using exponential decay
    
    Returns: score between 0 and 1, 1 = very recent, 0 = very old
    """
    if created_at is None:
        return 0.5
    
    current_time = datetime.now(timezone.utc).timestamp()
    age_seconds = current_time - created_at
    age_days = age_seconds / (24 * 3600)
    
    # Exponential decay with 30-day half-life
    recency = exp(-age_days / 30)
    
    return min(max(recency, 0.0), 1.0)


def calculate_engagement_score(item_type: str, metadata: Dict) -> float:
    """
    Calculate engagement score based on item type and metadata
    
    Returns: score between 0 and 1
    """
    score = 0.0
    
    # Episodic memories get higher engagement
    if item_type == "memory" and metadata.get("type") == "episodic":
        score += 0.3
    
    # Recently updated items get bonus
    if metadata.get("last_updated"):
        score += 0.2
    
    # Frequently accessed items (would need tracking)
    # score += 0.15 if accessed_recently else 0
    
    return min(score, 1.0)


async def enrich_context(
    context_items: List[NormalizedContextItem],
    user_id: str,
    query: str,
    user_profile: Dict
) -> List[Dict]:
    """
    Enrich context with pedagogical scores and metadata
    """
    enriched = []
    current_time = datetime.now(timezone.utc)
    
    for item in context_items:
        # Calculate relevance score
        relevance_score = calculate_relevance(item.content, query)
        
        # Calculate recency score
        created_at_timestamp = item.metadata.get("created_at")
        recency_score = calculate_recency_score(created_at_timestamp)
        
        # Calculate engagement score
        engagement_score = calculate_engagement_score(item.source_type, item.metadata)
        
        # Calculate user alignment score
        user_interests = user_profile.get("interests", [])
        subject_domain = item.metadata.get("subject_domain", "general")
        user_alignment = 1.0 if subject_domain in user_interests else 0.5
        
        enriched.append({
            **item.__dict__,
            "relevance_score": relevance_score,
            "recency_score": recency_score,
            "engagement_score": engagement_score,
            "pedagogical_level": deduce_pedagogical_level(item.content),
            "subject_domain": item.metadata.get("subject_domain", "general"),
            "user_preference_alignment": user_alignment
        })
    
    return enriched


# ============================================================================
# STEP 4: PEDAGOGICAL FILTERING
# ============================================================================

def filter_context_pedagogical(
    enriched_items: List[Dict],
    user_profile: Dict,
    config: Dict
) -> List[Dict]:
    """
    Filter context according to pedagogical criteria
    """
    relevance_min = config.get("relevance_threshold", 0.3)
    recency_min = config.get("recency_threshold", 0.1)
    
    filtered = []
    level_map = {"beginner": 0, "intermediate": 1, "advanced": 2}
    
    user_level = level_map.get(user_profile.get("pedagogical_level", "intermediate"), 1)
    
    for item in enriched_items:
        # Filter by relevance
        if item.get("relevance_score", 0) < relevance_min:
            continue
        
        # Filter by recency
        if item.get("recency_score", 0) < recency_min:
            continue
        
        # Filter by pedagogical level compatibility
        item_level = level_map.get(item.get("pedagogical_level", "intermediate"), 1)
        level_diff = abs(item_level - user_level)
        
        if level_diff > 1:  # Maximum gap of 1 level
            continue
        
        filtered.append(item)
    
    # Remove duplicates
    filtered = remove_duplicates(filtered)
    
    return filtered


def calculate_cosine_similarity(text1: str, text2: str) -> float:
    """
    Simple cosine similarity based on word overlap
    
    Returns: score between 0 and 1
    """
    if not text1 or not text2:
        return 0.0
    
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    similarity = intersection / union if union > 0 else 0.0
    
    return similarity


def compute_composite_score(item: Dict) -> float:
    """
    Compute composite score for ranking
    
    Weights: relevance 40%, engagement 30%, recency 20%, alignment 10%
    """
    return (
        0.4 * item.get("relevance_score", 0) +
        0.3 * item.get("engagement_score", 0) +
        0.2 * item.get("recency_score", 0) +
        0.1 * item.get("user_preference_alignment", 0)
    )


def remove_duplicates(items: List[Dict], similarity_threshold: float = 0.95) -> List[Dict]:
    """
    Remove duplicate or very similar items
    
    Keeps the item with highest composite score
    """
    unique = []
    
    for item1 in items:
        is_duplicate = False
        
        for i, item2 in enumerate(unique):
            similarity = calculate_cosine_similarity(
                item1.get("content", ""),
                item2.get("content", "")
            )
            
            if similarity > similarity_threshold:
                is_duplicate = True
                
                # Compare composite scores
                score1 = compute_composite_score(item1)
                score2 = compute_composite_score(item2)
                
                if score1 > score2:
                    unique[i] = item1
                
                break
        
        if not is_duplicate:
            unique.append(item1)
    
    return unique


# ============================================================================
# STEP 5: RANKING AND SORTING
# ============================================================================

def rank_context(
    filtered_items: List[Dict],
    weights: Dict[str, float] = None,
    diversity_strategy: bool = True,
    max_results: int = 20
) -> List[Dict]:
    """
    Rank context items by composite score
    """
    if weights is None:
        weights = {
            "relevance": 0.4,
            "engagement": 0.3,
            "recency": 0.2,
            "user_alignment": 0.1
        }
    
    # Calculate composite scores
    for item in filtered_items:
        composite_score = (
            weights.get("relevance", 0.4) * item.get("relevance_score", 0) +
            weights.get("engagement", 0.3) * item.get("engagement_score", 0) +
            weights.get("recency", 0.2) * item.get("recency_score", 0) +
            weights.get("user_alignment", 0.1) * item.get("user_preference_alignment", 0)
        )
        item["composite_score"] = composite_score
    
    # Sort by composite score
    ranked = sorted(filtered_items, key=lambda x: x.get("composite_score", 0), reverse=True)
    
    # Apply diversity if requested
    if diversity_strategy:
        ranked = apply_diversity_strategy(ranked)
    
    # Limit results
    ranked = ranked[:max_results]
    
    # Normalize scores and add ranking
    max_score = max([item.get("composite_score", 0) for item in ranked]) if ranked else 1.0
    
    for rank, item in enumerate(ranked, 1):
        item["ranking_position"] = rank
        item["normalized_score"] = (
            item.get("composite_score", 0) / max_score if max_score > 0 else 0
        )
    
    return ranked


def apply_diversity_strategy(items: List[Dict]) -> List[Dict]:
    """
    Apply diversity strategy to avoid source concentration
    """
    # Count source types
    source_counts = {}
    for item in items:
        source_type = item.get("source_type", "unknown")
        source_counts[source_type] = source_counts.get(source_type, 0) + 1
    
    if not source_counts:
        return items
    
    total = len(items)
    max_per_type = max(3, total // len(source_counts))
    
    # Rebalance
    diversified = []
    type_counts = {}
    
    for item in items:
        source_type = item.get("source_type", "unknown")
        type_counts[source_type] = type_counts.get(source_type, 0) + 1
        
        if type_counts[source_type] <= max_per_type:
            diversified.append(item)
    
    return diversified


def format_ranked_output(ranked_items: List[Dict]) -> List[Dict]:
    """
    Format final output for API response
    """
    output = []
    
    for item in ranked_items:
        content = item.get("content", "")
        preview = (content[:300] + "...") if len(content) > 300 else content
        
        output.append({
            "rank": item.get("ranking_position"),
            "source": item.get("source_type"),
            "source_id": item.get("id"),
            "content_preview": preview,
            "full_content": content,
            "metadata": {
                "type": item.get("metadata", {}).get("type", ""),
                "created_at": item.get("metadata", {}).get("created_at"),
                "last_updated": item.get("metadata", {}).get("last_updated"),
                "source_id": item.get("id"),
                "title": item.get("metadata", {}).get("title"),
                "subject_domain": item.get("subject_domain", "general")
            },
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


# ============================================================================
# API ROUTES
# ============================================================================

@router.post("/context/retrieve", response_model=List[ContextRetrievalResponse])
async def retrieve_context(
    request: ContextRetrievalRequest,
    user=Depends(get_verified_user),
    db=Depends(get_db),
):
    """
    Retrieve relevant context from multiple sources:
    - Pedagogical documents (RAG)
    - Internal memory (episodic, semantic, procedural, behavioral)
    - Generated summaries
    
    Results are filtered and ranked by pedagogical relevance.
    
    Query Parameters:
    - query: The search query
    - max_results: Maximum number of results (default: 20)
    - memory_types: Filter by memory types (optional)
    - pedagogical_level: User pedagogical level (default: intermediate)
    """
    try:
        # Build user profile
        user_profile = {
            "pedagogical_level": request.pedagogical_level or "intermediate",
            "interests": []
        }
        
        # STEP 1: Retrieve from multiple sources
        documents = await retrieve_pedagogical_documents(
            user.id, request.query, top_k=5
        )
        
        memories = await retrieve_internal_memory(
            user.id,
            request.query,
            memory_types=request.memory_types,
            limit=10,
            db=db
        )
        
        summaries = await retrieve_generated_summaries(
            user.id, request.query, limit=5
        )
        
        # Filter by source types if specified
        if request.include_source_types:
            source_types = request.include_source_types
            if "pedagogical" not in source_types:
                documents = []
            if "memory" not in source_types:
                memories = []
            if "summary" not in source_types:
                summaries = []
        
        # STEP 2: Normalize
        normalized = normalize_context(documents, memories, summaries)
        
        if not normalized:
            return []
        
        # STEP 3: Enrich with pedagogical metadata
        enriched = await enrich_context(
            normalized, user.id, request.query, user_profile
        )
        
        # STEP 4: Filter pedagogically
        filtered_config = {
            "relevance_threshold": 0.3,
            "recency_threshold": 0.1
        }
        filtered = filter_context_pedagogical(enriched, user_profile, filtered_config)
        
        if not filtered:
            return []
        
        # STEP 5: Rank and sort
        ranked = rank_context(
            filtered,
            weights={
                "relevance": 0.4,
                "engagement": 0.3,
                "recency": 0.2,
                "user_alignment": 0.1
            },
            diversity_strategy=True,
            max_results=request.max_results
        )
        
        # Format output
        result = format_ranked_output(ranked)
        
        return result
        
    except Exception as exc:
        print(f"Error in context retrieval: {str(exc)}")
        raise HTTPException(status_code=500, detail=f"Context retrieval failed: {str(exc)}")


@router.get("/context/stats")
async def get_context_stats(
    user=Depends(get_verified_user),
    db=Depends(get_db),
):
    """
    Get statistics about available context sources for the user
    """
    try:
        # Count memories by type
        memory_query = db.query(Memory).filter(Memory.user_id == user.id)
        total_memories = memory_query.count()
        
        memory_types_count = {}
        for memory_type in ["episodic", "semantic", "procedural", "behavioral"]:
            count = memory_query.filter(Memory.memory_type == memory_type).count()
            memory_types_count[memory_type] = count
        
        return {
            "user_id": user.id,
            "total_memories": total_memories,
            "memory_types": memory_types_count,
            "available_sources": ["memory"],
            "note": "Pedagogical documents and summaries support coming soon"
        }
        
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
