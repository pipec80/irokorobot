"""The conversation record: the only SQL on ``conversation_records`` (ADR 0027, Plan 0076).

A conversation is one or more consecutive **segments**. Exchanges are appended to the single open
segment; a silence of ``WORKING_MEMORY_IDLE_SECONDS`` ends the conversation, and a segment that
holds ``CONVERSATION_SEGMENT_MAX_TURNS`` exchanges or would pass
``CONVERSATION_SEGMENT_MAX_BYTES`` is closed and continued in a new segment linked to it. A closed
segment expires after ``CONVERSATION_RECORD_ELIGIBLE_DAYS`` when at least one exchange was the
owner's verified voice, after ``CONVERSATION_RECORD_INELIGIBLE_DAYS`` otherwise.

Nothing here logs a text: only ids, counts and closed reasons. No route, prompt or voice answer
reads this module (an architecture guard).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import json
import logging
from typing import TYPE_CHECKING

from server import db
from server.exceptions import BrainMemoryError
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.settings import settings

if TYPE_CHECKING:
    import aiosqlite

__all__ = [
    "EpisodeStatus",
    "RecordSummary",
    "RecordView",
    "append_turn",
    "close_idle_records",
    "count_failed_attempt",
    "delete_all_records",
    "delete_record",
    "has_open_record",
    "list_records",
    "next_pending_record",
    "purge_records",
    "read_record",
    "set_episode_status",
]

logger = logging.getLogger(__name__)

_BYTES_PER_MB = 1_000_000
_SUMMARY_COLUMNS = (
    "id, previous_id, started_at, closed_at, turn_count, byte_count, eligible, expires_at, "
    "episode_status"
)


class EpisodeStatus(StrEnum):
    """Where a closed record stands with the diary job."""

    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class RecordSummary:
    """A record's metadata; it carries no text."""

    id: int
    previous_id: int | None
    started_at: str
    closed_at: str | None
    turn_count: int
    byte_count: int
    eligible: bool
    expires_at: str | None
    episode_status: EpisodeStatus


@dataclass(frozen=True)
class RecordView:
    """A record with its exchanges, sorted by time; its ``repr`` omits them."""

    summary: RecordSummary
    owner_entity_id: int
    turns: tuple[RecordedTurn, ...] = field(repr=False)


def _iso(moment: datetime) -> str:
    """Return a fixed-width UTC ISO 8601 string, so strings sort like instants."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("conversation timestamps must be timezone-aware")
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _summary(row: tuple[object, ...]) -> RecordSummary:
    """Build a summary from one ``_SUMMARY_COLUMNS`` row."""
    return RecordSummary(
        id=int(str(row[0])),
        previous_id=None if row[1] is None else int(str(row[1])),
        started_at=str(row[2]),
        closed_at=None if row[3] is None else str(row[3]),
        turn_count=int(str(row[4])),
        byte_count=int(str(row[5])),
        eligible=bool(row[6]),
        expires_at=None if row[7] is None else str(row[7]),
        episode_status=EpisodeStatus(str(row[8])),
    )


def _turns(raw: str) -> tuple[RecordedTurn, ...]:
    """Parse a record's ``turns`` JSON; a malformed one raises a closed error (no text in it)."""
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            raise TypeError("turns is not a list")
        turns = [RecordedTurn.from_json_obj(item) for item in items]
    except (ValueError, TypeError, AttributeError):
        raise BrainMemoryError("A conversation record holds a malformed exchange") from None
    return tuple(sorted(turns, key=lambda turn: turn.at))


def _expiry(closed_at: datetime, *, eligible: bool) -> str:
    days = (
        settings.conversation_record_eligible_days
        if eligible
        else settings.conversation_record_ineligible_days
    )
    return _iso(closed_at + timedelta(days=days))


