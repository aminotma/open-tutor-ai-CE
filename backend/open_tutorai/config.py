import os

from open_tutorai.env import (
    ENABLE_SIGNUP,
    ENABLE_LOGIN_FORM,
    JWT_EXPIRES_IN,
    WEBHOOK_URL,
)
from pydantic import BaseModel
from typing import Optional


# ── Étape 1 — fonctions d'accès aux variables d'environnement OpenAI ─────────

def get_openai_api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "")


def get_openai_base_url() -> str:
    return os.environ.get("OPENAI_BASE_URL", "")


class AppConfig(BaseModel):
    ENABLE_SIGNUP: bool = ENABLE_SIGNUP
    ENABLE_LOGIN_FORM: bool = ENABLE_LOGIN_FORM
    JWT_EXPIRES_IN: str = JWT_EXPIRES_IN
    WEBHOOK_URL: Optional[str] = WEBHOOK_URL
    USER_PERMISSIONS: dict = {}


CONTEXT_RETRIEVAL_CONFIG: dict = {
    "filtering": {
        "relevance_threshold": 0.4,   # min vector score to keep a RAG doc
        "recency_threshold":   0.3,   # recency weight in combined score
        "max_age_days":        14,    # ignore memories older than 14 days
        "max_context_tokens":  3000,  # hard cap on total injected tokens
    },
    "memory": {
        "enabled":      True,
        "top_k":        10,
        "memory_types": ["episodic", "behavioral", "procedural", "session_summary"],
    },
    "rag": {
        "enabled":                True,
        "top_k_documents":        5,
        "min_vector_similarity":  0.5,
        "verification_enabled":   True,
        "verification_threshold": 0.65,
    },
    "summaries": {
        "enabled":                    True,
        "cache_ttl_hours":            24,
        "exchanges_per_summary":      5,
        "auto_summarize_token_limit": 1200,  # trigger if raw exchanges exceed this token count
    },
    "summarization": {
        "enabled":             True,
        "sliding_window_size": 10,
        "forget_irrelevant":   True,
    },
    "langchain": {
        "llm_model":            "gpt-4o-mini",
        "llm_temperature":      0.2,
        "orchestrator_use_llm": True,
    },
    "react": {
        "max_iterations": 10,
        "verbose":        True,
    },
}
