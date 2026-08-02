"""Unit tests for server.memory.working — in-process conversation buffer.

Tests the bounded deque mechanics: add, retrieve, clear, and maxlen enforcement.
"""

from collections.abc import Generator
from typing import Literal, cast

import pytest
from server.memory import working
from server.schemas import ConversationTurn
from server.settings import settings


@pytest.fixture(autouse=True)
def _clean_buffers() -> Generator[None, None, None]:
    """Clear all working memory buffers before each test."""
    working._buffers.clear()
    working._emotion_buffers.clear()
    yield
    working._buffers.clear()
    working._emotion_buffers.clear()


@pytest.mark.unit
def test_add_and_get_history() -> None:
    """Turns are stored and retrieved in insertion order."""
    working.add_turn("u1", "user", "hola")
    working.add_turn("u1", "assistant", "hola humano")

    history = working.get_history("u1")

    assert len(history) == 2
    assert all(isinstance(t, ConversationTurn) for t in history)
    assert history[0].role == "user"
    assert history[0].content == "hola"
    assert history[1].role == "assistant"
    assert history[1].content == "hola humano"


@pytest.mark.unit
def test_clear_empties_buffer() -> None:
    """clear() removes all turns for the given user."""
    working.add_turn("u1", "user", "test")
    working.clear("u1")

    assert working.get_history("u1") == []


@pytest.mark.unit
def test_respects_maxlen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Buffer must not grow beyond working_memory_size."""
    monkeypatch.setattr(settings, "working_memory_size", 3)
    working._buffers.clear()  # force re-creation with new maxlen

    for i in range(5):
        working.add_turn("u1", "user", f"msg-{i}")

    history = working.get_history("u1")
    assert len(history) == 3
    assert history[0].content == "msg-2"
    assert history[-1].content == "msg-4"


@pytest.mark.unit
def test_separate_conversations_have_independent_buffers() -> None:
    """Each conversation ID gets its own turn and emotion deques."""
    working.add_turn("alice", "user", "hello")
    working.add_turn("bob", "user", "hola")
    working.add_emotion("alice", "joy")
    working.add_emotion("bob", "sadness")

    assert len(working.get_history("alice")) == 1
    assert len(working.get_history("bob")) == 1
    assert working.get_history("alice")[0].content == "hello"
    assert working.get_recent_emotion("alice") == "joy"
    assert working.get_recent_emotion("bob") == "sadness"


@pytest.mark.unit
def test_empty_conversation_id_does_not_create_buffer() -> None:
    """An empty conversation ID should fail before allocating state."""
    with pytest.raises(ValueError, match="conversation_id"):
        working.get_history("")

    assert "" not in working._buffers


@pytest.mark.unit
def test_add_turn_invalid_role_raises_value_error() -> None:
    """Runtime validation must back the docstring's Raises contract."""
    invalid_role = cast("Literal['user', 'assistant']", "system")
    with pytest.raises(ValueError, match="Invalid role"):
        working.add_turn("u1", invalid_role, "no permitido")
