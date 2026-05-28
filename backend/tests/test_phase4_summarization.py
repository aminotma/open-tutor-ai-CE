"""
Phase 4 unit tests — Summarization Layer.
LLM calls are mocked; DB uses SQLite in-memory.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    from open_tutorai.models.database import Memory, KGConcept, KGRelation, KGUserMastery
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    for table in [Memory.__table__, KGConcept.__table__,
                  KGRelation.__table__, KGUserMastery.__table__]:
        table.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _mock_llm(response_text: str):
    llm = MagicMock()
    msg = MagicMock()
    msg.content = response_text
    llm.invoke.return_value = msg
    return llm


# ── should_summarize ──────────────────────────────────────────────────────────

def test_should_summarize_below_threshold():
    from open_tutorai.services.summarization import SummarizationService
    assert SummarizationService.should_summarize([{"role": "user", "content": "hi"}]) is False


def test_should_summarize_at_count_threshold():
    from open_tutorai.services.summarization import SummarizationService
    exchanges = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
    assert SummarizationService.should_summarize(exchanges) is True


def test_should_summarize_above_count_threshold():
    from open_tutorai.services.summarization import SummarizationService
    exchanges = [{"role": "user", "content": f"msg {i}"} for i in range(12)]
    assert SummarizationService.should_summarize(exchanges) is True


def test_should_summarize_by_volume_trigger():
    """Volume trigger: few exchanges but large content exceeds 1200 tokens."""
    from open_tutorai.services.summarization import SummarizationService
    # 2 exchanges with ~700 words each → well above 1200 token limit
    long_content = " ".join([f"word{i}" for i in range(700)])
    exchanges = [
        {"role": "user", "content": long_content},
        {"role": "assistant", "content": long_content},
    ]
    assert SummarizationService.should_summarize(exchanges) is True


def test_should_summarize_volume_below_limit():
    """Short content, few exchanges → neither trigger fires."""
    from open_tutorai.services.summarization import SummarizationService
    exchanges = [
        {"role": "user", "content": "What is recursion?"},
        {"role": "assistant", "content": "Recursion is a function calling itself."},
    ]
    assert SummarizationService.should_summarize(exchanges) is False


# ── cache_summary + get_cached_summary ───────────────────────────────────────

def test_cache_and_retrieve_summary(db):
    from open_tutorai.services.summarization import SummarizationService
    SummarizationService.cache_summary("user_a", "algorithms", "Covered sorting algorithms.", db)
    db.commit()
    result = SummarizationService.get_cached_summary("user_a", "algorithms", db)
    assert result == "Covered sorting algorithms."


def test_get_cached_summary_wrong_user_returns_none(db):
    from open_tutorai.services.summarization import SummarizationService
    result = SummarizationService.get_cached_summary("unknown_user", "algorithms", db)
    assert result is None


def test_get_cached_summary_wrong_topic_returns_none(db):
    from open_tutorai.services.summarization import SummarizationService
    SummarizationService.cache_summary("user_b", "python", "Learned loops.", db)
    db.commit()
    result = SummarizationService.get_cached_summary("user_b", "algorithms", db)
    assert result is None


def test_get_cached_summary_expired_returns_none(db):
    from open_tutorai.models.database import Memory
    from open_tutorai.services.summarization import SummarizationService, SUMMARY_MEMORY_TYPE

    old_time = datetime.now(timezone.utc) - timedelta(hours=25)
    mem = Memory(
        id=uuid4().hex,
        user_id="user_expire",
        memory_type=SUMMARY_MEMORY_TYPE,
        content="Old summary.",
        memory_metadata={"topic": "algorithms"},
    )
    mem.created_at = old_time
    db.add(mem)
    db.commit()

    result = SummarizationService.get_cached_summary("user_expire", "algorithms", db)
    assert result is None


# ── invalidate_cache ──────────────────────────────────────────────────────────

def test_invalidate_cache_removes_entries(db):
    from open_tutorai.services.summarization import SummarizationService
    SummarizationService.cache_summary("user_inv", "sorting", "Summary 1.", db)
    SummarizationService.cache_summary("user_inv", "sorting", "Summary 2.", db)
    db.commit()

    deleted = SummarizationService.invalidate_cache("user_inv", "sorting", db)
    db.commit()
    assert deleted == 2

    result = SummarizationService.get_cached_summary("user_inv", "sorting", db)
    assert result is None


def test_invalidate_cache_only_affects_topic(db):
    from open_tutorai.services.summarization import SummarizationService
    SummarizationService.cache_summary("user_sel", "algorithms", "Algo summary.", db)
    SummarizationService.cache_summary("user_sel", "python", "Python summary.", db)
    db.commit()

    SummarizationService.invalidate_cache("user_sel", "algorithms", db)
    db.commit()

    assert SummarizationService.get_cached_summary("user_sel", "python", db) == "Python summary."
    assert SummarizationService.get_cached_summary("user_sel", "algorithms", db) is None


# ── summarize_session ─────────────────────────────────────────────────────────

def test_summarize_session_calls_llm(db):
    from open_tutorai.services.summarization import SummarizationService
    exchanges = [{"role": "user", "content": f"Question {i}"} for i in range(6)]
    llm = _mock_llm("The learner studied recursion and identified gaps in base cases.")

    summary = SummarizationService.summarize_session("user_llm", "recursion", exchanges, llm, db)
    assert "recursion" in summary or "learner" in summary
    llm.invoke.assert_called_once()


def test_summarize_session_returns_cache_on_second_call(db):
    from open_tutorai.services.summarization import SummarizationService
    exchanges = [{"role": "user", "content": f"msg {i}"} for i in range(6)]
    llm = _mock_llm("Cached summary content.")

    SummarizationService.summarize_session("user_cache2", "graphs", exchanges, llm, db)
    db.commit()
    llm.invoke.reset_mock()

    result = SummarizationService.summarize_session("user_cache2", "graphs", exchanges, llm, db)
    llm.invoke.assert_not_called()
    assert "Cached summary content." in result


def test_summarize_session_empty_exchanges(db):
    from open_tutorai.services.summarization import SummarizationService
    llm = _mock_llm("Should not be called.")
    result = SummarizationService.summarize_session("user_empty", "math", [], llm, db)
    assert result == ""
    llm.invoke.assert_not_called()


def test_summarize_session_uses_sliding_window(db):
    from open_tutorai.services.summarization import SummarizationService
    exchanges = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
    llm = _mock_llm("Sliding window summary.")
    SummarizationService.summarize_session("user_window", "algos", exchanges, llm, db, force=True)

    call_args = llm.invoke.call_args[0][0]
    prompt_text = call_args[0].content
    assert "msg 10" in prompt_text or "msg 19" in prompt_text
    assert "msg 0" not in prompt_text


def test_summarize_session_force_bypasses_cache(db):
    from open_tutorai.services.summarization import SummarizationService
    exchanges = [{"role": "user", "content": f"msg {i}"} for i in range(6)]
    llm = _mock_llm("Forced regeneration.")

    SummarizationService.summarize_session("user_force", "trees", exchanges, llm, db)
    db.commit()
    llm.invoke.reset_mock()

    SummarizationService.summarize_session("user_force", "trees", exchanges, llm, db, force=True)
    llm.invoke.assert_called_once()


def test_summarize_session_llm_error_returns_fallback(db):
    from open_tutorai.services.summarization import SummarizationService
    exchanges = [{"role": "user", "content": "msg"}] * 6
    llm = MagicMock()
    llm.invoke.side_effect = Exception("LLM unreachable")

    result = SummarizationService.summarize_session("user_err", "topic_x", exchanges, llm, db, force=True)
    assert "topic_x" in result or "unavailable" in result
