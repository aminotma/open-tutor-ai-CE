from open_tutorai.env import (
    ENABLE_SIGNUP,
    ENABLE_LOGIN_FORM,
    JWT_EXPIRES_IN,
    WEBHOOK_URL,
)
from pydantic import BaseModel
from typing import Optional


class AppConfig(BaseModel):
    ENABLE_SIGNUP: bool = ENABLE_SIGNUP
    ENABLE_LOGIN_FORM: bool = ENABLE_LOGIN_FORM
    JWT_EXPIRES_IN: str = JWT_EXPIRES_IN
    WEBHOOK_URL: Optional[str] = WEBHOOK_URL
    USER_PERMISSIONS: dict = {}


# Context Retrieval Engine Configuration
CONTEXT_RETRIEVAL_CONFIG = {
    # RAG Configuration
    "rag": {
        "enabled": True,
        "top_k_documents": 5,
        "min_vector_similarity": 0.3
    },
    
    # Memory Configuration
    "memory": {
        "enabled": True,
        "top_k_memories": 10,
        "min_textual_relevance": 0.3,
        "memory_types": ["episodic", "semantic", "procedural", "behavioral"]
    },
    
    # Summaries Configuration
    "summaries": {
        "enabled": True,
        "top_k_summaries": 5,
        "cache_ttl_hours": 24,
        "summarization_model": "gpt-3.5-turbo"
    },
    
    # Pedagogical Filtering
    "filtering": {
        "relevance_threshold": 0.3,
        "recency_threshold": 0.1,
        "max_age_days": 365,
        "allow_level_gap": 1  # Maximum level gap (beginner, intermediate, advanced)
    },
    
    # Pedagogical Scoring (weights)
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
