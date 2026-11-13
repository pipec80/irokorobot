"""Which captured turn keeps a pending topic, and the hook that writes it (Plan 0084 D-2, D-7).

The capture asks ``decide_pending`` once per turn, before the append. With the switch on, only a
``VERIFIED`` turn that tells something and announces a plan for one day (``read_announcement``)
with a ``normal`` or ``medical`` sensitivity is kept; ``pending_hook`` then writes it inside the
append's transaction, unnamed. A reader error is its own narrow boundary: the turn is recorded
without a topic. Logs carry a closed outcome or an exception class, never a text nor a day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import logging
from typing import TYPE_CHECKING

from server.cognition.pending_topics import AnnouncementOutcome, read_announcement
from server.memory.conversation_types import TurnVerdict
from server.memory.household_time import household_day
from server.memory.pending_store import insert_unnamed, pending_topics_on
from server.memory.recall_sensitivity import classify_turn_text
from server.memory.recall_store import tells_something

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID

    import aiosqlite

    from server.cognition.pending_topics import Announcement
    from server.memory.conversation_record import TurnIndexer
    from server.memory.conversation_types import RecordedTurn
    from server.memory.pending_store import PendingSensitivity

logger = logging.getLogger(__name__)

__all__ = [
    "KeptTopic",
    "PendingCapture",
    "PendingCaptureOutcome",
    "decide_pending",
    "log_pending",
    "pending_hook",
]


class PendingCaptureOutcome(StrEnum):
    """What the capture made of one turn for the pending topics (D-15)."""

    KEPT = "kept"
    NO_PHRASE = "no_phrase"
    NOT_SINGLE_DAY = "not_single_day"
    NO_VERB = "no_verb"
    QUESTION = "question"
    SENSITIVE = "sensitive"
    NOT_VERIFIED = "not_verified"


@dataclass(frozen=True)
class KeptTopic:
    """What a kept announcement writes: its days (never in a repr) and its sensitivity."""

    said_day: date = field(repr=False)
    due_day: date = field(repr=False)
    sensitivity: PendingSensitivity


@dataclass(frozen=True)
class PendingCapture:
    """The decision on one turn; ``kept`` is set exactly when the outcome is ``KEPT``."""

    outcome: PendingCaptureOutcome
    kept: KeptTopic | None = None

    def __post_init__(self) -> None:
        """Refuse a kept topic without ``KEPT``, or ``KEPT`` without one."""
        if (self.outcome is PendingCaptureOutcome.KEPT) != (self.kept is not None):
            raise ValueError("a topic comes exactly with a kept decision")


def _sensitivity(heard: str) -> PendingSensitivity | None:
    """``normal`` or ``medical`` keep a topic; any other level yields none (D-7)."""
    match classify_turn_text(heard):
        case "normal":
            return "normal"
        case "medical":
            return "medical"
        case _:
            return None


def _read(heard: str, said_day: date) -> Announcement | None:
    """The grammar's verdict; a reader error is a narrow boundary that keeps the turn."""
    try:
        return read_announcement(heard, said_day=said_day)
    except Exception as exc:  # degradation boundary: a grammar bug must not lose the turn
        logger.warning(
            "Pending topic not read (%s)",
            type(exc).__name__,
            extra={"event": "pending.capture_error", "error_type": type(exc).__name__},
        )
        return None


def decide_pending(turn: RecordedTurn) -> PendingCapture | None:
    """Decide whether *turn* keeps a pending topic.

    Args:
        turn: The exchange about to be appended, with its verdict and time.

    Returns:
        ``None`` with the switch off, or when the grammar failed (the class is logged); else the
        closed decision.
    """
    if not pending_topics_on():
        return None
    if turn.voice is not TurnVerdict.VERIFIED:
        return PendingCapture(PendingCaptureOutcome.NOT_VERIFIED)
    if not tells_something(turn.heard):  # a question or a closed request (D-2)
        return PendingCapture(PendingCaptureOutcome.QUESTION)
    said_day = household_day(turn.at)
    announcement = _read(turn.heard, said_day)
    if announcement is None:
        return None
    return _kept_or_not(announcement, turn.heard, said_day)


def _kept_or_not(announcement: Announcement, heard: str, said_day: date) -> PendingCapture:
    """The grammar's verdict, then the sensitivity of a kept announcement (D-3, D-7)."""
    if announcement.outcome is not AnnouncementOutcome.KEPT or announcement.due_day is None:
        return PendingCapture(PendingCaptureOutcome(announcement.outcome.value))
    sensitivity = _sensitivity(heard)
    if sensitivity is None:
        return PendingCapture(PendingCaptureOutcome.SENSITIVE)
    return PendingCapture(
        PendingCaptureOutcome.KEPT,
        KeptTopic(said_day=said_day, due_day=announcement.due_day, sensitivity=sensitivity),
    )


def pending_hook(
    decision: PendingCapture | None, *, owner_id: int, correlation_id: UUID, now: datetime
) -> TurnIndexer | None:
    """Return the hook that writes a kept topic inside the append, or ``None``.

    Args:
        decision: What ``decide_pending`` returned for this turn.
        owner_id: The owner the record belongs to.
        correlation_id: The turn's id; one topic per turn.
        now: The creation instant.
    """
    kept = None if decision is None else decision.kept
    if kept is None:
        return None

    async def write(conn: aiosqlite.Connection, record_id: int, recorded: RecordedTurn) -> None:
        await insert_unnamed(
            conn,
            owner_entity_id=owner_id,
            record_id=record_id,
            correlation_id=correlation_id,
            said_day=kept.said_day,
            due_day=kept.due_day,
            heard=recorded.heard,
            sensitivity=kept.sensitivity,
            now=now,
        )

    return write


def log_pending(decision: PendingCapture | None, correlation_id: UUID) -> None:
    """Log the decision once the append committed; nothing with the switch off."""
    if decision is None:
        return
    logger.info(
        "Pending topic capture: %s",
        decision.outcome.value,
        extra={
            "event": "pending.capture",
            "outcome": decision.outcome.value,
            "correlation_id": str(correlation_id),
        },
    )