async def _close(
    conn: aiosqlite.Connection, record_id: int, *, eligible: bool, now: datetime
) -> None:
    await conn.execute(
        "UPDATE conversation_records SET closed_at = ?, expires_at = ? WHERE id = ?",
        (_iso(now), _expiry(now, eligible=eligible), record_id),
    )


async def append_turn(turn: RecordedTurn, *, owner_entity_id: int, now: datetime) -> int:
    """Append one exchange to the open segment, closing and opening segments as needed.

    Args:
        turn: The exchange.
        owner_entity_id: The owner the record belongs to.
        now: The time a segment closed here is stamped with.

    Returns:
        The id of the segment that received the exchange.
    """
    entry = turn.to_json()
    size = len(entry.encode("utf-8"))
    at = _iso(turn.at)
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "SELECT id, last_turn_at, turn_count, byte_count, eligible FROM conversation_records "
            "WHERE closed_at IS NULL"
        )
        row = await cursor.fetchone()
        await cursor.close()
        record_id: int | None = None
        previous_id: int | None = None
        if row is not None:
            open_id, last_turn_at = int(row[0]), datetime.fromisoformat(str(row[1]))
            count, total, eligible = int(row[2]), int(row[3]), bool(row[4])
            idle = (turn.at - last_turn_at).total_seconds() >= settings.working_memory_idle_seconds
            full = (
                count >= settings.conversation_segment_max_turns
                or total + size > settings.conversation_segment_max_bytes
            )
            if idle or full:
                await _close(conn, open_id, eligible=eligible, now=now)
                previous_id = None if idle else open_id
            else:
                record_id = open_id
        if record_id is None:
            cursor = await conn.execute(
                "INSERT INTO conversation_records "
                "(previous_id, owner_entity_id, started_at, last_turn_at) VALUES (?, ?, ?, ?)",
                (previous_id, owner_entity_id, at, at),
            )
            record_id = int(cursor.lastrowid or 0)
            await cursor.close()
        await conn.execute(
            "UPDATE conversation_records SET turns = json_insert(turns, '$[#]', json(?)), "
            "turn_count = turn_count + 1, byte_count = byte_count + ?, "
            "last_turn_at = max(last_turn_at, ?), eligible = max(eligible, ?) WHERE id = ?",
            (entry, size, at, int(turn.voice is TurnVerdict.VERIFIED), record_id),
        )
    return record_id


async def close_idle_records(now: datetime) -> int:
    """Close the open segment when nothing was appended for the session's idle time.

    Args:
        now: The current time.

    Returns:
        How many segments were closed (0 or 1).
    """
    threshold = _iso(now - timedelta(seconds=settings.working_memory_idle_seconds))
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "SELECT id, eligible FROM conversation_records "
            "WHERE closed_at IS NULL AND last_turn_at <= ?",
            (threshold,),
        )
        rows = list(await cursor.fetchall())
        await cursor.close()
        for row in rows:
            await _close(conn, int(row[0]), eligible=bool(row[1]), now=now)
    if rows:
        logger.info("Conversation record: %d idle segment(s) closed", len(rows))
    return len(rows)


async def has_open_record() -> bool:
    """Return whether a segment is open (someone is in a conversation)."""
    cursor = await db.get_conn().execute(
        "SELECT 1 FROM conversation_records WHERE closed_at IS NULL LIMIT 1"
    )
    row = await cursor.fetchone()
    await cursor.close()
    return row is not None


