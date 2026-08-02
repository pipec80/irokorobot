"""In-process working memory: turns and emotions per conversation.

A ``collections.deque`` bounded to ``settings.working_memory_size`` turns.
asyncio runs on a single thread; CPython's GIL makes dict operations on
``_buffers`` atomic, so no locking is needed here.
"""

from __future__ import annotations

from collections import deque
import logging
from typing import Literal

from server.schemas import ConversationTurn
from server.settings import settings

logger = logging.getLogger(__name__)

_buffers: dict[str, deque[ConversationTurn]] = {}

_EMOTION_WINDOW = 5
_emotion_buffers: dict[str, deque[str]] = {}


def _validate_conversation_id(conversation_id: str) -> None:
    """Reject an empty working-memory identifier."""
    if not conversation_id:
        raise ValueError("conversation_id must not be empty")


def _buffer(conversation_id: str) -> deque[ConversationTurn]:
    """Return the bounded deque for a conversation."""
    _validate_conversation_id(conversation_id)
    if conversation_id not in _buffers:
        _buffers[conversation_id] = deque(maxlen=settings.working_memory_size)
    return _buffers[conversation_id]


def _emotion_buffer(conversation_id: str) -> deque[str]:
    """Return the bounded emotion deque for a conversation."""
    _validate_conversation_id(conversation_id)
    if conversation_id not in _emotion_buffers:
        _emotion_buffers[conversation_id] = deque(maxlen=_EMOTION_WINDOW)
    return _emotion_buffers[conversation_id]


def add_turn(
    conversation_id: str,
    role: Literal["user", "assistant"],
    content: str,
) -> None:
    """Append a turn to one conversation's working-memory window.

    Args:
        conversation_id: Ephemeral working-memory identifier.
        role: Speaker role — ``"user"`` or ``"assistant"``.
        content: Text of the turn.

    Raises:
        ValueError: If *role* is not ``"user"`` or ``"assistant"``.
    """
    if role not in ("user", "assistant"):
        raise ValueError(f"Invalid role: {role!r}")
    _buffer(conversation_id).append(ConversationTurn(role=role, content=content))
    logger.info(
        "Working memory: turn added conversation=%s role=%s (%d chars)",
        conversation_id,
        role,
        len(content),
    )


def get_history(conversation_id: str) -> list[ConversationTurn]:
    """Return the conversation window as a list of ``ConversationTurn``.

    Args:
        conversation_id: Ephemeral working-memory identifier.

    Returns:
        List of conversation turns (oldest first).
    """
    return list(_buffer(conversation_id))


def add_emotion(conversation_id: str, emotion: str) -> None:
    """Record the detected user emotion for the current turn.

    Args:
        conversation_id: Ephemeral working-memory identifier.
        emotion: Detected emotion string (e.g. ``"joy"``, ``"neutral"``).
    """
    _emotion_buffer(conversation_id).append(emotion)


def get_recent_emotion(conversation_id: str) -> str | None:
    """Return the most frequent non-neutral emotion from the last N turns.

    Args:
        conversation_id: Ephemeral working-memory identifier.

    Returns:
        Most frequent non-neutral emotion, or ``None`` if all turns are neutral.
    """
    counts: dict[str, int] = {}
    for emotion in _emotion_buffer(conversation_id):
        if emotion != "neutral":
            counts[emotion] = counts.get(emotion, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def clear(conversation_id: str) -> None:
    """Discard all turns and emotion history for one conversation.

    Args:
        conversation_id: Ephemeral working-memory identifier.
    """
    _validate_conversation_id(conversation_id)
    _buffers.pop(conversation_id, None)
    _emotion_buffers.pop(conversation_id, None)
