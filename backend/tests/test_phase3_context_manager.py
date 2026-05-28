"""
Phase 3 unit tests — Dynamic Context Manager.

All async calls use asyncio.run() — no pytest-asyncio needed.
ChromaDB calls are mocked to isolate ContextManager logic.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

import pytest


# ── filter_memories ───────────────────────────────────────────────────────────

def test_filter_memories_same_topic():
    from open_tutorai.services.context_manager import ContextManager
    mems = [
        {"content": "A", "metadata": {"topic": "algorithms"}},
        {"content": "B", "metadata": {"topic": "biology"}},
        {"content": "C", "metadata": {"topic": "algorithms"}},
    ]
    result = ContextManager.filter_memories(mems, "algorithms", max_age_days=365)
    assert len(result) == 2
    assert all(m["metadata"]["topic"] == "algorithms" for m in result)


def test_filter_memories_no_topic_kept():
    from open_tutorai.services.context_manager import ContextManager
    mems = [{"content": "X", "metadata": {}}]
    result = ContextManager.filter_memories(mems, "algorithms", max_age_days=365)
    assert len(result) == 1


def test_filter_memories_wrong_topic_excluded():
    from open_tutorai.services.context_manager import ContextManager
    mems = [{"content": "X", "metadata": {"topic": "chemistry"}}]
    result = ContextManager.filter_memories(mems, "algorithms", max_age_days=365)
    assert result == []


def test_filter_memories_recency_recent_kept():
    from open_tutorai.services.context_manager import ContextManager
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    mems = [{"content": "A", "metadata": {"topic": "algorithms", "created_at": recent}}]
    result = ContextManager.filter_memories(mems, "algorithms", max_age_days=14)
    assert len(result) == 1


def test_filter_memories_recency_old_excluded():
    from open_tutorai.services.context_manager import ContextManager
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    mems = [{"content": "A", "metadata": {"topic": "algorithms", "created_at": old}}]
    result = ContextManager.filter_memories(mems, "algorithms", max_age_days=14)
    assert result == []


def test_filter_memories_invalid_date_kept():
    from open_tutorai.services.context_manager import ContextManager
    mems = [{"content": "A", "metadata": {"topic": "algorithms", "created_at": "not-a-date"}}]
    result = ContextManager.filter_memories(mems, "algorithms", max_age_days=14)
    assert len(result) == 1


def test_filter_memories_empty_list():
    from open_tutorai.services.context_manager import ContextManager
    assert ContextManager.filter_memories([], "algorithms") == []


# ── _count_tokens ─────────────────────────────────────────────────────────────

def test_count_tokens_nonzero():
    from open_tutorai.services.context_manager import _count_tokens
    assert _count_tokens("hello world recursion") > 0


def test_count_tokens_empty():
    from open_tutorai.services.context_manager import _count_tokens
    assert _count_tokens("") == 0


# ── _trim_to_budget ───────────────────────────────────────────────────────────

def test_trim_keeps_high_score_docs():
    from open_tutorai.services.context_manager import _trim_to_budget
    docs = [
        {"content": "short", "vector_score": 0.9},
        {"content": "short", "vector_score": 0.5},
        {"content": "short", "vector_score": 0.3},
    ]
    kept = _trim_to_budget(docs, max_tokens=50, summary="")
    assert kept[0]["vector_score"] == 0.9


def test_trim_respects_budget():
    from open_tutorai.services.context_manager import _trim_to_budget, _count_tokens
    long_text = " ".join(["word"] * 400)
    docs = [{"content": long_text, "vector_score": 0.9}] * 5
    kept = _trim_to_budget(docs, max_tokens=500, summary="")
    total_tokens = _count_tokens(" ".join(d["content"] for d in kept))
    assert total_tokens <= 500


# ── build_agent_context ───────────────────────────────────────────────────────

def test_build_agent_context_returns_agent_context():
    from open_tutorai.services.context_manager import ContextManager, AgentContext

    mock_docs = [
        {"id": "d1", "content": "Recursion basics.", "metadata": {}, "vector_score": 0.8},
    ]
    with patch("open_tutorai.services.context_manager._fetch_rag_docs",
               new=AsyncMock(return_value=mock_docs)):
        ctx = asyncio.run(ContextManager.build_agent_context(
            user_id="u1", topic="algorithms", query="recursion",
            db=None, user_name="Alice", language="en",
        ))

    assert isinstance(ctx, AgentContext)
    assert ctx.user_id == "u1"
    assert ctx.topic == "algorithms"
    assert ctx.user_message == "recursion"
    assert ctx.user_name == "Alice"


def test_build_agent_context_empty_query_falls_back_to_topic():
    from open_tutorai.services.context_manager import ContextManager
    calls = []

    async def mock_fetch(user_id, query, top_k, min_score):
        calls.append(query)
        return []

    with patch("open_tutorai.services.context_manager._fetch_rag_docs", side_effect=mock_fetch):
        asyncio.run(ContextManager.build_agent_context(
            user_id="u1", topic="sorting", query="   ", db=None,
        ))

    assert calls[0] == "sorting"


def test_build_agent_context_no_rag_graceful():
    from open_tutorai.services.context_manager import ContextManager

    with patch("open_tutorai.services.context_manager._fetch_rag_docs",
               new=AsyncMock(return_value=[])):
        ctx = asyncio.run(ContextManager.build_agent_context(
            user_id="u1", topic="math", query="integrals", db=None,
        ))

    assert ctx.rag_docs == []
    assert ctx.token_count >= 0


def test_build_agent_context_token_count_within_budget():
    from open_tutorai.services.context_manager import ContextManager
    from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG

    huge_doc = {"content": " ".join(["word"] * 600), "vector_score": 0.9, "metadata": {}, "id": "d1"}
    docs = [huge_doc] * 10

    with patch("open_tutorai.services.context_manager._fetch_rag_docs",
               new=AsyncMock(return_value=docs)):
        ctx = asyncio.run(ContextManager.build_agent_context(
            user_id="u1", topic="algorithms", query="sort", db=None,
        ))

    max_tokens = CONTEXT_RETRIEVAL_CONFIG["filtering"]["max_context_tokens"]
    assert ctx.token_count <= max_tokens


def test_build_agent_context_carries_session_summary():
    from open_tutorai.services.context_manager import ContextManager

    with patch("open_tutorai.services.context_manager._fetch_rag_docs",
               new=AsyncMock(return_value=[])):
        ctx = asyncio.run(ContextManager.build_agent_context(
            user_id="u1", topic="python", query="loops", db=None,
            session_summary="Previously covered: for loops, while loops.",
        ))

    assert "for loops" in ctx.session_summary