async def list_records(limit: int = 50) -> tuple[RecordSummary, ...]:
    """Return the newest records' metadata, newest first; never a text.

    Args:
        limit: How many records at most.

    Returns:
        The summaries.
    """
    cursor = await db.get_conn().execute(
        f"SELECT {_SUMMARY_COLUMNS} FROM conversation_records ORDER BY id DESC LIMIT ?",  # noqa: S608
        (limit,),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return tuple(_summary(tuple(row)) for row in rows)


async def _view(where: str, params: tuple[object, ...]) -> RecordView | None:
    cursor = await db.get_conn().execute(
        f"SELECT {_SUMMARY_COLUMNS}, owner_entity_id, turns FROM conversation_records "  # noqa: S608
        f"WHERE {where}",
        params,
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        return None
    values = tuple(row)
    return RecordView(
        summary=_summary(values[:9]),
        owner_entity_id=int(str(values[9])),
        turns=_turns(str(values[10])),
    )


async def read_record(record_id: int) -> RecordView | None:
    """Return one record with its exchanges, or ``None`` when it does not exist.

    Raises:
        BrainMemoryError: If the record holds a malformed exchange.
    """
    return await _view("id = ?", (record_id,))


async def next_pending_record() -> RecordView | None:
    """Return the oldest closed record still waiting for the diary job, or ``None``.

    Raises:
        BrainMemoryError: If the record holds a malformed exchange.
    """
    return await _view(
        "closed_at IS NOT NULL AND episode_status = 'pending' ORDER BY closed_at, id LIMIT 1", ()
    )


async def set_episode_status(
    record_id: int, status: EpisodeStatus, *, conn: aiosqlite.Connection | None = None
) -> None:
    """Set a record's diary status, inside the caller's transaction when *conn* is given."""
    sql = "UPDATE conversation_records SET episode_status = ? WHERE id = ?"
    if conn is not None:
        await conn.execute(sql, (status.value, record_id))
        return
    async with db.transaction() as own:
        await own.execute(sql, (status.value, record_id))


async def count_failed_attempt(record_id: int) -> int:
    """Add one failed diary attempt to a record and return the new count (0 if it is gone)."""
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE conversation_records SET episode_attempts = episode_attempts + 1 WHERE id = ?",
            (record_id,),
        )
        cursor = await conn.execute(
            "SELECT episode_attempts FROM conversation_records WHERE id = ?", (record_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
    return 0 if row is None else int(row[0])


async def delete_record(record_id: int) -> bool:
    """Delete one segment and, by cascade, its episode; the next segment is unlinked.

    Returns:
        Whether a segment was deleted.
    """
    async with db.transaction() as conn:
        cursor = await conn.execute("DELETE FROM conversation_records WHERE id = ?", (record_id,))
        deleted = cursor.rowcount
        await cursor.close()
    if deleted:
        await db.checkpoint_wal()
    return bool(deleted)


async def delete_all_records(conn: aiosqlite.Connection) -> int:
    """Delete every segment (and every episode) inside the caller's open transaction.

    Args:
        conn: The connection of an open ``db.transaction()``.

    Returns:
        How many segments were deleted.
    """
    cursor = await conn.execute("DELETE FROM conversation_records")
    deleted = cursor.rowcount
    await cursor.close()
    return max(deleted, 0)


async def purge_records(now: datetime) -> int:
    """Delete expired segments, then the oldest closed ones while the record is over its cap.

    Not-eligible segments go before eligible ones; the open segment is never deleted. Episodes
    go with their records (cascade).

    Args:
        now: The current time.

    Returns:
        How many segments were deleted.
    """
    cap = settings.conversation_record_max_total_mb * _BYTES_PER_MB
    deleted = 0
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "DELETE FROM conversation_records WHERE closed_at IS NOT NULL AND expires_at < ?",
            (_iso(now),),
        )
        deleted += max(cursor.rowcount, 0)
        await cursor.close()
        while True:
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(byte_count), 0) FROM conversation_records"
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None or int(row[0]) <= cap:
                break
            cursor = await conn.execute(
                "DELETE FROM conversation_records WHERE id = (SELECT id FROM conversation_records "
                "WHERE closed_at IS NOT NULL ORDER BY eligible, closed_at, id LIMIT 1)"
            )
            removed = max(cursor.rowcount, 0)
            await cursor.close()
            if removed == 0:
                break
            deleted += removed
    if deleted:
        logger.info("Conversation record: %d segment(s) purged", deleted)
        await db.checkpoint_wal()
    return deleted
