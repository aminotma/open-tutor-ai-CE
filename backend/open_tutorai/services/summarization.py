from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG

SUMMARY_MEMORY_TYPE = "session_summary"

SUMMARIZATION_PROMPT = """You are an educational session summarizer.
Given the following recent exchanges between a learner and a tutor, write a concise summary (3-5 sentences) that captures:
- The topic and concepts covered
- The learner's current level and identified difficulties
- Any progress or remaining gaps

Exchanges:
{exchanges}

Summary:"""


class SummarizationService:

    # ── Read (cache) ──────────────────────────────────────────────────────────

    @staticmethod
    def get_cached_summary(user_id: str, topic: str, db) -> Optional[str]:
        """
        Return the most recent valid session summary from cache.
        Returns None if no valid summary exists or TTL has expired.
        """
        from open_tutorai.models.database import Memory

        cfg = CONTEXT_RETRIEVAL_CONFIG["summaries"]
        ttl_hours = cfg.get("cache_ttl_hours", 24)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)

        # JSONField doesn't support SQL-level JSON path queries — filter topic in Python
        rows = (
            db.query(Memory)
            .filter(
                Memory.user_id == user_id,
                Memory.memory_type == SUMMARY_MEMORY_TYPE,
                Memory.created_at >= cutoff,
            )
            .order_by(Memory.created_at.desc())
            .all()
        )

        for row in rows:
            meta_topic = (row.memory_metadata or {}).get("topic", "")
            if not meta_topic or meta_topic == topic:
                return row.content

        return None

    # ── Write (cache) ─────────────────────────────────────────────────────────

    @staticmethod
    def cache_summary(user_id: str, topic: str, summary: str, db) -> None:
        """Persist a session summary into opentutorai_memory."""
        from open_tutorai.models.database import Memory

        mem = Memory(
            id=uuid4().hex,
            user_id=user_id,
            memory_type=SUMMARY_MEMORY_TYPE,
            content=summary,
            memory_metadata={
                "topic": topic,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(mem)
        db.flush()

    @staticmethod
    def invalidate_cache(user_id: str, topic: str, db) -> int:
        """Delete all cached summaries for this user+topic. Returns deleted count."""
        from open_tutorai.models.database import Memory

        rows = (
            db.query(Memory)
            .filter(
                Memory.user_id == user_id,
                Memory.memory_type == SUMMARY_MEMORY_TYPE,
            )
            .all()
        )
        to_delete = [
            r for r in rows
            if (r.memory_metadata or {}).get("topic", "") == topic
        ]
        for r in to_delete:
            db.delete(r)
        db.flush()
        return len(to_delete)

    # ── Summarization ─────────────────────────────────────────────────────────

    @staticmethod
    def summarize_session(
        user_id: str,
        topic: str,
        exchanges: list[dict],
        llm,
        db,
        force: bool = False,
    ) -> str:
        """
        Generate (or return cached) a session summary.

        Args:
            exchanges : list of {role, content} dicts (full history)
            llm       : LangChain ChatOpenAI instance
            db        : SQLAlchemy session
            force     : bypass cache and always regenerate

        Returns:
            Summary string (cached or freshly generated).
        """
        cfg = CONTEXT_RETRIEVAL_CONFIG["summarization"]
        window_size = cfg.get("sliding_window_size", 10)

        if not force:
            cached = SummarizationService.get_cached_summary(user_id, topic, db)
            if cached:
                return cached

        # Sliding window — keep the last N exchanges
        windowed = exchanges[-window_size:] if len(exchanges) > window_size else exchanges

        if not windowed:
            return ""

        exchanges_text = "\n".join(
            f"{ex.get('role', 'user').capitalize()}: {ex.get('content', '')}"
            for ex in windowed
        )

        prompt = SUMMARIZATION_PROMPT.format(exchanges=exchanges_text)

        try:
            from langchain_core.messages import HumanMessage
            response = llm.invoke([HumanMessage(content=prompt)])
            summary = response.content.strip()
        except Exception as exc:
            summary = f"Session on '{topic}'. Summary unavailable: {exc}"

        SummarizationService.cache_summary(user_id, topic, summary, db)
        return summary

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def should_summarize(exchanges: list[dict]) -> bool:
        """
        Return True when summarization should be triggered.

        Two independent conditions (either is sufficient):
          1. Count trigger  : len(exchanges) >= exchanges_per_summary (default 5)
          2. Volume trigger : total token count of exchanges >= auto_summarize_token_limit (default 1200)

        The volume trigger fires before the context budget (3000 tokens) is
        exhausted, leaving headroom for RAG docs and user profile.
        """
        cfg = CONTEXT_RETRIEVAL_CONFIG["summaries"]

        # Condition 1 — count
        if len(exchanges) >= cfg.get("exchanges_per_summary", 5):
            return True

        # Condition 2 — volume
        token_limit = cfg.get("auto_summarize_token_limit", 1200)
        total_tokens = _count_exchange_tokens(exchanges)
        if total_tokens >= token_limit:
            return True

        return False


def _count_exchange_tokens(exchanges: list[dict]) -> int:
    """Count total tokens in a list of exchange dicts."""
    text = " ".join(ex.get("content", "") for ex in exchanges)
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text.split())
