"""LLM factory — returns OpenAI or Ollama client based on the model chosen by the learner."""
from __future__ import annotations

import os
from typing import Optional

_OPENAI_PREFIXES = ("gpt-", "o1", "o3", "o4", "text-", "whisper-", "davinci", "babbage")


def _is_openai_model(model: str) -> bool:
    return any(model.startswith(p) for p in _OPENAI_PREFIXES)


def get_llm(model: Optional[str] = None, temperature: float = 0.2):
    """
    Returns a ChatOpenAI instance configured for the provider detected from the model name.

    - OpenAI model (gpt-*, o1*, o3*, o4*...) -> OpenAI API via OPENAI_API_KEY
    - Any other model (llama3, mistral, qwen...) -> Ollama via OLLAMA_BASE_URL/v1
    """
    from langchain_openai import ChatOpenAI
    from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG

    lc_cfg = CONTEXT_RETRIEVAL_CONFIG["langchain"]
    model = model or lc_cfg.get("llm_model", "gpt-4o-mini")

    if _is_openai_model(model):
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
        )

    # Ollama exposes an OpenAI-compatible API at /v1
    ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        base_url=f"{ollama_base}/v1",
        api_key="ollama",
    )
