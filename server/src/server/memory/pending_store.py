"""The pending-topics store: the only SQL on ``pending_topics`` (Plan 0084 D-14, a guard).

A row is what the owner said they would do on one day. It is written ``unnamed`` inside the
capture's transaction, named (or deleted) by the conversation job, read by the follow-up, marked
``asked`` once and deleted two days after its due day or with its record. Days are local household
ISO dates; instants are fixed-width UTC ISO strings. Nothing here logs a text, a topic or a day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Literal, cast

from server import db
from server.cognition.pending_topics import follow_up_due_days
from server.cognition.spoken_dates import DayWindow, window_utc_bounds
from server.memory.candidates import iso_utc
from server.memory.recall_search import household_zone
from server.settings import settings

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    import aiosqlite

__all__ = [
    "PendingSensitivity",
    "PendingTopic",
    "asked_today",
    "count_naming_failure",
    "delete_expired",
    "drop",
    "due_topic",
    "insert_unnamed",
    "mark_asked",
    "next_unnamed",
    "pending_topics_on",
    "set_topic",
]

type PendingSensitivity = Literal["normal", "medical"]


@dataclass(frozen=True)
class PendingTopic:
    """A named open topic a greeting may pick up.

    Attributes:
        id: The row id.
        topic: The topic as named; hidden from ``repr``, it carries the owner's words.
        due_day: The local day the plan named.
        sensitivity: ``normal`` or ``medical``.
    """

    id: int
    topic: str = field(repr=False)
    due_day: date = field(repr=False)
    sensitivity: PendingSensitivity


def pending_topics_on() -> bool:
    """Whether pending topics are kept and picked up (D-1).

    The one place the three switches meet: ``PENDING_TOPICS_ENABLED`` works only with
    ``MEMORY_ENABLED`` and ``CONVERSATION_RECORD_ENABLED``; every consumer asks here.
    """
    return (
        settings.memory_enabled
        and settings.conversation_record_enabled
        and settings.pending_topics_enabled
    )


async def insert_unnamed(
    conn: aiosqlite.Connection,
    *,
    owner_entity_id: int,
    record_id: int,
    correlation_id: UUID,
    said_day: date,
    due_day: date,
    heard: str,
    sensitivity: PendingSensitivity,
    now: datetime,
) -> int:
    """Write one unnamed topic, inside the caller's open transaction (the capture's append).

    Args:
        conn: The connection of an open ``db.transaction()``.
        owner_entity_id: The owner who said it.
        record_id: The record the turn was appended to.
        correlation_id: The turn's id; one topic per turn.
        said_day: The local day the words were said.
        due_day: The local day the plan names.
        heard: The owner's words, kept until the topic is named.
        sensitivity: ``normal`` or ``medical``.
        now: The creation instant.

    Returns:
        The new row's id.
    """
    cursor = await conn.execute(
        "INSERT INTO pending_topics (owner_entity_id, source_record_id, correlation_id, said_day, "
        "due_day, heard, state, sensitivity, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'unnamed', ?, ?)",
        (
            owner_entity_id,
            record_id,
            str(correlation_id),
            said_day.isoformat(),
            due_day.isoformat(),
            heard,
            sensitivity,
            iso_utc(now),
        ),
    )
    topic_id = int(cursor.lastrowid or 0)
    await cursor.close()
    return topic_id


async def _one(sql: str, params: tuple[object, ...]) -> aiosqlite.Row | None:
    cursor = await db.get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    return row


async def _write(sql: str, params: tuple[object, ...]) -> int:
    """Run one write in its own transaction; return how many rows it changed."""
    async with db.transaction() as conn:
        cursor = await conn.execute(sql, params)
        changed = cursor.rowcount
        await cursor.close()
    return changed


async def next_unnamed() -> tuple[int, str] | None:
    """Return the unnamed topic to name next (fewest failed tries, then oldest), or ``None``."""
    row = await _one(
        "SELECT id, heard FROM pending_topics WHERE state = 'unnamed' "
        "ORDER BY naming_attempts, id LIMIT 1",
        (),
    )
    return None if row is None else (int(row[0]), str(row[1]))


async def count_naming_failure(topic_id: int) -> int:
    """Count one failed naming of an unnamed topic; return its failures, or 0 if it is named."""
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "UPDATE pending_topics SET naming_attempts = naming_attempts + 1 "
            "WHERE id = ? AND state = 'unnamed' RETURNING naming_attempts",
            (topic_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
    return 0 if row is None else int(row[0])


async def set_topic(topic_id: int, topic: str) -> bool:
    """Name an unnamed topic and forget its words; ``False`` if it is no longer unnamed."""
    return (
        await _write(
            "UPDATE pending_topics SET topic = ?, heard = NULL, state = 'open' "
            "WHERE id = ? AND state = 'unnamed'",
            (topic, topic_id),
        )
        == 1
    )


async def drop(topic_id: int) -> None:
    """Delete one topic (one the model could not name)."""
    await _write("DELETE FROM pending_topics WHERE id = ?", (topic_id,))


async def due_topic(owner_entity_id: int, *, today: date) -> PendingTopic | None:
    """Return the owner's oldest open topic a greeting of *today* may ask about (D-4, D-8).

    Args:
        owner_entity_id: The owner.
        today: The household's local day.

    Returns:
        The open topic due one or two days before today with the oldest due day, or ``None``.
    """
    oldest, newest = follow_up_due_days(today)
    row = await _one(
        "SELECT id, topic, due_day, sensitivity FROM pending_topics "
        "WHERE owner_entity_id = ? AND state = 'open' AND due_day BETWEEN ? AND ? "
        "ORDER BY due_day, id LIMIT 1",
        (owner_entity_id, oldest.isoformat(), newest.isoformat()),
    )
    if row is None:
        return None
    return PendingTopic(
        id=int(row[0]),
        topic=str(row[1]),
        due_day=date.fromisoformat(str(row[2])),
        sensitivity=cast("PendingSensitivity", str(row[3])),
    )


async def asked_today(owner_entity_id: int, *, today: date) -> bool:
    """Whether a topic of the owner was already asked on the household's *today* (D-8)."""
    start, end = window_utc_bounds(DayWindow(start=today, end=today), household_zone())
    row = await _one(
        "SELECT 1 FROM pending_topics WHERE owner_entity_id = ? AND state = 'asked' "
        "AND asked_at >= ? AND asked_at < ? LIMIT 1",
        (owner_entity_id, start, end),
    )
    return row is not None


async def mark_asked(topic_id: int, *, now: datetime) -> bool:
    """Move an open topic to ``asked``; ``False`` when it was not open (compare-and-set)."""
    return (
        await _write(
            "UPDATE pending_topics SET state = 'asked', asked_at = ? "
            "WHERE id = ? AND state = 'open'",
            (iso_utc(now), topic_id),
        )
        == 1
    )


async def delete_expired(*, today: date) -> int:
    """Delete every topic more than two days past its due day, asked or not (D-5).

    Args:
        today: The household's local day.

    Returns:
        How many rows were deleted.
    """
    oldest, _newest = follow_up_due_days(today)
    return await _write("DELETE FROM pending_topics WHERE due_day < ?", (oldest.isoformat(),))
