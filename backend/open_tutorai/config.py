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
        "min_vector_similarity": 0.3,
        "verification_enabled": True,
        "verification_threshold": 0.65,
        "verification_min_support": 0.5,
        "local_document_paths": ["docs", "backend"]
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
    
    # Summarization Layer Configuration
    "summarization": {
        "enabled": True,
        "max_content_length": 1000,
        "sliding_window_size": 10,
        "score_threshold": 0.3,
        "summarize_interactions": True,
        "extract_key_elements": True,
        "forget_irrelevant": {
            "enabled": True,
            "context_threshold": 0.15,
            "min_relevance": 0.1,
            "sentence_match_ratio": 0.15
        }
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
    },
    
    # LangChain Configuration (pour la partie LLM et embeddings)
    "langchain": {
        "enabled": True,
        "llm_model": "gpt-4o-mini",          # Modèle OpenAI utilisé
        "llm_temperature": 0.2,               # Faible pour des réponses stables
        "embedding_model": "all-MiniLM-L6-v2",# Même qu'avant, géré par LangChain
        "retriever_search_type": "similarity", # Type de recherche ChromaDB
        "fallback_to_web_search": True,        # DuckDuckGo si RAG vide
        "max_rag_chars_in_prompt": 1000,       # Limite contexte RAG dans le prompt
        "max_memory_items_in_prompt": 5,       # Limite mémoires dans le prompt
    },
    "react": {
        "max_iterations": 10,           # Nombre max d'itérations de la boucle
        "stop_on_final_answer": True,   # Arrêter dès tool_final_answer
        "max_corrective_cycles": 2,     # Cycles correctifs max si vérification échoue
        "verbose": True,                # Afficher le raisonnement dans les logs
        "handle_parsing_errors": True,  # Gérer les erreurs de parsing LLM
        "early_stopping": "generate",   # Comportement si max_iterations atteint
        "mandatory_tools": [            # Outils obligatoires (vérifiés à la fin)
            "tool_diagnose",
            "tool_generate_exercises",
            "tool_final_answer",
        ],
    },
}
