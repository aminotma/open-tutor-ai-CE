from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG

# ── AgentContext dataclass ────────────────────────────────────────────────────

@dataclass
class AgentContext:
    user_name:           str
    user_id:             str
    topic:               str
    language:            str
    learning_objectives: list[str]
    user_message:        str
    memories:            list[dict] = field(default_factory=list)
    rag_docs:            list[dict] = field(default_factory=list)
    session_summary:     str        = ""
    token_count:         int        = 0


# ── ContextManager ────────────────────────────────────────────────────────────

class ContextManager:

    @staticmethod
    async def build_agent_context(
        user_id: str,
        topic: str,
        query: str,
        db,
        user_name: str = "",
        language: str = "en",
        learning_objectives: Optional[list[str]] = None,
        session_summary: str = "",
    ) -> AgentContext:
        """
        Assemble a pre-session AgentContext from stable sources:
          - RAG docs from ChromaDB  (driven by query / topic fallback)
          - Session summary cache   (from SummarizationService — passed in)

        Memories and weak_concepts are intentionally excluded here:
        they are loaded fresh by MemoryAgent and KnowledgeAgent inside the graph.
        """
        cfg_f = CONTEXT_RETRIEVAL_CONFIG["filtering"]
        cfg_r = CONTEXT_RETRIEVAL_CONFIG["rag"]

        effective_query = query.strip() if query.strip() else topic

        # 1. RAG retrieval
        rag_docs = await _fetch_rag_docs(
            user_id=user_id,
            query=effective_query,
            top_k=cfg_r["top_k_documents"],
            min_score=cfg_f["relevance_threshold"],
        )

        # 2. Token budget
        all_text = " ".join(
            [session_summary]
            + [d.get("content", "") for d in rag_docs]
        )
        token_count = _count_tokens(all_text)

        # 3. Trim if over budget
        max_tokens = cfg_f["max_context_tokens"]
        if token_count > max_tokens:
            rag_docs = _trim_to_budget(rag_docs, max_tokens, session_summary)
            token_count = _count_tokens(
                " ".join([session_summary] + [d.get("content", "") for d in rag_docs])
            )

        return AgentContext(
            user_name=user_name,
            user_id=user_id,
            topic=topic,
            language=language,
            learning_objectives=learning_objectives or [],
            user_message=query,
            rag_docs=rag_docs,
            session_summary=session_summary,
            token_count=token_count,
        )

    @staticmethod
    def filter_memories(
        memories: list[dict],
        topic: str,
        max_age_days: Optional[int] = None,
    ) -> list[dict]:
        """
        Filter a list of memory dicts by topic and recency.
        Called by MemoryAgent inside the graph after it fetches memories from SQL.
        """
        if max_age_days is None:
            max_age_days = CONTEXT_RETRIEVAL_CONFIG["filtering"]["max_age_days"]

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        topic_lower = topic.strip().lower()
        filtered = []

        for mem in memories:
            meta = mem.get("metadata") or mem.get("memory_metadata") or {}

            # Topic filter — keep if same topic or no topic declared
            mem_topic = str(meta.get("topic", "")).strip().lower()
            if mem_topic and mem_topic != topic_lower:
                continue

            # Recency filter — parse created_at if available
            created_raw = meta.get("created_at")
            if created_raw:
                try:
                    created = datetime.fromisoformat(str(created_raw))
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if created < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass

            filtered.append(mem)

        return filtered


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _fetch_rag_docs(
    user_id: str,
    query: str,
    top_k: int,
    min_score: float,
) -> list[dict]:
    try:
        from open_tutorai.services.context_retrieval import retrieve_pedagogical_documents
        docs = retrieve_pedagogical_documents(user_id, query, top_k=top_k)
        return [d for d in docs if d.get("vector_score", 0) >= min_score]
    except Exception:
        return []


def _count_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text.split())


def _trim_to_budget(
    docs: list[dict],
    max_tokens: int,
    summary: str,
) -> list[dict]:
    """Remove lowest-scoring docs until we fit within the token budget."""
    docs_sorted = sorted(docs, key=lambda d: d.get("vector_score", 0), reverse=True)
    kept = []
    used = _count_tokens(summary)
    for doc in docs_sorted:
        doc_tokens = _count_tokens(doc.get("content", ""))
        if used + doc_tokens <= max_tokens:
            kept.append(doc)
            used += doc_tokens
        else:
            break
    return kept
